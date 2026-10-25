from pydantic import BaseModel, Field
from typing import List, Optional


class BookCandidate(BaseModel):
    """Um resultado da busca de metadados (Google Books / Open Library)."""
    source: str
    title: str
    original_title: Optional[str] = None  # título da obra, quando difere do da edição (ex.: "Dune" para "Duna")
    authors: List[str] = Field(default_factory=list)
    publisher: Optional[str] = None
    pages: Optional[int] = None
    language: Optional[str] = None  # nome em português (ex.: "Português")
    isbn: Optional[str] = None
    published_year: Optional[int] = None
    cover_url: Optional[str] = None
    categories: List[str] = Field(default_factory=list)  # como vieram da API (em inglês)
    genres: List[str] = Field(default_factory=list)      # traduzidos para os gêneros do app (até 2)
    series: Optional[str] = None
    series_number: Optional[float] = None
    work_key: Optional[str] = None                       # Open Library: /works/OL...W (série e posição)


class LookupResponse(BaseModel):
    query: str
    results: List[BookCandidate] = []
