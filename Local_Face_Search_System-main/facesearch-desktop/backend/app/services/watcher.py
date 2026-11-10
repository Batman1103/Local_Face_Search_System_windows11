from pathlib import Path
from threading import Timer, RLock, Thread, Event
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from app.services.indexer import IMAGE_EXTS


class _Handler(FileSystemEventHandler):
    def __init__(self, indexer):
        self.indexer = indexer
        self.timers = {}
        self.lock = RLock()

    def _schedule(self, path):
        p = Path(path)
        if p.suffix.lower() not in IMAGE_EXTS:
            return
        key = str(p)
        with self.lock:
            old = self.timers.pop(key, None)
            if old:
                old.cancel()
            timer = Timer(2.0, self._run, args=(p,))
            timer.daemon = True
            self.timers[key] = timer
            timer.start()

    def _run(self, path):
        with self.lock:
            self.timers.pop(str(path), None)
        self.indexer.enqueue(path)

    def stop(self):
        with self.lock:
            timers = list(self.timers.values())
            self.timers.clear()
        for timer in timers:
            timer.cancel()

    def on_created(self, event):
        if event.is_directory:
            self.indexer.enqueue_tree(event.src_path)
        else:
            self._schedule(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            self.indexer.db.mark_missing_under_root(Path(event.src_path))
            self.indexer.enqueue_tree(event.dest_path)
        else:
            self.indexer.db.mark_missing_path(event.src_path)
            self._schedule(event.dest_path)

    def on_deleted(self, event):
        if event.is_directory:
            self.indexer.db.mark_missing_under_root(Path(event.src_path))
        else:
            self.indexer.db.mark_missing_path(event.src_path)


class FolderWatcher:
    def __init__(self):
        self.observer = None
        self.handler = None
        self.reconcile_stop = Event()
        self.reconcile_thread = None

    def start(self, root, indexer):
        self.stop()
        self.observer = Observer()
        self.handler = _Handler(indexer)
        self.observer.schedule(self.handler, str(root), recursive=True)
        self.observer.start()
        self.reconcile_stop.clear()
        self.reconcile_thread = Thread(
            target=self._reconcile_loop, args=(indexer,), daemon=True
        )
        self.reconcile_thread.start()

    def _reconcile_loop(self, indexer):
        # Watcher events provide prompt updates. A periodic metadata-only walk
        # reconciles missed events on removable/network drives.
        while not self.reconcile_stop.wait(3600):
            if not indexer.stop_event.is_set():
                indexer.start_scan()

    def stop(self):
        self.reconcile_stop.set()
        if self.reconcile_thread and self.reconcile_thread.is_alive():
            self.reconcile_thread.join(timeout=3)
        self.reconcile_thread = None
        if self.handler:
            self.handler.stop()
            self.handler = None
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=3)
            self.observer = None
