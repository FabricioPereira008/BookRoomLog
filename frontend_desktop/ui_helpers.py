"""Pequenos utilitários de UI compartilhados pelas views."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QWidget

from frontend_desktop import icons
from frontend_desktop.styles.tokens import COLORS


def repolish(widget: QWidget) -> None:
    """Reaplica o QSS depois de mudar uma propriedade dinâmica (ex.: class)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_button_icon(button: QAbstractButton, name: str, color: str = COLORS["text_muted"],
                    active_color: str = "", size: int = 16) -> None:
    button.setIcon(icons.icon(name, color, size, active_color))
    button.setIconSize(QSize(size, size))


def set_status(label: QLabel, kind: str, text: str) -> None:
    """Mostra uma mensagem de status colorida via QSS: kind em {'ok','error','muted'}."""
    label.setProperty("class", f"status-{kind}")
    label.setText(text)
    repolish(label)


def style_color_dot(label: QLabel, color: str, size: int = 12) -> None:
    """Bolinha de cor de gênero; a cor vem do dado, forma e borda vêm do QSS."""
    label.setProperty("class", "color-dot")
    label.setFixedSize(size, size)
    label.setStyleSheet(f"background-color: {color};")


def make_color_dot(color: str, size: int = 12) -> QLabel:
    dot = QLabel()
    style_color_dot(dot, color, size)
    return dot


def add_search_icon(line_edit: QLineEdit) -> None:
    """Ícone de lupa à esquerda do campo de busca (substitui o emoji no placeholder)."""
    line_edit.addAction(icons.icon("search", COLORS["text_dim"], 16), QLineEdit.LeadingPosition)
