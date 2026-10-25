"""Card de livro pintado com QPainter: zero widgets por card, rolagem e resize fluidos."""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from frontend_desktop import icons, preferences
from frontend_desktop.cover_loader import COVER_RADIUS, cover_loader
from frontend_desktop.data_quality import is_incomplete
from frontend_desktop.models.book_list_model import BookRole
from frontend_desktop.styles.tokens import COLORS
from frontend_desktop.views import book_status as bs

PADDING = 10
ROW_GAP = 6
TITLE_H = 18
AUTHOR_H = 16
BADGE_H = 18
CARD_RADIUS = 10
PROGRESS_H = 6

CARD_WIDTHS = {"small": 130, "medium": 170, "large": 230}


def _rgba(hex_or_rgba: str) -> QColor:
    """Aceita '#rrggbb' ou 'rgba(r, g, b, a)' (formato usado nos tokens)."""
    if hex_or_rgba.startswith("rgba"):
        r, g, b, a = [p.strip() for p in hex_or_rgba[5:-1].split(",")]
        return QColor(int(r), int(g), int(b), int(float(a) * 255))
    return QColor(hex_or_rgba)


@dataclass(frozen=True)
class CardMetrics:
    card_width: int
    cover_width: int
    cover_height: int
    card_height: int

    @staticmethod
    def for_mode(size_mode: str) -> "CardMetrics":
        width = CARD_WIDTHS.get(size_mode, CARD_WIDTHS["medium"])
        cover_w = width - 2 * PADDING
        cover_h = int(cover_w * 1.5)
        height = PADDING + cover_h + 8 + TITLE_H + 2 + AUTHOR_H + ROW_GAP + BADGE_H + PADDING
        return CardMetrics(width, cover_w, cover_h, height)


def current_size_mode() -> str:
    return preferences.card_size()


_PLACEHOLDERS: Dict[Tuple[int, int], QPixmap] = {}


