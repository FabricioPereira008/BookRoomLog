import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QLineEdit, QMessageBox

from frontend_desktop.views.dialogs import book_dialog as bd
from frontend_desktop.views.dialogs import book_dialog_cover as bdc
from frontend_desktop.views.dialogs.book_dialog import (
    BookDialog, MultiValueCompleter, brief_label, reading_group, split_authors,
)


@pytest.fixture
def no_popups(monkeypatch):
    shown = []
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, _n=name, **k: shown.append(_n)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    return shown


def test_split_authors():
    assert split_authors(" Terry  Pratchett, Neil Gaiman; terry pratchett ,, ") == ["Terry Pratchett", "Neil Gaiman"]
    assert split_authors("") == []


def test_brief_label_and_reading_group():
    briefs = [{"id": 1, "title": "A", "status": "Lido", "author": "Ana", "read_number": 1, "finish_date": "2020-01-02"},
              {"id": 2, "title": "A", "status": "Lendo", "read_number": 2, "reread_of_id": 1},
              {"id": 3, "title": "B", "status": "Quero Ler"}]
    assert brief_label(briefs[0]) == "A  —  Ana · Lido · terminado em 2020"
    assert brief_label(briefs[1]) == "A  —  Lendo · 2ª leitura"
    assert [b["id"] for b in reading_group(briefs, 2, 1)] == [1, 2]
    assert reading_group(briefs, None, None) == []


def test_multi_value_completer(qapp):
    edit = QLineEdit("Neil Gaiman, Ter")
    completer = MultiValueCompleter(["Terry Pratchett"])
    edit.setCompleter(completer)
    assert completer.splitPath(edit.text()) == ["Ter"]
    completer.setCompletionPrefix("Ter")
    index = completer.completionModel().index(0, 0)
    assert completer.pathFromIndex(index) == "Neil Gaiman, Terry Pratchett"


def test_new_book_payload_and_status_fields(qapp, backend, sync_async, add_book):
    add_book(title="Outro", authors=["Ana"], genres=["Drama"], publisher="Ed", series="Saga")
    dialog = BookDialog()
    assert dialog.combo_genre.count() == 1 and dialog.btn_save.isEnabled()
    assert not dialog.field_progress.isVisibleTo(dialog) and not dialog.field_score.isVisibleTo(dialog)

    dialog.input_title.setText("  Duna ")
    dialog.input_authors.setText("Frank Herbert, ")
    dialog.combo_series.setEditText("Duna")
    dialog.spin_series_number.setValue(1)
    dialog.combo_genre.setEditText("Ficção")
    dialog.combo_genre2.setEditText("ficção")
    dialog.combo_publisher.setEditText("Aleph")
    dialog.spin_pages.setValue(680)
    dialog.combo_format.setCurrentText("Físico")
    dialog.combo_language.setEditText("Português")
    dialog.input_isbn.setText("978")
    dialog.combo_status.setCurrentIndex(dialog.combo_status.findData("Lendo"))
    assert dialog.field_progress.isVisibleTo(dialog)
    dialog.spin_progress.setValue(30)
    payload = dialog.build_payload()
    assert payload["title"] == "Duna" and payload["authors"] == ["Frank Herbert"]
    assert payload["genres"] == ["Ficção"] and payload["series_number"] == 1
    assert payload["progress"] == 30 and payload["score"] is None and payload["finish_date"] is None

    dialog.combo_status.setCurrentIndex(dialog.combo_status.findData("Lido"))
    assert dialog.field_score.isVisibleTo(dialog) and not dialog.date_finish.is_blank()  # terminou hoje
    dialog.spin_score.setValue(9.5)
    dialog.date_finish.setDate(QDate(2025, 3, 10))
    payload = dialog.build_payload()
    assert payload["finish_date"] == "2025-03-10" and payload["score"] == 9.5 and payload["progress"] is None

    dialog.combo_series.setEditText("")
    assert dialog.build_payload()["series_number"] is None
    dialog.save_book()
    assert dialog.saved_book["title"] == "Duna" and dialog.saved_book["score"] == 9.5
    assert dialog.saved_book["publisher"]["name"] == "Aleph"


