"""Regras de negócio compartilhadas pelas categorias (autores, gêneros, editoras e séries)."""
from typing import Any, Callable, List, Optional, Type

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.author import Author
from backend.app.models.book import Book, BookStatus, book_authors, book_genres
from backend.app.models.genre import Genre
from backend.app.models.publisher import Publisher
from backend.app.models.series import Series
from backend.app.schemas.book import BookResponse
from backend.app.schemas.category import CategoryResponse

SCOPE_READ, SCOPE_ALL = "read", "all"  # páginas de categoria: só lidos ou todos os livros
MAX_COVER_SAMPLES = 4
DEFAULT_GENRE_COLOR = "#b45309"


class CategoryNotFoundError(Exception):
    pass


class CategoryConflictError(Exception):
    pass


class CategoryDetailResponse(BaseModel):
    id: int
    name: str
    category_type: str  # 'author', 'genre', 'publisher', 'series'
    color: Optional[str] = None
    total_books: int
    read_books: int = 0
    total_pages: int = 0
    books: List[BookResponse] = []


def find_by_name(db: Session, model: Type[Any], name: str):
    """Categoria com o mesmo nome, sem diferenciar maiúsculas (inclusive acentuadas)."""
    found = db.query(model).filter(model.name.ilike(name)).first()
    if found is None:  # o ILIKE do SQLite só ignora maiúsculas em ASCII ("ÉDITIONS" x "Éditions")
        key = name.casefold()
        found = next((obj for obj in db.query(model).all() if obj.name.casefold() == key), None)
    return found


def get_or_create(db: Session, model: Type[Any], name: str, **defaults):
    """Devolve a categoria `name` (criando se não existir); só faz flush, o commit é de quem chamou."""
    name = name.strip()
    obj = find_by_name(db, model, name)
    if obj is None:
        obj = model(name=name, **defaults)
        db.add(obj)
        db.flush()
    return obj


