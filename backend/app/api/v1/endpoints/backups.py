import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.engine import Engine
from starlette.background import BackgroundTask

from backend.app.core.database import engine as default_engine
from backend.app.core.migrations import run_migrations
from backend.app.schemas.backup import BackupInfo, BackupList, RestoreResponse
from backend.app.services import backup_service
from backend.app.services.backup_service import BackupNotFoundError, InvalidBackupError

router = APIRouter()


def get_engine() -> Engine:
    """Banco alvo dos backups (substituível nos testes)."""
    return default_engine


@router.get("/", response_model=BackupList)
def list_backups(engine: Engine = Depends(get_engine)):
    folder = backup_service.backup_dir(engine)
    return BackupList(folder=str(folder) if folder else None, max_backups=backup_service.MAX_BACKUPS,
                      backups=backup_service.list_backups(engine))


@router.post("/", response_model=BackupInfo, status_code=status.HTTP_201_CREATED)
def create_backup(engine: Engine = Depends(get_engine)):
    try:
        return backup_service.create_backup(engine, reason="manual")
    except InvalidBackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{name}/restore", response_model=RestoreResponse)
def restore_backup(name: str, engine: Engine = Depends(get_engine)):
    try:
        return backup_service.restore_backup(engine, name, run_migrations)
    except BackupNotFoundError:
        raise HTTPException(status_code=404, detail="Backup não encontrado")
    except InvalidBackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{name}/export")
def export_backup(name: str, engine: Engine = Depends(get_engine)):
    """Baixa o backup `name` como .zip (banco + capas), para guardar fora deste computador."""
    handle = tempfile.NamedTemporaryFile(prefix="bookroom-export-", suffix=".zip", delete=False)
    try:
        with handle:
            backup_service.export_backup(engine, name, handle)
    except BackupNotFoundError:
        os.unlink(handle.name)
        raise HTTPException(status_code=404, detail="Backup não encontrado")
    except InvalidBackupError as exc:
        os.unlink(handle.name)
        raise HTTPException(status_code=400, detail=str(exc))
    download = name.removesuffix(".db") + ".zip"
    return FileResponse(handle.name, media_type="application/zip", filename=download,
                        background=BackgroundTask(os.unlink, handle.name))


@router.post("/import", response_model=BackupInfo, status_code=status.HTTP_201_CREATED)
def import_backup(file: UploadFile = File(...), engine: Engine = Depends(get_engine)):
    """Recebe um .zip exportado e o adiciona à lista de backups (a restauração é feita depois)."""
    try:
        return backup_service.import_backup(engine, file.file)
    except InvalidBackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
