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
