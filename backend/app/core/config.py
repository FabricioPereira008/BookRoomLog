import sys
import os
from pathlib import Path
from app_version import __version__
from pydantic_settings import BaseSettings, SettingsConfigDict

# Porta própria: o GameRoomLog usa a 8000 e os dois apps podem ficar abertos ao mesmo tempo
DEFAULT_PORT = 8010


def get_base_data_dir() -> Path:
    """
    Retorna o diretório base para armazenamento de dados e banco SQLite.
    - Se BOOKROOM_DATA_DIR estiver definido: utiliza o caminho configurado.
    - Se estiver em execução compilada/empacotada (frozen/AppImage/.exe):
        * Linux: ~/.local/share/bookroomlog
        * Windows: %APPDATA%/BookRoomLog
        * macOS: ~/Library/Application Support/BookRoomLog
    - Se estiver em desenvolvimento local: utiliza o diretório backend do repositório.
    """
    if "BOOKROOM_DATA_DIR" in os.environ:
        p = Path(os.environ["BOOKROOM_DATA_DIR"]).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "BookRoomLog"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "BookRoomLog"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "bookroomlog"
        base.mkdir(parents=True, exist_ok=True)
        return base

    return Path(__file__).resolve().parent.parent.parent

_BASE_DATA_DIR = get_base_data_dir()

class Settings(BaseSettings):
    PROJECT_NAME: str = "BookRoomLog API"
    VERSION: str = __version__
    API_V1_STR: str = "/api/v1"

    BASE_DIR: Path = _BASE_DATA_DIR
    DATABASE_URL: str = f"sqlite:///{_BASE_DATA_DIR}/bookroom.db"

    STORAGE_DIR: Path = _BASE_DATA_DIR / "storage"
    COVERS_DIR: Path = _BASE_DATA_DIR / "storage" / "covers"

    # Opcional: sem chave o Google Books funciona, mas com cota diária menor
    GOOGLE_BOOKS_API_KEY: str = ""

    # Origens web autorizadas via CORS (o cliente desktop não depende de CORS)
    CORS_ORIGINS: list[str] = [f"http://127.0.0.1:{DEFAULT_PORT}", f"http://localhost:{DEFAULT_PORT}"]
    # Tamanho máximo de imagens de capa (upload ou download), em bytes
    MAX_COVER_BYTES: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env", extra="ignore")

settings = Settings()

# Garantir que o diretório de capas existe
settings.COVERS_DIR.mkdir(parents=True, exist_ok=True)
