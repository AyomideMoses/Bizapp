import sqlite3
from datetime import datetime
from pathlib import Path
from . import config
from .utils import now_wat

DB_FILE = "bizapp.db"

def make_backup() -> Path:
    folder = Path(config.BACKUP_DIR)
    folder.mkdir(exist_ok=True)
    target = folder / f"bizapp-{now_wat().strftime('%Y%m%d-%H%M%S')}.db"

    source = sqlite3.connect(DB_FILE)
    destination = sqlite3.connect(target)
    with destination:
        source.backup(destination)     # safe even while the app is running
    destination.close()
    source.close()

    prune()
    return target

def prune():
    files = sorted(Path(config.BACKUP_DIR).glob("bizapp-*.db"))
    for old in files[:-config.BACKUP_KEEP]:
        old.unlink()

def list_backups() -> list[dict]:
    folder = Path(config.BACKUP_DIR)
    if not folder.exists():
        return []
    rows = [
        {
            "name": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created": datetime.utcfromtimestamp(f.stat().st_mtime),
        }
        for f in folder.glob("bizapp-*.db")
    ]
    return sorted(rows, key=lambda r: r["name"], reverse=True)

def find(name: str):
    folder = Path(config.BACKUP_DIR)
    for f in folder.glob("bizapp-*.db"):
        if f.name == name:          # only exact matches from the folder are allowed
            return f
    return None

if __name__ == "__main__":
    print("Backup created:", make_backup())