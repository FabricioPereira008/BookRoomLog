"""Busca de metadados de livros: Google Books (principal) e Open Library (alternativa)."""
import difflib
import logging
import re
import unicodedata
from typing import Iterable, List, Optional, Tuple

import httpx

from backend.app.core.config import settings
from backend.app.schemas.lookup import BookCandidate
from backend.app.services.genre_mapping import fold, map_genres, with_existing_spelling

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_COVER = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"
OPEN_LIBRARY_BASE = "https://openlibrary.org"
SOURCE_GOOGLE, SOURCE_OPEN_LIBRARY = "Google Books", "Open Library"
SOURCES = {"google": SOURCE_GOOGLE, "openlibrary": SOURCE_OPEN_LIBRARY}
DEFAULT_LIMIT = 10
TIMEOUT = 12.0
OPEN_LIBRARY_FIELDS = ("key,title,author_name,publisher,number_of_pages_median,language,isbn,first_publish_year,"
                       "cover_i,subject,editions,editions.title,editions.language,editions.isbn,"
                       "editions.publisher,editions.cover_i")
OPEN_LIBRARY_LANG = "pt"  # a edição devolvida junto com a obra é, de preferência, a em português
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


# "Título (Série #2)", "Título (Série, Vol. 2)", "Título (Série - Livro 2)"
SERIES_IN_PARENS = re.compile(
    r"\((?P<series>[^()#]+?)[\s,;:–-]*(?:#|n[º°o.]\s*|vol(?:ume)?\.?\s*|livro\s+|book\s+)\s*"
    r"(?P<number>\d+(?:[.,]\d+)?)\)\s*$", re.IGNORECASE)
# "Título - Volume 2" (só o número; o nome da série não dá para separar do título)
VOLUME_SUFFIX = re.compile(r"[-–:,]\s*(?:vol(?:ume)?\.?|livro|book)\s*(?P<number>\d+(?:[.,]\d+)?)\s*$",
                           re.IGNORECASE)
MIN_TITLE_SIMILARITY = 0.8


def series_from_title(title: Optional[str]) -> Tuple[Optional[str], Optional[float]]:
    """(série, volume) achados no título; (None, None) se não houver padrão."""
    title = title or ""
    match = SERIES_IN_PARENS.search(title)
    if match:
        return match.group("series").strip(" ,;:-–"), float(match.group("number").replace(",", "."))
    match = VOLUME_SUFFIX.search(title)
    if match:
        return None, float(match.group("number").replace(",", "."))
    return None, None


def series_from_subjects(subjects: Iterable[str]) -> Optional[str]:
    """A Open Library marca a série nos assuntos como "series:Harry_Potter"."""
    for subject in subjects or []:
        if subject and subject.lower().startswith("series:"):
            name = subject.split(":", 1)[1].replace("_", " ").strip()
            if name:
                return name
    return None


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
        series, number = series_from_title(title)
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
            genres=map_genres(info.get("categories") or []),
            series=series,
            series_number=number,
        ))
    return results


def _first_isbn(values) -> Optional[str]:
    isbns = [normalize_isbn(i) for i in values or []]
    return next((i for i in isbns if i and len(i) == 13), None) or next((i for i in isbns if i), None)


