#!/usr/bin/env python3
"""
Script helper para analisar a cobertura de testes de novos arquivos e do projeto todo.
"""

import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]

def run_coverage():
    pytest_bin = ROOT_DIR / "venv" / "bin" / "pytest"
    cmd = [
        str(pytest_bin) if pytest_bin.exists() else "pytest",
        "--cov=backend/app",
        "--cov=frontend_desktop/api_client",
        "--cov=frontend_desktop/views/components",
        "--cov-report=term-missing",
        "-v"
    ]
    print("🔍 Executando análise de cobertura de testes...")
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr)
    return res.returncode

if __name__ == "__main__":
    sys.exit(run_coverage())
