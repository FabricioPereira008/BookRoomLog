"""Identificadores, títulos e ícones das telas (única fonte para sidebar, cabeçalho e navegação)."""
from dataclasses import dataclass
from enum import IntEnum


class ViewId(IntEnum):
    SHELF = 0
    WANT = 1
    NEXT = 2
    READ = 3
    LIBRARY = 4
    YEARBOOK = 5
    AUTHORS = 6
    GENRES = 7
    SERIES = 8
    PUBLISHERS = 9
    SETTINGS = 10
    CATEGORY_DETAIL = 11


@dataclass(frozen=True)
class ViewMeta:
    title: str       # título no cabeçalho
    nav_label: str   # rótulo na sidebar
    icon: str        # nome do SVG em resources/icons


VIEW_META = {
    ViewId.SHELF: ViewMeta("Estante", "Estante", "library"),
    ViewId.WANT: ViewMeta("Quero ler", "Quero ler", "bookmark"),
    ViewId.NEXT: ViewMeta("Próximos da fila", "Próximos", "list-ordered"),
    ViewId.READ: ViewMeta("Livros lidos", "Lidos", "circle-check"),
    ViewId.LIBRARY: ViewMeta("Biblioteca de livros", "Biblioteca (tabela)", "table-2"),
    ViewId.YEARBOOK: ViewMeta("Anuário de leitura", "Anuário", "calendar-days"),
    ViewId.AUTHORS: ViewMeta("Autores", "Autores", "user"),
    ViewId.GENRES: ViewMeta("Gêneros", "Gêneros", "tags"),
    ViewId.SERIES: ViewMeta("Séries / sagas", "Séries", "layers"),
    ViewId.PUBLISHERS: ViewMeta("Editoras", "Editoras", "building-2"),
    ViewId.SETTINGS: ViewMeta("Configurações", "Configurações", "settings"),
    ViewId.CATEGORY_DETAIL: ViewMeta("Detalhes da categoria", "Detalhes", "tags"),
}

# Grupos exibidos na sidebar, na ordem
NAV_SECTIONS = [
    ("Leituras", [ViewId.SHELF, ViewId.WANT, ViewId.NEXT, ViewId.READ, ViewId.LIBRARY]),
    ("Explorar", [ViewId.YEARBOOK, ViewId.AUTHORS, ViewId.GENRES, ViewId.SERIES, ViewId.PUBLISHERS]),
]

# Página de cada categoria (category_type -> ViewId)
CATEGORY_VIEWS = {"author": ViewId.AUTHORS, "genre": ViewId.GENRES, "series": ViewId.SERIES,
                  "publisher": ViewId.PUBLISHERS}
