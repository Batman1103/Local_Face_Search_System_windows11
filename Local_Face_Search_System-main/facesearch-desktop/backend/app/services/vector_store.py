from pathlib import Path
import threading
import numpy as np

DIM = 512
SCALE = 127.0
BATCH_SIZE = 8192


class VectorStore:
    """
    Compact append-only store of normalized 512-D face vectors.
    Each vector occupies exactly 512 bytes (INT8). Search is a batched
    cosine scan, so no float32 copy of the complete collection is kept in RAM.
    """
    def __init__(self, index_dir):
        self.dir = Path(index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "faces.int8"
        self.lock = threading.RLock()
        if not self.path.exists():
            self.path.touch()
        size = self.path.stat().st_size
        if size % DIM:
            raise RuntimeError("Corrupt compact vector file: invalid byte length")
        self._count = size // DIM

    @property
    def ntotal(self):
        return self._count

    def add(self, embeddings):
        arr = np.asarray(embeddings, dtype=np.float32)
        if arr.size == 0:
            return self._count
        arr = arr.reshape(-1, DIM)
        # Per-vector scaling uses the full signed INT8 range. The scale factor
        # cancels during cosine normalization, so it need not be stored.
        max_abs = np.max(np.abs(arr), axis=1, keepdims=True)
        scaled = arr / np.maximum(max_abs, 1e-12)
        quantized = np.clip(np.rint(scaled * SCALE), -127, 127).astype(np.int8)
        with self.lock:
            start = self._count
            with self.path.open("ab") as f:
                f.write(quantized.tobytes(order="C"))
                f.flush()
            self._count += len(quantized)
            return start

    def search(self, embedding, top_k, active_ids=None):
        with self.lock:
            return self._search_locked(embedding, top_k, active_ids)

    def _search_locked(self, embedding, top_k, active_ids=None):
        if self._count == 0 or top_k <= 0:
            return np.empty((1, 0), np.float32), np.empty((1, 0), np.int64)
        q = np.asarray(embedding, dtype=np.float32).reshape(DIM)
        q /= max(float(np.linalg.norm(q)), 1e-12)
        if active_ids is None:
            ids = np.arange(self._count, dtype=np.int64)
        else:
            ids = np.asarray(active_ids, dtype=np.int64)
            ids = ids[(ids >= 0) & (ids < self._count)]
        if ids.size == 0:
            return np.empty((1, 0), np.float32), np.empty((1, 0), np.int64)

        best_scores = np.empty(0, dtype=np.float32)
        best_ids = np.empty(0, dtype=np.int64)
        # Gather in bounded chunks; avoids loading the entire vector file.
        mm = np.memmap(self.path, dtype=np.int8, mode="r", shape=(self._count, DIM))
        for offset in range(0, len(ids), BATCH_SIZE):
            batch_ids = ids[offset:offset + BATCH_SIZE]
            block = np.asarray(mm[batch_ids], dtype=np.float32) / SCALE
            norms = np.linalg.norm(block, axis=1)
            scores = (block @ q) / np.maximum(norms, 1e-12)
            k = min(top_k, len(scores))
            if k < len(scores):
                chosen = np.argpartition(scores, -k)[-k:]
            else:
                chosen = np.arange(len(scores))
            best_scores = np.concatenate((best_scores, scores[chosen]))
            best_ids = np.concatenate((best_ids, batch_ids[chosen]))
            if len(best_scores) > top_k:
                keep = np.argpartition(best_scores, -top_k)[-top_k:]
                best_scores, best_ids = best_scores[keep], best_ids[keep]
        order = np.argsort(best_scores)[::-1][:top_k]
        return best_scores[order].reshape(1, -1), best_ids[order].astype(np.int64).reshape(1, -1)

    def reset(self):
        with self.lock:
            with self.path.open("wb"):
                pass
            self._count = 0

    def save(self):
        # Writes are flushed on each append; retained for API compatibility.
        return None
