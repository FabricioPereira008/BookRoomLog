"""Grades de livros baseadas em model/view: cards pintados por delegate, filtro sem recriar widgets."""
import math
from dataclasses import dataclass

import shiboken6
from typing import Callable, List, Optional

from PySide6.QtCore import QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListView, QPushButton, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget
)

from frontend_desktop import preferences
from frontend_desktop.cover_loader import cover_loader
from frontend_desktop.text_search import fold, fold_query
from frontend_desktop.models.book_list_model import BookFilterProxy, BookListModel, BookRole
from frontend_desktop.ui_helpers import add_search_icon
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.components.book_card_delegate import BookCardDelegate, current_size_mode

GRID_SPACING = 12
FILTER_DEBOUNCE_MS = 150
MODE_INFINITE = "infinite"  # preenche a área e rola sozinho (listas de status)
MODE_BUTTON = "button"      # altura limitada em linhas + botão "Mostrar mais"
MODE_FULL = "full"          # mostra todas as linhas, sem rolagem própria (ex.: Anuário)
MODE_STRIP = "strip"        # uma linha só, rolando na horizontal (faixas da Estante)


class BookListView(QListView):
    """QListView em modo ícones, com tamanhos uniformes e hover; pode ceder a rolagem ao pai."""
    book_clicked = Signal(dict)

    def __init__(self, scrolls: bool = True, strip: bool = False, parent=None):
        super().__init__(parent)
        self._scrolls = scrolls
        self._strip = strip
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setWrapping(not strip)
        self.setFlow(QListView.LeftToRight)
        self.setUniformItemSizes(True)
        self.setSpacing(GRID_SPACING)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setFrameShape(QListView.NoFrame)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(28)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if not scrolls:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._emit_book)
        self.activated.connect(self._emit_book)

    def _emit_book(self, index: QModelIndex):
        book = index.data(BookRole)
        if book:
            self.book_clicked.emit(book)

    def wheelEvent(self, event):
        if self._strip:
            # Faixa: rolagem horizontal (trackpad ou Shift+roda); a roda comum continua rolando a página
            delta = event.angleDelta()
            step = delta.x() or (delta.y() if event.modifiers() & Qt.ShiftModifier else 0)
            if step:
                bar = self.horizontalScrollBar()
                bar.setValue(bar.value() - step)
                event.accept()
                return
            event.ignore()
        elif self._scrolls:
            super().wheelEvent(event)
        else:
            event.ignore()  # o QScrollArea pai rola