def placeholder_pixmap(width: int, height: int) -> QPixmap:
    key = (width, height)
    if key not in _PLACEHOLDERS:
        pm = QPixmap(width, height)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, width, height), COVER_RADIUS, COVER_RADIUS)
        p.fillPath(path, QColor(COLORS["surface_2"]))
        size = min(32, width // 3)
        icon_px = icons.pixmap("book", COLORS["text_dim"], size)
        p.drawPixmap((width - size) // 2, (height - size) // 2, size, size, icon_px)
        p.end()
        _PLACEHOLDERS[key] = pm
    return _PLACEHOLDERS[key]


class BookCardDelegate(QStyledItemDelegate):
    def __init__(self, size_mode: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.metrics = CardMetrics.for_mode(size_mode or current_size_mode())

    def set_size_mode(self, size_mode: str) -> bool:
        """Retorna True se o tamanho mudou (a view precisa refazer o layout)."""
        new = CardMetrics.for_mode(size_mode)
        changed = new != self.metrics
        self.metrics = new
        return changed

    def sizeHint(self, option, index) -> QSize:
        return QSize(self.metrics.card_width, self.metrics.card_height)

    # --- pintura ---
    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        book = index.data(BookRole)
        if not book:
            return
        m = self.metrics
        rect = QRect(option.rect.topLeft(), QSize(m.card_width, m.card_height))
        hovered = bool(option.state & QStyle.State_MouseOver)
        focused = bool(option.state & QStyle.State_Selected)

        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)

        # fundo do card
        bg = QColor(COLORS["surface_2"] if hovered or focused else COLORS["surface"])
        border = _rgba(COLORS["accent_border"]) if hovered else QColor(COLORS["border"])
        if focused:
            border = QColor(COLORS["accent"])
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), CARD_RADIUS, CARD_RADIUS)
        painter.fillPath(path, bg)
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)

        # capa
        cover_rect = QRect(rect.x() + PADDING, rect.y() + PADDING, m.cover_width, m.cover_height)
        pixmap = None
        filename = book.get("cover_image")
        if filename:
            pixmap = cover_loader.request(filename, m.cover_width, m.cover_height)
        painter.drawPixmap(cover_rect, pixmap or placeholder_pixmap(m.cover_width, m.cover_height))
        if book.get("is_favorite"):
            self._cover_mark(painter, cover_rect, "star", COLORS["accent"], left=True)
        if is_incomplete(book):  # aviso discreto: o tooltip do card lista o que falta
            self._cover_mark(painter, cover_rect, "circle-alert", COLORS["warning"])
        if (book.get("read_number") or 1) > 1:
            self._cover_mark(painter, cover_rect, "repeat", COLORS["text"], left=True, bottom=True)

        # título e autor
        y = cover_rect.bottom() + 1 + 8
        inner_w = m.card_width - 2 * PADDING
        left = rect.x() + PADDING
        title_font = QFont(option.font)
        title_font.setPixelSize(12 if m.card_width <= 130 else 13)
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(COLORS["text"]))
        title = QFontMetrics(title_font).elidedText(book.get("title") or "Sem título", Qt.ElideRight, inner_w)
        painter.drawText(QRect(left, y, inner_w, TITLE_H), Qt.AlignVCenter | Qt.AlignLeft, title)

        y += TITLE_H + 2
        small = QFont(option.font)
        small.setPixelSize(11)
        small_fm = QFontMetrics(small)
        painter.setFont(small)
        painter.setPen(QColor(COLORS["text_muted"]))
        author = small_fm.elidedText(bs.author_names(book) or "Autor desconhecido", Qt.ElideRight, inner_w)
        painter.drawText(QRect(left, y, inner_w, AUTHOR_H), Qt.AlignVCenter | Qt.AlignLeft, author)

        # linha de meta: progresso (Lendo) ou páginas; à direita a nota (Lido) ou a posição na fila (Próximo)
        y += AUTHOR_H + ROW_GAP
        right_limit = left + inner_w
        meta_right = right_limit
        status = book.get("status")
        badge_font = QFont(small)
        badge_font.setWeight(QFont.DemiBold)
        badge_fm = QFontMetrics(badge_font)
        badge = None
        if status == bs.LIDO and book.get("score") is not None:
            badge = f"{book['score']:.1f}"
        elif status == bs.PROXIMO and book.get("next_position"):
            badge = f"#{book['next_position']}"
        if badge:
            w = badge_fm.horizontalAdvance(badge) + 12
            self._badge(painter, badge_font, QRectF(right_limit - w, y, w, BADGE_H), badge,
                        _rgba(COLORS["accent_soft"]), QColor(COLORS["accent_text"]))
            meta_right = right_limit - w - 6

        if status == bs.LENDO:
            self._progress(painter, small, small_fm, left, y, meta_right - left, book.get("progress") or 0)
        else:
            fmt_icon = bs.FORMAT_ICONS.get(book.get("format"), "book-open")
            painter.drawPixmap(QRect(left, y + (BADGE_H - 12) // 2, 12, 12), icons.pixmap(fmt_icon, COLORS["text_muted"], 12))
            painter.setFont(small)
            painter.setPen(QColor(COLORS["text_muted"]))
            meta = bs.pages_text(book) or book.get("format") or ""
            meta = small_fm.elidedText(meta, Qt.ElideRight, max(0, meta_right - left - 16))
            painter.drawText(QRect(left + 16, y, max(0, meta_right - left - 16), BADGE_H),
                             Qt.AlignVCenter | Qt.AlignLeft, meta)

        painter.restore()

    @staticmethod
    def _progress(painter, font, fm, x, y, width, progress: int) -> None:
        """Barra fina com o % ao lado (o % lido no Kindle)."""
        progress = max(0, min(100, int(progress)))
        text = f"{progress}%"
        text_w = fm.horizontalAdvance("100%") + 4
        bar_w = max(10, width - text_w)
        bar = QRectF(x, y + (BADGE_H - PROGRESS_H) / 2, bar_w, PROGRESS_H)
        track = QPainterPath()
        track.addRoundedRect(bar, PROGRESS_H / 2, PROGRESS_H / 2)
        painter.fillPath(track, QColor(COLORS["surface_3"]))
        if progress:
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(bar.x(), bar.y(), max(PROGRESS_H, bar_w * progress / 100), PROGRESS_H),
                                PROGRESS_H / 2, PROGRESS_H / 2)
            painter.fillPath(fill, QColor(COLORS["accent"]))
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(QRectF(x + bar_w + 4, y, text_w, BADGE_H), Qt.AlignVCenter | Qt.AlignRight, text)

    @staticmethod
    def _cover_mark(painter, cover_rect: QRect, icon_name: str, color: str, left: bool = False,
                    bottom: bool = False) -> None:
        size = 22
        x = cover_rect.left() + 5 if left else cover_rect.right() - size - 5
        y = cover_rect.bottom() - size - 5 if bottom else cover_rect.top() + 5
        r = QRectF(x, y, size, size)
        path = QPainterPath()
        path.addEllipse(r)
        painter.fillPath(path, QColor(0, 0, 0, 170))
        icon = 14
        painter.drawPixmap(QRect(int(r.x() + (size - icon) / 2), int(r.y() + (size - icon) / 2), icon, icon),
                           icons.pixmap(icon_name, color, icon))

    @staticmethod
    def _badge(painter, font, rect: QRectF, text: str, bg: QColor, fg: QColor) -> None:
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        painter.fillPath(path, bg)
        painter.setFont(font)
        painter.setPen(fg)
        painter.drawText(rect, Qt.AlignCenter, text)
