#!/usr/bin/env bash
# Instala o hook de pré-commit versionado em scripts/pre-commit
set -e
ROOT="$(git rev-parse --show-toplevel)"
install -m 755 "$ROOT/scripts/pre-commit" "$ROOT/.git/hooks/pre-commit"
echo "✅ Hook de pré-commit instalado."
