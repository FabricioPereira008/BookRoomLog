import pytest
from PySide6.QtWidgets import QMessageBox

from frontend_desktop.views import main_window as mw
from frontend_desktop.views.main_window import MainWindow, read_order
from frontend_desktop.views.view_ids import ViewId


@pytest.fixture
def window(qapp, backend, sync_async):
    win = MainWindow(auto_load=False)
    yield win
    win.close()


def ids(books):
    return [b["id"] for b in books]


def test_load_distributes_books(window, add_book):
    reading = add_book(title="Lendo", status="Lendo", progress=10)
    nxt = add_book(title="Próximo", status="Próximo")
    want = add_book(title="Quero")
    old = add_book(title="Lido velho", status="Lido", finish_date="2024-01-01")
    new = add_book(title="Lido novo", status="Lido", finish_date="2025-01-01")
    window.refresh_all_data_sync()
    assert len(window.all_books) == 5
    assert ids(window.view_shelf.grid_reading.books) == [reading["id"]]
    assert ids(window.view_want.grid.books) == [want["id"]]
    assert ids(window.view_next.books) == [nxt["id"]]
    assert ids(window.view_read.grid.books) == [new["id"], old["id"]]
    assert len(window.view_table.books) == 5
    assert ids(read_order(window.all_books)) == [new["id"], old["id"]]
    assert "5" in window.statusBar().currentMessage()


def test_load_failure_shows_message(qapp, sync_async):
    win = MainWindow(auto_load=False)
    win.refresh_all_data_sync()  # sem a fixture backend: API offline
    assert "Erro de conexão" in win.statusBar().currentMessage()


def test_new_and_moved_books_update_views_in_place(window, add_book):
    window.refresh_all_data_sync()
    created = add_book(title="Novo", status="Quero Ler")
    window.apply_book_mutation(created, is_new=True)
    assert ids(window.view_want.grid.books) == [created["id"]]
    assert ids(window.view_shelf.grid_want.books) == [created["id"]]

    moved = window.view_shelf.grid_want.books[0] | {"status": "Lido", "score": 8}
    window.apply_book_mutation(moved, old_status="Quero Ler")
    assert window.view_want.grid.books == [] and ids(window.view_read.grid.books) == [created["id"]]
    assert ids(window.view_shelf.grid_read.books) == [created["id"]]
    assert "movido" in window.statusBar().currentMessage()

    edited = moved | {"title": "Editado"}
    window.apply_book_mutation(edited, old_status="Lido")
    assert window.view_read.grid.books[0]["title"] == "Editado"
    assert window.view_table.books[0]["title"] == "Editado"

    # Livro que ainda não estava em memória entra mesmo assim
    window.apply_book_mutation({"id": 999, "title": "Fantasma", "status": "Lido"}, old_status="Lido")
    assert window.all_books[0]["id"] == 999


def test_next_queue_is_refreshed_from_the_server(window, add_book, backend):
    a = add_book(title="A", status="Próximo")
    b = add_book(title="B", status="Próximo")
    window.refresh_all_data_sync()
    c = add_book(title="C", status="Próximo")
    window.apply_book_mutation(c, is_new=True)
    assert ids(window.view_next.books) == [a["id"], b["id"], c["id"]]

    started = backend.put(f"/api/v1/books/{a['id']}", json={"status": "Lendo"}).json()
    window.apply_book_mutation(started, old_status="Próximo")
    assert ids(window.view_next.books) == [b["id"], c["id"]]
    assert [x["next_position"] for x in window.view_shelf.grid_next.books] == [1, 2]
    assert ids(window.view_shelf.grid_reading.books) == [a["id"]]

    edited = backend.put(f"/api/v1/books/{b['id']}", json={"notes": "x"}).json()
    window.apply_book_mutation(edited, old_status="Próximo")
    assert window.view_next.books[0]["notes"] == "x"

    backend.delete(f"/api/v1/books/{b['id']}")
    window.apply_book_deletion(b["id"])
    assert ids(window.view_next.books) == [c["id"]] and window.view_next.books[0]["next_position"] == 1


def test_deleting_root_of_rereads_reloads_everything(window, add_book, backend):
    root = add_book(title="A", status="Lido")
    reread = backend.post(f"/api/v1/books/{root['id']}/reread").json()
    window.refresh_all_data_sync()
    window.apply_book_mutation(reread, is_new=True)
    assert next(b for b in window.all_books if b["id"] == root["id"])["rereads_count"] == 1
    called = []
    window.refresh_all_data = lambda: called.append(True)
    window.apply_book_deletion(root["id"])
    assert called

    window.apply_book_deletion(reread["id"])
    assert reread["id"] not in ids(window.all_books)


