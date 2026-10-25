import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from frontend_desktop import preferences
from frontend_desktop.views.components import management_view as mv
from frontend_desktop.views.components import settings_view as sv
from frontend_desktop.views.components.category_detail_view import CategoryDetailView
from frontend_desktop.views.components.management_view import ManagementView, card_count_text
from frontend_desktop.views.components.next_queue_view import NextQueueView, describe
from frontend_desktop.views.components.settings_view import SettingsView
from frontend_desktop.views.components.yearbook_view import YearbookView, pages_text, plural
from frontend_desktop.views.dialogs.lookup_dialog import LookupDialog, describe_candidate
from frontend_desktop.views.dialogs.quick_search_dialog import QuickSearchDialog, search_books
from frontend_desktop.views.dialogs.top3_dialog import Top3Dialog, book_option_text


@pytest.fixture
def no_popups(monkeypatch):
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))


def test_next_queue_reorders_and_starts(qapp, backend, sync_async, add_book):
    a, b, c = (add_book(title=t, status="Próximo", pages=100) for t in "ABC")
    view = NextQueueView()
    changes, saved = [], []
    view.queue_changed.connect(changes.append)
    view.book_saved.connect(lambda book, old: saved.append((book["title"], old)))
    view.set_books([c, a, b])
    assert [x["title"] for x in view.books] == ["A", "B", "C"] and view.list.currentRow() == 0
    assert describe(1, a).startswith("1.  A") and "100 págs." in describe(1, a)

    view.list.setCurrentRow(2)
    view.move_selected(to_top=True)
    assert [x["title"] for x in changes[-1]] == ["C", "A", "B"] and view.current_book()["title"] == "C"
    view.move_selected(1)
    assert [x["title"] for x in view.books] == ["A", "C", "B"]
    view.list.setCurrentRow(0)
    view.move_selected(-1)  # já está no topo
    assert len(changes) == 2

    item = view.list.takeItem(2)  # simula um arrastar: B para o topo
    view.list.insertItem(0, item)
    view._on_dropped()
    assert [x["title"] for x in changes[-1]] == ["B", "A", "C"]
    assert [x["next_position"] for x in changes[-1]] == [1, 2, 3]

    view.list.setCurrentRow(0)
    view.start_selected()
    assert saved == [("B", "Próximo")]
    view._on_cover_loaded("x.jpg")
    view._open_item(view.list.item(0))


def test_next_queue_error_and_empty(qapp, sync_async):
    view = NextQueueView()
    view.set_books([{"id": 1, "title": "A", "status": "Próximo"}, {"id": 2, "title": "B", "status": "Próximo"}])
    view.list.setCurrentRow(1)
    view.move_selected(-1)  # API offline
    assert "Não foi possível" in view.status_label.text()
    view.set_books([])
    assert view.empty_label.isVisibleTo(view) and view.current_book() is None
    view.move_selected(1)
    view.start_selected()


def test_yearbook_view(qapp, backend, sync_async, add_book, monkeypatch):
    first = add_book(title="Duna", authors=["Frank Herbert"], series="Duna", genres=["Ficção"], status="Lido",
                     finish_date="2025-03-01", score=9, pages=600, is_favorite=True)
    second = add_book(title="Emma", authors=["Jane Austen"], status="Lido", finish_date="2025-05-01", score=7,
                      pages=400)
    add_book(title="Antigo", status="Lido", finish_date="2023-01-01")
    view = YearbookView()
    view.load_data()
    assert view.year_combo.count() == 2 and view.current_year == 2025
    assert view.card_read.val_label.text() == "2" and view.card_pages.val_label.text() == "1.000"
    assert view.tile_longest.value.text() == "Duna · 600 págs." and "Frank Herbert" in view.tile_author.value.text()
    assert view.podium_cards[1].book["id"] == first["id"] and "Sugestão" in view.podium_hint.text()
    assert len(view.book_grid.books) == 2

    class FakeTop3:
        def __init__(self, year, books, current, parent):
            self.selected_ids = [second["id"]]

        def exec(self):
            return QDialog.Accepted
    from frontend_desktop.views.components import yearbook_view as yv
    monkeypatch.setattr(yv, "Top3Dialog", FakeTop3)
    view.choose_top3()
    assert view.summary["top3_custom"] and view.podium_cards[1].book["id"] == second["id"]
    assert view.podium_hint.text() == "Escolhido por você"
    view.year_combo.setCurrentIndex(1)
    assert view.current_year == 2023 and view.card_avg.val_label.text() == "N/A"
    view._on_year_loaded(-1, 1900, {})  # resposta atrasada é ignorada
    assert view.current_year == 2023
    assert view.compare_text(3, None, 2025) == "Livros lidos"
    assert view.compare_text(3, 3, 2025).endswith("igual a 2024")
    assert plural(1, "livro", "livros") == "1 livro" and pages_text(1234) == "1.234 págs."
    view.podium_cards[1]._on_cover_loaded("x.jpg")


