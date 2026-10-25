from pydantic import BaseModel, Field
from typing import List, Optional


class BookCandidate(BaseModel):
    """Um resultado da busca de metadados (Google Books / Open Library)."""
    source: str
    title: str
    authors: List[str] = Field(default_factory=list)
    publisher: Optional[str] = None
    pages: Optional[int] = None
    language: Optional[str] = None  # nome em português (ex.: "Português")
    isbn: Optional[str] = None
    published_year: Optional[int] = None
    cover_url: Optional[str] = None
    categories: List[str] = Field(default_factory=list)


class LookupResponse(BaseModel):
    query: str
    results: List[BookCandidate] = []
