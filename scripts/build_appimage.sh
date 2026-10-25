#!/usr/bin/env bash
set -e

echo "========================================================="
echo "📚 BookRoomLog — Build de AppImage (Linux)"
echo "========================================================="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="python3"
if [ -d "venv" ]; then
    PYTHON_BIN="venv/bin/python"
fi

echo "1. Instalando / Verificando dependências de build..."
$PYTHON_BIN -m pip install -r requirements-build.txt -c constraints-build.txt

echo "2. Compilando o binário unificado com PyInstaller..."
$PYTHON_BIN -m PyInstaller --clean bookroomlog.spec

echo "3. Montando a estrutura AppDir para o AppImage..."
APP_DIR="$PROJECT_DIR/dist/AppDir"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/256x256/apps"

# Copiar binário compilado
cp "$PROJECT_DIR/dist/bookroomlog" "$APP_DIR/usr/bin/bookroomlog"

# Copiar .desktop e ícone
cp "$PROJECT_DIR/resources/bookroomlog.desktop" "$APP_DIR/bookroomlog.desktop"
if [ -f "$PROJECT_DIR/resources/icon.png" ]; then
    cp "$PROJECT_DIR/resources/icon.png" "$APP_DIR/bookroomlog.png"
    cp "$PROJECT_DIR/resources/icon.png" "$APP_DIR/usr/share/icons/hicolor/256x256/apps/bookroomlog.png"
else
    # Cria um ícone dummy caso não exista
    touch "$APP_DIR/bookroomlog.png"
fi

# Criar script de execução AppRun
cat << 'EOF' > "$APP_DIR/AppRun"
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/bookroomlog" "$@"
EOF
chmod +x "$APP_DIR/AppRun"

echo "4. Gerando o arquivo .AppImage com appimagetool..."
APPIMAGETOOL="$PROJECT_DIR/dist/appimagetool"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Baixando appimagetool..."
    # appimagetool atual (runtime estático, funciona com FUSE 3 ou sem FUSE)
    wget -q -O "$APPIMAGETOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$APPIMAGETOOL"
fi

ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run "$APP_DIR" "$PROJECT_DIR/dist/BookRoomLog-x86_64.AppImage"
chmod +x "$PROJECT_DIR/dist/BookRoomLog-x86_64.AppImage"

echo "========================================================="
echo "🎉 Build concluído com sucesso!"
echo "📍 Arquivo gerado: dist/BookRoomLog-x86_64.AppImage"
echo "========================================================="
