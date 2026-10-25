#!/usr/bin/env python3
"""
BookRoomLog — Release Automation Script
Atualiza versões nos arquivos, valida a suíte de testes, atualiza o CHANGELOG.md e cria tag git.
"""

import sys
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]

VERSION_FILE = ROOT_DIR / "app_version.py"
FILES_WITH_VERSION = [VERSION_FILE]  # fonte única; o resto importa de app_version

def run_cmd(cmd, cwd=ROOT_DIR, check=True):
    print(f"⚙️  Executando: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"❌ Erro ao executar comando:\n{res.stderr or res.stdout}")
        sys.exit(res.returncode)
    return res

def get_current_version():
    m = re.search(r'__version__\s*=\s*"([^"]+)"', VERSION_FILE.read_text(encoding="utf-8"))
    if not m:
        raise ValueError("Não foi possível encontrar __version__ em app_version.py")
    return m.group(1)

def run_tests():
    print("🧪 Executando suíte de testes antes do release...")
    pytest_bin = ROOT_DIR / "venv" / "bin" / "pytest"
    cmd = [str(pytest_bin) if pytest_bin.exists() else "pytest", "-v"]
    res = run_cmd(cmd, check=False)
    if res.returncode != 0:
        print("❌ Testes falharam! O processo de release foi abortado.")
        print(res.stdout)
        print(res.stderr)
        sys.exit(1)
    print("✅ Todos os testes passaram!")

def update_version_in_files(old_version, new_version):
    print(f"📝 Atualizando versão de {old_version} para {new_version}...")
    text = VERSION_FILE.read_text(encoding="utf-8")
    updated = re.sub(r'(__version__\s*=\s*)"[^"]+"', rf'\g<1>"{new_version}"', text, count=1)
    VERSION_FILE.write_text(updated, encoding="utf-8")
    print(f"  ✓ {VERSION_FILE.relative_to(ROOT_DIR)}")

def update_changelog(new_version, notes=None):
    changelog_file = ROOT_DIR / "CHANGELOG.md"
    today_str = date.today().isoformat()
    
    if not notes:
        notes = "### Modificado\n- Atualizações gerais e melhorias de estabilidade."
    
    new_entry = f"## [{new_version}] - {today_str}\n{notes.strip()}\n\n"
    
    if changelog_file.exists():
        content = changelog_file.read_text(encoding="utf-8")
        # Insere logo após o cabeçalho inicial
        header_end = content.find("## [")
        if header_end != -1:
            updated_content = content[:header_end] + new_entry + content[header_end:]
        else:
            updated_content = content + "\n\n" + new_entry
        changelog_file.write_text(updated_content, encoding="utf-8")
    else:
        changelog_file.write_text(f"# Changelog\n\n{new_entry}", encoding="utf-8")
    print(f"  ✓ CHANGELOG.md atualizado com a versão [{new_version}]")

def git_commit_and_tag(new_version):
    print("📦 Criando commit e tag no Git...")
    run_cmd(["git", "add", "CHANGELOG.md"] + [str(f.relative_to(ROOT_DIR)) for f in FILES_WITH_VERSION if f.exists()])
    run_cmd(["git", "commit", "-m", f"chore(release): bump version to v{new_version}"])
    tag_name = f"v{new_version}"
    run_cmd(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"])
    print(f"🎉 Tag {tag_name} criada com sucesso!")

def main():
    if len(sys.argv) < 2:
        print("Uso: python release.py <NOVA_VERSAO> [\"Notas do release\"]")
        sys.exit(1)
        
    new_version = sys.argv[1].lstrip("v")
    notes = sys.argv[2] if len(sys.argv) > 2 else None
    
    old_version = get_current_version()
    print(f"🚀 Iniciando processo de release: v{old_version} -> v{new_version}")
    
    # 1. Testes antes de mexer em arquivos
    run_tests()
    
    # 2. Atualizar arquivos
    update_version_in_files(old_version, new_version)
    
    # 3. Atualizar CHANGELOG
    update_changelog(new_version, notes)
    
    # 4. Rodar testes novamente para validar que asserções de versão nos testes continuam passando
    run_tests()
    
    # 5. Commit e Tag no Git
    git_commit_and_tag(new_version)
    
    print(f"\n✨ Release da versão v{new_version} finalizado com 100% de sucesso!")

if __name__ == "__main__":
    main()
