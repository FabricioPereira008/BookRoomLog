from frontend_desktop import preferences
from frontend_desktop.views.components.book_grid import (
    BookGrid, CardSizeSelector, MODE_BUTTON, MODE_FULL, MODE_STRIP, SORT_CRITERIA, ScrollableBookGrid,
    make_predicate, search_text,
)
from frontend_desktop.views.components.shelf_view import ShelfView, next_queue, recently_read


def book(i, status="Quero Ler", **fields):
    return {"id": i, "title": f"Livro {i}", "status": status, **fields}


def test_search_matches_title_author_and_series():
    b = book(1, title="O Hobbit", authors=[{"name": "J. R. R. Tolkien"}], series={"name": "Terra-média"})
    assert "tolkien" in search_text(b)
    assert make_predicate("hobbit TOLKIEN")(b)
    assert make_predicate("terra media")(b)  # cada palavra basta estar contida
    assert make_predicate("terra-média")(b)
    assert make_predicate("")(b) and not make_predicate("duna")(b)


def test_sort_criteria_keys():
    b = book(1, title="Émile", authors=[{"name": "Rousseau"}], pages=0, score=None)
    assert SORT_CRITERIA["title"].key(b) == "emile"
    assert SORT_CRITERIA["author"].key(b) == "rousseau" and SORT_CRITERIA["author"].key(book(2)) is None
    assert SORT_CRITERIA["pages"].key(b) is None and SORT_CRITERIA["score"].key(b) is None
    assert SORT_CRITERIA["series"].key(book(3, series={"name": "S"}, series_number=2)) == ("s", 2)
    assert SORT_CRITERIA["series"].key(b) is None
    assert SORT_CRITERIA["finished"].direction_label(True) == "Recentes"


def test_book_grid_modes(qapp):
    strip = BookGrid(mode=MODE_STRIP)
    strip.resize(600, 400)
    strip.set_books([book(i) for i in range(6)])
    strip.show()
    qapp.processEvents()
    assert strip.view.height() > 0
    strip.scroll_strip(1)
    strip.set_books([])
    strip._update_height()
    assert strip.view.height() == 0

    button = BookGrid(mode=MODE_BUTTON, initial_rows=1)
    button.resize(400, 600)
    button.set_books([book(i) for i in range(10)])
    button.show()
    qapp.processEvents()
    before = button.rendered_count
    assert button.more_button.isVisibleTo(button) and before < 10
    button.load_more_cards()
    assert button.rendered_count > before

    full = BookGrid(mode=MODE_FULL)
    full.set_books([book(1)])
    full.insert_book(0, book(2))
    assert full.update_book(book(2, title="X")) and full.remove_book(1)
    assert [b["id"] for b in full.books] == [2]
    assert not full.strip_overflows()
    full._on_cover_loaded("x.jpg")

    selected = []
    full.book_selected.connect(selected.append)
    full.view.clicked.emit(full.proxy.index(0, 0))
    assert selected[0]["id"] == 2


def test_card_size_follows_preference(qapp):
    grid = BookGrid(mode=MODE_FULL)
    selector = CardSizeSelector()
    preferences.set_card_size("large")
    assert grid.delegate.metrics.card_width == 230 and selector.buttons["large"].isChecked()
    preferences.set_card_size("nada")
    assert preferences.card_size() == "medium"
    fixed = BookGrid(mode=MODE_FULL, size_mode="small")
    preferences.set_card_size("large")
    assert fixed.delegate.metrics.card_width == 130


def test_scrollable_grid_search_and_sort(qapp):
    grid = ScrollableBookGrid(sorts=("finished", "title"))
    grid.set_books([book(1, finish_date="2024-01-01", title="B"), book(2, finish_date="2025-01-01", title="A"),
                    book(3, title="C")])
    assert [b["id"] for b in grid.grid.books] == [2, 1, 3]  # mais recente primeiro, sem data no fim
    assert grid.sort_dir_btn.text() == "Recentes"
    grid.sort_dir_btn.setChecked(False)
    assert [b["id"] for b in grid.grid.books] == [1, 2, 3]
    grid.sort_combo.setCurrentIndex(1)
    assert [b["id"] for b in grid.grid.books] == [2, 1, 3] and grid.sort_dir_btn.text() == "A→Z"
    grid.search_input.setText("c")
    assert [b["id"] for b in grid.grid.books] == [3]
    grid.clear_filters()
    assert len(grid.grid.books) == 3 and grid.all_books_source
    grid.insert_book(0, book(4))
    assert grid.update_book(book(4, title="D")) and grid.remove_book(4)


def test_shelf_distributes_books(qapp):
    books = [book(1, "Lendo"), book(2, "Próximo", next_position=2), book(3, "Próximo", next_position=1),
             book(4), book(5, "Lido", finish_date="2025-01-01"), book(6, "Lido", finish_date="2026-01-01")]
    assert [b["id"] for b in next_queue(books)] == [3, 2]
    assert [b["id"] for b in recently_read(books)] == [6, 5]
    assert len(recently_read(books * 30, limit=0)) == 60

    shelf = ShelfView()
    shelf.set_books(books)
    assert [b["id"] for b in shelf.grid_next.books] == [3, 2]
    assert shelf.sec_reading.isVisibleTo(shelf) and not shelf.empty_label.isVisibleTo(shelf)
    assert shelf._counts[shelf.grid_read].text() == "2"

    shelf.search_input.setText("livro 4")
    assert not shelf.sec_reading.isVisibleTo(shelf) and shelf.sec_want.isVisibleTo(shelf)
    shelf.clear_filters()

    shelf.insert_book_by_status(book(7, "Próximo", next_position=3))
    assert [b["id"] for b in shelf.grid_next.model.books] == [3, 2, 7]
    shelf.insert_book_by_status(book(8, "Desconhecido"))
    assert shelf.update_book(book(1, "Lendo", title="Novo"))
    assert shelf.remove_book(1) and not shelf.sec_reading.isVisibleTo(shelf)
    views = []
    shelf.view_all_requested.connect(views.append)
    shelf.sections()[1][1].findChildren(type(shelf.search_input))  # seção existe
    shelf.set_books([])
    assert shelf.empty_label.isVisibleTo(shelf)
