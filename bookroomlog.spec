# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None

BASE_DIR = os.path.abspath(SPECPATH if 'SPECPATH' in locals() else os.getcwd())

added_datas = [
    (os.path.join(BASE_DIR, 'frontend_desktop', 'styles', 'dark_theme.qss'), os.path.join('frontend_desktop', 'styles')),
    (os.path.join(BASE_DIR, 'resources'), 'resources'),
    (os.path.join(BASE_DIR, 'backend', 'migrations'), os.path.join('backend', 'migrations')),
]

hidden_imports = [
    'alembic',
    'alembic.runtime.migration',
    'alembic.script',
    'app_version',
    'app_logging',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    'pydantic',
    'pydantic_settings',
    'sqlalchemy',
    'sqlalchemy.dialects.sqlite',
    'backend.app.api.v1.api_router',
    'backend.app.api.v1.endpoints.books',
    'backend.app.api.v1.endpoints.categories',
    'backend.app.api.v1.endpoints.stats',
    'backend.app.api.v1.endpoints.lookup',
    'backend.app.api.v1.endpoints.uploads',
    'backend.app.api.v1.endpoints.backups',
    'backend.app.models.book',
    'backend.app.models.author',
    'backend.app.models.genre',
    'backend.app.models.publisher',
    'backend.app.models.series',
    'backend.app.models.yearbook',
    'frontend_desktop.views.main_window',
    'frontend_desktop.views.components.shelf_view',
    'frontend_desktop.views.components.book_grid',
    'frontend_desktop.views.components.book_card_delegate',
    'frontend_desktop.views.components.book_table',
    'frontend_desktop.views.components.next_queue_view',
    'frontend_desktop.views.components.sidebar',
    'frontend_desktop.views.components.yearbook_view',
    'frontend_desktop.views.components.management_view',
    'frontend_desktop.views.components.category_detail_view',
    'frontend_desktop.views.components.settings_view',
    'frontend_desktop.views.view_ids',
    'frontend_desktop.views.book_status',
    'frontend_desktop.models.book_list_model',
    'frontend_desktop.models.book_table_model',
    'frontend_desktop.views.dialogs.book_dialog',
    'frontend_desktop.views.dialogs.lookup_dialog',
    'frontend_desktop.views.dialogs.quick_search_dialog',
    'frontend_desktop.views.dialogs.top3_dialog',
    'frontend_desktop.cover_loader',
    'frontend_desktop.theme',
    'frontend_desktop.icons',
    'frontend_desktop.ui_helpers',
    'frontend_desktop.workers',
    'PySide6.QtSvg',
]

a = Analysis(
    ['desktop_launcher.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=added_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='bookroomlog',
    # Windows exige .ico; no Linux o ícone vem do .desktop/AppImage
    icon=os.path.join(BASE_DIR, 'resources', 'icon.ico') if sys.platform == 'win32' and os.path.exists(os.path.join(BASE_DIR, 'resources', 'icon.ico')) else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX costuma corromper binários do Qt
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

