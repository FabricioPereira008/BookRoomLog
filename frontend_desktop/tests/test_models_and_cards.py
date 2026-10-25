import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

from frontend_desktop.models.book_list_model import BookFilterProxy, BookListModel, BookRole
from frontend_desktop.models.book_table_model import COLUMNS, BookTableModel, BookTableProxy, cell_text, sort_key
from frontend_desktop.views.components.book_card_delegate import (
    BookCardDelegate, CardMetrics, current_size_mode, placeholder_pixmap,
)


def book(i, **fields):
    return {"id": i, "title": f"Livro {i}", "status": "Quero Ler", **fields}


def test_list_model_mutations(qapp):
    model = BookListModel()
    model.set_books([book(1), book(2)])
    assert model.rowCount() == 2 and model.row_for_id(2) == 1 and model.row_for_id(9) == -1
    model.insert_book(99, book(3))
    assert [b["id"] for b in model.books] == [1, 2, 3]
    assert model.update_book(book(2, title="Novo", cover_image="x.jpg"))
    assert model.data(model.index(1), Qt.DisplayRole) == "Novo"
    assert not model.update_book(book(42))
    assert model.remove_book(1) and not model.remove_book(1)
    assert model.data(model.index(10), BookRole) is None
    assert model.data(model.index(0), Qt.DecorationRole) is None


def test_list_model_tooltip(qapp):
    model = BookListModel()
    model.set_books([book(1, authors=[{"name": "Ana"}], genres=[{"name": "Drama"}], pages=200,
                          series={"name": "Saga"}, series_number=1, read_number=2)])
    tip = model.data(model.index(0), Qt.ToolTipRole)
    assert tip.splitlines()[:6] == ["Livro 1", "Ana", "Saga #1", "Drama", "200 págs.", "2ª leitura"]
    assert "Faltando: capa" in tip


def test_filter_proxy_sort_and_predicate(qapp):
    model = BookListModel()
    model.set_books([book(1, pages=300), book(2, pages=None), book(3, pages=100), book(4, pages=300, title="A")])
    proxy = BookFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_sort(lambda b: b.get("pages"))
    assert [b["id"] for b in proxy.books] == [3, 4, 1, 2]  # empate por título; sem valor no fim
    proxy.set_sort(lambda b: b.get("pages"), descending=True)
    assert [b["id"] for b in proxy.books] == [4, 1, 3, 2]
    proxy.set_sort(None)
    assert [b["id"] for b in proxy.books] == [1, 2, 3, 4]
    proxy.set_predicate(lambda b: b["id"] % 2 == 0)
    assert [b["id"] for b in proxy.books] == [2, 4]
    proxy.set_predicate(None)
    assert proxy.rowCount() == 4


def test_table_cells_and_sort_keys():
    full = book(1, authors=[{"name": "Ana"}], status="Lido", genres=[{"name": "A"}, {"name": "B"}],
                series={"name": "Saga"}, series_number=2, publisher={"name": "Ed"}, format="Físico", pages=200,
                finish_date="2025-03-04", score=8.5, read_number=2)
    assert [cell_text(full, c) for c in range(len(COLUMNS))] == [
        "Livro 1", "Ana", "Lido", "A, B", "Saga #2", "Ed", "Físico", "200", "04/03/2025", "8.5", "2"]
    assert cell_text(book(2, status="Lendo", progress=30), 2) == "Lendo (30%)"
    assert cell_text(book(3, status="Próximo", next_position=1), 2) == "Próximo (#1)"
    assert cell_text(book(4), 8) == "" and cell_text(book(4), 9) == ""
    assert sort_key(book(4), 9) == -1 and sort_key(full, 9) == 8.5
    assert sort_key(full, 2) > sort_key(book(5, status="Quero Ler"), 2)
    assert sort_key(book(6, status="?"), 2)[0] == 99
    assert sort_key(full, 4) == ("saga", 2) and sort_key(full, 7) == 200 and sort_key(full, 10) == 2
    assert sort_key(full, 8) == "2025-03-04" and sort_key(full, 0) == "livro 1"


def test_table_model_and_proxy(qapp):
    model = BookTableModel()
    model.set_books([book(1, status="Lido", pages=10), book(2, status="Lendo", pages=5)])
    assert model.columnCount() == len(COLUMNS) and model.rowCount() == 2
    assert model.headerData(7, Qt.Horizontal, Qt.ToolTipRole) == "Número de páginas"
    assert model.headerData(0, Qt.Horizontal) == "Livro" and model.headerData(0, Qt.Vertical) is None
    assert model.data(model.index(0, 2), Qt.ForegroundRole) is not None
    assert model.data(model.index(0, 1), Qt.ForegroundRole) is None
    assert model.data(model.index(0, 7), Qt.TextAlignmentRole)
    assert "Faltando" in model.data(model.index(0, 0), Qt.ToolTipRole)
    assert model.data(model.index(0, 0), BookRole)["id"] == 1
    model.insert_book(book(3))
    assert model.update_book(book(3, title="X")) and not model.update_book(book(9))
    assert model.remove_book(3) and not model.remove_book(3)

    proxy = BookTableProxy()
    proxy.setSourceModel(model)
    proxy.sort(7, Qt.AscendingOrder)
    assert [b["id"] for b in proxy.books] == [2, 1]
    proxy.sort(2, Qt.AscendingOrder)  # chaves em tupla
    assert [b["id"] for b in proxy.books] == [2, 1]
    proxy.set_predicate(lambda b: b["id"] == 1)
    assert [b["id"] for b in proxy.books] == [1]


def test_card_metrics_and_size_mode():
    small, large = CardMetrics.for_mode("small"), CardMetrics.for_mode("large")
    assert small.card_width < large.card_width and large.cover_height == int(large.cover_width * 1.5)
    assert CardMetrics.for_mode("?") == CardMetrics.for_mode("medium")
    assert current_size_mode() == "medium"
    delegate = BookCardDelegate("small")
    assert delegate.set_size_mode("large") and not delegate.set_size_mode("large")
    assert placeholder_pixmap(40, 60) is placeholder_pixmap(40, 60)


@pytest.mark.parametrize("fields", [
    {"status": "Lendo", "progress": 55, "is_favorite": True},
    {"status": "Lendo"},
    {"status": "Próximo", "next_position": 2, "format": "Audiobook"},
    {"status": "Lido", "score": 9.5, "read_number": 2, "pages": 300, "authors": [{"name": "Ana"}]},
    {"status": "Quero Ler", "cover_image": "nao-carregada.jpg"},
])
def test_card_paints_every_state(qapp, fields):
    model = BookListModel()
    model.set_books([book(1, **fields)])
    delegate = BookCardDelegate("medium")
    m = delegate.metrics
    image = QImage(m.card_width, m.card_height, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, m.card_width, m.card_height)
    option.state = QStyle.State_MouseOver | QStyle.State_Selected
    delegate.paint(painter, option, model.index(0))
    delegate.paint(painter, option, BookListModel().index(0))  # índice inválido: não pinta nada
    painter.end()
    assert delegate.sizeHint(option, model.index(0)).width() == m.card_width
    assert image.pixelColor(m.card_width // 2, 2).alpha() > 0
