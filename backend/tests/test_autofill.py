import asyncio

import httpx
import pytest
import respx

from backend.app.schemas.lookup import BookCandidate
from backend.app.services import autofill_service, lookup_service as ls
from backend.app.services.genre_mapping import map_genres, with_existing_spelling

API = "/api/v1/books"


# --- gêneros ---
@pytest.mark.parametrize("categories, expected", [
    (["Juvenile Fiction / Fantasy & Magic"], ["Fantasia"]),
    (["Fiction / Science Fiction / General"], ["Ficção científica"]),  # "science" não vira Ciência
    (["Fiction"], ["Ficção"]),
    (["Romances"], ["Ficção"]),  # "romances" (gênero literário em inglês) não é romance
    (["series:Harry_Potter", "Magic", "Wizards", "Witches", "Juvenile fiction", "School stories",
      "Children's stories", "Ghosts"], ["Fantasia", "Infantojuvenil"]),
    (["Horror"] * 4 + ["Thriller"] * 3, ["Terror", "Suspense"]),
    (["Fantasy"] * 10 + ["Science fiction"] * 2, ["Fantasia"]),  # secundário irrelevante fica de fora
    (["True crime", "Crime"], ["Policial"]),
    ([], []),
    (["Cooking"], []),
])
def test_map_genres(categories, expected):
    assert map_genres(categories) == expected


def test_genres_use_existing_spelling():
    assert map_genres(["Fantasy"], ["fantasia", "Outro"]) == ["fantasia"]
    assert with_existing_spelling(["Ficção científica", "Terror"], ["FICCAO CIENTIFICA"]) == ["FICCAO CIENTIFICA", "Terror"]
    assert with_existing_spelling(["Terror"], None) == ["Terror"]


# --- série ---
@pytest.mark.parametrize("title, expected", [
    ("A Guerra dos Tronos (As Crônicas de Gelo e Fogo #1)", ("As Crônicas de Gelo e Fogo", 1.0)),
    ("Mistborn (Mistborn, Book 1)", ("Mistborn", 1.0)),
    ("O Silmarillion (Legendarium - Livro 2,5)", ("Legendarium", 2.5)),
    ("Duna - Volume 2", (None, 2.0)),
    ("Fundação", (None, None)),
    (None, (None, None)),
])
def test_series_from_title(title, expected):
    assert ls.series_from_title(title) == expected


def test_series_from_subjects():
    assert ls.series_from_subjects(["Magic", "series:Harry_Potter"]) == "Harry Potter"
    assert ls.series_from_subjects(["series:", "Magic"]) is None and ls.series_from_subjects(None) is None


def test_parse_open_library_prefers_matching_edition():
    data = {"docs": [{"key": "/works/OL1W", "title": "Dune", "author_name": ["Frank Herbert"],
                      "subject": ["Science fiction", "series:Dune", "Desert"], "number_of_pages_median": 608,
                      "cover_i": 1, "editions": {"docs": [{"title": "Duna", "language": ["por"],
                                                           "isbn": ["8576574942", "9788576574941"],
                                                           "publisher": ["Aleph"], "cover_i": 2}]}}]}
    candidate = ls.parse_open_library(data)[0]
    assert (candidate.title, candidate.original_title, candidate.publisher) == ("Duna", "Dune", "Aleph")
    assert candidate.isbn == "9788576574941" and candidate.language == "Português" and candidate.pages == 608
    assert candidate.genres == ["Ficção científica"] and candidate.series == "Dune"
    assert candidate.cover_url.endswith("/2-L.jpg?default=false") and candidate.work_key == "/works/OL1W"
    assert candidate.categories == ["Science fiction", "Desert"]


def test_parse_google_genres_and_series():
    data = {"items": [{"volumeInfo": {"title": "A Guerra dos Tronos (As Crônicas de Gelo e Fogo #1)",
                                      "categories": ["Fiction / Fantasy / Epic"]}}]}
    candidate = ls.parse_google(data)[0]
    assert candidate.genres == ["Fantasia"] and candidate.series == "As Crônicas de Gelo e Fogo"
    assert candidate.series_number == 1