def test_top3_and_quick_search_dialogs(qapp, monkeypatch):
    books = [{"id": 1, "title": "B", "score": 7, "authors": [{"name": "Ana"}]}, {"id": 2, "title": "A"}]
    assert book_option_text(books[0]) == "B — Ana   (nota 7)"
    dialog = Top3Dialog(2025, books, [2], None)
    assert dialog.chosen_ids() == [2]
    dialog.combos[1].setCurrentIndex(dialog.combos[1].findData(2))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dialog.save()
    assert dialog.selected_ids is None  # repetido
    dialog.combos[1].setCurrentIndex(dialog.combos[1].findData(1))
    dialog.save()
    assert dialog.selected_ids == [2, 1]
    dialog.use_suggestion()
    assert dialog.selected_ids == []

    library = [{"id": 1, "title": "O Hobbit", "authors": [{"name": "Tolkien"}], "status": "Lido"},
               {"id": 2, "title": "Hobbit, O", "status": "Quero Ler"}, {"id": 3, "title": "Duna"}]
    assert [b["id"] for b in search_books(library, "hobbit")] == [2, 1]
    assert [b["id"] for b in search_books(library, "tolkien")] == [1] and search_books(library, " ") == []
    quick = QuickSearchDialog(library)
    quick.input.setText("hob")
    assert quick.results.count() == 2
    quick.accept_current()
    assert quick.selected_book["id"] == 2
    quick.input.setText("xyz")
    assert quick.hint.text() == "Nenhum livro encontrado."
    quick.accept_current()


def test_lookup_dialog(qapp, backend, sync_async, monkeypatch):
    from frontend_desktop.views.dialogs import lookup_dialog as ld
    calls = []

    def fake_lookup(**kwargs):
        calls.append(kwargs)
        return [{"title": "O Hobbit", "authors": ["Tolkien"], "pages": 300, "isbn": "978", "source": "Google Books",
                 "cover_url": "https://c"}]
    monkeypatch.setattr(ld.api_client, "lookup_books", fake_lookup)
    preferences.set_google_books_key(" chave ")
    dialog = LookupDialog("O Hobbit", "Tolkien")
    assert calls[-1] == {"title": "O Hobbit", "author": "Tolkien", "isbn": None, "source": None, "api_key": "chave"}
    assert dialog.results_list.count() == 1 and dialog.btn_use.isEnabled()
    assert "300 págs." in describe_candidate(dialog.results[0]) and "com capa" in describe_candidate(dialog.results[0])
    dialog.accept_current()
    assert dialog.selected["title"] == "O Hobbit" and dialog.download_cover
    dialog.chk_cover.setChecked(False)
    assert not dialog.download_cover

    empty = LookupDialog(auto_search=False)
    empty.search()
    assert "Digite" in empty.status.text()
    empty.set_results([])
    assert "Nada encontrado" in empty.status.text() and not empty.btn_use.isEnabled()
    empty.accept_current()
    assert empty.selected is None
    monkeypatch.setattr(ld.api_client, "lookup_books", lambda **k: (_ for _ in ()).throw(RuntimeError("429")))
    empty.input_isbn.setText("123")
    empty.search()
    assert "falhou" in empty.status.text()
    empty._on_results(-1, [])
    empty._on_failed(-1, "velho")