class CategoryService:
    """CRUD + contagens para uma categoria de livros.

    `book_filter(category_id)` retorna a condição SQLAlchemy que liga um Book à categoria;
    `rows(db)` devolve pares (category_id, Book) para as contagens.
    """
    link_table = None  # tabela associativa (só nas categorias muitos-para-muitos)

    def __init__(self, model: Type[Any], label: str, not_found: str, category_type: str,
                 book_filter: Callable[[int], Any], book_fk: Optional[Any] = None):
        self.model = model
        self.label = label
        self.not_found = not_found
        self.category_type = category_type
        self.book_filter = book_filter
        self.book_fk = book_fk

    # --- consultas ---
    def get(self, db: Session, category_id: int):
        obj = db.get(self.model, category_id)
        if not obj:
            raise CategoryNotFoundError(self.not_found)
        return obj

    def rows(self, db: Session) -> list:
        """Pares (category_id, Book) de todos os livros ligados a alguma categoria deste tipo."""
        return db.query(self.book_fk, Book).filter(self.book_fk.isnot(None)).all()

    def list_with_counts(self, db: Session, scope: str = SCOPE_READ) -> List[CategoryResponse]:
        """`scope="read"` conta/mostra só os lidos; `"all"` considera todos os livros."""
        summary: dict = {}
        # Lidos primeiro e com melhor nota: as capas de amostra são as dos favoritos da categoria
        ordered = sorted(self.rows(db), key=lambda r: (r[1].status != BookStatus.LIDO, -(r[1].score or 0), r[1].id))
        for category_id, book in ordered:
            done = book.status == BookStatus.LIDO
            if scope != SCOPE_ALL and not done:
                continue
            entry = summary.setdefault(category_id, {"books": 0, "read": 0, "pages": 0, "covers": []})
            entry["books"] += 1
            if done:
                entry["read"] += 1
                entry["pages"] += book.pages or 0
            if book.cover_image and len(entry["covers"]) < MAX_COVER_SAMPLES and book.cover_image not in entry["covers"]:
                entry["covers"].append(book.cover_image)
        results = []
        for obj in db.query(self.model).order_by(self.model.name.asc()).all():
            info = summary.get(obj.id, {})
            results.append(CategoryResponse(
                id=obj.id, name=obj.name, color=getattr(obj, "color", None),
                books_count=info.get("books", 0), read_count=info.get("read", 0),
                total_pages=info.get("pages", 0), cover_samples=info.get("covers", []),
            ))
        return results

    def details(self, db: Session, category_id: int, scope: str = SCOPE_READ) -> CategoryDetailResponse:
        obj = self.get(db, category_id)
        query = db.query(Book).filter(self.book_filter(category_id))
        if scope != SCOPE_ALL:
            query = query.filter(Book.status == BookStatus.LIDO)
        books = query.order_by(Book.finish_date.desc().nullslast(), Book.title.asc()).all()
        done = [b for b in books if b.status == BookStatus.LIDO]
        return CategoryDetailResponse(
            id=obj.id,
            name=obj.name,
            category_type=self.category_type,
            color=getattr(obj, "color", None),
            total_books=len(books),
            read_books=len(done),
            total_pages=sum(b.pages or 0 for b in done),
            books=[BookResponse.model_validate(b) for b in books],
        )

    # --- escrita ---
    def create(self, db: Session, name: str, color: Optional[str] = None):
        existing = find_by_name(db, self.model, name.strip())
        if existing:
            return existing
        obj = self.model(name=name.strip())
        if hasattr(obj, "color"):
            obj.color = color or DEFAULT_GENRE_COLOR
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, category_id: int, name: Optional[str] = None, color: Optional[str] = None):
        obj = self.get(db, category_id)
        if name is not None:
            duplicate = find_by_name(db, self.model, name.strip())
            if duplicate and duplicate.id != obj.id:
                raise CategoryConflictError(f"Já existe {self.label} com o nome '{name.strip()}'")
            obj.name = name.strip()
        if color is not None and hasattr(obj, "color"):
            obj.color = color.strip()
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise CategoryConflictError(f"Já existe {self.label} com esse nome")
        db.refresh(obj)
        return obj

    def delete(self, db: Session, category_id: int) -> None:
        obj = self.get(db, category_id)
        if self.book_fk is not None and self.link_table is None:
            # Desvincula os livros antes de remover (a FK não tem ON DELETE)
            db.query(Book).filter(self.book_fk == category_id).update({self.book_fk: None}, synchronize_session=False)
        db.delete(obj)
        db.commit()


class LinkedCategoryService(CategoryService):
    """Categorias muitos-para-muitos (autores e gêneros), ligadas por uma tabela associativa."""

    def __init__(self, model, label, not_found, category_type, relation, link_table, link_column):
        super().__init__(model, label, not_found, category_type,
                         book_filter=lambda cid: relation.any(model.id == cid), book_fk=link_column)
        self.link_table = link_table

    def rows(self, db: Session) -> list:
        return (db.query(self.book_fk, Book)
                .join(self.link_table, self.link_table.c.book_id == Book.id).all())


author_service = LinkedCategoryService(
    Author, "um autor", "Autor não encontrado", "author",
    Book.authors, book_authors, book_authors.c.author_id,
)
genre_service = LinkedCategoryService(
    Genre, "um gênero", "Gênero não encontrado", "genre",
    Book.genres, book_genres, book_genres.c.genre_id,
)
publisher_service = CategoryService(
    Publisher, "uma editora", "Editora não encontrada", "publisher",
    book_filter=lambda pid: Book.publisher_id == pid, book_fk=Book.publisher_id,
)
series_service = CategoryService(
    Series, "uma série", "Série não encontrada", "series",
    book_filter=lambda sid: Book.series_id == sid, book_fk=Book.series_id,
)

SERVICES = {
    "authors": author_service,
    "genres": genre_service,
    "publishers": publisher_service,
    "series": series_service,
}
