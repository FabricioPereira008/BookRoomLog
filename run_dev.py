import sys
import os
import subprocess
import time
from pathlib import Path
from watchfiles import watch

BASE_DIR = Path(__file__).resolve().parent
_VENV_PYTHON = BASE_DIR / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
PYTHON_EXE = _VENV_PYTHON if _VENV_PYTHON.exists() else Path(sys.executable)
FRONTEND_MAIN = BASE_DIR / "frontend_desktop" / "main_app.py"
BACKEND_MAIN = BASE_DIR / "backend" / "run_server.py"
WATCH_DIR = BASE_DIR / "frontend_desktop"

def is_backend_running():
    try:
        import requests
        r = requests.get("http://127.0.0.1:8010/", timeout=1)
        return r.status_code == 200
    except Exception:
        return False

def run_dev_server():
    print("=" * 65)
    print("🚀 Modo Dev do BookRoomLog")
    print("🎨 Edição de QSS (dark_theme.qss): Atualiza AO VIVO sem fechar a janela!")
    print("🐍 Edição de Python (*.py): Reinicia a janela em ~100ms.")
    print("=" * 65)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)

    backend_proc = None
    if not is_backend_running():
        print("⚡ Iniciando servidor Backend (FastAPI) em segundo plano...")
        backend_proc = subprocess.Popen([str(PYTHON_EXE), str(BACKEND_MAIN)], env=env)
        time.sleep(1.0)
    else:
        print("✓ Backend já está online em http://127.0.0.1:8010")

    app_proc = None

    def start_app():
        nonlocal app_proc
        if app_proc:
            try:
                app_proc.terminate()
                app_proc.wait(timeout=1.0)
            except Exception:
                app_proc.kill()
        
        app_proc = subprocess.Popen([str(PYTHON_EXE), str(FRONTEND_MAIN)], env=env)

    start_app()

    try:
        # Monitorar apenas arquivos .py para reinício de processo
        # (arquivos .qss são atualizados AO VIVO dentro da própria janela aberta!)
        for changes in watch(WATCH_DIR):
            py_changes = [Path(c[1]).name for c in changes if c[1].endswith(".py")]
            if py_changes:
                print(f"\n⚡ Código Python alterado: {', '.join(py_changes)} -> Reiniciando janela...")
                start_app()
    except KeyboardInterrupt:
        print("\nEncerrando ambiente de desenvolvimento...")
    finally:
        if app_proc:
            app_proc.terminate()
        if backend_proc:
            backend_proc.terminate()

if __name__ == "__main__":
    run_dev_server()
