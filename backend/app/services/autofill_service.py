"""Preenchimento automático dos dados de um livro já cadastrado (só os campos vazios)."""
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app.models.genre import Genre
from backend.app.schemas.book import MAX_AUTHORS, NAME_MAX, BookUpdate
from backend.app.services.book_service import BookService
from backend.app.services.cover_service import fetch_cover_url
from backend.app.services.genre_mapping import fold
from backend.app.services.lookup_service import find_best

logger = logging.getLogger(__name__)


def genre_names(db: Session) -> List[str]:
    return [name for (name,) in db.query(Genre.name).all()]


def _name(text: str) -> str:
    return text.strip()[:NAME_MAX]


async def autofill_book(db: Session, book_id: int, api_key: Optional[str] = None) -> Optional[dict]:
    """Busca o livro (ISBN, ou título + 1º autor) e completa o que estiver vazio.

    Devolve {"book", "filled" (nomes legíveis do que foi preenchido), "source"} ou None se o livro não existe.
    Nada que já está preenchido é trocado; sem um resultado seguro, nada muda.
    """
    book = BookService.get_book_by_id(db, book_id)
    if book is None:
        return None
    author = book.authors[0].name if book.authors else None
    candidate = await find_best(book.title, author, book.isbn, api_key, genre_names(db))
    if candidate is None:
        return {"book": book, "filled": [], "source": None}

    changes, filled = {}, []
    if not book.authors and candidate.authors:
        changes["authors"] = [_name(a) for a in candidate.authors[:MAX_AUTHORS]]
        filled.append("autor")
    if not book.genres and candidate.genres:
        changes["genres"] = candidate.genres
        filled.append("gênero")
    if not book.publisher_id and candidate.publisher:
        changes["publisher"] = _name(candidate.publisher)
        filled.append("editora")
    if not book.series_id and candidate.series:
        changes["series"] = _name(candidate.series)
        filled.append("série")
        if book.series_number is None and candidate.series_number is not None:
            changes["series_number"] = candidate.series_number
    elif (book.series_id and book.series_number is None and candidate.series_number is not None
          and fold(candidate.series) == fold(book.series.name)):
        changes["series_number"] = candidate.series_number
        filled.append("volume")
    if not book.pages and candidate.pages:
        changes["pages"] = candidate.pages
        filled.append("páginas")
    if not book.language and candidate.language:
        changes["language"] = candidate.language[:40]
        filled.append("idioma")
    if not book.isbn and candidate.isbn:
        changes["isbn"] = candidate.isbn
        filled.append("ISBN")
    if not book.cover_image and candidate.cover_url:
        try:
            cover = await fetch_cover_url(candidate.cover_url)
        except Exception:
            logger.warning("Falha ao baixar a capa de '%s'", book.title, exc_info=True)
            cover = None
        if cover:
            changes["cover_image"] = cover
            filled.append("capa")

    if changes:
        book = BookService.update_book(db, book_id, BookUpdate(**changes))
    return {"book": book, "filled": filled, "source": candidate.source}