def test_title_is_required(qapp, backend, sync_async, no_popups):
    dialog = BookDialog()
    dialog.save_book()
    assert no_popups == ["warning"] and dialog.saved_book is None


def test_edit_populates_and_saves(qapp, backend, sync_async, add_book):
    book = add_book(title="Duna", authors=["Frank Herbert"], genres=["Ficção", "Aventura"], series="Duna",
                    series_number=2, publisher="Aleph", pages=500, format="Audiobook", language="Inglês",
                    isbn="123", status="Lido", score=8, finish_date="2024-05-06", is_favorite=True, notes="bom")
    dialog = BookDialog(book_data=book)
    assert dialog.input_title.text() == "Duna" and dialog.input_authors.text() == "Frank Herbert"
    assert dialog.combo_genre2.currentText() == "Aventura" and dialog.spin_series_number.value() == 2
    assert dialog.combo_format.currentText() == "Audiobook" and dialog.combo_language.currentText() == "Inglês"
    assert dialog.date_finish.date() == QDate(2024, 5, 6) and dialog.spin_score.value() == 8
    assert dialog.chk_favorite.isChecked() and dialog.input_notes.toPlainText() == "bom"
    assert dialog.btn_reread.isVisibleTo(dialog)
    dialog.input_notes.setText("ótimo")
    dialog.save_book()
    assert dialog.saved_book["notes"] == "ótimo" and dialog.saved_book["id"] == book["id"]


def test_reread_link_and_group(qapp, backend, sync_async, add_book, no_popups):
    original = add_book(title="Duna", status="Lido", finish_date="2020-01-01", score=7)
    add_book(title="Outro")
    dialog = BookDialog()
    dialog.input_title.setText("Duna")
    dialog.chk_reread.setChecked(True)
    assert dialog.field_reread_of.isVisibleTo(dialog)
    assert dialog.selected_reread_of() == original["id"]  # sugerido pelo título
    dialog.combo_reread_of.setEditText("texto solto")
    assert dialog.selected_reread_of() is None
    dialog.save_book()
    assert no_popups == ["warning"]
    dialog.combo_reread_of.setCurrentIndex(dialog.combo_reread_of.findData(original["id"]))
    dialog.save_book()
    reread = dialog.saved_book
    assert reread["reread_of_id"] == original["id"] and reread["read_number"] == 2

    edit = BookDialog(book_data=reread)
    assert edit.chk_reread.isChecked() and edit.selected_reread_of() == original["id"]
    assert "2ª leitura" in edit.lbl_reads.text() and edit.lbl_reads.isVisibleTo(edit)
    edit.chk_reread.setChecked(False)
    assert edit.build_payload()["reread_of_id"] is None

    root_dialog = BookDialog(book_data={**original, "rereads_count": 1})
    assert root_dialog._briefs is not None and root_dialog.lbl_reads.isVisibleTo(root_dialog)


def test_reread_button_and_delete(qapp, backend, sync_async, add_book, no_popups):
    book = add_book(title="Duna", status="Lido")
    dialog = BookDialog(book_data=book)
    dialog.start_reread()
    assert dialog.reread_created["reread_of_id"] == book["id"] and dialog.reread_created["status"] == "Lendo"
    deleting = BookDialog(book_data=book)
    deleting.delete_book()
    assert deleting.is_deleted
    gone = BookDialog(book_data=book)
    gone.delete_book()  # já excluído no servidor
    assert not gone.is_deleted
    gone._on_book_deleted(False)
    assert "critical" in no_popups


def test_options_failure_and_save_failure(qapp, sync_async, no_popups):
    dialog = BookDialog(book_data={"title": "Pré-preenchido"})  # API offline
    assert dialog.btn_save.isEnabled() and "API offline" in dialog.lbl_cover_status.text()
    assert dialog.input_title.text() == "Pré-preenchido"
    dialog.save_book()
    assert no_popups == ["critical"] and dialog.btn_save.isEnabled()


