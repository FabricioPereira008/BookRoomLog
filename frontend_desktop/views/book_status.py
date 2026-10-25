"""Status de livro (valores da API), formatos e textos derivados mostrados nos cards e tabelas."""
QUERO_LER = "Quero Ler"
PROXIMO = "Próximo"
LENDO = "Lendo"
LIDO = "Lido"

# Ordem usada nos filtros e no formulário
ALL_STATUSES = [QUERO_LER, PROXIMO, LENDO, LIDO]

EBOOK = "Kindle / E-book"
FISICO = "Físico"
AUDIOBOOK = "Audiobook"
FORMATS = [EBOOK, FISICO, AUDIOBOOK]
FORMAT_ICONS = {EBOOK: "book-open", FISICO: "book", AUDIOBOOK: "headphones"}

LANGUAGES = ["Português", "Inglês", "Espanhol", "Francês", "Alemão", "Italiano", "Japonês"]


def filter_books(status: str, books: list) -> list:
    return [b for b in books if b.get("status") == status]


def author_names(book: dict) -> str:
    """"Terry Pratchett, Neil Gaiman" (vazio se não houver autor)."""
    return ", ".join(a.get("name", "") for a in book.get("authors") or [] if a.get("name"))


def main_author(book: dict) -> str:
    authors = book.get("authors") or []
    return authors[0].get("name", "") if authors else ""


def series_text(book: dict) -> str:
    """"Duna #2" (ou só "Duna" sem volume; vazio fora de série)."""
    series = (book.get("series") or {}).get("name")
    if not series:
        return ""
    number = book.get("series_number")
    return f"{series} #{number:g}" if number is not None else series


def pages_text(book: dict) -> str:
    pages = book.get("pages")
    return f"{pages} págs." if pages else ""


def read_label(book: dict) -> str:
    """"2ª leitura" para releituras (vazio na primeira)."""
    number = book.get("read_number") or 1
    return f"{number}ª leitura" if number > 1 else ""
