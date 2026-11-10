import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.services.vector_store import VectorStore


class CompactStoreTests(unittest.TestCase):
    def test_storage_is_512_bytes_per_face_and_search_ranks_similar_vectors(self):
        with tempfile.TemporaryDirectory() as temp:
            store = VectorStore(temp)
            rng = np.random.default_rng(7)
            query = rng.normal(size=512).astype(np.float32)
            query /= np.linalg.norm(query)
            near = query + rng.normal(0, 0.01, size=512).astype(np.float32)
            far = rng.normal(size=512).astype(np.float32)

            store.add([query, far, near])
            scores, ids = store.search(query, 3)

            self.assertEqual(Path(temp, "faces.int8").stat().st_size, 3 * 512)
            self.assertEqual(int(ids[0, 0]), 0)
            self.assertEqual(int(ids[0, 1]), 2)
            self.assertGreater(float(scores[0, 0]), float(scores[0, 1]))

    def test_active_ids_exclude_deleted_vectors(self):
        with tempfile.TemporaryDirectory() as temp:
            store = VectorStore(temp)
            query = np.zeros(512, dtype=np.float32)
            query[4] = 1
            store.add([query, -query])
            scores, ids = store.search(query, 10, active_ids=[1])
            self.assertEqual(ids.tolist(), [[1]])
            self.assertAlmostEqual(float(scores[0, 0]), -1.0, places=2)


if __name__ == "__main__":
    unittest.main()