def test_candidate_fills_only_empty_fields(qapp, backend, sync_async, monkeypatch):
    dialog = BookDialog()
    downloads = []
    monkeypatch.setattr(dialog, "download_cover_url", downloads.append)
    candidate = {"title": "O Hobbit", "authors": ["J.R.R. Tolkien"], "publisher": "HarperCollins", "pages": 336,
                 "language": "Português", "isbn": "978", "cover_url": "https://x/c.jpg",
                 "genres": ["Fantasia", "Infantojuvenil"], "series": "Terra-média", "series_number": 1}
    filled = dialog.apply_candidate(candidate, download_cover=True)
    assert filled == ["título", "autor", "gênero", "série", "editora", "páginas", "idioma", "ISBN", "capa"]
    assert dialog.input_title.text() == "O Hobbit" and dialog.input_authors.text() == "J.R.R. Tolkien"
    assert (dialog.combo_genre.currentText(), dialog.combo_genre2.currentText()) == ("Fantasia", "Infantojuvenil")
    assert dialog.combo_series.currentText() == "Terra-média" and dialog.spin_series_number.value() == 1
    assert dialog.combo_publisher.currentText() == "HarperCollins" and dialog.spin_pages.value() == 336
    assert dialog.input_isbn.text() == "978" and downloads == ["https://x/c.jpg"]

    # Tudo já preenchido: nada é trocado
    other = {"title": "Outro", "authors": ["X"], "publisher": "Y", "pages": 1, "language": "Inglês", "isbn": "1",
             "genres": ["Terror"], "series": "Outra", "series_number": 5, "cover_url": "https://x/2.jpg"}
    dialog.cover_filename = "capa.jpg"
    assert dialog.apply_candidate(other, download_cover=True) == []
    assert dialog.input_title.text() == "O Hobbit" and dialog.combo_genre.currentText() == "Fantasia"
    assert dialog.spin_series_number.value() == 1

    # Volume só entra se a série for a mesma
    dialog.spin_series_number.setValue(0)
    assert dialog.apply_candidate({"series": "Outra", "series_number": 3}) == []
    assert dialog.apply_candidate({"series": "terra-média", "series_number": 3}) == ["volume"]
    assert dialog.apply_candidate({"title": ""}) == []


def test_lookup_dialog_result_is_applied(qapp, backend, sync_async, monkeypatch):
    dialog = BookDialog()
    dialog.input_title.setText("O Hobbit")
    dialog.input_authors.setText("Tolkien")

    class FakeLookup:
        def __init__(self, title, author, isbn, parent):
            FakeLookup.args = (title, author, isbn)
            self.selected = {"title": "Outro título", "pages": 300}
            self.download_cover = False

        def exec(self):
            return True
    monkeypatch.setattr(bd, "LookupDialog", FakeLookup)
    dialog.open_lookup()
    assert FakeLookup.args == ("O Hobbit", "Tolkien", "")
    assert dialog.input_title.text() == "O Hobbit" and dialog.spin_pages.value() == 300
    assert "Preenchido: páginas" in dialog.lbl_autofill.text()


