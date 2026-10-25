import logging
from app_logging import setup_logging
import sys
import time
import threading
from urllib.parse import urlparse
from pathlib import Path

# Em executáveis desktop sem janela de terminal (console=False), sys.stdout e sys.stderr são None no Windows.
# O NullWriter evita que bibliotecas como o Uvicorn quebrem ao tentar chamar sys.stdout.isatty().
class NullWriter:
    def write(self, s):
        pass
    def flush(self):
        pass
    def isatty(self):
        return False

if sys.stdout is None:
    sys.stdout = NullWriter()
if sys.stderr is None:
    sys.stderr = NullWriter()

# Garantir que o diretório raiz está no sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import uvicorn

from backend.app.main import app as fastapi_app
from frontend_desktop.api_client.client import api_client
from frontend_desktop.main_app import create_app, create_main_window, show_main_window

logger = logging.getLogger(__name__)


class EmbeddedBackendServer(threading.Thread):
    """Executa o servidor FastAPI/Uvicorn em uma thread em segundo plano."""
    def __init__(self, host: str = "127.0.0.1", port: int = 8010):
        super().__init__(daemon=True, name="BackendServerThread")
        self.host = host
        self.port = port
        self.config = uvicorn.Config(
            fastapi_app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            log_config=None,
            use_colors=False
        )
        self.server = uvicorn.Server(self.config)


    def run(self):
        try:
            self.server.run()
        except Exception:
            logger.exception("Erro no backend embutido")

    def stop(self):
        self.server.should_exit = True

def is_server_ready() -> bool:
    return api_client.is_backend_online()

def main():
    setup_logging()
    backend_thread = None

    # Se o backend não estiver rodando externamente, inicia o backend embutido
    if not is_server_ready():
        logger.info("Iniciando backend FastAPI integrado...")
        parsed = urlparse(api_client.server_url)
        backend_thread = EmbeddedBackendServer(host=parsed.hostname or "127.0.0.1", port=parsed.port or 8010)
        backend_thread.start()

        # Aguardar inicialização com limite de 5 segundos
        start_time = time.time()
        while not is_server_ready() and (time.time() - start_time) < 5.0:
            time.sleep(0.05)

        if is_server_ready():
            logger.info("Backend FastAPI pronto em %s", api_client.server_url)
        else:
            logger.warning("Backend demorou para responder, abrindo interface mesmo assim...")

    # Inicializar aplicação PySide6
    app = create_app()
    window = create_main_window(app)
    show_main_window(window)

    exit_code = app.exec()

    if backend_thread:
        logger.info("Encerrando servidor backend integrado...")
        backend_thread.stop()

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
