from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date, datetime
from backend.app.models.book import BookStatus, BookFormat
from backend.app.schemas.category import GenreRef, NamedRef

MAX_AUTHORS = 6
MAX_GENRES = 2  # gênero principal + secundário (a ordem da lista define qual é qual)
NAME_MAX = 150


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    status: BookStatus = BookStatus.QUERO_LER
    cover_image: Optional[str] = None
    series_number: Optional[float] = Field(default=None, ge=0)
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    pages: Optional[int] = Field(default=None, ge=0)
    format: BookFormat = BookFormat.EBOOK
    language: Optional[str] = Field(default=None, max_length=40)
    isbn: Optional[str] = Field(default=None, max_length=20)
    score: Optional[float] = Field(default=None, ge=0, le=10)
    finish_date: Optional[date] = None
    reread_of_id: Optional[int] = None  # registro original desta releitura
    read_number: int = Field(default=1, ge=1)
    is_favorite: bool = False
    notes: Optional[str] = None


class BookCreate(BookBase):
    # Categorias por nome: nomes novos são criados (sem diferenciar maiúsculas dos existentes)
    authors: List[str] = Field(default_factory=list, max_length=MAX_AUTHORS)
    genres: List[str] = Field(default_factory=list, max_length=MAX_GENRES)
    publisher: Optional[str] = Field(default=None, max_length=NAME_MAX)
    series: Optional[str] = Field(default=None, max_length=NAME_MAX)


class BookUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    status: Optional[BookStatus] = None
    cover_image: Optional[str] = None
    series_number: Optional[float] = Field(default=None, ge=0)
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    pages: Optional[int] = Field(default=None, ge=0)
    format: Optional[BookFormat] = None
    language: Optional[str] = Field(default=None, max_length=40)
    isbn: Optional[str] = Field(default=None, max_length=20)
    score: Optional[float] = Field(default=None, ge=0, le=10)
    finish_date: Optional[date] = None
    reread_of_id: Optional[int] = None
    read_number: Optional[int] = Field(default=None, ge=1)
    is_favorite: Optional[bool] = None
    notes: Optional[str] = None
    authors: Optional[List[str]] = Field(default=None, max_length=MAX_AUTHORS)
    genres: Optional[List[str]] = Field(default=None, max_length=MAX_GENRES)
    publisher: Optional[str] = Field(default=None, max_length=NAME_MAX)
    series: Optional[str] = Field(default=None, max_length=NAME_MAX)


class BookResponse(BookBase):
    # Respostas não revalidam limites: dados legados/importados podem estar fora da faixa
    title: str
    score: Optional[float] = None
    progress: Optional[int] = None
    pages: Optional[int] = None
    read_number: int = 1
    id: int
    next_position: Optional[int] = None
    completion_year: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    authors: List[NamedRef] = []
    genres: List[GenreRef] = []
    publisher: Optional[NamedRef] = None
    series: Optional[NamedRef] = None
    rereads_count: int = 0  # no registro original: quantas releituras estão vinculadas a ele

    model_config = ConfigDict(from_attributes=True)


class BookBrief(BaseModel):
    """Resumo leve de um livro (escolha do original de uma releitura e histórico de leituras)."""
    id: int
    title: str
    status: BookStatus
    author: Optional[str] = None
    read_number: int = 1
    reread_of_id: Optional[int] = None
    finish_date: Optional[date] = None
    score: Optional[float] = None


class NextOrderRequest(BaseModel):
    """Ordem completa da fila de Próximos (ids na ordem desejada)."""
    book_ids: List[int] = Field(default_factory=list)
