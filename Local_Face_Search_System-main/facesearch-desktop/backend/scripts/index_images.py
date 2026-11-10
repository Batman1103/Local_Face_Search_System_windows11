import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.db.database import MetadataDB
from app.services.face_engine import FaceEngine
from app.services.vector_store import VectorStore
from app.services.indexer import IncrementalIndexer


def main():
    parser = argparse.ArgumentParser(description="Index a photo folder into the local FaceSearch database.")
    parser.add_argument("--root", required=True, help="Photo folder to index recursively")
    args = parser.parse_args()

    image_root = Path(args.root).expanduser().resolve()
    if not image_root.is_dir():
        raise SystemExit(f"Image directory does not exist: {image_root}")

    cfg = load_config()
    db = MetadataDB(cfg["database_path"])
    engine = FaceEngine(cfg["model"]["name"], cfg["model"]["providers"])
    store = VectorStore(cfg["index_dir"])
    indexer = IncrementalIndexer(image_root, engine, store, db)
    try:
        indexer.scan()
        indexer.queue.join()
        print(f"Indexed images: {db.stats()['indexed_images']:,}")
        print(f"Indexed faces: {db.stats()['indexed_faces']:,}")
        print(f"Vector bytes: {Path(cfg['index_dir'], 'faces.int8').stat().st_size:,}")
        if indexer.errors:
            print(f"Errors: {indexer.errors:,}")
            print(indexer.last_error)
    finally:
        indexer.stop()
        db.close()


if __name__ == "__main__":
    main()
