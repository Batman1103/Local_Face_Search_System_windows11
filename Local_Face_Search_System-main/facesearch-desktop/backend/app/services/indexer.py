from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event, RLock
import os
import time

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}


class IncrementalIndexer:
    def __init__(self, root, engine, store, db):
        self.root = Path(root).expanduser().resolve()
        self.engine, self.store, self.db = engine, store, db
        self.queue = Queue()
        self.stop_event = Event()
        self.lock = RLock()
        self.pending = set()
        self.dirty = set()
        self.processed = self.discovered = self.errors = 0
        self.processing = False
        self.last_error = ''
        self.scan_running = False
        self.scan_thread = None
        self.worker = Thread(target=self._worker, daemon=True)
        self.worker.start()

    def is_image(self, path):
        return Path(path).suffix.lower() in IMAGE_EXTS

    def enqueue(self, path):
        if self.stop_event.is_set():
            return
        path = Path(path)
        if not path.is_file() or not self.is_image(path):
            return
        try:
            path = path.resolve()
        except OSError:
            return
        key = str(path).casefold()
        with self.lock:
            if key in self.pending:
                self.dirty.add(key)
                return
            self.pending.add(key)
            self.discovered += 1
            self.queue.put((path, key))

    def enqueue_tree(self, folder):
        folder = Path(folder)
        if not folder.is_dir():
            return
        for current, _, names in os.walk(folder):
            for name in names:
                p = Path(current) / name
                if self.is_image(p):
                    self.enqueue(p)

    def scan(self):
        with self.lock:
            if self.scan_running:
                return
            self.scan_running = True
        try:
            walk_errors = []
            def on_walk_error(error):
                walk_errors.append(str(error))
            for current, _, names in os.walk(self.root, onerror=on_walk_error):
                if self.stop_event.is_set():
                    break
                for name in names:
                    p = Path(current) / name
                    if self.is_image(p):
                        self.enqueue(p)
            if not self.stop_event.is_set() and not walk_errors:
                self.db.mark_missing_under_root(self.root)
            elif walk_errors:
                self.last_error = "Some folders could not be scanned: " + "; ".join(walk_errors[:3])
        finally:
            with self.lock:
                self.scan_running = False

    def start_scan(self):
        if self.scan_thread and self.scan_thread.is_alive():
            return
        self.scan_thread = Thread(target=self.scan, daemon=True)
        self.scan_thread.start()

    def process(self, path):
        try:
            st = path.stat()
            relative = str(path.relative_to(self.root))
        except (FileNotFoundError, ValueError, OSError):
            return
        image_id, needs = self.db.prepare_image(path, st.st_size, st.st_mtime_ns, relative)
        if not needs:
            return
        try:
            # Wait for copy operations to finish; do not mark a half-written image as bad.
            last_size = -1
            stable = 0
            for _ in range(8):
                try:
                    size = path.stat().st_size
                except OSError:
                    return
                if size == last_size and size > 0:
                    stable += 1
                    if stable >= 2:
                        break
                else:
                    stable = 0
                last_size = size
                time.sleep(0.5)
            data = path.read_bytes()
            faces = self.engine.detect(self.engine.read_image(data))
            embeddings = [f['embedding'] for f in faces]
            if embeddings:
                with self.lock:
                    start_id = self.store.add(embeddings)
                    rows = [
                        (start_id + offset, image_id, *map(int, face['bbox']), float(face['score']))
                        for offset, face in enumerate(faces)
                    ]
                    self.db.add_faces(rows)
            self.db.finish_image(image_id, True)
            self.processed += 1
        except Exception as exc:
            self.last_error = f'{path}: {exc}'
            self.errors += 1
            self.db.finish_image(image_id, False)

    def _worker(self):
        while not self.stop_event.is_set():
            try:
                path, key = self.queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                with self.lock:
                    self.processing = True
                self.process(path)
            finally:
                with self.lock:
                    self.processing = False
                    self.pending.discard(key)
                    if key in self.dirty and not self.stop_event.is_set():
                        self.dirty.discard(key)
                        self.pending.add(key)
                        self.queue.put((path, key))
                self.queue.task_done()

    def stop(self):
        self.stop_event.set()
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=30)
            if self.scan_thread.is_alive():
                raise TimeoutError("Indexer scan did not stop safely")
        if self.worker.is_alive():
            self.worker.join(timeout=60)
            if self.worker.is_alive():
                raise TimeoutError("Indexer worker did not stop safely")

    def status(self):
        return {
            'root': str(self.root),
            'queued': self.queue.qsize(),
            'discovered': self.discovered,
            'processed_this_run': self.processed,
            'errors_this_run': self.errors,
            'last_error': self.last_error,
            'running': self.scan_running or self.queue.qsize() > 0 or self.processing,
        }
