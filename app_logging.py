"""Configuração de logging compartilhada (arquivo rotativo + console quando existir)."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False


def get_log_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "BookRoomLog"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "BookRoomLog"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "bookroomlog"
    return base / "logs"


def setup_logging(level: int = logging.INFO) -> None:
    """Idempotente. Em builds sem console (windowed) o arquivo é a única saída."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.stderr is not None and getattr(sys.stderr, "write", None):
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)
    try:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_dir / "bookroomlog.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        pass
