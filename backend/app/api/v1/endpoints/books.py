from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.book import BookStatus
from backend.app.schemas.book import (
    AutofillResponse, BookBrief, BookCreate, BookResponse, BookUpdate, NextOrderRequest,
)
from backend.app.services.autofill_service import autofill_book
from backend.app.services.book_service import BookService, NextOrderError, RereadLinkError

router = APIRouter()
NOT_FOUND = "Livro não encontrado"


class RereadRequest(BaseModel):
    status: BookStatus = BookStatus.LENDO


class AutofillRequest(BaseModel):
    api_key: Optional[str] = None


@router.get("/", response_model=List[BookResponse])
def list_books(
    status: Optional[BookStatus] = None,
    author_id: Optional[int] = None,
    genre_id: Optional[int] = None,
    series_id: Optional[int] = None,
    publisher_id: Optional[int] = None,
    completion_year: Optional[int] = None,
    is_favorite: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("title_asc", description="title_asc, title_desc, score_desc, pages_asc, finish_date_desc, next, recent"),
    db: Session = Depends(get_db),
):
    return BookService.get_books(
        db=db, status=status, author_id=author_id, genre_id=genre_id, series_id=series_id,
        publisher_id=publisher_id, completion_year=completion_year, is_favorite=is_favorite,
        search=search, sort_by=sort_by,
    )

@router.get("/brief", response_model=List[BookBrief])
def list_book_briefs(db: Session = Depends(get_db)):
    """Todos os livros em formato resumido (escolha do original de uma releitura, histórico de leituras)."""
    return BookService.get_briefs(db)

@router.put("/next-order", response_model=List[BookResponse])
def set_next_order(payload: NextOrderRequest, db: Session = Depends(get_db)):
    """Reordena a fila de Próximos (a lista deve conter todos os livros da fila)."""
    try:
        return BookService.set_next_order(db, payload.book_ids)
    except NextOrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@router.post("/", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(book_in: BookCreate, db: Session = Depends(get_db)):
    try:
        return BookService.create_book(db=db, book_in=book_in)
    except RereadLinkError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = BookService.get_book_by_id(db=db, book_id=book_id)
    if not book:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return book

@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: int, book_in: BookUpdate, db: Session = Depends(get_db)):
    try:
        book = BookService.update_book(db=db, book_id=book_id, book_in=book_in)
    except RereadLinkError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not book:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return book

@router.post("/{book_id}/reread", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_reread(book_id: int, payload: RereadRequest = RereadRequest(), db: Session = Depends(get_db)):
    """Começa uma nova leitura do livro (novo registro ligado ao original)."""
    book = BookService.create_reread(db, book_id, payload.status)
    if not book:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return book

@router.post("/{book_id}/autofill", response_model=AutofillResponse)
async def autofill(book_id: int, payload: AutofillRequest = AutofillRequest(), db: Session = Depends(get_db)):
    """Completa os campos vazios (autor, gênero, série, editora, páginas, idioma, ISBN, capa) pela busca online."""
    result = await autofill_book(db, book_id, payload.api_key)
    if result is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return result

@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    if not BookService.delete_book(db=db, book_id=book_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
