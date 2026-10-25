"""Gráficos simples do Anuário, pintados com QPainter.

Uma série por gráfico, em uma só cor (o destaque do tema): barras finas com a ponta arredondada (4px) e a base
reta, eixo discreto, texto nas cores de texto e um tooltip por barra ao passar o mouse.
"""
from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from frontend_desktop.styles.tokens import COLORS

BAR_RADIUS = 4
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _bar_path(rect: QRectF, vertical: bool) -> QPainterPath:
    """Barra com só a ponta arredondada (a base fica reta, ancorada no eixo)."""
    r = min(BAR_RADIUS, rect.width() / 2, rect.height() / 2)
    path = QPainterPath()
    if vertical:  # ponta em cima
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + r)
        path.quadTo(rect.left(), rect.top(), rect.left() + r, rect.top())
        path.lineTo(rect.right() - r, rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r)
        path.lineTo(rect.right(), rect.bottom())
    else:  # ponta à direita
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right() - r, rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r)
        path.lineTo(rect.right(), rect.bottom() - r)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - r, rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
    path.closeSubpath()
    return path


class _HoverChart(QWidget):
    """Base: guarda os retângulos de acerto de cada barra e mostra o tooltip da barra sob o mouse."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._hits: List[tuple] = []  # (QRectF, índice)
        self.hover_index: Optional[int] = None

    def tooltip_for(self, index: int) -> str:
        raise NotImplementedError

    def index_at(self, pos) -> Optional[int]:
        for rect, index in self._hits:
            if rect.contains(pos):
                return index
        return None

    def mouseMoveEvent(self, event):
        index = self.index_at(event.position())
        if index != self.hover_index:
            self.hover_index = index
            self.update()
        if index is None:
            QToolTip.hideText()
        else:
            QToolTip.showText(event.globalPosition().toPoint() + QPoint(12, 12), self.tooltip_for(index), self)

    def leaveEvent(self, event):
        self.hover_index = None
        self.update()
        super().leaveEvent(event)

    def _bar_color(self, index: int) -> QColor:
        color = QColor(COLORS["accent"])
        if self.hover_index is not None and self.hover_index != index:
            color.setAlpha(150)  # destaca a barra sob o mouse
        return color


class MonthlyBarChart(_HoverChart):
    """Barras verticais por mês (jan..dez)."""

    def __init__(self, unit=("livro lido", "livros lidos"), empty_text="Sem datas de término neste ano", parent=None):
        super().__init__(parent)
        self.unit = unit
        self.empty_text = empty_text
        self.values: List[int] = [0] * 12
        self.year: Optional[int] = None
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, values: List[int], year: Optional[int] = None) -> None:
        values = list(values or [])[:12]
        self.values = values + [0] * (12 - len(values))
        self.year = year
        self.update()

    def sizeHint(self):
        return QSize(520, 190)

    def tooltip_for(self, index: int) -> str:
        n = self.values[index]
        month = MONTHS[index] + (f"/{self.year}" if self.year else "")
        return f"{month}: {n} {self.unit[0] if n == 1 else self.unit[1]}"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        small = QFont(self.font())
        small.setPixelSize(11)
        fm = QFontMetrics(small)
        p.setFont(small)
        top, bottom_pad = 18, fm.height() + 8
        area = QRectF(4, top, self.width() - 8, self.height() - top - bottom_pad)
        peak = max(self.values) if any(self.values) else 0
        slot = area.width() / 12
        bar_w = min(28.0, slot * 0.56)
        self._hits = []
        # eixo (base) discreto
        p.setPen(QColor(COLORS["border_strong"]))
        p.drawLine(int(area.left()), int(area.bottom()), int(area.right()), int(area.bottom()))
        for i, value in enumerate(self.values):
            cx = area.left() + slot * i + slot / 2
            if value and peak:
                h = max(3.0, area.height() * value / peak)
                rect = QRectF(cx - bar_w / 2, area.bottom() - h, bar_w, h)
                p.fillPath(_bar_path(rect, vertical=True), self._bar_color(i))
                # rótulo direto só nas barras com valor (é pouco texto: no máximo 12 números)
                p.setPen(QColor(COLORS["text_muted"]))
                p.drawText(QRectF(cx - slot / 2, rect.top() - fm.height() - 2, slot, fm.height()), Qt.AlignCenter, str(value))
            self._hits.append((QRectF(cx - slot / 2, area.top(), slot, area.height()), i))
            p.setPen(QColor(COLORS["text_dim"]))
            p.drawText(QRectF(cx - slot / 2, area.bottom() + 4, slot, fm.height()), Qt.AlignCenter, MONTHS[i])
        if not peak:
            p.setPen(QColor(COLORS["text_dim"]))
            p.drawText(area, Qt.AlignCenter, self.empty_text)
        p.end()


@dataclass
class BarRow:
    label: str
    value: float
    tooltip: str = ""
    dot_color: Optional[str] = None  # identidade (ex.: cor do gênero) ao lado do nome


class HorizontalBarChart(_HoverChart):
    """Ranking em barras horizontais: nome à esquerda, barra e valor à direita."""
    ROW_H = 26

    def __init__(self, value_format: Callable[[float], str] = lambda v: f"{v:g}", max_rows: int = 8, parent=None):
        super().__init__(parent)
        self.value_format = value_format
        self.max_rows = max_rows
        self.rows: List[BarRow] = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._resize_for_rows()

    def set_rows(self, rows: List[BarRow]) -> None:
        self.rows = list(rows)[: self.max_rows]
        self._resize_for_rows()
        self.update()

    def _resize_for_rows(self):
        self.setFixedHeight(max(1, len(self.rows)) * self.ROW_H + 8)

    def tooltip_for(self, index: int) -> str:
        row = self.rows[index]
        return row.tooltip or f"{row.label}: {self.value_format(row.value)}"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(12)
        fm = QFontMetrics(font)
        p.setFont(font)
        self._hits = []
        if not self.rows:
            p.setPen(QColor(COLORS["text_dim"]))
            p.drawText(self.rect(), Qt.AlignCenter, "Sem dados neste ano")
            p.end()
            return
        label_w = min(170, max(fm.horizontalAdvance(r.label) for r in self.rows) + 22)
        value_w = max(fm.horizontalAdvance(self.value_format(r.value)) for r in self.rows) + 10
        bar_x = label_w + 8
        bar_max = max(10.0, self.width() - bar_x - value_w - 4)
        peak = max(r.value for r in self.rows) or 1
        for i, row in enumerate(self.rows):
            y = 4 + i * self.ROW_H
            text_x = 0
            if row.dot_color:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(row.dot_color))
                p.drawEllipse(QRectF(2, y + self.ROW_H / 2 - 4, 8, 8))
                text_x = 16
            p.setPen(QColor(COLORS["text"]))
            label = fm.elidedText(row.label, Qt.ElideRight, int(label_w - text_x))
            p.drawText(QRectF(text_x, y, label_w - text_x, self.ROW_H), Qt.AlignVCenter | Qt.AlignLeft, label)
            w = max(3.0, bar_max * row.value / peak) if row.value else 0.0
            bar = QRectF(bar_x, y + 6, w, self.ROW_H - 12)
            if w:
                p.fillPath(_bar_path(bar, vertical=False), self._bar_color(i))
            p.setPen(QColor(COLORS["text_muted"]))
            p.drawText(QRectF(bar_x + w + 6, y, value_w, self.ROW_H), Qt.AlignVCenter | Qt.AlignLeft,
                       self.value_format(row.value))
            self._hits.append((QRectF(0, y, self.width(), self.ROW_H), i))
        p.end()
