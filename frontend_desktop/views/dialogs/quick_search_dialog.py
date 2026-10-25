"""Busca rápida (Ctrl+F): encontra qualquer livro da biblioteca pelo título ou autor e abre a edição."""
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from frontend_desktop.text_search import fold
from frontend_desktop.ui_helpers import add_search_icon
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.components.book_grid import search_text

MAX_RESULTS = 50


def search_books(books: List[dict], query: str, limit: int = MAX_RESULTS) -> List[dict]:
    """Livros com todas as palavras da busca no título, autor ou série; títulos que começam com ela vêm primeiro."""
    words = fold(query).split()
    if not words:
        return []
    needle = " ".join(words)
    hits = [b for b in books if all(w in search_text(b) for w in words)]
    hits.sort(key=lambda b: (not fold(b.get("title")).startswith(needle), fold(b.get("title")), b.get("read_number") or 1))
    return hits[:limit]


def describe(book: dict) -> str:
    extra = " · ".join(p for p in (bs.author_names(book), book.get("status"), bs.read_label(book)) if p)
    return f"{book.get('title') or 'Sem título'}" + (f"   —   {extra}" if extra else "")


class QuickSearchDialog(QDialog):
    def __init__(self, books: List[dict], parent=None):
        super().__init__(parent)
        self.books = books
        self.selected_book: Optional[dict] = None
        self.setWindowTitle("Buscar livro")
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Digite o título, autor ou série...")
        self.input.setProperty("class", "search-input")
        self.input.setClearButtonEnabled(True)
        add_search_icon(self.input)
        self.input.textChanged.connect(self.update_results)
        self.input.returnPressed.connect(self.accept_current)
        layout.addWidget(self.input)

        self.results = QListWidget()
        self.results.setObjectName("quickSearchResults")
        self.results.itemActivated.connect(lambda _item: self.accept_current())
        layout.addWidget(self.results, 1)

        self.hint = QLabel("↑ ↓ para escolher · Enter para abrir · Esc para fechar")
        self.hint.setProperty("class", "status-muted")
        layout.addWidget(self.hint)
        self.update_results("")

    def update_results(self, text: str) -> None:
        self.results.clear()
        for book in search_books(self.books, text):
            item = QListWidgetItem(describe(book))
            item.setData(Qt.UserRole, book)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
        if text.strip() and not self.results.count():
            self.hint.setText("Nenhum livro encontrado.")
        else:
            self.hint.setText("↑ ↓ para escolher · Enter para abrir · Esc para fechar")

    def keyPressEvent(self, event):
        # Setas no campo de busca movem a seleção da lista
        if event.key() in (Qt.Key_Down, Qt.Key_Up) and self.results.count():
            step = 1 if event.key() == Qt.Key_Down else -1
            row = max(0, min(self.results.count() - 1, self.results.currentRow() + step))
            self.results.setCurrentRow(row)
            return
        super().keyPressEvent(event)

    def accept_current(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        self.selected_book = item.data(Qt.UserRole)
        self.accept()
