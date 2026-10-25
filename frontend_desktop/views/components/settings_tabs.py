"""Blocos das Configurações que não dependem do backend: página, grupo, botão de restaurar e a aba Atalhos."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from frontend_desktop.shortcuts import GROUPS, SHORTCUTS


def settings_page() -> tuple:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(8, 16, 16, 20)
    layout.setSpacing(20)
    layout.setAlignment(Qt.AlignTop)
    return page, layout


def settings_group(title: str, description: str = "") -> tuple:
    group = QGroupBox(title)
    group.setProperty("class", "settings-group")
    layout = QVBoxLayout(group)
    layout.setSpacing(10)
    if description:
        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setProperty("class", "settings-desc")
        layout.addWidget(desc)
    return group, layout


def restore_button(on_click) -> QHBoxLayout:
    """Linha com o botão "Restaurar padrões" alinhado à direita (um por aba)."""
    row = QHBoxLayout()
    row.addStretch()
    button = QPushButton("Restaurar padrões")
    button.setProperty("class", "small-btn")
    button.setCursor(Qt.PointingHandCursor)
    button.clicked.connect(on_click)
    row.addWidget(button)
    return row


class ShortcutsTab(QWidget):
    """Configurações → Atalhos: só consulta, gerada do registro em frontend_desktop/shortcuts.py."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        page, layout = settings_page()
        outer.addWidget(page)
        self.key_labels = []
        for group_name in GROUPS:
            group, group_layout = settings_group(group_name)
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(1, 1)
            for row, item in enumerate(s for s in SHORTCUTS if s.group == group_name):
                key = QLabel(item.keys)
                key.setProperty("class", "shortcut-key")
                key.setAlignment(Qt.AlignCenter)
                key.setMinimumWidth(72)  # mesma coluna nos dois grupos
                desc = QLabel(item.description)
                desc.setProperty("class", "shortcut-desc")
                desc.setWordWrap(True)
                grid.addWidget(key, row, 0, Qt.AlignLeft)
                grid.addWidget(desc, row, 1)
                self.key_labels.append(key)
            group_layout.addLayout(grid)
            layout.addWidget(group)