# --- escolha segura ---
def cand(title, authors=("Frank Herbert",), **fields):
    return BookCandidate(source="Open Library", title=title, authors=list(authors), **fields)


def test_best_match():
    dune = cand("Duna", isbn="9788576574941", original_title="Dune")
    messiah = cand("Messias de Duna", isbn="9788576571162")
    assert ls.best_match([messiah, dune], "Duna", "Frank Herbert") is dune
    assert ls.best_match([messiah, dune], "Dune", None) is dune  # pelo título original
    assert ls.best_match([messiah, dune], "Qualquer", isbn="978-85-7657-116-2") is messiah  # ISBN vence
    assert ls.best_match([dune], None, isbn="9780000000002") is dune  # busca só por ISBN
    assert ls.best_match([], None, isbn="9780000000002") is None
    assert ls.best_match([dune], "Duna", "Isaac Asimov") is None  # autor diferente
    assert ls.best_match([messiah], "Fundação") is None
    assert ls.best_match([dune], "duna: edição especial") is dune  # um título é o começo do outro
    rich = cand("Duna", pages=600, cover_url="x", genres=["Ficção científica"])
    assert ls.best_match([cand("Duna"), rich], "Duna") is rich  # empate: o que traz mais dados
    assert ls._similarity(None, "x") == 0.0


@respx.mock
def test_enrich_series_from_work():
    respx.get("https://openlibrary.org/works/OL1W.json").mock(return_value=httpx.Response(
        200, json={"series": [{"series": {"key": "/series/OL9L"}, "position": "3."}]}))
    respx.get("https://openlibrary.org/series/OL9L.json").mock(return_value=httpx.Response(200, json={"name": "Duna"}))
    respx.get("https://openlibrary.org/works/OL2W.json").mock(return_value=httpx.Response(500))

    async def run(candidate):
        async with httpx.AsyncClient() as client:
            return await ls.enrich_series(client, candidate)
    enriched = asyncio.run(run(cand("Filhos de Duna", work_key="/works/OL1W")))
    assert (enriched.series, enriched.series_number) == ("Duna", 3.0)
    broken = asyncio.run(run(cand("X", work_key="/works/OL2W", series_number=2)))
    assert broken.series is None and broken.series_number is None  # volume sem série é descartado
    done = cand("Y", work_key="/works/OL3W", series="S", series_number=1)
    assert asyncio.run(run(done)) is done  # já completo: nem consulta


def test_find_best(monkeypatch):
    calls = []

    async def fake_search(title, author=None, isbn=None, api_key=None):
        calls.append(isbn)
        return [] if isbn else [cand("Duna", genres=["Ficção científica"])]

    async def fake_enrich(client, candidate):
        candidate.series = "Duna"
        return candidate
    monkeypatch.setattr(ls, "search_books", fake_search)
    monkeypatch.setattr(ls, "enrich_series", fake_enrich)
    found = asyncio.run(ls.find_best("Duna", "Frank Herbert", "9780000000002", None, ["ficção científica"]))
    assert calls == ["9780000000002", None]  # ISBN sem resultado: tenta pelo título
    assert found.genres == ["ficção científica"] and found.series == "Duna"
    assert asyncio.run(ls.find_best("Outro livro")) is None


# --- preenchimento de um livro cadastrado ---
@pytest.fixture
def candidate(monkeypatch):
    found = {"value": cand("Duna", publisher="Aleph", pages=608, language="Português", isbn="9788576574941",
                           genres=["Ficção científica"], series="Duna", series_number=1, cover_url="https://c/1.jpg")}
    seen = {}

    async def fake_find(title, author=None, isbn=None, api_key=None, existing_genres=()):
        seen.update(title=title, author=author, isbn=isbn, api_key=api_key, existing=list(existing_genres))
        return found["value"]

    async def fake_cover(url):
        return "capa.jpg"
    monkeypatch.setattr(autofill_service, "find_best", fake_find)
    monkeypatch.setattr(autofill_service, "fetch_cover_url", fake_cover)
    return found, seen