def test_management_and_category_detail(qapp, backend, sync_async, add_book, monkeypatch, no_popups):
    add_book(title="Duna", authors=["Frank Herbert"], genres=["Ficção"], status="Lido", pages=600)
    add_book(title="Emma", authors=["Jane Austen"], status="Quero Ler")
    view = ManagementView("author")
    view.resize(1200, 800)
    view.load_data()
    assert [i["name"] for i in view.visible_items()] == ["Frank Herbert"]  # só quem tem livro lido
    view.search_input.setText("jane")
    assert [i["name"] for i in view.visible_items()] == ["Jane Austen"]
    view.search_input.setText("ninguém")
    view.search_input.setText("")
    preferences.set_category_scope("all")
    view.load_data()
    assert len(view.visible_items()) == 2
    assert card_count_text(view.items[0], "all") == "1 livro · 1 lido · 600 págs."
    assert card_count_text({"books_count": 2}, "read") == "2 livros"

    frank = view.items[0]
    monkeypatch.setattr(mv.QInputDialog, "getText", staticmethod(lambda *a, **k: ("Frank P. Herbert", True)))
    view.on_create_new()
    assert any(i["name"] == "Frank P. Herbert" for i in view.items)
    view.on_edit_requested(frank, {"name": "F. Herbert"})
    assert any(i["name"] == "F. Herbert" for i in view.items)
    view.on_delete_requested(next(i for i in view.items if i["name"] == "Frank P. Herbert"))
    assert len(view.items) == 2
    view.on_edit_requested(frank, {"name": "Jane Austen"})  # conflito vira mensagem de erro
    view._on_items_loaded(-1, [])  # resposta antiga ignorada
    assert view.items

    card = mv.ManageItemCard("genre", {"id": 1, "name": "Ficção", "books_count": 1, "color": "#123456"})
    edits, deletes = [], []
    card.edit_requested.connect(lambda item, fields: edits.append(fields))
    card.delete_requested.connect(deletes.append)
    monkeypatch.setattr(mv.QColorDialog, "getColor", staticmethod(lambda *a, **k: mv.QColor("#abcdef")))
    card.on_edit()
    assert edits == [{"name": "Frank P. Herbert", "color": "#abcdef"}]
    card.on_delete()
    assert deletes
    genres = ManagementView("genre")
    genres.load_data()
    genres.on_create_new()

    detail = CategoryDetailView()
    detail.load_category("genre", genres.items[0]["id"])
    assert detail.title_label.text() and detail.btn_edit_color.isVisibleTo(detail)
    monkeypatch.setattr("frontend_desktop.views.components.category_detail_view.QColorDialog.getColor",
                        staticmethod(lambda *a, **k: mv.QColor("#111111")))
    detail.on_change_color()
    assert detail.category_data["color"] == "#111111"
    detail._on_category_loaded("author", 999, {})  # outra categoria: ignorado
    detail.load_category("author", view.items[0]["id"])
    assert not detail.btn_edit_color.isVisibleTo(detail) and detail.card_all_books.isVisibleTo(detail)


def test_settings_view(qapp, backend, sync_async, add_book, monkeypatch, tmp_path, no_popups):
    from backend.app.api.v1.endpoints import backups as backups_endpoint
    from backend.app.main import app
    import sqlalchemy as sa
    from backend.app.core.migrations import run_migrations
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'bookroom.db'}")
    run_migrations(engine)
    app.dependency_overrides[backups_endpoint.get_engine] = lambda: engine
    try:
        view = SettingsView()
        view.show()
        assert view.backup_list.count() == 0 and "Nenhum backup" in view.lbl_backup_status.text()
        view.on_backup_now()
        assert view.backup_list.count() == 1 and "Backup criado" in view.lbl_backup_status.text()
        assert "0 livros" in view.backup_list.item(0).text()
        view.backup_list.setCurrentRow(0)
        assert view.btn_restore.isEnabled()
        imported = []
        view.data_imported.connect(lambda: imported.append(True))
        view.on_restore()
        assert imported and "restaurado" in view.lbl_backup_status.text()
        assert view.describe_backup({"created_at": "2026-01-02T03:04:05", "reason_label": "Manual",
                                     "books_count": 1, "size_bytes": 2048}).startswith("02/01/2026 03:04")
        assert view.format_size(1024 * 1024 * 1.5) == "1,5 MB"

        view.input_google_key.setText(" abc ")
        view.save_google_key()
        assert preferences.google_books_key() == "abc" and view.lbl_key_status.text() == "Chave salva."
        view.input_google_key.setText("")
        view.save_google_key()
        assert view.lbl_key_status.text() == "Chave removida."

        changed = []
        view.settings_changed.connect(lambda: changed.append(True))
        view.on_scope_changed("all")
        assert preferences.category_scope() == "all" and changed
        view.restore_appearance()
        assert preferences.category_scope() == "read"
        view.size_buttons["small"].click()
        assert preferences.card_size() == "small"

        view.load_orphan_covers()
        assert "Nenhuma capa sem uso" in view.lbl_cleanup_status.text()
        result = sv.SettingsView.cleanup_covers()
        assert result["removed"] == 0
        view._on_covers_cleaned({"removed": 1, "freed_bytes": 10, "cache_removed": 0})
        view.on_cover_batch_finished(0, 0)
        assert "já têm capa" in view.lbl_cover_status.text()
        view.on_cover_batch_finished(3, 1)
        view.on_cover_progress(1, 2, "Duna", True)
    finally:
        app.dependency_overrides.pop(backups_endpoint.get_engine, None)


