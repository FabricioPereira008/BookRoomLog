import asyncio

import httpx
import pytest
import respx

from backend.app.services import cover_service, lookup_service as ls

GOOGLE_PAYLOAD = {"items": [
    {"volumeInfo": {
        "title": "O Hobbit", "subtitle": "lá e de volta outra vez", "authors": ["J.R.R. Tolkien"],
        "publisher": "HarperCollins", "publishedDate": "2019-11-25", "pageCount": 336, "language": "pt-BR",
        "industryIdentifiers": [{"type": "ISBN_10", "identifier": "8595084742"},
                                {"type": "ISBN_13", "identifier": "9788595084742"}],
        "imageLinks": {"smallThumbnail": "http://books.google.com/s.jpg",
                       "thumbnail": "http://books.google.com/t.jpg?zoom=1&edge=curl"},
        "categories": ["Fiction"],
    }},
    {"volumeInfo": {"title": "Sem dados"}},
    {"volumeInfo": {}},
]}

OPEN_LIBRARY_PAYLOAD = {"docs": [
    {"title": "\x98O \x9cHobbit", "author_name": ["J.R.R. Tolkien"], "publisher": ["WMF Martins Fontes"],
     "number_of_pages_median": 297, "language": ["eng", "por"], "isbn": ["8533615540", "9788533615540", "lixo"],
     "first_publish_year": 1937, "cover_i": 123, "subject": ["Fantasy", "Dragons", "Elves", "Hobbits"]},
    {"title": "Outro", "language": ["spa"], "isbn": ["8533615540"]},
    {"title": None},
]}


def test_parse_google():
    results = ls.parse_google(GOOGLE_PAYLOAD)
    assert len(results) == 2
    first = results[0]
    assert first.title == "O Hobbit: lá e de volta outra vez"
    assert first.authors == ["J.R.R. Tolkien"] and first.publisher == "HarperCollins"
    assert (first.pages, first.language, first.isbn, first.published_year) == (336, "Português", "9788595084742", 2019)
    assert first.cover_url == "https://books.google.com/t.jpg?zoom=1"
    assert first.categories == ["Fiction"] and first.source == ls.SOURCE_GOOGLE
    assert results[1].cover_url is None and results[1].isbn is None and results[1].pages is None


def test_parse_open_library():
    results = ls.parse_open_library(OPEN_LIBRARY_PAYLOAD)
    assert len(results) == 2
    first = results[0]
    assert first.title == "O Hobbit"  # marcas MARC removidas
    assert (first.pages, first.language, first.isbn, first.published_year) == (297, "Português", "9788533615540", 1937)
    assert first.cover_url == "https://covers.openlibrary.org/b/id/123-L.jpg?default=false"
    assert first.categories == ["Fantasy", "Dragons", "Elves"]
    assert results[1].language == "Espanhol" and results[1].isbn == "8533615540" and results[1].cover_url is None


@pytest.mark.parametrize("text, expected", [
    ("978-85-9508-474-2", "9788595084742"), ("85 950 8474 x", "859508474X"), ("123", None), (None, None),
    ("X234567890", None),
])
def test_normalize_isbn(text, expected):
    assert ls.normalize_isbn(text) == expected


def test_language_name_and_clean_text():
    assert ls.language_name("EN") == "Inglês" and ls.language_name("tlh") == "tlh" and ls.language_name(None) is None
    assert ls.clean_text("\x98  ") is None and ls.clean_text(None) is None


def _run(coro):
    return asyncio.run(coro)


@respx.mock
def test_search_uses_google_with_title_author_and_key(monkeypatch):
    monkeypatch.setattr(ls.settings, "GOOGLE_BOOKS_API_KEY", "chave-padrao")
    route = respx.get(ls.GOOGLE_BOOKS_URL).mock(return_value=httpx.Response(200, json=GOOGLE_PAYLOAD))
    results = _run(ls.search_books("O Hobbit", author="Tolkien", limit=5))
    assert results[0].source == ls.SOURCE_GOOGLE
    params = route.calls.last.request.url.params
    assert params["q"] == "intitle:O Hobbit inauthor:Tolkien" and params["maxResults"] == "5"
    assert params["key"] == "chave-padrao"
    _run(ls.search_books("x", isbn="978-85-9508-474-2", api_key="minha"))
    params = route.calls.last.request.url.params
    assert params["q"] == "isbn:9788595084742" and params["key"] == "minha"


