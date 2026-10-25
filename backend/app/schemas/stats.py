from pydantic import BaseModel, Field
from typing import List, Optional
from backend.app.schemas.book import BookResponse


class CountItem(BaseModel):
    name: str
    count: int
    pages: int = 0
    color: Optional[str] = None  # gêneros


class YearbookSummary(BaseModel):
    year: int
    total_books_read: int
    total_pages_read: int
    average_score: Optional[float] = None
    books: List[BookResponse] = []
    # Detalhes do ano
    previous_year_read: Optional[int] = None  # para comparar com o ano anterior
    monthly_read: List[int] = Field(default_factory=lambda: [0] * 12)  # jan..dez
    genres: List[CountItem] = []       # principal e secundário contam
    authors: List[CountItem] = []      # top 5
    series: List[CountItem] = []       # top 5
    formats: List[CountItem] = []
    average_pages: Optional[float] = None
    rereads: int = 0
    favorites: int = 0
    longest_book: Optional[BookResponse] = None
    shortest_book: Optional[BookResponse] = None
    best_book: Optional[BookResponse] = None
    # Pódio: escolhido pelo usuário ou, sem escolha, sugerido pela nota
    top3: List[BookResponse] = []
    top3_custom: bool = False


class Top3Request(BaseModel):
    book_ids: List[int] = Field(default_factory=list, max_length=3)  # na ordem (1º, 2º, 3º); vazio = sugestão


class StatusCounts(BaseModel):
    quero_ler: int = 0
    proximos: int = 0
    lendo: int = 0
    lidos: int = 0
    total: int = 0


class OverallStats(BaseModel):
    status_counts: StatusCounts
    total_pages_read: int
    available_years: List[int]
