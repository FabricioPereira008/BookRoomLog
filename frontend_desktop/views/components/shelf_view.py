"""Estante: o que está sendo lido em destaque e faixas com a fila de próximos, a lista de desejos e os lidos."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from frontend_desktop import icons
from frontend_desktop.styles.tokens import COLORS
from frontend_desktop.ui_helpers import add_search_icon
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.components.book_grid import (
    BookGrid, CardSizeSelector, FILTER_DEBOUNCE_MS, MODE_FULL, MODE_STRIP, make_predicate,
)

RECENT_READ_LIMIT = 20  # a faixa de lidos mostra só os mais recentes ("Ver todos" abre a lista completa)


def next_queue(books: list) -> list:
    """Livros Próximo na ordem da fila."""
    return sorted(bs.filter_books(bs.PROXIMO, books), key=lambda b: (b.get("next_position") or 10 ** 6, b.get("id") or 0))


def recently_read(books: list, limit: int = RECENT_READ_LIMIT) -> list:
    done = bs.filter_books(bs.LIDO, books)
    done.sort(key=lambda b: (b.get("finish_date") or "", b.get("id") or 0), reverse=True)
    return done[:limit] if limit else done


class ShelfView(QWidget):
    book_selected = Signal(dict)
    view_all_requested = Signal(str)  # status da lista para abrir a página completa

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("shelfView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(FILTER_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.apply_filter)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar na estante por título, autor ou série...")
        add_search_icon(self.search_input)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setProperty("class", "search-input")
        self.search_input.textChanged.connect(self.on_search_changed)
        top_bar.addWidget(self.search_input)
        top_bar.addWidget(CardSizeSelector())
        main_layout.addLayout(top_bar)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("shelfScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("shelfScrollContainer")
        container.setAttribute(Qt.WA_StyledBackground, True)
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(12)

        self._counts, self._arrows, self._sections = {}, {}, []
        # Destaque: o que está sendo lido, sempre com cards grandes
        self.grid_reading, self.sec_reading = self._create_section(
            "Lendo agora", "readingSection", MODE_FULL, size_mode="large")
        self.grid_next, self.sec_next = self._create_section(
            "Próximos", "nextSection", MODE_STRIP, bs.PROXIMO, "Organizar fila")
        self.grid_want, self.sec_want = self._create_section("Quero ler", "wantSection", MODE_STRIP, bs.QUERO_LER)
        self.grid_read, self.sec_read = self._create_section("Lidos recentemente", "readSection", MODE_STRIP, bs.LIDO)
        self.container_layout.addStretch()

        self.empty_label = QLabel("Sua estante está vazia. Use \"Adicionar livro\" (Ctrl+N) para começar.")
        self.empty_label.setProperty("class", "empty-state-text")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)
        self.container_layout.insertWidget(0, self.empty_label)

        self.scroll.setWidget(container)
        main_layout.addWidget(self.scroll)

    def _create_section(self, title, object_name, mode, list_key=None, link_text="Ver todos", size_mode=None):
        """Seção com cabeçalho (título, contagem, setas da faixa e link) e a grade."""
        section = QFrame()
        section.setObjectName(object_name)
        section.setProperty("class", "section-card")
        section.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header = QLabel(title)
        header.setProperty("class", "section-header")
        header_row.addWidget(header)
        count = QLabel("")
        count.setProperty("class", "section-count")
        header_row.addWidget(count)
        header_row.addStretch()

        grid = BookGrid(mode=mode, size_mode=size_mode)
        arrows = []
        if mode == MODE_STRIP:
            for icon, direction, tip in (("chevron-left", -1, "Anteriores"), ("chevron-right", 1, "Próximos")):
                btn = QToolButton()
                btn.setIcon(icons.icon(icon, COLORS["text"]))
                btn.setToolTip(tip)
                btn.setProperty("class", "strip-arrow")
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _c=False, g=grid, d=direction: g.scroll_strip(d))
                header_row.addWidget(btn)
                arrows.append(btn)
            bar = grid.view.horizontalScrollBar()
            update = lambda *_a, g=grid, arr=arrows: self._update_arrows(g, arr)
            bar.rangeChanged.connect(update)
            bar.valueChanged.connect(update)
        if list_key:
            btn_all = QPushButton(link_text)
            btn_all.setProperty("class", "link-btn")
            btn_all.setCursor(Qt.PointingHandCursor)
            btn_all.clicked.connect(lambda _c=False, k=list_key: self.view_all_requested.emit(k))
            header_row.addWidget(btn_all)
        layout.addLayout(header_row)
        layout.addWidget(grid)
        self.container_layout.addWidget(section)

        grid.book_selected.connect(self.book_selected.emit)
        self._counts[grid] = count
        self._arrows[grid] = arrows
        self._sections.append((grid, section))
        return grid, section

    def sections(self):
        return list(self._sections)

    @staticmethod
    def _update_arrows(grid, arrows):
        bar = grid.view.horizontalScrollBar()
        overflow = bar.maximum() > 0
        for btn in arrows:
            btn.setVisible(overflow)
        if arrows:
            arrows[0].setEnabled(bar.value() > bar.minimum())
            arrows[1].setEnabled(bar.value() < bar.maximum())

    def _sync_visibility(self):
        """Mostra apenas as seções que têm livros após a busca, com a contagem no cabeçalho."""
        any_books = False
        for grid, sec in self._sections:
            total = grid.proxy.rowCount()
            any_books = any_books or grid.model.rowCount() > 0
            sec.setVisible(total > 0)
            self._counts[grid].setText(str(total) if total else "")
            self._update_arrows(grid, self._arrows[grid])
        self.empty_label.setVisible(not any_books)

    # --- dados ---
    def set_books(self, books: list):
        """Distribui a biblioteca inteira pelas seções."""
        self.grid_reading.set_books(bs.filter_books(bs.LENDO, books))
        self.grid_next.set_books(next_queue(books))
        self.grid_want.set_books(bs.filter_books(bs.QUERO_LER, books))
        self.grid_read.set_books(recently_read(books))
        self.apply_filter()

    def grid_for_status(self, status: str):
        return {bs.LENDO: self.grid_reading, bs.PROXIMO: self.grid_next,
                bs.QUERO_LER: self.grid_want, bs.LIDO: self.grid_read}.get(status)

    def update_book(self, book: dict) -> bool:
        """Atualiza o livro in-place em qualquer seção em que ele esteja."""
        updated = False
        for grid, _ in self._sections:
            updated = grid.update_book(book) or updated
        return updated

    def remove_book(self, book_id: int) -> bool:
        removed = False
        for grid, _ in self._sections:
            removed = grid.remove_book(book_id) or removed
        self._sync_visibility()
        return removed

    def insert_book_by_status(self, book: dict):
        """Insere o livro no topo da seção do seu status (Próximo entra na posição da fila)."""
        grid = self.grid_for_status(book.get("status"))
        if grid is None:
            return
        index = 0
        if book.get("status") == bs.PROXIMO:
            index = sum(1 for b in grid.model.books if (b.get("next_position") or 0) < (book.get("next_position") or 0))
        grid.insert_book(index, book)
        self._sync_visibility()

    # --- busca ---
    def on_search_changed(self, text: str):
        if self.search_input.hasFocus():
            self._debounce.start()
        else:
            self.apply_filter()

    def clear_filters(self):
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.apply_filter()

    def apply_filter(self):
        self._debounce.stop()
        predicate = make_predicate(self.search_input.text())
        for grid, _ in self._sections:
            grid.set_predicate(predicate)
        self._sync_visibility()