def test_cover_fetcher_thread(qapp, backend, add_book, monkeypatch):
    from frontend_desktop.api_client.client import api_client
    add_book(title="Sem capa")
    add_book(title="Com capa", cover_image="a.jpg")
    monkeypatch.setattr(api_client, "auto_cover_book", lambda book_id, key=None: {"success": True})
    monkeypatch.setattr(sv.time, "sleep", lambda s: None)
    thread = sv.CoverFetcherThread("k")
    progress, finished = [], []
    thread.progress_updated.connect(lambda *a: progress.append(a))
    thread.batch_finished.connect(lambda *a: finished.append(a))
    thread.run()
    assert progress == [(1, 1, "Sem capa", True)] and finished == [(1, 1)]


def test_autofill_thread(qapp, backend, add_book, monkeypatch):
    from frontend_desktop.api_client.client import api_client
    complete = dict(authors=["A"], genres=["G"], cover_image="c.jpg", pages=1, publisher="P", isbn="1",
                    language="Português")
    add_book(title="Completo", **complete)
    first = add_book(title="Faltando 1")
    second = add_book(title="Faltando 2")
    add_book(title="Faltando 3")
    results = {first["id"]: {"filled": ["autor"], "source": "Open Library"},
               second["id"]: {"filled": [], "source": None}}

    def fake_autofill(book_id, key=None):
        if book_id not in results:
            raise RuntimeError("429")
        return results[book_id]
    monkeypatch.setattr(api_client, "autofill_book", fake_autofill)
    monkeypatch.setattr(sv.time, "sleep", lambda s: None)
    thread = sv.AutofillThread("k")
    progress, finished = [], []
    thread.progress_updated.connect(lambda *a: progress.append(a))
    thread.batch_finished.connect(lambda *a: finished.append(a))
    thread.run()
    assert [p[2] for p in progress] == ["Faltando 1", "Faltando 2", "Faltando 3"]
    assert progress[0][3] == ["autor"] and finished == [(3, 1, 2)]

    stopped = sv.AutofillThread()
    stopped.stop()
    stopped.batch_finished.connect(lambda *a: finished.append(a))
    stopped.run()
    assert finished[-1] == (0, 0, 0)

    monkeypatch.setattr(api_client, "get_books", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    broken = sv.AutofillThread()
    broken.batch_finished.connect(lambda *a: finished.append(a))
    broken.run()
    assert finished[-1] == (0, 0, 0)


def test_settings_autofill_ui(qapp, monkeypatch):
    view = SettingsView()
    started = []
    monkeypatch.setattr(sv.AutofillThread, "start", lambda self: started.append(self))
    view.start_autofill()
    assert started and not view.btn_autofill.isEnabled() and not view.btn_stop_autofill.isHidden()
    monkeypatch.setattr(sv.AutofillThread, "isRunning", lambda self: True)
    view.start_autofill()  # já rodando: não começa outro
    assert len(started) == 1
    view.stop_autofill()
    assert not view.autofill_thread.is_running and not view.btn_stop_autofill.isEnabled()
    view.on_autofill_progress(1, 2, "Duna", ["autor", "gênero"])
    assert "Duna — preenchido: autor, gênero" in view.lbl_autofill_status.text()
    view.on_autofill_progress(2, 2, "Emma", [])
    assert "nada novo" in view.lbl_autofill_status.text()
    reloaded = []
    view.data_imported.connect(lambda: reloaded.append(True))
    view.on_autofill_finished(0, 0, 0)
    assert "Nenhum livro" in view.lbl_autofill_status.text() and not reloaded
    view.on_autofill_finished(2, 1, 1)
    assert "1 de 2" in view.lbl_autofill_status.text() and reloaded and view.btn_autofill.isEnabled()
    monkeypatch.setattr(sv.AutofillThread, "isRunning", lambda self: False)
