import sqlite3
from pathlib import Path
from threading import RLock
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    image_id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL UNIQUE,
    relative_path TEXT,
    file_size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'indexed',
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS faces (
    vector_id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL,
    x1 INTEGER NOT NULL,
    y1 INTEGER NOT NULL,
    x2 INTEGER NOT NULL,
    y2 INTEGER NOT NULL,
    detection_score REAL,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(image_id) REFERENCES images(image_id)
);
CREATE INDEX IF NOT EXISTS idx_faces_image_id ON faces(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_active ON faces(active);
CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_relative_path ON images(relative_path);
"""

class MetadataDB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = RLock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def set_state(self, key, value):
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES(?,?)", (key, str(value)))
            self.conn.commit()

    def get_state(self, key, default=None):
        with self.lock:
            row = self.conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def get_image_state(self, image_path):
        with self.lock:
            return self.conn.execute(
                "SELECT image_id, file_size, mtime_ns, status FROM images WHERE image_path=?",
                (str(image_path),)
            ).fetchone()

    def prepare_image(self, image_path, file_size, mtime_ns, relative_path):
        image_path = str(Path(image_path).resolve())
        with self.lock:
            row = self.conn.execute(
                "SELECT image_id, file_size, mtime_ns, status FROM images WHERE image_path=?",
                (image_path,)
            ).fetchone()
            if row and row[1] == file_size and row[2] == mtime_ns and row[3] == 'indexed':
                return row[0], False
            if row:
                image_id = row[0]
                self.conn.execute(
                    "UPDATE images SET relative_path=?, file_size=?, mtime_ns=?, status='indexing', indexed_at=CURRENT_TIMESTAMP WHERE image_id=?",
                    (relative_path, file_size, mtime_ns, image_id)
                )
                self.conn.execute("UPDATE faces SET active=0 WHERE image_id=?", (image_id,))
            else:
                cur = self.conn.execute(
                    "INSERT INTO images(image_path,relative_path,file_size,mtime_ns,status) VALUES(?,?,?,?, 'indexing')",
                    (image_path, relative_path, file_size, mtime_ns)
                )
                image_id = cur.lastrowid
            self.conn.commit()
            return image_id, True

    def finish_image(self, image_id, success=True):
        with self.lock:
            self.conn.execute("UPDATE images SET status=? WHERE image_id=?", ('indexed' if success else 'error', image_id))
            self.conn.commit()

    def mark_missing_path(self, path):
        path = str(Path(path).resolve())
        with self.lock:
            row = self.conn.execute("SELECT image_id FROM images WHERE image_path=?", (path,)).fetchone()
            if not row:
                return False
            self.conn.execute("UPDATE images SET status='missing' WHERE image_id=?", (row[0],))
            self.conn.execute("UPDATE faces SET active=0 WHERE image_id=?", (row[0],))
            self.conn.commit()
            return True

    def mark_missing_under_root(self, root):
        root = Path(root).resolve()
        with self.lock:
            rows = self.conn.execute("SELECT image_id,image_path FROM images WHERE status!='missing'").fetchall()
            changed = 0
            for image_id, path in rows:
                p = Path(path).resolve()
                try:
                    p.relative_to(root)
                except ValueError:
                    continue
                if not p.is_file():
                    self.conn.execute("UPDATE images SET status='missing' WHERE image_id=?", (image_id,))
                    self.conn.execute("UPDATE faces SET active=0 WHERE image_id=?", (image_id,))
                    changed += 1
            self.conn.commit()
            return changed

    def rebind_root(self, old_root, new_root):
        old_root, new_root = Path(old_root).resolve(), Path(new_root).resolve()
        updated = 0
        with self.lock:
            rows = self.conn.execute(
                "SELECT image_id, relative_path, file_size, mtime_ns FROM images WHERE relative_path IS NOT NULL"
            ).fetchall()
            for image_id, relative_path, size, mtime in rows:
                if not relative_path:
                    continue
                candidate = (new_root / relative_path).resolve()
                if candidate.is_file():
                    st = candidate.stat()
                    if st.st_size == size and st.st_mtime_ns == mtime:
                        self.conn.execute(
                            "UPDATE images SET image_path=?, status='indexed', mtime_ns=? WHERE image_id=?",
                            (str(candidate), st.st_mtime_ns, image_id)
                        )
                        updated += 1
                        continue
                self.conn.execute(
                    "UPDATE images SET status='missing' WHERE image_id=?", (image_id,)
                )
                self.conn.execute(
                    "UPDATE faces SET active=0 WHERE image_id=?", (image_id,)
                )
            self.conn.commit()
        return updated

    def add_faces(self, rows):
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO faces(vector_id,image_id,x1,y1,x2,y2,detection_score,active) VALUES(?,?,?,?,?,?,?,1)",
                rows
            )
            self.conn.commit()

    def get_face(self, vector_id, active_only=True):
        sql = """SELECT f.vector_id,i.image_id,i.image_path,f.x1,f.y1,f.x2,f.y2,f.detection_score
                 FROM faces f JOIN images i ON f.image_id=i.image_id
                 WHERE f.vector_id=?"""
        if active_only:
            sql += " AND f.active=1 AND i.status='indexed'"
        with self.lock:
            return self.conn.execute(sql, (int(vector_id),)).fetchone()

    def stats(self):
        with self.lock:
            return {
                "indexed_images": self.conn.execute("SELECT COUNT(*) FROM images WHERE status='indexed'").fetchone()[0],
                "indexed_faces": self.conn.execute("SELECT COUNT(*) FROM faces WHERE active=1").fetchone()[0],
                "missing_images": self.conn.execute("SELECT COUNT(*) FROM images WHERE status='missing'").fetchone()[0],
                "error_images": self.conn.execute("SELECT COUNT(*) FROM images WHERE status='error'").fetchone()[0],
            }

    def reset_for_rebuild(self):
        with self.lock:
            self.conn.execute("UPDATE faces SET active=0")
            self.conn.execute("UPDATE images SET status='stale'")
            self.conn.commit()

    def active_face_rows(self):
        with self.lock:
            return self.conn.execute(
                "SELECT vector_id,image_id,x1,y1,x2,y2,detection_score FROM faces WHERE active=1 ORDER BY vector_id"
            ).fetchall()


    def active_vector_ids(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT vector_id FROM faces WHERE active=1 ORDER BY vector_id"
            ).fetchall()
            return [int(row[0]) for row in rows]

    def clear_collection(self):
        with self.lock:
            self.conn.execute("DELETE FROM faces")
            self.conn.execute("DELETE FROM images")
            self.conn.commit()

    def close(self):
        with self.lock:
            self.conn.close()
