"""Preferências do usuário salvas neste computador (QSettings)."""
import weakref

import shiboken6
from PySide6.QtCore import QObject, QSettings, Signal

CATEGORY_SCOPE_KEY = "category_scope"
SCOPE_READ, SCOPE_ALL = "read", "all"  # páginas de autor/gênero/série/editora


CARD_SIZE_KEY = "card_size"
CARD_SIZES = ("small", "medium", "large")


class _Notifier(QObject):
    card_size_changed = Signal(str)


# Avisa grades e seletores abertos quando o tamanho dos cards muda (em qualquer tela)
notifier = _Notifier()


def subscribe(signal, deliver, slot) -> None:
    """Liga `signal` a `slot` (método de um QObject) via `deliver(method, *args)`.

    Os avisos são globais e vivem mais que os widgets: a ligação guarda só uma referência fraca ao dono e
    é desfeita quando ele é destruído (evita chamar objetos C++ já apagados)."""
    owner = slot.__self__
    method_ref = weakref.WeakMethod(slot)

    def relay(*args) -> None:
        method = method_ref()
        if method is not None and shiboken6.isValid(method.__self__):
            deliver(method, *args)

    signal.connect(relay)

    def drop(*_args) -> None:
        try:
            signal.disconnect(relay)
        except (RuntimeError, TypeError):
            pass

    owner.destroyed.connect(drop)


def subscribe_card_size(slot) -> None:
    """Chama `slot(size)` quando o tamanho dos cards muda (em qualquer tela)."""
    subscribe(notifier.card_size_changed, lambda method, size: method(size), slot)


def settings() -> QSettings:
    return QSettings("BookRoom", "BookRoomLog")


def category_scope() -> str:
    """"read" mostra só livros lidos nas páginas de categoria; "all" mostra todos."""
    value = str(settings().value(CATEGORY_SCOPE_KEY, SCOPE_READ))
    return value if value in (SCOPE_READ, SCOPE_ALL) else SCOPE_READ


def set_category_scope(scope: str) -> None:
    settings().setValue(CATEGORY_SCOPE_KEY, scope if scope in (SCOPE_READ, SCOPE_ALL) else SCOPE_READ)


def card_size() -> str:
    value = str(settings().value(CARD_SIZE_KEY, "medium"))
    return value if value in CARD_SIZES else "medium"


def set_card_size(size: str) -> None:
    size = size if size in CARD_SIZES else "medium"
    if size != card_size():
        settings().setValue(CARD_SIZE_KEY, size)
        notifier.card_size_changed.emit(size)


def reset_appearance() -> None:
    """Restaura a aba Aparência: cards médios e páginas de categoria só com os lidos."""
    set_card_size("medium")
    set_category_scope(SCOPE_READ)


GOOGLE_KEY = "google_books_key"


def google_books_key() -> str:
    """Chave da API do Google Books (opcional: sem ela a cota diária é compartilhada e acaba rápido)."""
    return str(settings().value(GOOGLE_KEY, "") or "").strip()


def set_google_books_key(key: str) -> None:
    settings().setValue(GOOGLE_KEY, (key or "").strip())
