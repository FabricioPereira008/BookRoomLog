"""Busca de metadados de livros: Google Books (principal) e Open Library (alternativa)."""
import logging
import re
import unicodedata
from typing import List, Optional

import httpx

from backend.app.core.config import settings
from backend.app.schemas.lookup import BookCandidate

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_COVER = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"
SOURCE_GOOGLE, SOURCE_OPEN_LIBRARY = "Google Books", "Open Library"
SOURCES = {"google": SOURCE_GOOGLE, "openlibrary": SOURCE_OPEN_LIBRARY}
DEFAULT_LIMIT = 10
TIMEOUT = 12.0
OPEN_LIBRARY_FIELDS = "title,author_name,publisher,number_of_pages_median,language,isbn,first_publish_year,cover_i,subject"
# Maiores primeiro: a busca do Google costuma trazer só as miniaturas
GOOGLE_IMAGE_KEYS = ("extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail")

# Códigos ISO 639-1 (Google) e 639-2 (Open Library) -> nome mostrado no app
LANGUAGES = {
    "pt": "Português", "por": "Português", "en": "Inglês", "eng": "Inglês", "es": "Espanhol", "spa": "Espanhol",
    "fr": "Francês", "fre": "Francês", "fra": "Francês", "de": "Alemão", "ger": "Alemão", "deu": "Alemão",
    "it": "Italiano", "ita": "Italiano", "ja": "Japonês", "jpn": "Japonês",
}


def language_name(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return LANGUAGES.get(code.lower().split("-")[0], code)


def normalize_isbn(text: Optional[str]) -> Optional[str]:
    """Só dígitos (e X final do ISBN-10); None se não tiver o tamanho de um ISBN."""
    cleaned = re.sub(r"[^0-9Xx]", "", text or "").upper()
    return cleaned if len(cleaned) in (10, 13) and "X" not in cleaned[:-1] else None


def clean_text(text: Optional[str]) -> Optional[str]:
    """Remove caracteres de controle (a Open Library traz marcas MARC como \x98 e \x9c nos títulos)."""
    if not text:
        return None
    cleaned = "".join(c for c in text if unicodedata.category(c) != "Cc").strip()
    return cleaned or None


def _year(text) -> Optional[int]:
    match = re.match(r"\d{4}", str(text or ""))
    return int(match.group()) if match else None


def _https(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url.replace("http://", "https://", 1).replace("&edge=curl", "")


def parse_google(data: dict) -> List[BookCandidate]:
    results = []
    for item in data.get("items") or []:
        info = item.get("volumeInfo") or {}
        if not clean_text(info.get("title")):
            continue
        title = clean_text(info["title"]) + (f": {clean_text(info['subtitle'])}" if info.get("subtitle") else "")
        ids = {i.get("type"): i.get("identifier") for i in info.get("industryIdentifiers") or []}
        images = info.get("imageLinks") or {}
        cover = next((images[k] for k in GOOGLE_IMAGE_KEYS if images.get(k)), None)
        results.append(BookCandidate(
            source=SOURCE_GOOGLE,
            title=title,
            authors=info.get("authors") or [],
            publisher=clean_text(info.get("publisher")),
            pages=info.get("pageCount") or None,
            language=language_name(info.get("language")),
            isbn=normalize_isbn(ids.get("ISBN_13") or ids.get("ISBN_10")),
            published_year=_year(info.get("publishedDate")),
            cover_url=_https(cover),
            categories=info.get("categories") or [],
        ))
    return results


def parse_open_library(data: dict) -> List[BookCandidate]:
    results = []
    for doc in data.get("docs") or []:
        title = clean_text(doc.get("title"))
        if not title:
            continue
        isbns = [normalize_isbn(i) for i in doc.get("isbn") or []]
        isbn = next((i for i in isbns if i and len(i) == 13), None) or next((i for i in isbns if i), None)
        languages = doc.get("language") or []
        results.append(BookCandidate(
            source=SOURCE_OPEN_LIBRARY,
            title=title,
            authors=doc.get("author_name") or [],
            publisher=clean_text((doc.get("publisher") or [None])[0]),
            pages=doc.get("number_of_pages_median") or None,
            # Prefere português quando a obra tem edições em vários idiomas
            language=language_name("por" if "por" in languages else (languages[0] if languages else None)),
            isbn=isbn,
            published_year=doc.get("first_publish_year"),
            cover_url=OPEN_LIBRARY_COVER.format(cover_id=doc["cover_i"]) if doc.get("cover_i") else None,
            categories=(doc.get("subject") or [])[:3],
        ))
    return results


async def search_google(client: httpx.AsyncClient, title: str, author: Optional[str] = None,
                        isbn: Optional[str] = None, api_key: Optional[str] = None,
                        limit: int = DEFAULT_LIMIT) -> List[BookCandidate]:
    if isbn:
        query = f"isbn:{isbn}"
    else:
        query = f"intitle:{title}" + (f" inauthor:{author}" if author else "")
    params = {"q": query, "maxResults": limit, "printType": "books"}
    key = api_key or settings.GOOGLE_BOOKS_API_KEY
    if key:
        params["key"] = key
    res = await client.get(GOOGLE_BOOKS_URL, params=params)
    res.raise_for_status()
    return parse_google(res.json())


async def search_open_library(client: httpx.AsyncClient, title: str, author: Optional[str] = None,
                              isbn: Optional[str] = None, limit: int = DEFAULT_LIMIT) -> List[BookCandidate]:
    params = {"fields": OPEN_LIBRARY_FIELDS, "limit": limit}
    if isbn:
        params["isbn"] = isbn
    else:
        params["title"] = title
        if author:
            params["author"] = author
    res = await client.get(OPEN_LIBRARY_URL, params=params, headers={"User-Agent": "BookRoomLog (app pessoal)"})
    res.raise_for_status()
    return parse_open_library(res.json())


async def search_books(title: str, author: Optional[str] = None, isbn: Optional[str] = None,
                       api_key: Optional[str] = None, source: Optional[str] = None,
                       limit: int = DEFAULT_LIMIT) -> List[BookCandidate]:
    """Busca por ISBN (se válido) ou título + autor.

    Sem `source`, tenta o Google Books e só recorre à Open Library se ele falhar ou não achar nada.
    """
    isbn = normalize_isbn(isbn)
    order = [source] if source in SOURCES else list(SOURCES)
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for name in order:
            try:
                if name == "google":
                    results = await search_google(client, title, author, isbn, api_key, limit)
                else:
                    results = await search_open_library(client, title, author, isbn, limit)
            except (httpx.HTTPError, ValueError) as exc:  # ex.: 429 do Google sem chave; tenta a próxima fonte
                logger.warning("Falha na busca de metadados (%s) para '%s': %s", SOURCES[name], title or isbn, exc)
                continue
            if results:
                return results
    return []
