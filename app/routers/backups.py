from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .. import backup

router = APIRouter(prefix="/backups", tags=["Backups"])

@router.post("/")
def create_backup():
    path = backup.make_backup()
    return {"created": path.name, "size_kb": round(path.stat().st_size / 1024, 1)}

@router.get("/")
def list_backups():
    return backup.list_backups()

@router.get("/{name}")
def download_backup(name: str):
    path = backup.find(name)
    if not path:
        raise HTTPException(404, "Backup not found")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")