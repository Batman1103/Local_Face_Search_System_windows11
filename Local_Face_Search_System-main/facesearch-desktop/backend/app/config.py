from pathlib import Path
import os
import sys
import yaml

if getattr(sys, "frozen", False):
    CONFIG_PATH = Path(sys._MEIPASS) / "config" / "config.yaml"
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def _data_root() -> Path:
    raw = os.environ.get("FACESEARCH_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        return base / "FaceSearch"
    if os.uname().sysname == "Darwin":
        return home / "Library" / "Application Support" / "FaceSearch"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "facesearch"


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    data_root = _data_root()
    data_root.mkdir(parents=True, exist_ok=True)
    cfg["index_dir"] = str(data_root / "index")
    cfg["database_path"] = str(data_root / "metadata.db")
    cfg["data_root"] = str(data_root)
    return cfg
