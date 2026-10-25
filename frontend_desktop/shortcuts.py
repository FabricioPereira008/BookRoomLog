"""Registro único dos atalhos de teclado: a janela principal os cria e a aba Atalhos os lista daqui."""
from dataclasses import dataclass
from typing import Optional

GROUP_GENERAL = "Geral"
GROUP_LISTS = "Listas de livros"
GROUPS = (GROUP_GENERAL, GROUP_LISTS)


@dataclass(frozen=True)
class Shortcut:
    keys: str                      # como o QKeySequence entende e como é mostrado
    description: str
    group: str
    action: Optional[str] = None   # método da MainWindow; None = comportamento nativo do Qt (só documentado)


SHORTCUTS = (
    Shortcut("Ctrl+N", "Adicionar um livro novo", GROUP_GENERAL, "open_add_book_dialog"),
    Shortcut("Ctrl+F", "Busca rápida: encontrar qualquer livro pelo título ou autor", GROUP_GENERAL, "open_quick_search"),
    Shortcut("Esc", "Fechar a janela de diálogo aberta", GROUP_GENERAL),
    Shortcut("Enter", "Abrir o livro selecionado", GROUP_LISTS),
    Shortcut("Del", "Excluir o livro selecionado (pede confirmação)", GROUP_LISTS, "delete_selected_book"),
)
