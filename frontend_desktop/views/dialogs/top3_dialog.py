"""Escolha do pódio do ano (top 3) entre os livros terminados naquele ano."""
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)

PLACES = ("1º lugar", "2º lugar", "3º lugar")


def book_option_text(book: dict) -> str:
    score = book.get("score")
    author = ", ".join(a.get("name", "") for a in book.get("authors") or [])
    text = book.get("title") or "Sem título"
    if author:
        text += f" — {author}"
    return text + (f"   (nota {score:g})" if score is not None else "")


class Top3Dialog(QDialog):
    def __init__(self, year: int, books: List[dict], current_ids: List[int], parent=None):
        super().__init__(parent)
        self.selected_ids: Optional[List[int]] = None  # None = cancelado; [] = voltar à sugestão
        self.setWindowTitle(f"Top 3 de {year}")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel(f"Os melhores livros de {year}")
        title.setProperty("class", "section-header")
        layout.addWidget(title)
        hint = QLabel("Escolha entre os livros terminados no ano. Deixe uma posição vazia se quiser menos de três.")
        hint.setWordWrap(True)
        hint.setProperty("class", "settings-desc")
        layout.addWidget(hint)

        ordered = sorted(books, key=lambda g: (g.get("score") is None, -(g.get("score") or 0), (g.get("title") or "").casefold()))
        form = QFormLayout()
        form.setSpacing(10)
        self.combos: List[QComboBox] = []
        for i, place in enumerate(PLACES):
            combo = QComboBox()
            combo.addItem("—", None)
            for g in ordered:
                combo.addItem(book_option_text(g), g["id"])
            if i < len(current_ids):
                idx = combo.findData(current_ids[i])
                combo.setCurrentIndex(max(0, idx))
            form.addRow(place, combo)
            self.combos.append(combo)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.btn_suggest = QPushButton("Usar a sugestão pela nota")
        self.btn_suggest.setProperty("class", "small-btn")
        self.btn_suggest.setCursor(Qt.PointingHandCursor)
        self.btn_suggest.clicked.connect(self.use_suggestion)
        buttons.addWidget(self.btn_suggest)
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("class", "cancel-btn")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.btn_save = QPushButton("Salvar pódio")
        self.btn_save.setProperty("class", "action-btn")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self.save)
        buttons.addWidget(self.btn_save)
        layout.addLayout(buttons)

    def chosen_ids(self) -> List[int]:
        return [c.currentData() for c in self.combos if c.currentData() is not None]

    def save(self) -> None:
        ids = self.chosen_ids()
        if len(set(ids)) != len(ids):
            QMessageBox.warning(self, "Pódio", "Um livro não pode ocupar duas posições.")
            return
        self.selected_ids = ids
        self.accept()

    def use_suggestion(self) -> None:
        self.selected_ids = []
        self.accept()
