"""Model/proxy de livros: dados em memória, filtragem sem recriar widgets."""
from typing import Callable, List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt

from frontend_desktop.cover_loader import cover_loader
from frontend_desktop.data_quality import missing_fields
from frontend_desktop.text_search import fold
from frontend_desktop.views import book_status as bs

BookRole = Qt.UserRole + 1


class BookListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._books: List[dict] = []

    # --- leitura ---
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._books)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._books)):
            return None
        book = self._books[index.row()]
        if role == BookRole:
            return book
        if role == Qt.DisplayRole:
            return book.get("title") or ""
        if role == Qt.ToolTipRole:  # título, autores e série completos, que podem estar elididos no card
            genres = " · ".join(g["name"] for g in book.get("genres") or [] if g.get("name"))
            details = [bs.author_names(book), bs.series_text(book), genres, bs.pages_text(book), bs.read_label(book)]
            lines = [book.get("title") or ""] + [d for d in details if d]
            missing = missing_fields(book)
            if missing:
                lines.append("Faltando: " + ", ".join(missing))
            return "\n".join(lines)
        return None

    @property
    def books(self) -> List[dict]:
        return list(self._books)

    def row_for_id(self, book_id) -> int:
        for row, book in enumerate(self._books):
            if book.get("id") == book_id:
                return row
        return -1

    # --- mutações in-place (respeitam a regra de não recarregar tudo) ---
    def set_books(self, books: List[dict]) -> None:
        self.beginResetModel()
        self._books = list(books)
        self.endResetModel()

    def insert_book(self, index: int, book: dict) -> None:
        index = max(0, min(index, len(self._books)))
        self.beginInsertRows(QModelIndex(), index, index)
        self._books.insert(index, book)
        self.endInsertRows()

    def update_book(self, book: dict) -> bool:
        row = self.row_for_id(book.get("id"))
        if row < 0:
            return False
        old_cover = self._books[row].get("cover_image")
        if old_cover != book.get("cover_image"):
            cover_loader.invalidate(old_cover)
            cover_loader.invalidate(book.get("cover_image"))
        self._books[row] = book
        idx = self.index(row)
        self.dataChanged.emit(idx, idx)
        return True

    def remove_book(self, book_id) -> bool:
        row = self.row_for_id(book_id)
        if row < 0:
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._books[row]
        self.endRemoveRows()
        return True


class BookFilterProxy(QSortFilterProxyModel):
    """Aplica um predicado (busca + painel de filtros) sobre o model."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._predicate: Optional[Callable[[dict], bool]] = None
        self._sort_key: Optional[Callable[[dict], object]] = None
        self._descending = False

    def set_sort(self, key: Optional[Callable[[dict], object]], descending: bool = False) -> None:
        """Ordena a exibição por `key(book)` (None volta à ordem original do model).

        Livros em que `key` devolve None ficam sempre no fim, nas duas direções; empates saem por nome.
        A direção é aplicada aqui (o Qt ordena sempre "crescente") para não inverter esses dois casos.
        """
        self._sort_key = key
        self._descending = descending
        if key is None:
            self.sort(-1)
        else:
            self.invalidate()
            self.sort(0, Qt.AscendingOrder)

    def lessThan(self, left, right) -> bool:
        if self._sort_key is None:
            return left.row() < right.row()
        a, b = left.data(BookRole), right.data(BookRole)
        ka, kb = self._sort_key(a), self._sort_key(b)
        if (ka is None) != (kb is None):
            return kb is None  # quem tem valor vem antes
        if ka is not None and ka != kb:
            return ka > kb if self._descending else ka < kb
        ta, tb = fold(a.get("title")), fold(b.get("title"))
        if ta != tb:
            return ta < tb
        return left.row() < right.row()

    def set_predicate(self, predicate: Optional[Callable[[dict], bool]]) -> None:
        if hasattr(self, "beginFilterChange"):  # Qt >= 6.9 (invalidateFilter foi descontinuado)
            self.beginFilterChange()
            self._predicate = predicate
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._predicate = predicate
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if self._predicate is None:
            return True
        book = self.sourceModel().index(source_row, 0, source_parent).data(BookRole)
        return bool(book) and self._predicate(book)

    @property
    def books(self) -> List[dict]:
        """Livros que passam no filtro, na ordem exibida."""
        return [self.index(r, 0).data(BookRole) for r in range(self.rowCount())]
