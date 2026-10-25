---
name: build-release
description: >-
  Builds standalone packages (Linux AppImage and Windows .exe) for BookRoomLog.
  Use this skill whenever the user wants to compile, package, or build the application
  for distribution.
---

# Build & Packaging Workflow (BookRoomLog)

This skill describes how to package BookRoomLog into standalone distributable packages (**Linux AppImage** and **Windows .EXE**).

---

## 1. Automated CI/CD (GitHub Actions)

The repository includes a complete GitHub Actions workflow (`.github/workflows/build-release.yml`).

### Triggering an Automated Cloud Build:
Whenever a version tag is pushed (e.g. `git push origin v0.3.0`), GitHub Actions will:
1. Run the entire automated test suite (`pytest -v`).
2. Build the **Linux AppImage** on Ubuntu 22.04 (`dist/BookRoomLog-x86_64.AppImage`).
3. Build the **Windows Executable** on Windows (`dist/BookRoomLog-Windows-x64.zip`).
4. Automatically create a **GitHub Release** and attach the binaries for download.

You can also trigger builds manually via GitHub Web UI under the **Actions** tab -> **Build & Release BookRoomLog** -> **Run workflow**.

---

## 2. Local Linux Build (AppImage)

To compile an AppImage locally on Linux:

```bash
# Execute o script de build
./scripts/build_appimage.sh
```

Output:
`dist/BookRoomLog-x86_64.AppImage`

---

## 3. Local Windows Build (.EXE)

To compile a `.exe` on Windows:

```cmd
scripts\build_windows.bat
```

Output:
`dist\BookRoomLog-Windows-x64.zip`

---

## 4. Dependências do build

Os builds instalam `requirements-build.txt` com `-c constraints-build.txt` (versões exatas já validadas). Para atualizar as versões: recrie o venv, instale `requirements-build.txt` sem constraints, rode `pytest` e um build local com smoke test, e regenere `constraints-build.txt`. Desenvolvimento e CI usam `requirements-dev.txt`, com faixas compatíveis.

---

## 5. Key Files

- `desktop_launcher.py`: Unified entrypoint that launches the FastAPI backend silently in a background thread and runs the PySide6 Qt GUI.
- `bookroomlog.spec`: PyInstaller configuration bundle with assets and hidden imports.
- `resources/bookroomlog.desktop`: Linux desktop integration entry.
- `.github/workflows/build-release.yml`: GitHub Actions automated release pipeline.