class BookGrid(QWidget):
    """Lista de cards. A fonte de dados completa fica em `model`; `proxy` aplica o filtro."""
    book_selected = Signal(dict)

    def __init__(self, mode: str = MODE_INFINITE, initial_rows: int = 2, parent=None, size_mode: Optional[str] = None):
        super().__init__(parent)
        self.mode = mode
        self._fixed_size = size_mode  # ex.: "large" nos destaques; None segue a preferência do usuário
        self._rows_step = max(1, initial_rows)
        self._visible_rows = self._rows_step

        self.model = BookListModel(self)
        self.proxy = BookFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.delegate = BookCardDelegate(size_mode, parent=self)
        self.view = BookListView(scrolls=(mode == MODE_INFINITE), strip=(mode == MODE_STRIP), parent=self)
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(self.delegate)
        self.view.book_clicked.connect(self.book_selected.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.view)

        self.empty_label = QLabel("Nenhum livro encontrado.")
        self.empty_label.setProperty("class", "empty-state-text")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.more_button = QPushButton("Mostrar mais")
        self.more_button.setProperty("class", "small-btn")
        self.more_button.setCursor(Qt.PointingHandCursor)
        self.more_button.clicked.connect(self.load_more_cards)
        self.more_button.setVisible(False)
        layout.addWidget(self.more_button, alignment=Qt.AlignLeft)

        if mode != MODE_INFINITE:
            self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.proxy.rowsInserted.connect(self._schedule_height_update)
            self.proxy.rowsRemoved.connect(self._schedule_height_update)
            self.proxy.modelReset.connect(self._schedule_height_update)
            self.proxy.layoutChanged.connect(self._schedule_height_update)

        for signal in (self.proxy.rowsInserted, self.proxy.rowsRemoved, self.proxy.modelReset, self.proxy.layoutChanged):
            signal.connect(self._update_empty_state)
        cover_loader.subscribe(self._on_cover_loaded)
        preferences.subscribe_card_size(self._on_card_size_changed)

    def _on_card_size_changed(self, size: str) -> None:
        if self._fixed_size is None and self.delegate.set_size_mode(size):
            self._apply_grid_size()
            self.view.scheduleDelayedItemsLayout()
            self._update_height()

    def _apply_grid_size(self) -> None:
        """Distribui a sobra de largura entre as colunas (sem faixa vazia à direita)."""
        if self.mode == MODE_STRIP:
            return
        m = self.delegate.metrics
        width = self.view.viewport().width() or self.width()
        cols = self._columns()
        cell_w = max(m.card_width + GRID_SPACING, (width - GRID_SPACING) // cols)
        size = QSize(cell_w, m.card_height + GRID_SPACING)
        if self.view.gridSize() != size:
            self.view.setGridSize(size)

    def _update_empty_state(self, *args) -> None:
        """Mensagem amigável quando a lista (ou o resultado da busca) está vazia; seções da Estante somem sozinhas."""
        self.empty_label.setVisible(self.mode != MODE_BUTTON and self.proxy.rowCount() == 0)

    # --- dados ---
    @property
    def books(self) -> List[dict]:
        """Livros que passam no filtro atual (ordem exibida)."""
        return self.proxy.books

    @property
    def rendered_count(self) -> int:
        """Quantos cards estão visíveis (em MODE_BUTTON, limitado pelas linhas abertas)."""
        total = self.proxy.rowCount()
        if self.mode == MODE_BUTTON:
            return min(total, self._columns() * self._visible_rows)
        return total

    def set_predicate(self, predicate: Optional[Callable[[dict], bool]]) -> None:
        self.proxy.set_predicate(predicate)
        self._update_height()

    def set_books(self, books: list) -> None:
        if self.delegate.set_size_mode(self._fixed_size or current_size_mode()):
            self._apply_grid_size()
            self.view.scheduleDelayedItemsLayout()
        self._visible_rows = self._rows_step
        self.model.set_books(books)
        self._update_height()

    def insert_book(self, index: int, book: dict) -> None:
        self.model.insert_book(index, book)

    def update_book(self, book: dict) -> bool:
        return self.model.update_book(book)

    def remove_book(self, book_id: int) -> bool:
        return self.model.remove_book(book_id)

    # --- layout ---
    def _columns(self) -> int:
        cell = self.delegate.metrics.card_width + GRID_SPACING
        width = self.view.viewport().width() or self.width()
        return max(1, (width - GRID_SPACING) // cell)

    def _total_rows(self) -> int:
        return math.ceil(self.proxy.rowCount() / self._columns()) if self.proxy.rowCount() else 0

    def _schedule_height_update(self, *args) -> None:
        QTimer.singleShot(0, self, self._update_height)  # com contexto: cancelado se a grade for destruída

    def _update_height(self) -> None:
        """Em modos sem rolagem própria, ajusta a altura da lista ao número de linhas exibidas."""
        if self.mode == MODE_INFINITE or not shiboken6.isValid(self.proxy):
            return
        if self.mode == MODE_STRIP:
            has = self.proxy.rowCount() > 0
            self.view.setFixedHeight(self.delegate.metrics.card_height + 2 * GRID_SPACING if has else 0)
            return
        total_rows = self._total_rows()
        rows = min(total_rows, self._visible_rows) if self.mode == MODE_BUTTON else total_rows
        height = rows * (self.delegate.metrics.card_height + GRID_SPACING) + GRID_SPACING if rows else 0
        self.view.setFixedHeight(height)
        hidden = self.proxy.rowCount() - self.rendered_count
        self.more_button.setVisible(self.mode == MODE_BUTTON and hidden > 0)
        if hidden > 0:
            self.more_button.setText(f"Mostrar mais ({hidden})")

    def load_more_cards(self) -> None:
        """Abre mais linhas (MODE_BUTTON). Nos demais modos a lista já mostra tudo."""
        if self.mode == MODE_BUTTON:
            self._visible_rows += self._rows_step
            self._update_height()

    def _on_cover_loaded(self, filename: str) -> None:
        self.view.viewport().update()

    def scroll_strip(self, direction: int) -> None:
        """Faixa: avança/volta quase uma tela de cards."""
        bar = self.view.horizontalScrollBar()
        bar.setValue(bar.value() + direction * int(self.view.viewport().width() * 0.8))

    def strip_overflows(self) -> bool:
        return self.mode == MODE_STRIP and self.view.horizontalScrollBar().maximum() > 0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_grid_size()
        self._update_height()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_grid_size()
        self._update_height()


class CardSizeSelector(QWidget):
    """Seletor rápido P/M/G do tamanho dos cards; fica em sincronia com as demais telas."""
    LABELS = (("small", "P", "Cards pequenos"), ("medium", "M", "Cards médios"), ("large", "G", "Cards grandes"))

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for i, (size, text, tip) in enumerate(self.LABELS):
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("class", "segmented-btn segmented-" + ("first" if i == 0 else "last" if i == 2 else "mid"))
            self.group.addButton(btn)
            self.buttons[size] = btn
            layout.addWidget(btn)
            btn.clicked.connect(lambda _checked=False, s=size: preferences.set_card_size(s))
        self._sync(preferences.card_size())
        preferences.subscribe_card_size(self._sync)

    def _sync(self, size: str) -> None:
        btn = self.buttons.get(size)
        if btn and not btn.isChecked():
            btn.setChecked(True)


@dataclass(frozen=True)
class SortCriterion:
    label: str
    key: Optional[Callable[[dict], object]]  # None = ordem em que a lista chegou
    descending: bool = False                 # direção inicial
    asc_label: str = "A→Z"
    desc_label: str = "Z→A"

    def direction_label(self, descending: bool) -> str:
        return self.desc_label if descending else self.asc_label


def _score(book: dict):
    return book.get("score")


SORT_CRITERIA = {
    "added": SortCriterion("Adicionados", lambda b: b.get("created_at") or "", True, "Antigos", "Recentes"),
    "title": SortCriterion("Título", lambda b: fold(b.get("title"))),
    "author": SortCriterion("Autor", lambda b: fold(bs.main_author(b)) or None),
    "series": SortCriterion("Série", lambda b: (fold((b.get("series") or {}).get("name")), b.get("series_number") or 0)
                            if b.get("series") else None),
    "pages": SortCriterion("Páginas", lambda b: b.get("pages") or None, False, "Menos", "Mais"),
    "finished": SortCriterion("Data de término", lambda b: b.get("finish_date") or None, True, "Antigos", "Recentes"),
    "score": SortCriterion("Nota", _score, True, "Menor", "Maior"),
}


class ScrollableBookGrid(QWidget):
    """Grade com busca, ordenação e rolagem nativa. A busca digitada usa debounce."""
    book_selected = Signal(dict)

    def __init__(self, sorts=("added", "title", "author", "pages"), parent=None):
        super().__init__(parent)
        self.setObjectName("scrollableBookGridWrapper")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.sorts = tuple(sorts)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por título, autor ou série...")
        add_search_icon(self.search_input)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setProperty("class", "search-input")
        self.search_input.textChanged.connect(self.on_search_changed)
        top_bar_layout.addWidget(self.search_input)

        self.sort_combo = QComboBox()
        self.sort_combo.setProperty("class", "filter-combo")
        for key in self.sorts:
            self.sort_combo.addItem(f"Ordenar: {SORT_CRITERIA[key].label}", key)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_key_changed)
        top_bar_layout.addWidget(self.sort_combo)

        self.sort_dir_btn = QPushButton("A→Z")
        self.sort_dir_btn.setProperty("class", "small-btn")
        self.sort_dir_btn.setCheckable(True)
        self.sort_dir_btn.setCursor(Qt.PointingHandCursor)
        self.sort_dir_btn.setToolTip("Alternar direção da ordenação")
        self.sort_dir_btn.toggled.connect(self._apply_sort)
        top_bar_layout.addWidget(self.sort_dir_btn)

        self.size_selector = CardSizeSelector()
        top_bar_layout.addWidget(self.size_selector)
        main_layout.addLayout(top_bar_layout)

        self.grid = BookGrid(mode=MODE_INFINITE)
        self.grid.book_selected.connect(self.book_selected.emit)
        main_layout.addWidget(self.grid)

        # Debounce: só para digitação do usuário (campo com foco); setText programático aplica na hora
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(FILTER_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.apply_filter)
        self._on_sort_key_changed()

    # --- dados ---
    @property
    def all_books_source(self) -> List[dict]:
        """Lista completa (sem filtro)."""
        return self.grid.model.books

    def set_books(self, books: list) -> None:
        self.grid.set_books(books)
        self.apply_filter()

    def update_book(self, book: dict) -> bool:
        return self.grid.update_book(book)

    def remove_book(self, book_id: int) -> bool:
        return self.grid.remove_book(book_id)

    def insert_book(self, index: int, book: dict) -> None:
        self.grid.insert_book(index, book)

    # --- ordenação ---
    def _set_direction(self, descending: bool) -> None:
        self.sort_dir_btn.blockSignals(True)
        self.sort_dir_btn.setChecked(descending)
        self.sort_dir_btn.blockSignals(False)

    def _on_sort_key_changed(self, *args) -> None:
        key = self.sort_combo.currentData()
        if key is None:
            return
        self._set_direction(SORT_CRITERIA[key].descending)  # cada critério tem sua direção inicial
        self._apply_sort()

    def _apply_sort(self, *args) -> None:
        key = self.sort_combo.currentData()
        if key is None:
            return
        criterion = SORT_CRITERIA[key]
        descending = self.sort_dir_btn.isChecked()
        self.sort_dir_btn.setText(criterion.direction_label(descending))
        self.grid.proxy.set_sort(criterion.key, descending)

    # --- busca ---
    def on_search_changed(self, text: str) -> None:
        if self.search_input.hasFocus():
            self._debounce.start()
        else:
            self.apply_filter()

    def clear_filters(self) -> None:
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.apply_filter()

    def apply_filter(self) -> None:
        self._debounce.stop()
        self.grid.set_predicate(make_predicate(self.search_input.text()))


def search_text(book: dict) -> str:
    """Texto pesquisável do livro: título, autores e série."""
    return fold(" ".join((book.get("title") or "", bs.author_names(book), bs.series_text(book))))


def make_predicate(query: str) -> Callable[[dict], bool]:
    """Predicado de busca: todas as palavras precisam aparecer no título, autores ou série."""
    words = fold_query(query).split()

    def predicate(book: dict) -> bool:
        if not words:
            return True
        haystack = search_text(book)
        return all(w in haystack for w in words)

    return predicate
