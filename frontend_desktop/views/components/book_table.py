from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QTableView, QVBoxLayout, QWidget
)

from frontend_desktop import preferences
from frontend_desktop.models.book_list_model import BookRole
from frontend_desktop.models.book_table_model import COLUMN_TOOLTIPS, COLUMNS, BookTableModel, BookTableProxy
from frontend_desktop.text_search import fold
from frontend_desktop.ui_helpers import add_search_icon
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.components.book_grid import make_predicate

# A coluna 0 (título) ocupa o espaço que sobrar; as demais têm largura inicial ajustável
COLUMN_WIDTHS = {1: 170, 2: 110, 3: 150, 4: 140, 5: 130, 6: 120, 7: 60, 8: 104, 9: 52, 10: 64}
HIDDEN_COLUMNS_KEY = "table_hidden_columns"
DEFAULT_HIDDEN_COLUMNS = {5, 10}  # "Editora", "Leitura"
ALL = "__all__"


class BookTable(QWidget):
    """Biblioteca em tabela virtualizada (QTableView), ordenável por coluna."""
    book_selected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = BookTableModel(self)
        self.proxy = BookTableProxy(self)
        self.proxy.setSourceModel(self.model)
        self.init_ui()
        for signal in (self.proxy.rowsInserted, self.proxy.rowsRemoved, self.proxy.modelReset, self.proxy.layoutChanged):
            signal.connect(self.update_count_label)

    @property
    def books(self) -> list:
        return self.model.books

    @property
    def filtered_books(self) -> list:
        return self.proxy.books

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filtrar por título, autor ou série...")
        add_search_icon(self.search_input)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setProperty("class", "search-input")
        self.search_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos os status", ALL)
        for status in bs.ALL_STATUSES:
            self.status_filter.addItem(status, status)
        self.status_filter.currentIndexChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.status_filter)

        self.genre_filter = QComboBox()
        self.genre_filter.addItem("Todos os gêneros", ALL)
        self.genre_filter.currentIndexChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.genre_filter)

        self.format_filter = QComboBox()
        self.format_filter.addItem("Todos os formatos", ALL)
        for fmt in bs.FORMATS:
            self.format_filter.addItem(fmt, fmt)
        self.format_filter.currentIndexChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.format_filter)

        self.count_label = QLabel("0 livros")
        self.count_label.setProperty("class", "card-meta")
        filter_layout.addWidget(self.count_label)
        layout.addLayout(filter_layout)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setCursor(Qt.PointingHandCursor)

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setStretchLastSection(False)
        for col in range(self.model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            self.table.setColumnWidth(col, COLUMN_WIDTHS.get(col, 100))
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setMinimumSectionSize(44)
        header.setSortIndicatorShown(True)
        # Clique direito no cabeçalho: mostrar/esconder colunas (lembrado entre sessões)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_columns_menu)
        for col in self.hidden_columns():
            self.table.setColumnHidden(col, True)

        self.table.doubleClicked.connect(self.on_row_activated)
        self.table.activated.connect(self.on_row_activated)
        layout.addWidget(self.table)

    # --- colunas ---
    @staticmethod
    def hidden_columns() -> set:
        raw = preferences.settings().value(HIDDEN_COLUMNS_KEY, None)
        if raw is None:
            return set(DEFAULT_HIDDEN_COLUMNS)
        if isinstance(raw, str):
            raw = [raw] if raw else []
        return {int(c) for c in raw if str(c).isdigit() and 0 < int(c) < len(COLUMNS)}

    def set_column_visible(self, column: int, visible: bool) -> None:
        if column == 0:
            return  # o título sempre aparece
        self.table.setColumnHidden(column, not visible)
        hidden = sorted(c for c in range(1, len(COLUMNS)) if self.table.isColumnHidden(c))
        preferences.settings().setValue(HIDDEN_COLUMNS_KEY, [str(c) for c in hidden] or "")

    def build_columns_menu(self) -> QMenu:
        menu = QMenu(self)
        for col, name in enumerate(COLUMNS):
            if col == 0:
                continue
            action = menu.addAction(COLUMN_TOOLTIPS.get(col, name))
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(col))
            action.toggled.connect(lambda checked, c=col: self.set_column_visible(c, checked))
        return menu

    def show_columns_menu(self, pos) -> None:
        self.build_columns_menu().exec(self.table.horizontalHeader().mapToGlobal(pos))

    # --- dados ---
    def set_books(self, books: list):
        self.model.set_books(books)
        self._refresh_genre_options()
        self.apply_filter()

    def insert_book(self, book: dict):
        self.model.insert_book(book, 0)
        self._refresh_genre_options()

    def update_book(self, book: dict) -> bool:
        updated = self.model.update_book(book)
        self._refresh_genre_options()
        return updated

    def remove_book(self, book_id: int) -> bool:
        return self.model.remove_book(book_id)

    def _refresh_genre_options(self) -> None:
        """Gêneros presentes na biblioteca (mantém a escolha atual se ela continuar existindo)."""
        names = sorted({g["name"] for b in self.model.books for g in b.get("genres") or [] if g.get("name")},
                       key=fold)
        current = self.genre_filter.currentData()
        existing = [self.genre_filter.itemData(i) for i in range(1, self.genre_filter.count())]
        if existing == names:
            return
        self.genre_filter.blockSignals(True)
        self.genre_filter.clear()
        self.genre_filter.addItem("Todos os gêneros", ALL)
        for name in names:
            self.genre_filter.addItem(name, name)
        self.genre_filter.setCurrentIndex(max(0, self.genre_filter.findData(current)))
        self.genre_filter.blockSignals(False)

    # --- filtro ---
    def apply_filter(self, *_):
        search = make_predicate(self.search_input.text())
        status, genre, fmt = (c.currentData() for c in (self.status_filter, self.genre_filter, self.format_filter))

        def predicate(book: dict) -> bool:
            if status != ALL and book.get("status") != status:
                return False
            if genre != ALL and genre not in {g.get("name") for g in book.get("genres") or []}:
                return False
            if fmt != ALL and book.get("format") != fmt:
                return False
            return search(book)

        self.proxy.set_predicate(predicate)
        self.update_count_label()

    def update_count_label(self, *_):
        total = self.proxy.rowCount()
        self.count_label.setText(f"{total} {'livro' if total == 1 else 'livros'}")

    def on_row_activated(self, index: QModelIndex):
        book = index.sibling(index.row(), 0).data(BookRole)
        if book:
            self.book_selected.emit(book)
