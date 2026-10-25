"""Capa de categoria: mosaico com até 4 capas de livros (ou um placeholder com a inicial)."""
from typing import List, Optional

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QSizePolicy, QWidget

from frontend_desktop import icons
from frontend_desktop.cover_loader import COVER_RADIUS, cover_loader
from frontend_desktop.styles.tokens import COLORS

MOSAIC_HEIGHT = 160
TILE_GAP = 6
V_MARGIN = 8
SIZE_STEP = 32  # larguras de pedido arredondadas: redimensionar a janela não gera um pedido por pixel


def tile_rects(count: int, width: int, height: int, gap: int = TILE_GAP) -> List[QRect]:
    """Divide a área em `count` (1–4) espaços iguais lado a lado, com margem vertical; cada capa se encaixa
    inteira no seu espaço."""
    count = max(1, count)
    slot_w = (width - gap * (count - 1)) // count
    slot_h = height - 2 * V_MARGIN
    return [QRect(i * (slot_w + gap), V_MARGIN, slot_w, slot_h) for i in range(count)]


class CoverMosaic(QWidget):
    def __init__(self, covers: List[str], title: str = "", accent_color: Optional[str] = None,
                 badge_icon: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.covers = list(covers)[:4]
        self.title = title
        self.accent_color = accent_color
        self.badge_icon = badge_icon
        self._corner_widget: Optional[QWidget] = None
        self.setFixedHeight(MOSAIC_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cover_loader.subscribe(self._on_cover_loaded)

    def set_corner_widget(self, widget: QWidget) -> None:
        """Widget sobreposto no canto superior direito (ex.: botão de menu)."""
        self._corner_widget = widget
        widget.setParent(self)
        self._place_corner_widget()

    def _place_corner_widget(self) -> None:
        if self._corner_widget is not None:
            w = self._corner_widget
            w.move(self.width() - w.width() - 8, 8)
            w.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_corner_widget()

    def _on_cover_loaded(self, filename: str) -> None:
        if filename in self.covers:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), COVER_RADIUS, COVER_RADIUS)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor(COLORS["surface_2"]))

        if self.covers:
            for filename, rect in zip(self.covers, tile_rects(len(self.covers), w, h)):
                req_w = -(-rect.width() // SIZE_STEP) * SIZE_STEP
                pixmap = cover_loader.request(filename, req_w, rect.height(), contain=True)
                if pixmap is not None:  # capa inteira, centralizada no espaço
                    size = pixmap.size().scaled(rect.size(), Qt.KeepAspectRatio)
                    target = QRect(0, 0, size.width(), size.height())
                    target.moveCenter(rect.center())
                    painter.drawPixmap(target, pixmap)
                else:
                    painter.fillRect(rect, QColor(COLORS["surface"]))
        else:
            font = QFont(self.font())
            font.setPixelSize(48)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(COLORS["text_dim"]))
            painter.drawText(self.rect(), Qt.AlignCenter, (self.title.strip()[:1] or "?").upper())

        if self.accent_color:  # gênero: faixa com a cor da tag na base
            painter.fillRect(QRect(0, h - 5, w, 5), QColor(self.accent_color))
        if self.badge_icon:  # tipo da categoria: selo no canto superior esquerdo
            badge = QRect(8, 8, 28, 28)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 170))
            painter.drawRoundedRect(badge, 6, 6)
            painter.drawPixmap(badge.adjusted(5, 5, -5, -5), icons.pixmap(self.badge_icon, "#ffffff", 18))
        painter.end()
