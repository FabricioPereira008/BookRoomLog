"""Model da tabela da biblioteca (dados em memória; ordenação e filtro via proxy)."""
from typing import Callable, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from frontend_desktop.data_quality import missing_fields
from frontend_desktop.models.book_list_model import BookRole
from frontend_desktop.styles.tokens import COLORS
from frontend_desktop.views import book_status as bs

SortRole = Qt.UserRole + 2

COLUMNS = [
    "Livro", "Autor", "Status", "Gênero", "Série", "Editora", "Formato", "Págs.", "Terminado", "Nota", "Leitura",
]
COLUMN_TOOLTIPS = {7: "Número de páginas", 8: "Data de término", 10: "Nº da leitura (releituras)"}
NUMERIC_COLUMNS = {7, 9, 10}

STATUS_COLORS = {bs.LENDO: COLORS["accent_text"], bs.LIDO: COLORS["success"], bs.PROXIMO: COLORS["text"]}


def _date_br(iso: Optional[str]) -> str:
    if not iso:
        return ""
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def cell_text(book: dict, column: int) -> str:
    if column == 0:
        return book.get("title", "")
    if column == 1:
        return bs.author_names(book)
    if column == 2:
        status = book.get("status", "")
        if status == bs.LENDO and book.get("progress"):
            return f"{status} ({book['progress']}%)"
        if status == bs.PROXIMO and book.get("next_position"):
            return f"{status} (#{book['next_position']})"
        return status
    if column == 3:
        return ", ".join(g.get("name", "") for g in book.get("genres") or [])
    if column == 4:
        return bs.series_text(book)
    if column == 5:
        return (book.get("publisher") or {}).get("name", "")
    if column == 6:
        return book.get("format", "")
    if column == 7:
        return str(book.get("pages") or "")
    if column == 8:
        return _date_br(book.get("finish_date"))
    if column == 9:
        score = book.get("score")
        return f"{score:g}" if score is not None else ""
    return str(book.get("read_number") or 1)


def sort_key(book: dict, column: int):
    if column == 7:
        return book.get("pages") or 0
    if column == 8:
        return book.get("finish_date") or ""
    if column == 9:
        score = book.get("score")
        return -1 if score is None else score
    if column == 10:
        return book.get("read_number") or 1
    if column == 2:  # na ordem da leitura: Quero Ler, Próximo, Lendo, Lido
        status = book.get("status")
        return (bs.ALL_STATUSES.index(status) if status in bs.ALL_STATUSES else 99, book.get("next_position") or 0)
    if column == 4:
        return ((book.get("series") or {}).get("name", "").lower(), book.get("series_number") or 0)
    return cell_text(book, column).lower()


class BookTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._books: List[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._books)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        if orientation == Qt.Horizontal and role == Qt.ToolTipRole:
            return COLUMN_TOOLTIPS.get(section, COLUMNS[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        book = self._books[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return cell_text(book, col)
        if role == BookRole:
            return book
        if role == SortRole:
            return sort_key(book, col)
        if role == Qt.TextAlignmentRole and col in NUMERIC_COLUMNS:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and col == 2:
            color = STATUS_COLORS.get(book.get("status"))
            return QColor(color) if color else None
        if role == Qt.ToolTipRole and col == 0:
            missing = missing_fields(book)
            return book.get("title", "") + (f"\nFaltando: {', '.join(missing)}" if missing else "")
        return None

    @property
    def books(self) -> List[dict]:
        return list(self._books)

    def row_for_id(self, book_id) -> int:
        return next((r for r, b in enumerate(self._books) if b.get("id") == book_id), -1)

    def set_books(self, books: List[dict]) -> None:
        self.beginResetModel()
        self._books = list(books)
        self.endResetModel()

    def insert_book(self, book: dict, index: int = 0) -> None:
        self.beginInsertRows(QModelIndex(), index, index)
        self._books.insert(index, book)
        self.endInsertRows()

    def update_book(self, book: dict) -> bool:
        row = self.row_for_id(book.get("id"))
        if row < 0:
            return False
        self._books[row] = book
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))
        return True

    def remove_book(self, book_id) -> bool:
        row = self.row_for_id(book_id)
        if row < 0:
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._books[row]
        self.endRemoveRows()
        return True


class BookTableProxy(QSortFilterProxyModel):
    """Filtro (predicado) + ordenação numérica/textual pelas SortRole."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(SortRole)
        self._predicate: Optional[Callable[[dict], bool]] = None

    def set_predicate(self, predicate: Optional[Callable[[dict], bool]]) -> None:
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self._predicate = predicate
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._predicate = predicate
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        if self._predicate is None:
            return True
        book = self.sourceModel().index(source_row, 0, source_parent).data(BookRole)
        return bool(book) and self._predicate(book)

    def lessThan(self, left, right) -> bool:
        # As chaves podem ser tuplas (status, série): o Qt não compara tuplas vindas do Python
        return left.data(SortRole) < right.data(SortRole)

    @property
    def books(self) -> List[dict]:
        return [self.index(r, 0).data(BookRole) for r in range(self.rowCount())]
