"""Busca de dados do livro na internet (Google Books / Open Library) para preencher o formulário."""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from frontend_desktop import preferences
from frontend_desktop.api_client.client import api_client
from frontend_desktop.ui_helpers import add_search_icon, set_status
from frontend_desktop.workers import run_async

SOURCES = (("Automático (Google Books, depois Open Library)", None), ("Só Google Books", "google"),
           ("Só Open Library", "openlibrary"))


def describe_candidate(candidate: dict) -> str:
    """Duas linhas: título e, abaixo, autores · editora · ano · páginas · idioma · fonte."""
    details = [
        ", ".join(candidate.get("authors") or []),
        candidate.get("publisher") or "",
        str(candidate.get("published_year") or ""),
        f"{candidate['pages']} págs." if candidate.get("pages") else "",
        candidate.get("language") or "",
        f"ISBN {candidate['isbn']}" if candidate.get("isbn") else "",
        "com capa" if candidate.get("cover_url") else "sem capa",
        candidate.get("source") or "",
    ]
    return f"{candidate.get('title') or 'Sem título'}\n      " + " · ".join(d for d in details if d)


def search_books(title: str, author: str, isbn: str, source: Optional[str]) -> list:
    """Roda fora da thread da UI."""
    return api_client.lookup_books(title=title, author=author or None, isbn=isbn or None, source=source,
                                   api_key=preferences.google_books_key() or None)


class LookupDialog(QDialog):
    """Ao aceitar, `selected` tem o resultado escolhido e `download_cover` diz se a capa deve ser baixada."""

    def __init__(self, title: str = "", author: str = "", isbn: str = "", parent=None, auto_search: bool = True):
        super().__init__(parent)
        self.selected: Optional[dict] = None
        self.results: list = []
        self._seq = 0
        self.setWindowTitle("Buscar dados do livro")
        self.setMinimumSize(720, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel("Buscar dados do livro")
        heading.setProperty("class", "section-header")
        layout.addWidget(heading)
        hint = QLabel("Pesquise pelo título (e autor) ou pelo ISBN. Os dados escolhidos preenchem o formulário; "
                      "você ainda pode ajustar tudo antes de salvar.")
        hint.setWordWrap(True)
        hint.setProperty("class", "settings-desc")
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.input_title = QLineEdit(title)
        self.input_title.setPlaceholderText("Título")
        add_search_icon(self.input_title)
        self.input_author = QLineEdit(author)
        self.input_author.setPlaceholderText("Autor (opcional)")
        self.input_isbn = QLineEdit(isbn)
        self.input_isbn.setPlaceholderText("ISBN (opcional; tem prioridade)")
        self.combo_source = QComboBox()
        for label, value in SOURCES:
            self.combo_source.addItem(label, value)
        self.btn_search = QPushButton("Buscar")
        self.btn_search.setProperty("class", "action-btn")
        self.btn_search.setCursor(Qt.PointingHandCursor)
        self.btn_search.clicked.connect(self.search)
        for field in (self.input_title, self.input_author, self.input_isbn):
            field.returnPressed.connect(self.search)
        form.addWidget(self.input_title, 0, 0, 1, 2)
        form.addWidget(self.input_author, 1, 0)
        form.addWidget(self.input_isbn, 1, 1)
        form.addWidget(self.combo_source, 2, 0)
        form.addWidget(self.btn_search, 2, 1, Qt.AlignRight)
        layout.addLayout(form)

        self.results_list = QListWidget()
        self.results_list.setObjectName("lookupResults")
        self.results_list.itemDoubleClicked.connect(lambda _item: self.accept_current())
        self.results_list.currentRowChanged.connect(lambda *_: self._update_buttons())
        layout.addWidget(self.results_list, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.chk_cover = QCheckBox("Baixar a capa do resultado")
        self.chk_cover.setChecked(True)
        buttons.addWidget(self.chk_cover)
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setProperty("class", "cancel-btn")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.btn_use = QPushButton("Usar estes dados")
        self.btn_use.setProperty("class", "action-btn")
        self.btn_use.setCursor(Qt.PointingHandCursor)
        self.btn_use.clicked.connect(self.accept_current)
        buttons.addWidget(self.btn_use)
        layout.addLayout(buttons)
        self._update_buttons()

        if auto_search and (title.strip() or isbn.strip()):
            self.search()

    @property
    def download_cover(self) -> bool:
        return self.chk_cover.isChecked() and bool((self.selected or {}).get("cover_url"))

    def _update_buttons(self) -> None:
        self.btn_use.setEnabled(0 <= self.results_list.currentRow() < len(self.results))

    def search(self) -> None:
        title, isbn = self.input_title.text().strip(), self.input_isbn.text().strip()
        if not title and not isbn:
            set_status(self.status, "error", "Digite o título ou o ISBN.")
            return
        self._seq += 1
        seq = self._seq
        self.btn_search.setEnabled(False)
        set_status(self.status, "muted", "Buscando…")
        run_async(self, search_books, lambda results: self._on_results(seq, results),
                  lambda msg: self._on_failed(seq, msg),
                  title, self.input_author.text().strip(), isbn, self.combo_source.currentData())

    def _on_results(self, seq: int, results: list) -> None:
        if seq != self._seq:
            return
        self.btn_search.setEnabled(True)
        self.set_results(results)

    def set_results(self, results: list) -> None:
        self.results = list(results)
        self.results_list.clear()
        for candidate in self.results:
            item = QListWidgetItem(describe_candidate(candidate))
            item.setToolTip(candidate.get("title") or "")
            self.results_list.addItem(item)
        if self.results:
            self.results_list.setCurrentRow(0)
            set_status(self.status, "ok", f"{len(self.results)} resultado(s). Escolha um e clique em \"Usar estes dados\".")
        else:
            set_status(self.status, "muted", "Nada encontrado. Tente só o título, outra grafia ou o ISBN.")
        self._update_buttons()

    def _on_failed(self, seq: int, message: str) -> None:
        if seq != self._seq:
            return
        self.btn_search.setEnabled(True)
        set_status(self.status, "error", f"A busca falhou: {message}")

    def accept_current(self) -> None:
        row = self.results_list.currentRow()
        if not 0 <= row < len(self.results):
            return
        self.selected = self.results[row]
        self.accept()

    def done(self, result):
        for worker in list(self.__dict__.get("_workers", ())):
            worker.wait(5000)
        super().done(result)
