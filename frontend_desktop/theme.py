"""Tema: gera QPalette e QSS a partir dos mesmos tokens e carrega fontes embutidas."""
import logging
import os
import sys
import tempfile
from pathlib import Path
from string import Template

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from frontend_desktop import icons
from frontend_desktop.styles.tokens import COLORS, FONT_FAMILY, qss_mapping

logger = logging.getLogger(__name__)

_FONT_FILES = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf")


def _resource_dir(*parts: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).joinpath("resources", *parts)
    return Path(__file__).resolve().parent.parent.joinpath("resources", *parts)


def get_qss_path() -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        for cand in (
            base / "frontend_desktop" / "styles" / "dark_theme.qss",
            base / "styles" / "dark_theme.qss",
            base / "dark_theme.qss",
        ):
            if cand.exists():
                return cand
    return Path(__file__).parent / "styles" / "dark_theme.qss"


def _asset_tokens() -> dict:
    """Ícones usados pelo QSS (setas de combo/spin) exportados já na cor do tema."""
    dest = Path(tempfile.gettempdir()) / "bookroomlog-theme"
    return {
        "arrow_down": icons.export_tinted_svg("chevron-down", COLORS["text_muted"], dest),
        "arrow_up": icons.export_tinted_svg("chevron-up", COLORS["text_muted"], dest),
    }


def build_qss(template_text: str, extra: dict = None) -> str:
    """Preenche os placeholders `$token` do template. Falha se algum token não existir."""
    mapping = qss_mapping()
    mapping.update(extra or {})
    return Template(template_text).substitute(mapping)


def load_qss() -> str:
    return build_qss(get_qss_path().read_text(encoding="utf-8"), _asset_tokens())


def load_fonts() -> bool:
    """Registra a Inter embutida. Retorna False se nenhum arquivo foi carregado (usa fallback do sistema)."""
    loaded = 0
    for name in _FONT_FILES:
        path = _resource_dir("fonts") / name
        if path.exists() and QFontDatabase.addApplicationFont(str(path)) != -1:
            loaded += 1
    if not loaded:
        logger.warning("Fontes embutidas não encontradas; usando fontes do sistema.")
    else:
        logger.info("Fontes embutidas carregadas: %d/%d", loaded, len(_FONT_FILES))
    return bool(loaded)


def build_palette() -> QPalette:
    c = {k: QColor(v) for k, v in COLORS.items() if len(v) == 7}
    palette = QPalette()
    palette.setColor(QPalette.Window, c["bg"])
    palette.setColor(QPalette.WindowText, c["text"])
    palette.setColor(QPalette.Base, c["surface_2"])
    palette.setColor(QPalette.AlternateBase, c["surface"])
    palette.setColor(QPalette.ToolTipBase, c["surface_3"])
    palette.setColor(QPalette.ToolTipText, c["text"])
    palette.setColor(QPalette.Text, c["text"])
    palette.setColor(QPalette.Button, c["surface"])
    palette.setColor(QPalette.ButtonText, c["text"])
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Link, c["accent"])
    palette.setColor(QPalette.Highlight, c["accent"])
    palette.setColor(QPalette.HighlightedText, c["on_accent"])
    palette.setColor(QPalette.PlaceholderText, c["text_dim"])
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, c["text_dim"])
    return palette


def apply_theme(app: QApplication) -> None:
    """Aplica estilo Fusion, paleta, fonte e QSS (ordem importa: fonte antes do QSS)."""
    app.setStyle("Fusion")
    load_fonts()
    app.setFont(QFont(FONT_FAMILY, 10))
    app.setPalette(build_palette())
    app.setStyleSheet(load_qss())


def setup_live_stylesheet(app: QApplication) -> None:
    """Dev: recarrega o QSS ao salvar (F5 força). Em builds empacotados não há polling."""
    qss_path = get_qss_path()
    last_mtime = [0.0]

    def reload_qss():
        if not qss_path.exists():
            return
        try:
            mtime = os.path.getmtime(qss_path)
            if mtime == last_mtime[0]:
                return
            last_mtime[0] = mtime
            app.setStyleSheet("")
            app.setStyleSheet(load_qss())
            logger.info("[QSS Live Reload] Estilos atualizados")
        except Exception as e:
            logger.warning("[QSS Live Reload] Erro ao aplicar estilos: %s", e)

    app._force_reload_qss = reload_qss
    if getattr(sys, "frozen", False):
        return
    timer = QTimer()
    timer.setInterval(500)
    timer.timeout.connect(reload_qss)
    timer.start()
    app._qss_timer = timer
