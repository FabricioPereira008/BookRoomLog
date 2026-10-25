from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_, desc, asc, update, func
from backend.app.models.author import Author
from backend.app.models.book import Book, BookStatus, book_authors, book_genres
from backend.app.models.genre import Genre
from backend.app.models.publisher import Publisher
from backend.app.models.series import Series
from backend.app.schemas.book import BookCreate, BookUpdate
from backend.app.services.category_service import DEFAULT_GENRE_COLOR, get_or_create
from backend.app.services.cover_service import discard_cover_if_unused

MAX_REREAD_DEPTH = 50  # proteção contra ciclos em dados antigos/corrompidos
CATEGORY_KEYS = ("authors", "genres", "publisher", "series")
# Campos copiados do livro original quando uma releitura é criada a partir dele
REREAD_COPY_FIELDS = ("title", "cover_image", "series_number", "pages", "format", "language", "isbn",
                      "publisher_id", "series_id")

SORTS = {
    "title_asc": (asc(Book.title),),
    "title_desc": (desc(Book.title),),
    "score_desc": (desc(Book.score).nullslast(),),
    "pages_asc": (asc(Book.pages).nullslast(),),
    "finish_date_desc": (desc(Book.finish_date).nullslast(),),
    "next": (asc(Book.next_position).nullslast(),),
    "recent": (desc(Book.updated_at),),
}


class RereadLinkError(Exception):
    """Vínculo de releitura inválido (vira 422 na API)."""


class NextOrderError(Exception):
    """Ordem da fila de Próximos inválida (vira 422 na API)."""


def _with_relations(query):
    return query.options(
        selectinload(Book.authors), selectinload(Book.genres),
        selectinload(Book.publisher), selectinload(Book.series),
    )


