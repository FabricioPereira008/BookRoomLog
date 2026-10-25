import subprocess
import sys
import time
import os
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent
    venv_python = root_dir / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python_exec = str(venv_python) if venv_python.exists() else sys.executable

    # Iniciar backend em subprocesso
    print("Iniciando o servidor Backend (FastAPI)...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_dir)

    backend_proc = subprocess.Popen(
        [python_exec, str(root_dir / "backend" / "run_server.py")],
        env=env
    )

    # Esperar backend subir
    time.sleep(1.5)

    print("Iniciando a Interface Desktop (PySide6)...")
    try:
        subprocess.run(
            [python_exec, str(root_dir / "frontend_desktop" / "main_app.py")],
            env=env
        )
    finally:
        print("Encerrando o Backend...")
        backend_proc.terminate()
        backend_proc.wait()

if __name__ == "__main__":
    main()
