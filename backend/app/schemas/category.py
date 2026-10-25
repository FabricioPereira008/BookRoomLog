from pydantic import BaseModel, ConfigDict, Field
from typing import List, Literal, Optional

# Páginas de categoria: "read" = só livros lidos (padrão), "all" = todos os livros
CategoryScope = Literal["read", "all"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    color: Optional[str] = None  # só gêneros


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    color: Optional[str] = None


class CategoryResponse(BaseModel):
    """Autor, gênero, editora ou série, com contagens."""
    id: int
    name: str
    color: Optional[str] = None
    books_count: int = 0
    read_count: int = 0       # livros lidos (igual a books_count no escopo "read")
    total_pages: int = 0      # páginas dos livros lidos
    cover_samples: List[str] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class NamedRef(BaseModel):
    """Referência curta a uma categoria dentro de um livro."""
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class GenreRef(NamedRef):
    color: Optional[str] = None