def test_navigation_and_lazy_views(window, add_book):
    add_book(title="Duna", authors=["Frank Herbert"], status="Lido", finish_date="2025-02-01", score=9)
    window.refresh_all_data_sync()
    for view_id in ViewId:
        if view_id == ViewId.CATEGORY_DETAIL:
            continue
        window.switch_view(int(view_id))
        assert window.current_view_id == view_id
    window.switch_view(int(ViewId.YEARBOOK))
    assert window.view_yearbook.summary["total_books_read"] == 1
    window.switch_view(int(ViewId.AUTHORS))
    author = window._views[ViewId.AUTHORS].items[0]
    window.open_category_detail("author", author["id"])
    assert window.current_view_id == ViewId.CATEGORY_DETAIL
    assert window.view_category_detail.title_label.text() == "Frank Herbert"
    window.refresh_all_data_sync()  # recarrega o detalhe aberto
    window.return_from_category_detail()
    assert window.current_view_id == ViewId.AUTHORS
    window.open_list_view("Lido")
    assert window.current_view_id == ViewId.READ
    window.open_list_view("Lendo")  # não tem página própria
    assert window.current_view_id == ViewId.READ
    window.refresh_all_data_sync()


def test_dialog_results_are_applied(window, add_book, monkeypatch):
    book = add_book(title="Duna", status="Lido")
    window.refresh_all_data_sync()

    class FakeDialog:
        result = {}

        def __init__(self, book_data=None, parent=None):
            self.book_data = book_data
            self.saved_book = FakeDialog.result.get("saved")
            self.is_deleted = FakeDialog.result.get("deleted", False)
            self.reread_created = FakeDialog.result.get("reread")

        def exec(self):
            return FakeDialog.result.get("accepted", True)
    monkeypatch.setattr(mw, "BookDialog", FakeDialog)

    FakeDialog.result = {"saved": {**book, "id": 50, "title": "Novo"}}
    window.open_add_book_dialog()
    assert window.all_books[0]["title"] == "Novo"
    FakeDialog.result = {"saved": {**book, "title": "Duna 2"}}
    window.open_edit_book_dialog(book)
    assert next(b for b in window.all_books if b["id"] == book["id"])["title"] == "Duna 2"
    FakeDialog.result = {"reread": {**book, "id": 60, "status": "Lendo", "reread_of_id": book["id"]}}
    window.open_edit_book_dialog(book)
    assert 60 in ids(window.view_shelf.grid_reading.books)
    FakeDialog.result = {"deleted": True}
    window.open_edit_book_dialog(book)
    assert book["id"] not in ids(window.all_books)
    FakeDialog.result = {"accepted": False}
    window.open_edit_book_dialog({"id": 60})


def test_delete_selected_and_quick_search(window, add_book, monkeypatch):
    book = add_book(title="Excluir")
    window.refresh_all_data_sync()
    window.switch_view(int(ViewId.WANT))
    view = window.view_want.grid.view
    view.setCurrentIndex(view.model().index(0, 0))
    assert window.selected_book_in(view)["id"] == book["id"]
    table = window.view_table.table
    table.setCurrentIndex(table.model().index(0, 0))
    assert window.selected_book_in(table.viewport())["id"] == book["id"]
    assert window.selected_book_in(None) is None

    monkeypatch.setattr(mw.QApplication, "focusWidget", staticmethod(lambda: view))
    monkeypatch.setattr(mw.QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    window.delete_selected_book()
    assert window.all_books
    monkeypatch.setattr(mw.QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    window.delete_selected_book()
    assert window.all_books == []
    monkeypatch.setattr(mw.QApplication, "focusWidget", staticmethod(lambda: None))
    window.delete_selected_book()

    opened = []
    monkeypatch.setattr(window, "open_edit_book_dialog", opened.append)

    class FakeSearch:
        def __init__(self, books, parent=None):
            self.selected_book = {"id": 1}

        def exec(self):
            return True
    monkeypatch.setattr(mw, "QuickSearchDialog", FakeSearch)
    window.open_quick_search()
    assert opened == [{"id": 1}]


def test_async_refresh_runs_in_background(qapp, backend, add_book):
    add_book(title="Thread")
    win = MainWindow(auto_load=True)
    win.refresh_all_data()  # já está carregando: só agenda outra rodada
    assert win._refresh_pending
    win._loader.wait(5000)
    for _ in range(50):
        qapp.processEvents()
        if not win._loading and not win._refresh_pending and win.all_books:
            break
    if win._loader is not None:
        win._loader.wait(5000)
    qapp.processEvents()
    assert win.all_books and win.all_books[0]["title"] == "Thread"
    win.close()