def test_autofill_fills_only_empty_fields(client, make_book, candidate):
    found, seen = candidate
    make_book(title="Outro", genres=["Fantasia"])
    book = make_book(title="Duna", authors=["Frank Herbert"], pages=500)
    res = client.post(f"{API}/{book['id']}/autofill", json={"api_key": "k"})
    assert res.status_code == 200
    data = res.json()
    assert data["filled"] == ["gênero", "editora", "série", "idioma", "ISBN", "capa"]
    assert data["source"] == "Open Library"
    filled = data["book"]
    assert filled["pages"] == 500  # já preenchido: não muda
    assert [a["name"] for a in filled["authors"]] == ["Frank Herbert"]
    assert [g["name"] for g in filled["genres"]] == ["Ficção científica"]
    assert (filled["series"]["name"], filled["series_number"]) == ("Duna", 1)
    assert filled["publisher"]["name"] == "Aleph" and filled["cover_image"] == "capa.jpg"
    assert seen == {"title": "Duna", "author": "Frank Herbert", "isbn": None, "api_key": "k",
                    "existing": ["Fantasia"]}

    again = client.post(f"{API}/{book['id']}/autofill").json()
    assert again["filled"] == []  # nada mais a completar


def test_autofill_volume_of_existing_series(client, make_book, candidate):
    book = make_book(title="Duna", authors=["Frank Herbert"], series="duna", genres=["X"], publisher="P",
                     pages=1, language="L", isbn="1", cover_image="c.jpg")
    assert client.post(f"{API}/{book['id']}/autofill").json()["filled"] == ["volume"]
    other = make_book(title="Duna", authors=["A"], series="Outra série", genres=["X"], publisher="P", pages=1,
                      language="L", isbn="1", cover_image="c.jpg")
    assert client.post(f"{API}/{other['id']}/autofill").json()["filled"] == []


def test_autofill_without_result_and_errors(client, make_book, candidate, monkeypatch):
    found, _ = candidate
    book = make_book(title="Desconhecido")
    found["value"] = None
    res = client.post(f"{API}/{book['id']}/autofill").json()
    assert res == {**res, "filled": [], "source": None} and res["book"]["id"] == book["id"]
    assert client.post(f"{API}/999/autofill").status_code == 404

    found["value"] = cand("Desconhecido", authors=["Autora " + "x" * 200], cover_url="https://c/2.jpg")

    async def broken_cover(url):
        raise RuntimeError("timeout")
    monkeypatch.setattr(autofill_service, "fetch_cover_url", broken_cover)
    res = client.post(f"{API}/{book['id']}/autofill").json()
    assert res["filled"] == ["autor"] and len(res["book"]["authors"][0]["name"]) == 150


def test_lookup_best_endpoint(client, make_book, monkeypatch):
    from backend.app.api.v1.endpoints import lookup
    make_book(title="x", genres=["fantasia"])
    seen = {}

    async def fake_find(title, author=None, isbn=None, api_key=None, existing_genres=()):
        seen.update(title=title, author=author, isbn=isbn, existing=list(existing_genres))
        return cand("Duna", genres=["fantasia"]) if title != "nada" else None
    monkeypatch.setattr(lookup.lookup_service, "find_best", fake_find)
    res = client.get("/api/v1/lookup/best", params={"title": " Duna ", "author": " "})
    assert res.status_code == 200 and res.json()["genres"] == ["fantasia"]
    assert seen == {"title": "Duna", "author": None, "isbn": None, "existing": ["fantasia"]}
    assert client.get("/api/v1/lookup/best", params={"title": "nada"}).status_code == 404
    assert client.get("/api/v1/lookup/best").status_code == 422