def test_autofill_button(qapp, backend, sync_async, monkeypatch, no_popups):
    from frontend_desktop import preferences
    from frontend_desktop.api_client.client import api_client
    dialog = BookDialog()
    dialog.autofill()
    assert no_popups == ["warning"]  # sem título nem ISBN

    calls = []

    def fake_best(title, author, isbn, api_key):
        calls.append((title, author, isbn, api_key))
        return {"source": "Open Library", "authors": ["Frank Herbert"], "genres": ["Ficção científica"]}
    monkeypatch.setattr(api_client, "lookup_best", fake_best)
    monkeypatch.setattr(dialog, "download_cover_url", lambda url: None)
    preferences.set_google_books_key("chave")
    dialog.input_title.setText("Duna")
    dialog.autofill()
    assert calls == [("Duna", None, None, "chave")]
    assert dialog.input_authors.text() == "Frank Herbert" and dialog.combo_genre.currentText() == "Ficção científica"
    assert "Preenchido (Open Library): autor, gênero" in dialog.lbl_autofill.text()
    assert dialog.btn_autofill.isEnabled() and dialog.btn_autofill.text() == "Preencher automaticamente"

    dialog.autofill()  # tudo que o resultado traz já está preenchido
    assert "já estavam preenchidos" in dialog.lbl_autofill.text()

    monkeypatch.setattr(api_client, "lookup_best", lambda *a: None)
    dialog.autofill()
    assert "Nada encontrado com segurança" in dialog.lbl_autofill.text()

    def boom(*a):
        raise RuntimeError("429")
    monkeypatch.setattr(api_client, "lookup_best", boom)
    dialog.autofill()
    assert "A busca falhou" in dialog.lbl_autofill.text() and dialog.btn_autofill.isEnabled()


def test_autofill_through_the_real_api(qapp, backend, sync_async, monkeypatch, add_book):
    from backend.app.api.v1.endpoints import lookup
    from backend.app.schemas.lookup import BookCandidate
    add_book(title="Outro", genres=["fantasia"])

    async def fake_find(title, author=None, isbn=None, api_key=None, existing_genres=()):
        if title == "Desconhecido":
            return None
        return BookCandidate(source="Open Library", title=title, authors=["Tolkien"],
                             genres=[g for g in existing_genres if g == "fantasia"])
    monkeypatch.setattr(lookup.lookup_service, "find_best", fake_find)
    dialog = BookDialog()
    dialog.input_title.setText("O Hobbit")
    dialog.autofill()
    assert dialog.input_authors.text() == "Tolkien" and dialog.combo_genre.currentText() == "fantasia"
    dialog.input_title.setText("Desconhecido")
    dialog.autofill()
    assert "Nada encontrado" in dialog.lbl_autofill.text()


def test_cover_actions(qapp, backend, sync_async, monkeypatch, tmp_path, no_popups):
    from frontend_desktop.api_client.client import api_client
    dialog = BookDialog()
    dialog.auto_search_cover()
    assert no_popups == ["warning"]  # sem título

    monkeypatch.setattr(api_client, "auto_search_cover", lambda *a: "capa.jpg")
    dialog.input_title.setText("Duna")
    dialog.input_authors.setText("Frank Herbert")
    dialog.auto_search_cover()
    assert dialog.cover_filename == "capa.jpg" and dialog.btn_remove_cover.isVisibleTo(dialog)
    monkeypatch.setattr(api_client, "auto_search_cover", lambda *a: None)
    dialog.auto_search_cover()
    assert "não encontrada" in dialog.lbl_cover_status.text()

    monkeypatch.setattr(api_client, "upload_cover_url", lambda url: "url.jpg" if "ok" in url else None)
    dialog.download_cover_url("https://ok/c.jpg")
    assert dialog.cover_filename == "url.jpg"
    dialog.download_cover_url("https://ruim/c.jpg")
    assert "Não foi possível" in dialog.lbl_cover_status.text()
    monkeypatch.setattr(bdc.QInputDialog, "getText", staticmethod(lambda *a, **k: ("https://ok/2.jpg", True)))
    dialog.choose_cover_url()

    image = tmp_path / "c.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(bdc.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(image), "")))
    monkeypatch.setattr(api_client, "upload_cover", lambda path: "file.png")
    dialog.choose_cover_image()
    assert dialog.cover_filename == "file.png"
    monkeypatch.setattr(api_client, "upload_cover", lambda path: None)
    dialog.choose_cover_image()
    assert no_popups[-1] == "warning"
    monkeypatch.setattr(bdc.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    dialog.choose_cover_image()

    dialog._on_cover_loaded("file.png")
    dialog.remove_cover()
    assert dialog.cover_filename is None and dialog.lbl_cover_preview.text() == "Sem\ncapa"
    dialog.update_cover_preview()