def parse_open_library(data: dict) -> List[BookCandidate]:
    """Cada resultado é uma obra; quando a busca traz a edição que casou (em português, de preferência),
    título, ISBN, editora, idioma e capa vêm dela. Gêneros, série e páginas vêm da obra."""
    results = []
    for doc in data.get("docs") or []:
        work_title = clean_text(doc.get("title"))
        edition = ((doc.get("editions") or {}).get("docs") or [{}])[0]
        title = clean_text(edition.get("title")) or work_title
        if not title:
            continue
        languages = edition.get("language") or doc.get("language") or []
        subjects = doc.get("subject") or []
        cover_id = edition.get("cover_i") or doc.get("cover_i")
        title_series, number = series_from_title(title)
        results.append(BookCandidate(
            source=SOURCE_OPEN_LIBRARY,
            title=title,
            original_title=work_title if work_title and fold(work_title) != fold(title) else None,
            authors=doc.get("author_name") or [],
            publisher=clean_text((edition.get("publisher") or doc.get("publisher") or [None])[0]),
            pages=doc.get("number_of_pages_median") or None,
            # Prefere português quando a obra tem edições em vários idiomas
            language=language_name("por" if "por" in languages else (languages[0] if languages else None)),
            isbn=_first_isbn(edition.get("isbn")) or _first_isbn(doc.get("isbn")),
            published_year=doc.get("first_publish_year"),
            cover_url=OPEN_LIBRARY_COVER.format(cover_id=cover_id) if cover_id else None,
            categories=[c for c in subjects if not c.lower().startswith("series:")][:3],
            genres=map_genres(subjects),
            series=series_from_subjects(subjects) or title_series,
            series_number=number,
            work_key=doc.get("key"),
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
    params = {"fields": OPEN_LIBRARY_FIELDS, "limit": limit, "lang": OPEN_LIBRARY_LANG}
    if isbn:
        params["isbn"] = isbn
    else:
        # Busca geral (e não title=): acha também edições traduzidas, como "Duna" (obra "Dune")
        params["q"] = " ".join(p for p in (title, author) if p)
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


async def enrich_series(client: httpx.AsyncClient, candidate: BookCandidate) -> BookCandidate:
    """Open Library: completa a série e o volume pela obra (/works/...json). Falhas são ignoradas."""
    if not candidate.work_key or (candidate.series and candidate.series_number is not None):
        return candidate
    try:
        res = await client.get(f"{OPEN_LIBRARY_BASE}{candidate.work_key}.json")
        res.raise_for_status()
        entries = res.json().get("series") or []
        entry = entries[0] if entries and isinstance(entries[0], dict) else {}
        if candidate.series_number is None and entry.get("position"):
            match = re.match(r"\d+(?:[.,]\d+)?", str(entry["position"]))
            if match:
                candidate.series_number = float(match.group().replace(",", "."))
        series_key = (entry.get("series") or {}).get("key")
        if not candidate.series and series_key:
            named = await client.get(f"{OPEN_LIBRARY_BASE}{series_key}.json")
            named.raise_for_status()
            candidate.series = clean_text(named.json().get("name"))
    except (httpx.HTTPError, ValueError, AttributeError):
        logger.info("Sem dados de série na Open Library para %s", candidate.work_key)
    if not candidate.series:
        candidate.series_number = None  # volume sem série não serve para nada
    return candidate


def _similarity(a: Optional[str], b: Optional[str]) -> float:
    clean = lambda t: " ".join(re.sub(r"[^a-z0-9 ]", " ", fold(t)).split())
    a, b = clean(a), clean(b)
    if not a or not b:
        return 0.0
    # "O Hobbit" x "O Hobbit: lá e de volta outra vez": o título digitado pode ser só o começo do da API
    if b.startswith(a) or a.startswith(b):
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _author_matches(author: Optional[str], authors: List[str]) -> bool:
    """Sem autor informado vale qualquer um; senão o sobrenome precisa aparecer em algum autor."""
    words = fold(author).replace(".", " ").split()
    if not words:
        return True
    return any(words[-1] in fold(name) for name in authors)


def best_match(candidates: List[BookCandidate], title: Optional[str] = None, author: Optional[str] = None,
               isbn: Optional[str] = None) -> Optional[BookCandidate]:
    """O resultado que com segurança é o mesmo livro (ISBN igual, ou título parecido e mesmo autor); senão None."""
    isbn = normalize_isbn(isbn)
    if isbn:
        exact = next((c for c in candidates if c.isbn == isbn), None)
        if exact:
            return exact
        if not title:  # busca só por ISBN: a API já filtrou pelo número
            return candidates[0] if candidates else None
    scored = [(max(_similarity(title, c.title), _similarity(title, c.original_title)), c)
              for c in candidates if _author_matches(author, c.authors)]
    scored = [(score, c) for score, c in scored if score >= MIN_TITLE_SIMILARITY]
    if not scored:
        return None
    # Empate: o que traz mais dados (capa, páginas, gêneros, série)
    richness = lambda c: sum(bool(x) for x in (c.cover_url, c.pages, c.genres, c.series, c.publisher, c.isbn))
    return max(scored, key=lambda sc: (round(sc[0], 2), richness(sc[1])))[1]


async def find_best(title: str, author: Optional[str] = None, isbn: Optional[str] = None,
                    api_key: Optional[str] = None, existing_genres: Iterable[str] = ()) -> Optional[BookCandidate]:
    """Melhor resultado já com a série completada e os gêneros na grafia dos que o usuário já tem."""
    candidates = await search_books(title, author=author, isbn=isbn, api_key=api_key)
    match = best_match(candidates, title, author, isbn)
    if match is None and isbn and title:  # ISBN sem resultado: tenta pelo título
        match = best_match(await search_books(title, author=author, api_key=api_key), title, author)
    if match is None:
        return None
    match.genres = with_existing_spelling(match.genres, existing_genres)
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        return await enrich_series(client, match)
