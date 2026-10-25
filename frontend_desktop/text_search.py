"""Comparação de texto para buscas e filtros da GUI (ignora maiúsculas e acentos)."""
import unicodedata
from functools import lru_cache


@lru_cache(maxsize=16384)
def fold(text: str) -> str:
    """Minúsculas e sem acentos ("Pokémon" encontra "pokemon")."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def fold_query(text: str) -> str:
    """Texto digitado pelo usuário, pronto para comparar com `fold(...)`."""
    return fold((text or "").strip())