class BookService:
    # --- releituras ---
    @staticmethod
    def attach_reread_counts(db: Session, books: List[Book]) -> List[Book]:
        """Preenche `rereads_count` (releituras vinculadas a cada registro) com uma única consulta."""
        if not books:
            return books
        query = db.query(Book.reread_of_id, func.count(Book.id)).filter(Book.reread_of_id.isnot(None))
        if len(books) <= 500:
            query = query.filter(Book.reread_of_id.in_([b.id for b in books]))
        counts = dict(query.group_by(Book.reread_of_id).all())
        for book in books:
            book.rereads_count = counts.get(book.id, 0)
        return books

    @staticmethod
    def reread_root(db: Session, book: Book) -> Book:
        """Registro original (1ª leitura) do grupo de leituras de `book`."""
        current = book
        for _ in range(MAX_REREAD_DEPTH):
            if current.reread_of_id is None:
                return current
            parent = db.get(Book, current.reread_of_id)
            if parent is None:
                return current
            current = parent
        return current

    @staticmethod
    def _next_read_number(db: Session, root: Book) -> int:
        group = db.query(func.max(Book.read_number)).filter(
            or_(Book.id == root.id, Book.reread_of_id == root.id)).scalar()
        return (group or 1) + 1

    @staticmethod
    def _link_reread(db: Session, data: dict, book_id: Optional[int] = None) -> None:
        """Valida `reread_of_id`, aponta para o registro original e garante um nº de leitura ≥ 2."""
        if "reread_of_id" not in data:
            return
        target_id = data["reread_of_id"]
        if target_id is None:
            if "read_number" not in data:
                data["read_number"] = 1  # deixou de ser releitura
            return
        if target_id == book_id:
            raise RereadLinkError("Um livro não pode ser releitura de si mesmo")
        target = db.get(Book, target_id)
        if target is None:
            raise RereadLinkError("Livro original não encontrado")
        root = BookService.reread_root(db, target)
        if book_id is not None and root.id == book_id:
            raise RereadLinkError("Este livro já é o original desse grupo de leituras")
        data["reread_of_id"] = root.id
        if (data.get("read_number") or 1) < 2:
            current = db.get(Book, book_id) if book_id is not None else None
            if current is not None and current.reread_of_id == root.id and current.read_number >= 2:
                data["read_number"] = current.read_number  # já era desse grupo: mantém o número
            else:
                data["read_number"] = BookService._next_read_number(db, root)

    # --- consultas ---
    @staticmethod
    def get_briefs(db: Session) -> List[dict]:
        rows = db.query(Book).options(selectinload(Book.authors)).order_by(asc(Book.title), asc(Book.id)).all()
        return [{
            "id": b.id, "title": b.title, "status": b.status,
            "author": b.authors[0].name if b.authors else None,
            "read_number": b.read_number, "reread_of_id": b.reread_of_id,
            "finish_date": b.finish_date, "score": b.score,
        } for b in rows]

    @staticmethod
    def get_books(
        db: Session,
        status: Optional[BookStatus] = None,
        author_id: Optional[int] = None,
        genre_id: Optional[int] = None,
        series_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        completion_year: Optional[int] = None,
        is_favorite: Optional[bool] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = "title_asc",
    ) -> List[Book]:
        query = _with_relations(db.query(Book))
        if status:
            query = query.filter(Book.status == status)
        if author_id:
            query = query.filter(Book.authors.any(Author.id == author_id))
        if genre_id:
            query = query.filter(Book.genres.any(Genre.id == genre_id))
        if series_id:
            query = query.filter(Book.series_id == series_id)
        if publisher_id:
            query = query.filter(Book.publisher_id == publisher_id)
        if completion_year:
            query = query.filter(Book.completion_year == completion_year)
        if is_favorite is not None:
            query = query.filter(Book.is_favorite == is_favorite)
        if search:
            term = f"%{search}%"
            query = query.filter(or_(Book.title.ilike(term), Book.authors.any(Author.name.ilike(term))))
        query = query.order_by(*SORTS.get(sort_by or "", SORTS["title_asc"]), asc(Book.id))
        return BookService.attach_reread_counts(db, query.all())

    @staticmethod
    def get_book_by_id(db: Session, book_id: int) -> Optional[Book]:
        book = _with_relations(db.query(Book)).filter(Book.id == book_id).first()
        if book is not None:
            BookService.attach_reread_counts(db, [book])
        return book

    # --- categorias por nome ---
    @staticmethod
    def _clean_names(names) -> List[str]:
        """Nomes preenchidos, sem repetir (sem diferenciar maiúsculas), na ordem recebida."""
        seen, out = set(), []
        for name in names or []:
            name = (name or "").strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                out.append(name)
        return out

    @staticmethod
    def _set_ordered(db: Session, book: Book, relation: str, table, column, items: list) -> None:
        """Grava a lista na ordem recebida (1º = principal) usando a coluna `position`."""
        setattr(book, relation, items)
        db.flush()
        for position, item in enumerate(items):
            db.execute(
                update(table).where(table.c.book_id == book.id, column == item.id).values(position=position)
            )
        db.expire(book, [relation])  # recarrega já na ordem de position

    @staticmethod
    def _apply_categories(db: Session, book: Book, categories: dict) -> None:
        """Só mexe nas chaves presentes (serve para create e update parcial)."""
        if "publisher" in categories:
            name = (categories["publisher"] or "").strip()
            book.publisher_id = get_or_create(db, Publisher, name).id if name else None
        if "series" in categories:
            name = (categories["series"] or "").strip()
            book.series_id = get_or_create(db, Series, name).id if name else None
        if categories.get("authors") is not None:
            authors = [get_or_create(db, Author, n) for n in BookService._clean_names(categories["authors"])]
            BookService._set_ordered(db, book, "authors", book_authors, book_authors.c.author_id, authors)
        if categories.get("genres") is not None:
            genres = [get_or_create(db, Genre, n, color=DEFAULT_GENRE_COLOR)
                      for n in BookService._clean_names(categories["genres"])]
            BookService._set_ordered(db, book, "genres", book_genres, book_genres.c.genre_id, genres)

    # --- regras de status ---
    @staticmethod
    def _apply_status_rules(db: Session, book: Book) -> None:
        """Nota e término só valem para Lido; progresso só para Lendo; posição na fila só para Próximo."""
        if book.status == BookStatus.LIDO:
            book.finish_date = book.finish_date or date.today()
            book.completion_year = book.finish_date.year
        else:
            book.finish_date = None
            book.completion_year = None
            book.score = None
        if book.status != BookStatus.LENDO:
            book.progress = None
        if book.status == BookStatus.PROXIMO:
            if book.next_position is None:
                last = db.query(func.max(Book.next_position)).filter(
                    Book.status == BookStatus.PROXIMO, Book.id != book.id).scalar()
                book.next_position = (last or 0) + 1
        else:
            book.next_position = None

    @staticmethod
    def _renumber_next(db: Session) -> None:
        """Fila de Próximos sempre numerada de 1 a N, sem buracos."""
        queue = db.query(Book).filter(Book.status == BookStatus.PROXIMO).order_by(
            asc(Book.next_position).nullslast(), asc(Book.id)).all()
        for position, book in enumerate(queue, 1):
            book.next_position = position

    # --- escrita ---
    @staticmethod
    def create_book(db: Session, book_in: BookCreate) -> Book:
        data = book_in.model_dump()
        categories = {k: data.pop(k) for k in CATEGORY_KEYS}
        BookService._link_reread(db, data)
        db_book = Book(**data)
        db.add(db_book)
        db.flush()
        BookService._apply_categories(db, db_book, categories)
        BookService._apply_status_rules(db, db_book)
        db.flush()
        BookService._renumber_next(db)
        db.commit()
        return BookService.get_book_by_id(db, db_book.id)

    @staticmethod
    def update_book(db: Session, book_id: int, book_in: BookUpdate) -> Optional[Book]:
        db_book = db.get(Book, book_id)
        if not db_book:
            return None
        data = book_in.model_dump(exclude_unset=True)
        categories = {k: data.pop(k) for k in CATEGORY_KEYS if k in data}
        old_cover = db_book.cover_image

        BookService._link_reread(db, data, book_id)
        if data.get("reread_of_id") is not None:
            # Era o original de outras leituras: elas passam para o novo original
            db.query(Book).filter(Book.reread_of_id == book_id).update(
                {Book.reread_of_id: data["reread_of_id"]}, synchronize_session=False)

        for key, value in data.items():
            setattr(db_book, key, value)
        BookService._apply_categories(db, db_book, categories)
        BookService._apply_status_rules(db, db_book)
        db.flush()
        BookService._renumber_next(db)
        db.commit()
        if old_cover and old_cover != db_book.cover_image:
            discard_cover_if_unused(db, old_cover)  # capa trocada: o arquivo antigo não serve mais
        return BookService.get_book_by_id(db, book_id)

    @staticmethod
    def create_reread(db: Session, book_id: int, status: BookStatus = BookStatus.LENDO) -> Optional[Book]:
        """Nova leitura de um livro: copia os dados da edição, autores e gêneros e liga ao original."""
        source = BookService.get_book_by_id(db, book_id)
        if source is None:
            return None
        root = BookService.reread_root(db, source)
        reread = Book(**{f: getattr(source, f) for f in REREAD_COPY_FIELDS}, status=status,
                      reread_of_id=root.id, read_number=BookService._next_read_number(db, root))
        db.add(reread)
        db.flush()
        BookService._set_ordered(db, reread, "authors", book_authors, book_authors.c.author_id, list(source.authors))
        BookService._set_ordered(db, reread, "genres", book_genres, book_genres.c.genre_id, list(source.genres))
        BookService._apply_status_rules(db, reread)
        db.flush()
        BookService._renumber_next(db)
        db.commit()
        return BookService.get_book_by_id(db, reread.id)

    @staticmethod
    def set_next_order(db: Session, book_ids: List[int]) -> List[Book]:
        """Reordena a fila de Próximos; `book_ids` precisa ter exatamente os livros da fila."""
        queue = {b.id: b for b in db.query(Book).filter(Book.status == BookStatus.PROXIMO).all()}
        if len(set(book_ids)) != len(book_ids) or set(book_ids) != set(queue):
            raise NextOrderError("A nova ordem precisa conter exatamente os livros marcados como Próximo")
        for position, book_id in enumerate(book_ids, 1):
            queue[book_id].next_position = position
        db.commit()
        return BookService.get_books(db, status=BookStatus.PROXIMO, sort_by="next")

    @staticmethod
    def delete_book(db: Session, book_id: int) -> bool:
        db_book = db.get(Book, book_id)
        if not db_book:
            return False
        cover = db_book.cover_image
        rereads = db.query(Book).filter(Book.reread_of_id == book_id).order_by(
            asc(Book.read_number), asc(Book.id)).all()
        if rereads:  # o original saiu: a leitura mais antiga que sobrou vira o original do grupo
            new_root, others = rereads[0], rereads[1:]
            new_root.reread_of_id = None
            for reread in others:
                reread.reread_of_id = new_root.id
            db.flush()
        db.delete(db_book)
        db.flush()
        BookService._renumber_next(db)
        db.commit()
        discard_cover_if_unused(db, cover)
        return True
