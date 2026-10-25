"""Fila de Próximos: ordem manual (arrastar ou botões) e atalho para começar a leitura."""
import logging
from typing import List

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
    QWidget,
)

from frontend_desktop.api_client.client import api_client
from frontend_desktop.cover_loader import cover_loader
from frontend_desktop.styles.tokens import COLORS
from frontend_desktop.ui_helpers import set_button_icon, set_status
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.components.book_card_delegate import placeholder_pixmap
from frontend_desktop.workers import run_async

logger = logging.getLogger(__name__)

THUMB = (40, 60)
BookIdRole = Qt.UserRole + 10


def describe(position: int, book: dict) -> str:
    details = " · ".join(p for p in (bs.author_names(book), bs.series_text(book), bs.pages_text(book)) if p)
    return f"{position}.  {book.get('title') or 'Sem título'}" + (f"\n      {details}" if details else "")


class QueueList(QListWidget):
    """Lista reordenável por arrastar; avisa quando a ordem muda por drop."""
    order_dropped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nextQueueList")
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setIconSize(QSize(*THUMB))
        self.setSpacing(2)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.order_dropped.emit()


class NextQueueView(QWidget):
    book_selected = Signal(dict)
    queue_changed = Signal(list)   # fila completa na nova ordem (livros vindos da API)
    book_saved = Signal(dict, str)  # livro salvo, status anterior

    def __init__(self, parent=None):
        super().__init__(parent)
        self.books: List[dict] = []
        self._saving = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        hint = QLabel("Arraste os livros (ou use os botões) para definir a ordem de leitura. "
                      "O primeiro da lista é o próximo a ler. Clique duas vezes para abrir o livro.")
        hint.setWordWrap(True)
        hint.setProperty("class", "settings-desc")
        layout.addWidget(hint)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.list = QueueList()
        self.list.order_dropped.connect(self._on_dropped)
        self.list.currentRowChanged.connect(lambda *_: self._update_buttons())
        self.list.itemDoubleClicked.connect(self._open_item)
        body.addWidget(self.list, 1)

        side = QVBoxLayout()
        side.setSpacing(8)
        self.btn_top = self._button("Para o topo", "arrow-up-to-line", lambda: self.move_selected(to_top=True))
        self.btn_up = self._button("Subir", "arrow-up", lambda: self.move_selected(-1))
        self.btn_down = self._button("Descer", "arrow-down", lambda: self.move_selected(1))
        self.btn_start = self._button("Começar a ler", "book-open", self.start_selected, primary=True)
        for btn in (self.btn_top, self.btn_up, self.btn_down):
            side.addWidget(btn)
        side.addSpacing(12)
        side.addWidget(self.btn_start)
        side.addStretch()
        body.addLayout(side)
        layout.addLayout(body, 1)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        self.empty_label = QLabel("Nenhum livro na fila. Marque um livro como \"Próximo\" para ele aparecer aqui.")
        self.empty_label.setProperty("class", "empty-state-text")
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)
        cover_loader.subscribe(self._on_cover_loaded)
        self._update_buttons()

    def _button(self, text, icon, slot, primary=False) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("class", "action-btn" if primary else "small-btn")
        btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(btn, icon, COLORS["on_accent"] if primary else COLORS["text"])
        btn.clicked.connect(slot)
        return btn

    # --- dados ---
    def set_books(self, books: list) -> None:
        """Recebe a fila (qualquer ordem) e mostra pela posição."""
        self.books = sorted(books, key=lambda b: (b.get("next_position") or 10 ** 6, b.get("id") or 0))
        self._rebuild()

    def _rebuild(self, select_id=None) -> None:
        self.list.clear()
        for position, book in enumerate(self.books, 1):
            item = QListWidgetItem(describe(position, book))
            item.setData(BookIdRole, book["id"])
            item.setIcon(self._icon(book))
            item.setSizeHint(QSize(0, THUMB[1] + 10))
            self.list.addItem(item)
            if book["id"] == select_id:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self.empty_label.setVisible(not self.books)
        self.list.setVisible(bool(self.books))
        self._update_buttons()

    @staticmethod
    def _icon(book: dict) -> QIcon:
        filename = book.get("cover_image")
        pixmap = cover_loader.request(filename, *THUMB) if filename else None
        return QIcon(pixmap or placeholder_pixmap(*THUMB))

    def _on_cover_loaded(self, filename: str) -> None:
        for row, book in enumerate(self.books):
            if book.get("cover_image") == filename and row < self.list.count():
                self.list.item(row).setIcon(self._icon(book))

    def current_book(self):
        row = self.list.currentRow()
        return self.books[row] if 0 <= row < len(self.books) else None

    def _update_buttons(self) -> None:
        row = self.list.currentRow()
        has = 0 <= row < len(self.books) and not self._saving
        self.btn_top.setEnabled(has and row > 0)
        self.btn_up.setEnabled(has and row > 0)
        self.btn_down.setEnabled(has and row < len(self.books) - 1)
        self.btn_start.setEnabled(has)

    def _open_item(self, item: QListWidgetItem) -> None:
        book = next((b for b in self.books if b["id"] == item.data(BookIdRole)), None)
        if book:
            self.book_selected.emit(book)

    # --- reordenação ---
    def move_selected(self, step: int = 0, to_top: bool = False) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(self.books):
            return
        target = 0 if to_top else max(0, min(len(self.books) - 1, row + step))
        if target == row:
            return
        book = self.books.pop(row)
        self.books.insert(target, book)
        self._rebuild(select_id=book["id"])
        self._save_order(book["id"])

    def _on_dropped(self) -> None:
        by_id = {b["id"]: b for b in self.books}
        current = self.list.currentItem()
        self.books = [by_id[self.list.item(i).data(BookIdRole)] for i in range(self.list.count())]
        self._rebuild(select_id=current.data(BookIdRole) if current else None)
        self._save_order()

    def _save_order(self, select_id=None) -> None:
        self._saving = True
        self._update_buttons()
        set_status(self.status_label, "muted", "Salvando a ordem…")
        run_async(self, api_client.set_next_order, lambda books: self._on_order_saved(books, select_id),
                  self._on_order_failed, [b["id"] for b in self.books])

    def _on_order_saved(self, books: list, select_id=None) -> None:
        self._saving = False
        self.books = list(books)
        self._rebuild(select_id=select_id)
        set_status(self.status_label, "ok", "Ordem salva.")
        self.queue_changed.emit(list(books))

    def _on_order_failed(self, message: str) -> None:
        self._saving = False
        self._update_buttons()
        set_status(self.status_label, "error", f"Não foi possível salvar a ordem: {message}")

    # --- começar a ler ---
    def start_selected(self) -> None:
        book = self.current_book()
        if book is None:
            return
        self.btn_start.setEnabled(False)
        run_async(self, api_client.update_book, self._on_started,
                  lambda msg: QMessageBox.critical(self, "Erro", f"Não foi possível atualizar o livro: {msg}"),
                  book["id"], {"status": bs.LENDO})

    def _on_started(self, saved: dict) -> None:
        set_status(self.status_label, "ok", f"Boa leitura: '{saved.get('title')}' foi para Lendo.")
        self.book_saved.emit(saved, bs.PROXIMO)
