"""Ícones SVG (Lucide, ISC) tingidos em tempo de execução, com cache."""
import logging
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from frontend_desktop.styles.tokens import COLORS

logger = logging.getLogger(__name__)


def icons_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "resources" / "icons"
    return Path(__file__).resolve().parent.parent / "resources" / "icons"


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    path = icons_dir() / f"{name}.svg"
    if not path.exists():
        logger.warning("Ícone SVG não encontrado: %s (%s)", name, path)
        return ""
    return path.read_text(encoding="utf-8")


def export_tinted_svg(name: str, color: str, dest_dir: Path) -> str:
    """Grava uma cópia do SVG na cor dada (para uso em `image: url()` do QSS); retorna a URL."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{name}-{QColor(color).name(QColor.HexRgb).lstrip('#')}.svg"
    target.write_text(_svg_source(name).replace("currentColor", QColor(color).name(QColor.HexRgb)), encoding="utf-8")
    return target.as_posix()


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = COLORS["text_muted"], size: int = 18, dpr: int = 2) -> QPixmap:
    """Renderiza o ícone `name` na cor `color` (hex). Retorna pixmap vazio se o SVG não existir."""
    px = QPixmap(size * dpr, size * dpr)
    px.fill(Qt.transparent)
    px.setDevicePixelRatio(dpr)
    source = _svg_source(name)
    if not source:
        return px
    svg = source.replace("currentColor", QColor(color).name(QColor.HexRgb))
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(px)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return px


@lru_cache(maxsize=512)
def icon(name: str, color: str = COLORS["text_muted"], size: int = 18, active_color: str = "") -> QIcon:
    """QIcon com estado normal e (opcional) ativo/marcado em outra cor."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Normal, QIcon.Off)
    ic.addPixmap(pixmap(name, active_color or color, size), QIcon.Normal, QIcon.On)
    return ic
