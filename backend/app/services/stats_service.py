from collections import Counter
from datetime import date
from typing import Dict, List
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from backend.app.models.book import Book, BookStatus
from backend.app.models.yearbook import YearbookPick
from backend.app.schemas.book import BookResponse
from backend.app.schemas.stats import CountItem, YearbookSummary, StatusCounts, OverallStats


class InvalidTop3Error(Exception):
    pass


def _ranked(items: Dict[str, CountItem], limit: int = 0) -> List[CountItem]:
    out = sorted(items.values(), key=lambda i: (-i.count, -i.pages, i.name.casefold()))
    return out[:limit] if limit else out


class StatsService:
    @staticmethod
    def year_books(db: Session, year: int) -> List[Book]:
        """Livros terminados no ano (o ano de conclusão vem sempre da data de término)."""
        return db.query(Book).options(
            selectinload(Book.authors), selectinload(Book.genres),
            selectinload(Book.series), selectinload(Book.publisher),
        ).filter(
            Book.status == BookStatus.LIDO, Book.completion_year == year,
        ).order_by(Book.finish_date.desc().nullslast(), Book.title.asc()).all()

    @staticmethod
    def get_yearbook(db: Session, year: int) -> YearbookSummary:
        books = StatsService.year_books(db, year)
        scores = [b.score for b in books if b.score is not None]
        with_pages = [b for b in books if b.pages]

        monthly = [0] * 12
        for b in books:
            if b.finish_date:
                monthly[b.finish_date.month - 1] += 1

        genres: Dict[str, CountItem] = {}
        authors: Dict[str, CountItem] = {}
        series: Dict[str, CountItem] = {}
        formats: Dict[str, CountItem] = {}

        def bump(store: Dict[str, CountItem], name: str, book: Book, **extra) -> None:
            item = store.setdefault(name, CountItem(name=name, count=0, **extra))
            item.count += 1
            item.pages += book.pages or 0

        for b in books:
            for genre in b.genres:
                bump(genres, genre.name, b, color=genre.color)
            for author in b.authors:
                bump(authors, author.name, b)
            if b.series:
                bump(series, b.series.name, b)
            bump(formats, b.format.value, b)

        def best_by(pool, key, highest=True):
            pool = [b for b in pool if key(b) is not None]
            if not pool:
                return None
            pick = max(pool, key=key) if highest else min(pool, key=key)
            return BookResponse.model_validate(pick)

        top3, custom = StatsService.podium(db, year, books)

        return YearbookSummary(
            year=year,
            total_books_read=len(books),
            total_pages_read=sum(b.pages or 0 for b in books),
            average_score=round(sum(scores) / len(scores), 1) if scores else None,
            books=[BookResponse.model_validate(b) for b in books],
            previous_year_read=len(StatsService.year_books(db, year - 1)),
            monthly_read=monthly,
            genres=_ranked(genres),
            authors=_ranked(authors, 5),
            series=_ranked(series, 5),
            formats=_ranked(formats),
            average_pages=round(sum(b.pages for b in with_pages) / len(with_pages)) if with_pages else None,
            rereads=sum(1 for b in books if b.is_reread),
            favorites=sum(1 for b in books if b.is_favorite),
            longest_book=best_by(with_pages, lambda b: b.pages),
            shortest_book=best_by(with_pages, lambda b: b.pages, highest=False),
            best_book=best_by(books, lambda b: b.score),
            top3=[BookResponse.model_validate(b) for b in top3],
            top3_custom=custom,
        )

    @staticmethod
    def podium(db: Session, year: int, books: List[Book]):
        """(livros do pódio, escolhido pelo usuário?). Escolhas que deixaram de valer para o ano são ignoradas."""
        by_id = {b.id: b for b in books}
        picks = db.query(YearbookPick).filter(YearbookPick.year == year).order_by(YearbookPick.position).all()
        chosen = [by_id[p.book_id] for p in picks if p.book_id in by_id]
        if chosen:
            return chosen, True
        suggested = sorted(books, key=lambda b: (b.score is None, -(b.score or 0), not b.is_favorite,
                                                 b.title.casefold()))
        return suggested[:3], False

    @staticmethod
    def set_top3(db: Session, year: int, book_ids: List[int]) -> YearbookSummary:
        """Grava o pódio do ano (lista vazia volta para a sugestão). Só livros terminados no ano."""
        if len(set(book_ids)) != len(book_ids):
            raise InvalidTop3Error("Um livro não pode ocupar duas posições")
        valid = {b.id for b in StatsService.year_books(db, year)}
        invalid = [bid for bid in book_ids if bid not in valid]
        if invalid:
            raise InvalidTop3Error(f"Livros não terminados em {year}: {invalid}")
        db.query(YearbookPick).filter(YearbookPick.year == year).delete()
        for position, bid in enumerate(book_ids, 1):
            db.add(YearbookPick(year=year, position=position, book_id=bid))
        db.commit()
        return StatsService.get_yearbook(db, year)

    @staticmethod
    def get_overall_stats(db: Session) -> OverallStats:
        counts = Counter(dict(db.query(Book.status, func.count(Book.id)).group_by(Book.status).all()))
        status_counts = StatusCounts(
            quero_ler=counts[BookStatus.QUERO_LER],
            proximos=counts[BookStatus.PROXIMO],
            lendo=counts[BookStatus.LENDO],
            lidos=counts[BookStatus.LIDO],
            total=sum(counts.values()),
        )
        pages = db.query(func.sum(Book.pages)).filter(Book.status == BookStatus.LIDO).scalar()
        years = [y for (y,) in db.query(Book.completion_year).filter(
            Book.status == BookStatus.LIDO, Book.completion_year.isnot(None)).distinct()]
        return OverallStats(
            status_counts=status_counts,
            total_pages_read=int(pages or 0),
            available_years=sorted(years, reverse=True) or [date.today().year],
        )