@respx.mock
def test_search_falls_back_to_open_library_on_error_or_empty():
    respx.get(ls.GOOGLE_BOOKS_URL).mock(return_value=httpx.Response(429))
    ol = respx.get(ls.OPEN_LIBRARY_URL).mock(return_value=httpx.Response(200, json=OPEN_LIBRARY_PAYLOAD))
    assert _run(ls.search_books("O Hobbit", author="Tolkien"))[0].source == ls.SOURCE_OPEN_LIBRARY
    params = ol.calls.last.request.url.params
    assert params["q"] == "O Hobbit Tolkien" and params["lang"] == "pt"
    _run(ls.search_books("", isbn="9788533615540"))
    assert ol.calls.last.request.url.params["isbn"] == "9788533615540"

    respx.get(ls.GOOGLE_BOOKS_URL).mock(return_value=httpx.Response(200, json={"totalItems": 0}))
    assert _run(ls.search_books("Nada"))[0].source == ls.SOURCE_OPEN_LIBRARY


@respx.mock
def test_search_single_source_and_nothing_found():
    google = respx.get(ls.GOOGLE_BOOKS_URL).mock(return_value=httpx.Response(200, json=GOOGLE_PAYLOAD))
    respx.get(ls.OPEN_LIBRARY_URL).mock(return_value=httpx.Response(200, json={"docs": []}))
    assert _run(ls.search_books("Hobbit", source="openlibrary")) == []
    assert not google.called
    respx.get(ls.GOOGLE_BOOKS_URL).mock(return_value=httpx.Response(200, text="não é json"))
    assert _run(ls.search_books("Hobbit")) == []


def test_lookup_endpoint(client, monkeypatch):
    from backend.app.api.v1.endpoints import lookup
    seen = {}

    async def fake_search(title, author=None, isbn=None, api_key=None, source=None, limit=10):
        seen.update(title=title, author=author, isbn=isbn, source=source, limit=limit)
        return ls.parse_google(GOOGLE_PAYLOAD)
    monkeypatch.setattr(lookup, "search_books", fake_search)

    res = client.get("/api/v1/lookup/", params={"title": " O Hobbit ", "author": " ", "source": "google", "limit": 3})
    assert res.status_code == 200 and res.json()["query"] == "O Hobbit"
    assert res.json()["results"][0]["isbn"] == "9788595084742"
    assert seen == {"title": "O Hobbit", "author": None, "isbn": None, "source": "google", "limit": 3}
    assert client.get("/api/v1/lookup/", params={"isbn": "123"}).json()["query"] == "123"
    assert client.get("/api/v1/lookup/").status_code == 422
    assert client.get("/api/v1/lookup/", params={"title": "x", "source": "amazon"}).status_code == 422


def test_find_cover_tries_candidates_in_order(monkeypatch):
    candidates = ls.parse_google(GOOGLE_PAYLOAD) + ls.parse_open_library(OPEN_LIBRARY_PAYLOAD)

    async def fake_search(title, author=None, isbn=None, api_key=None):
        return candidates
    tried = []

    async def fake_fetch(url):
        tried.append(url)
        if "books.google" in url:
            raise RuntimeError("timeout")
        return "capa.jpg"
    monkeypatch.setattr(cover_service, "search_books", fake_search)
    monkeypatch.setattr(cover_service, "fetch_cover_url", fake_fetch)
    assert _run(cover_service.find_cover("O Hobbit")) == ("capa.jpg", ls.SOURCE_OPEN_LIBRARY)
    assert len(tried) == 2

    async def none_fetch(url):
        return None
    monkeypatch.setattr(cover_service, "fetch_cover_url", none_fetch)
    assert _run(cover_service.find_cover("O Hobbit")) is None


@respx.mock
def test_fetch_cover_url_rejects_tiny_placeholders(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))])
    respx.get("https://img.example/mini.jpg").mock(return_value=httpx.Response(200, content=b"gif"))
    assert _run(cover_service.fetch_cover_url("https://img.example/mini.jpg")) is None
    respx.get("https://img.example/err.jpg").mock(return_value=httpx.Response(500))
    assert _run(cover_service.fetch_cover_url("https://img.example/err.jpg")) is None
