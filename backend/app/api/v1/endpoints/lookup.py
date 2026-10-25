from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Query
from backend.app.schemas.lookup import LookupResponse
from backend.app.services.lookup_service import search_books

router = APIRouter()


@router.get("/", response_model=LookupResponse)
async def lookup_books(
    title: str = "",
    author: Optional[str] = None,
    isbn: Optional[str] = None,
    source: Optional[Literal["google", "openlibrary"]] = None,
    api_key: Optional[str] = None,
    limit: int = Query(10, ge=1, le=40),
):
    """Busca dados de livros (Google Books; Open Library se o Google não achar nada) por título/autor ou ISBN."""
    title, isbn = title.strip(), (isbn or "").strip()
    if not title and not isbn:
        raise HTTPException(status_code=422, detail="Informe o título ou o ISBN para buscar.")
    results = await search_books(title, author=(author or "").strip() or None, isbn=isbn or None,
                                 api_key=api_key, source=source, limit=limit)
    return LookupResponse(query=isbn or title, results=results)
