from frontend_desktop.data_quality import autofill_gaps, is_incomplete, missing_fields
from frontend_desktop.views import book_status as bs

FULL = {"title": "Duna", "authors": [{"name": "Frank Herbert"}], "genres": [{"name": "Ficção"}],
        "cover_image": "a.jpg", "pages": 600, "status": "Lido", "score": 9, "finish_date": "2025-01-01"}


def test_text_helpers():
    book = {"authors": [{"name": "Terry Pratchett"}, {"name": "Neil Gaiman"}, {"name": ""}],
            "series": {"name": "Discworld"}, "series_number": 2.0, "pages": 300, "read_number": 3}
    assert bs.author_names(book) == "Terry Pratchett, Neil Gaiman"
    assert bs.main_author(book) == "Terry Pratchett" and bs.main_author({}) == ""
    assert bs.series_text(book) == "Discworld #2"
    assert bs.series_text({"series": {"name": "S"}}) == "S" and bs.series_text({}) == ""
    assert bs.pages_text(book) == "300 págs." and bs.pages_text({}) == ""
    assert bs.read_label(book) == "3ª leitura" and bs.read_label({}) == ""
    assert bs.filter_books("Lido", [FULL, {"status": "Lendo"}]) == [FULL]


def test_missing_fields():
    assert missing_fields(FULL) == [] and not is_incomplete(FULL)
    assert missing_fields({"status": "Lido"}) == ["autor", "gênero", "capa", "nº de páginas", "nota", "data de término"]
    assert "nº de páginas" not in missing_fields({"format": bs.AUDIOBOOK})
    assert missing_fields({**FULL, "status": "Quero Ler", "score": None}) == []


def test_autofill_gaps():
    complete = {**FULL, "publisher": {"name": "Ed"}, "isbn": "1", "language": "Português"}
    assert autofill_gaps(complete) == []
    assert autofill_gaps({}) == ["autor", "gênero", "capa", "páginas", "editora", "ISBN", "idioma"]
    assert "páginas" not in autofill_gaps({"format": bs.AUDIOBOOK})
