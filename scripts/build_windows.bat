@echo off
echo =========================================================
echo  BookRoomLog - Build Windows Executable (.exe)
echo =========================================================

set PYTHON_CMD=python
if exist venv\Scripts\python.exe (
    set PYTHON_CMD=venv\Scripts\python.exe
)

echo 1. Instalando dependencias de build...
%PYTHON_CMD% -m pip install -r requirements-build.txt -c constraints-build.txt

echo 2. Compilando o executavel com PyInstaller...
%PYTHON_CMD% -m PyInstaller --clean bookroomlog.spec

echo 3. Compactando executavel em arquivo ZIP...
powershell -Command "Compress-Archive -Path dist\bookroomlog.exe, resources -DestinationPath dist\BookRoomLog-Windows-x64.zip -Force"

echo =========================================================
echo  Build concluido com sucesso!
echo  Arquivo gerado: dist\BookRoomLog-Windows-x64.zip
echo =========================================================
pause
