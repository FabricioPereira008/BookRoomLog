"""Campos que faltam no cadastro de um livro (aviso nos cards e na tabela)."""
from typing import List

from frontend_desktop.views import book_status as bs


def missing_fields(book: dict) -> List[str]:
    """Nomes legíveis dos campos vazios; livros lidos também precisam da nota e da data de término."""
    missing = []
    if not book.get("authors"):
        missing.append("autor")
    if not book.get("genres"):
        missing.append("gênero")
    if not book.get("cover_image"):
        missing.append("capa")
    if not book.get("pages") and book.get("format") != bs.AUDIOBOOK:
        missing.append("nº de páginas")
    if book.get("status") == bs.LIDO:
        if book.get("score") is None:
            missing.append("nota")
        if not book.get("finish_date"):
            missing.append("data de término")
    return missing


def is_incomplete(book: dict) -> bool:
    return bool(missing_fields(book))


def autofill_gaps(book: dict) -> List[str]:
    """Campos vazios que o preenchimento automático (busca online) pode completar."""
    gaps = []
    if not book.get("authors"):
        gaps.append("autor")
    if not book.get("genres"):
        gaps.append("gênero")
    if not book.get("cover_image"):
        gaps.append("capa")
    if not book.get("pages") and book.get("format") != bs.AUDIOBOOK:
        gaps.append("páginas")
    if not book.get("publisher"):
        gaps.append("editora")
    if not book.get("isbn"):
        gaps.append("ISBN")
    if not book.get("language"):
        gaps.append("idioma")
    return gaps
