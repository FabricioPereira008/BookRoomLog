from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class BackupInfo(BaseModel):
    name: str
    created_at: datetime
    reason: str  # auto | manual | antes-da-restauracao | importado
    reason_label: str
    size_bytes: int
    books_count: Optional[int] = None


class BackupList(BaseModel):
    folder: Optional[str] = None
    max_backups: int
    backups: List[BackupInfo]


class RestoreResponse(BaseModel):
    restored: str
    safety_backup: str
    covers_restored: int = 0
