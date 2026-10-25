import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Table, Text, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

def get_utc_now():
    return datetime.now(timezone.utc)

# Tabelas associativas Many-to-Many; position 0 = principal (1º autor, gênero principal)
book_authors = Table(
    "book_authors",
    Base.metadata,
    Column("book_id", Integer, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("author_id", Integer, ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False, server_default="0"),
)

book_genres = Table(
    "book_genres",
    Base.metadata,
    Column("book_id", Integer, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False, server_default="0"),
)

class BookStatus(str, enum.Enum):
    QUERO_LER = "Quero Ler"
    PROXIMO = "Próximo"
    LENDO = "Lendo"
    LIDO = "Lido"

class BookFormat(str, enum.Enum):
    EBOOK = "Kindle / E-book"
    FISICO = "Físico"
    AUDIOBOOK = "Audiobook"

class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False, index=True)

    # Chaves estrangeiras
    publisher_id = Column(Integer, ForeignKey("publishers.id"), nullable=True)
    series_id = Column(Integer, ForeignKey("series.id"), nullable=True)
    series_number = Column(Float, nullable=True)  # volume na série (1, 2, 2.5...)

    # Status e Imagens
    status = Column(SQLEnum(BookStatus), default=BookStatus.QUERO_LER, nullable=False, index=True)
    cover_image = Column(String(300), nullable=True)
    # Ordem manual da fila de Próximos (1 = o próximo a ler); vazio fora do status Próximo
    next_position = Column(Integer, nullable=True, index=True)
    # Progresso atual em % (só enquanto Lendo)
    progress = Column(Integer, nullable=True)

    # Dados da edição
    pages = Column(Integer, nullable=True)
    format = Column(SQLEnum(BookFormat), default=BookFormat.EBOOK, nullable=False)
    language = Column(String(40), nullable=True)
    isbn = Column(String(20), nullable=True, index=True)

    # Avaliação (0-10) e conclusão (só Lido)
    score = Column(Float, nullable=True)
    finish_date = Column(Date, nullable=True)
    completion_year = Column(Integer, nullable=True, index=True)

    # Releitura = novo registro; aponta sempre para o registro original (a 1ª leitura)
    reread_of_id = Column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True)
    read_number = Column(Integer, default=1, nullable=False)  # 1ª leitura, 2ª leitura...

    is_favorite = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now, nullable=False)

    # Relacionamentos
    publisher = relationship("Publisher", back_populates="books")
    series = relationship("Series", back_populates="books")
    authors = relationship("Author", secondary=book_authors, back_populates="books",
                           order_by=(book_authors.c.position, book_authors.c.author_id))
    genres = relationship("Genre", secondary=book_genres, back_populates="books",
                          order_by=(book_genres.c.position, book_genres.c.genre_id))

    # Calculado pelo BookService (não é coluna): quantas releituras apontam para este registro
    rereads_count = 0

    @property
    def is_reread(self) -> bool:
        return self.read_number > 1 or self.reread_of_id is not None
