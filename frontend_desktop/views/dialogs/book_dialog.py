"""Diálogo de criação/edição de livro. A capa fica em um mixin próprio (book_dialog_cover)."""
import logging
from typing import List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from frontend_desktop import preferences
from frontend_desktop.api_client.client import api_client
from frontend_desktop.cover_loader import cover_loader
from frontend_desktop.styles.tokens import COLORS
from frontend_desktop.text_search import fold
from frontend_desktop.ui_helpers import set_button_icon, set_status
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.dialogs.book_dialog_cover import CoverMixin
from frontend_desktop.views.dialogs.lookup_dialog import LookupDialog
from frontend_desktop.views.dialogs.optional_date_edit import OptionalDateEdit
from frontend_desktop.workers import run_async

logger = logging.getLogger(__name__)

CATEGORY_KINDS = ("author", "genre", "publisher", "series")


def split_authors(text: str) -> List[str]:
    """"Terry Pratchett, Neil Gaiman" -> ["Terry Pratchett", "Neil Gaiman"] (sem vazios nem repetidos)."""
    names, seen = [], set()
    for part in (text or "").replace(";", ",").split(","):
        name = " ".join(part.split())
        if name and fold(name) not in seen:
            seen.add(fold(name))
            names.append(name)
    return names


def brief_label(brief: dict) -> str:
    parts = [brief.get("author"), brief.get("status")]
    if (brief.get("read_number") or 1) > 1:
        parts.append(f"{brief['read_number']}ª leitura")
    if brief.get("finish_date"):
        parts.append(f"terminado em {brief['finish_date'][:4]}")
    return f"{brief.get('title') or 'Sem título'}  —  " + " · ".join(p for p in parts if p)


def reading_group(briefs: List[dict], book_id: Optional[int], root_id: Optional[int]) -> List[dict]:
    """Todas as leituras do mesmo livro (original + releituras), na ordem das leituras."""
    root = root_id or book_id
    if root is None:
        return []
    group = [b for b in briefs if b["id"] == root or b.get("reread_of_id") == root]
    return sorted(group, key=lambda b: (b.get("read_number") or 1, b["id"]))


class MultiValueCompleter(QCompleter):
    """Autocompleta só o último nome de uma lista separada por vírgulas."""

    def pathFromIndex(self, index):
        chosen = super().pathFromIndex(index)
        parts = [p.strip() for p in self.widget().text().split(",")[:-1] if p.strip()]
        return ", ".join(parts + [chosen])

    def splitPath(self, path):
        return [path.split(",")[-1].strip()]


class BookDialog(CoverMixin, QDialog):
    def __init__(self, book_data: dict = None, parent=None):
        super().__init__(parent)
        self.book_data = book_data or {}
        self.is_edit = bool(book_data and book_data.get("id"))
        self.cover_filename = self.book_data.get("cover_image")
        self.saved_book = None
        self.is_deleted = False
        self.reread_created = None  # livro novo criado pelo botão "Reler"
        self._briefs = None
        self._briefs_loading = False
        self.options = {kind: [] for kind in CATEGORY_KINDS}

        self.setWindowTitle("Editar livro" if self.is_edit else "Novo livro")
        self.setMinimumSize(820, 600)
        self.resize(920, 800)
        self.init_ui()
        cover_loader.subscribe(self._on_cover_loaded)
        self.load_options()

    def init_ui(self):
        self.setObjectName("bookDialog")
        self.setAttribute(Qt.WA_StyledBackground, True)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)
        self._build_header(main_layout)

        scroll = QScrollArea()
        scroll.setObjectName("bookDialogScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("bookDialogContainer")
        container.setAttribute(Qt.WA_StyledBackground, True)
        body = QHBoxLayout(container)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(16)
        body.addWidget(self._build_cover_card(), 0, Qt.AlignTop)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_identity_card())
        right.addWidget(self._build_edition_card())
        right.addWidget(self._build_reading_card())
        right.addWidget(self._build_notes_card())
        right.addStretch()
        body.addLayout(right, 1)
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)
        self._build_action_buttons(main_layout)
        self.on_status_changed()

    # --- blocos reutilizáveis ---
    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("class", "form-label")
        return lbl

    @staticmethod
    def _field(label: str, widget, required: bool = False) -> QWidget:
        """Rótulo acima do campo; o conjunto pode ser mostrado/ocultado como uma unidade."""
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(BookDialog._make_label(f"{label} *" if required else label))
        if isinstance(widget, QWidget):
            lay.addWidget(widget)
        else:
            lay.addLayout(widget)
        return box

    @staticmethod
    def _card(title: str):
        """Cartão com título; devolve (frame, grid de 2 colunas)."""
        frame = QFrame()
        frame.setProperty("class", "form-card")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(18, 14, 18, 18)
        outer.setSpacing(12)
        heading = QLabel(title)
        heading.setProperty("class", "card-title")
        outer.addWidget(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)
        return frame, grid

    @staticmethod
    def _editable_combo(placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.lineEdit().setPlaceholderText(placeholder)
        return combo

    def _build_header(self, main_layout):
        title = QLabel("Editar livro" if self.is_edit else "Novo livro")
        title.setProperty("class", "view-title-large")
        subtitle = QLabel(
            "Altere as informações e salve." if self.is_edit
            else "Digite o título e use \"Preencher automaticamente\" (ou escolha em \"Buscar dados online\"). "
                 "Os campos com * são obrigatórios."
        )
        subtitle.setProperty("class", "settings-desc")
        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

    # --- cartões ---
    def _build_identity_card(self) -> QFrame:
        """Título, autores, série, gêneros e status."""
        card, grid = self._card("Identificação")

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Ex: O Nome do Vento")
        title_row.addWidget(self.input_title, 1)
        self.btn_autofill = QPushButton("Preencher automaticamente")
        self.btn_autofill.setProperty("class", "small-btn")
        self.btn_autofill.setCursor(Qt.PointingHandCursor)
        self.btn_autofill.setToolTip("Busca este livro e completa só os campos vazios (autor, gênero, série, editora, "
                                     "páginas, idioma, ISBN e capa) com o resultado mais seguro")
        set_button_icon(self.btn_autofill, "wand-sparkles")
        self.btn_autofill.clicked.connect(self.autofill)
        title_row.addWidget(self.btn_autofill)
        self.btn_lookup = QPushButton("Buscar dados online")
        self.btn_lookup.setProperty("class", "small-btn")
        self.btn_lookup.setCursor(Qt.PointingHandCursor)
        self.btn_lookup.setToolTip("Mostra os resultados do Google Books / Open Library para você escolher")
        set_button_icon(self.btn_lookup, "search")
        self.btn_lookup.clicked.connect(self.open_lookup)
        title_row.addWidget(self.btn_lookup)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addLayout(title_row)
        self.lbl_autofill = QLabel("")
        self.lbl_autofill.setWordWrap(True)
        self.lbl_autofill.setVisible(False)
        title_box.addWidget(self.lbl_autofill)
        grid.addWidget(self._field("Título", title_box, required=True), 0, 0, 1, 2)

        self.input_authors = QLineEdit()
        self.input_authors.setPlaceholderText("Separe vários autores com vírgula")
        grid.addWidget(self._field("Autor(es)", self.input_authors), 1, 0, 1, 2)

        series_row = QHBoxLayout()
        series_row.setSpacing(6)
        self.combo_series = self._editable_combo("Opcional")
        series_row.addWidget(self.combo_series, 1)
        self.spin_series_number = QDoubleSpinBox()
        self.spin_series_number.setRange(0, 999)
        self.spin_series_number.setDecimals(0)
        self.spin_series_number.setPrefix("#")
        self.spin_series_number.setSpecialValueText("Vol.")
        self.spin_series_number.setFixedWidth(90)
        self.spin_series_number.setToolTip("Volume na série (ex.: 2; vazio = não informado)")
        series_row.addWidget(self.spin_series_number)
        grid.addWidget(self._field("Série / saga", series_row), 2, 0)

        self.combo_status = QComboBox()
        for s in bs.ALL_STATUSES:
            self.combo_status.addItem(s, s)
        self.combo_status.setCurrentIndex(0)
        self.combo_status.currentIndexChanged.connect(self.on_status_changed)
        grid.addWidget(self._field("Status", self.combo_status, required=True), 2, 1)

        self.combo_genre = self._editable_combo("Selecione ou digite…")
        grid.addWidget(self._field("Gênero principal", self.combo_genre), 3, 0)
        self.combo_genre2 = self._editable_combo("Opcional")
        grid.addWidget(self._field("Gênero secundário", self.combo_genre2), 3, 1)
        return card

    def _build_edition_card(self) -> QFrame:
        """Dados da edição: editora, páginas, formato, idioma e ISBN."""
        card, grid = self._card("Edição")
        self.combo_publisher = self._editable_combo("Opcional")
        grid.addWidget(self._field("Editora", self.combo_publisher), 0, 0)

        self.spin_pages = QSpinBox()
        self.spin_pages.setRange(0, 99999)
        self.spin_pages.setSuffix(" págs.")
        self.spin_pages.setSpecialValueText("—")
        grid.addWidget(self._field("Nº de páginas", self.spin_pages), 0, 1)

        self.combo_format = QComboBox()
        self.combo_format.addItems(bs.FORMATS)
        grid.addWidget(self._field("Formato", self.combo_format), 1, 0)

        self.combo_language = self._editable_combo("Opcional")
        self.combo_language.addItems(bs.LANGUAGES)
        self.combo_language.setCurrentIndex(-1)
        grid.addWidget(self._field("Idioma", self.combo_language), 1, 1)

        self.input_isbn = QLineEdit()
        self.input_isbn.setPlaceholderText("Opcional (ajuda a achar a capa certa)")
        grid.addWidget(self._field("ISBN", self.input_isbn), 2, 0)
        return card

    def _build_reading_card(self) -> QFrame:
        """Progresso (Lendo), término e nota (Lido), releitura e favorito."""
        card, grid = self._card("Leitura")

        self.spin_progress = QSpinBox()
        self.spin_progress.setRange(0, 100)
        self.spin_progress.setSuffix(" %")
        self.field_progress = self._field("Progresso (o % do Kindle)", self.spin_progress)
        grid.addWidget(self.field_progress, 0, 0)

        self.date_finish = OptionalDateEdit()
        self.field_finish = self._field("Terminei em", self.date_finish)
        grid.addWidget(self.field_finish, 0, 0)

        self.spin_score = QDoubleSpinBox()
        self.spin_score.setRange(0, 10)
        self.spin_score.setDecimals(1)
        self.spin_score.setSingleStep(0.5)
        self.spin_score.setSpecialValueText("Sem nota")
        self.field_score = self._field("Nota (0–10)", self.spin_score)
        grid.addWidget(self.field_score, 0, 1)

        self.chk_reread = QCheckBox("Esta leitura é uma releitura")
        self.chk_reread.toggled.connect(self.on_reread_toggled)
        grid.addWidget(self.chk_reread, 1, 0)
        self.chk_favorite = QCheckBox("Favorito")
        grid.addWidget(self.chk_favorite, 1, 1)

        self.combo_reread_of = self._editable_combo("Busque o registro da primeira leitura...")
        self.combo_reread_of.setToolTip("Liga esta leitura às anteriores do mesmo livro; o registro antigo não muda.")
        self.field_reread_of = self._field("Releitura de", self.combo_reread_of)
        self.field_reread_of.setVisible(False)
        grid.addWidget(self.field_reread_of, 2, 0, 1, 2)

        self.lbl_reads = QLabel("")
        self.lbl_reads.setWordWrap(True)
        self.lbl_reads.setProperty("class", "settings-desc")
        self.lbl_reads.setVisible(False)
        grid.addWidget(self.lbl_reads, 3, 0, 1, 2)
        return card

    def _build_notes_card(self) -> QFrame:
        card, grid = self._card("Anotações e resenha")
        self.input_notes = QTextEdit()
        self.input_notes.setPlaceholderText("Suas impressões, citações favoritas, resenha...")
        self.input_notes.setFixedHeight(100)
        grid.addWidget(self.input_notes, 0, 0, 1, 2)
        return card

    def _build_action_buttons(self, main_layout):
        btn_box = QHBoxLayout()
        if self.is_edit:
            self.btn_delete = QPushButton("Excluir livro")
            set_button_icon(self.btn_delete, "trash-2", COLORS["danger"])
            self.btn_delete.setProperty("class", "delete-btn")
            self.btn_delete.clicked.connect(self.delete_book)
            btn_box.addWidget(self.btn_delete)
            self.btn_reread = QPushButton("Reler este livro")
            set_button_icon(self.btn_reread, "repeat", COLORS["text"])
            self.btn_reread.setProperty("class", "cancel-btn")
            self.btn_reread.setToolTip("Cria uma nova leitura (status Lendo) ligada a esta, com os mesmos dados da edição")
            self.btn_reread.setVisible(self.book_data.get("status") == bs.LIDO)
            self.btn_reread.clicked.connect(self.start_reread)
            btn_box.addWidget(self.btn_reread)
        btn_box.addStretch()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setProperty("class", "cancel-btn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)
        self.btn_save = QPushButton("Salvar livro")
        self.btn_save.setProperty("class", "action-btn")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.save_book)
        btn_box.addWidget(self.btn_save)
        main_layout.addLayout(btn_box)

    # --- visibilidade por status ---
    def on_status_changed(self, *_):
        status = self.combo_status.currentData()
        is_read = status == bs.LIDO
        self.field_progress.setVisible(status == bs.LENDO)
        self.field_finish.setVisible(is_read)
        self.field_score.setVisible(is_read)
        if is_read and self.date_finish.is_blank():
            self.date_finish.setDate(QDate.currentDate())  # terminou hoje (editável)

    def on_reread_toggled(self, checked: bool):
        self.field_reread_of.setVisible(checked)
        if checked:
            self.load_briefs()

    # --- opções (autocompletar) ---
    def _wait_workers(self):
        for w in list(self.__dict__.get("_workers", ())):
            w.wait(5000)

    def done(self, result):
        self._wait_workers()
        super().done(result)

    @staticmethod
    def fetch_options() -> dict:
        """Busca as opções dos campos (roda fora da thread da UI)."""
        return {kind: api_client.get_categories(kind, "all") for kind in CATEGORY_KINDS}

    def _set_completer_names(self, combo: QComboBox, names: list):
        combo.clear()
        combo.addItems(names)
        combo.setCurrentIndex(-1)  # combo editável selecionaria o 1º item e o preencheria
        completer = QCompleter(names, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        combo.setCompleter(completer)

    def apply_options(self, options: dict):
        self.options = options
        names = lambda kind: [c["name"] for c in options.get(kind, [])]
        completer = MultiValueCompleter(names("author"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.input_authors.setCompleter(completer)
        self._set_completer_names(self.combo_genre, names("genre"))
        self._set_completer_names(self.combo_genre2, names("genre"))
        self._set_completer_names(self.combo_publisher, names("publisher"))
        self._set_completer_names(self.combo_series, names("series"))

    def load_options(self):
        """Carrega as opções em background e preenche o formulário ao terminar."""
        self.btn_save.setEnabled(False)
        run_async(self, self.fetch_options, self._on_options_loaded, self._on_options_failed)

    def _on_options_loaded(self, options: dict):
        self.apply_options(options)
        self.btn_save.setEnabled(True)
        self.populate_data()

    def _on_options_failed(self, message: str):
        logger.error("Erro ao carregar opções: %s", message)
        self.btn_save.setEnabled(True)
        self.populate_data()
        set_status(self.lbl_cover_status, "error", "Não foi possível carregar as listas (API offline?).")

    # --- releituras ---
    def load_briefs(self):
        if self._briefs is not None or self._briefs_loading:
            return
        self._briefs_loading = True
        run_async(self, api_client.get_book_briefs, self._on_briefs_loaded,
                  lambda msg: logger.warning("Falha ao carregar a lista de livros: %s", msg))

    def _on_briefs_loaded(self, briefs: list):
        self._briefs_loading = False
        own_id = self.book_data.get("id")
        self._briefs = briefs
        self.combo_reread_of.clear()
        candidates = [b for b in briefs if b["id"] != own_id and not b.get("reread_of_id")]
        for brief in candidates:
            self.combo_reread_of.addItem(brief_label(brief), brief["id"])
        completer = QCompleter([brief_label(b) for b in candidates], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.combo_reread_of.setCompleter(completer)
        target = self.book_data.get("reread_of_id")
        if target:
            self.combo_reread_of.setCurrentIndex(self.combo_reread_of.findData(target))
        else:
            self._suggest_original()
        self._show_reading_group()

    def _suggest_original(self):
        """Releitura nova: sugere o registro com o mesmo título."""
        title = fold(self.input_title.text().strip())
        for i in range(self.combo_reread_of.count()):
            brief = next((b for b in self._briefs or [] if b["id"] == self.combo_reread_of.itemData(i)), None)
            if title and brief and fold(brief.get("title")) == title:
                self.combo_reread_of.setCurrentIndex(i)
                return
        self.combo_reread_of.setCurrentIndex(-1)

    def _show_reading_group(self):
        group = reading_group(self._briefs or [], self.book_data.get("id"), self.book_data.get("reread_of_id"))
        if len(group) < 2:
            self.lbl_reads.setVisible(False)
            return
        lines = [f"{b.get('read_number') or 1}ª leitura: {b.get('status')}"
                 + (f" em {b['finish_date'][8:10]}/{b['finish_date'][5:7]}/{b['finish_date'][:4]}" if b.get("finish_date") else "")
                 + (f" · nota {b['score']:g}" if b.get("score") is not None else "")
                 for b in group]
        self.lbl_reads.setText("Leituras deste livro:\n" + "\n".join(lines))
        self.lbl_reads.setVisible(True)

    def selected_reread_of(self) -> Optional[int]:
        """Id do original escolhido (só se o texto do combo ainda corresponde a um item)."""
        index = self.combo_reread_of.currentIndex()
        if index < 0 or self.combo_reread_of.currentText() != self.combo_reread_of.itemText(index):
            return None
        return self.combo_reread_of.itemData(index)

    # --- preenchimento ---
    def populate_data(self):
        # Sem id também pode vir pré-preenchido (ex.: dados da busca online)
        if not self.book_data:
            return
        b = self.book_data
        self.input_title.setText(b.get("title", ""))
        self.input_authors.setText(bs.author_names(b))
        self.combo_series.setEditText((b.get("series") or {}).get("name", ""))
        self.spin_series_number.setValue(float(b.get("series_number") or 0))
        names = [g.get("name") or "" for g in b.get("genres") or []] + ["", ""]
        self.combo_genre.setEditText(names[0])
        self.combo_genre2.setEditText(names[1])
        status_index = self.combo_status.findData(b.get("status"))
        if status_index >= 0:
            self.combo_status.setCurrentIndex(status_index)
        self.combo_publisher.setEditText((b.get("publisher") or {}).get("name", ""))
        self.spin_pages.setValue(int(b.get("pages") or 0))
        if b.get("format") in bs.FORMATS:
            self.combo_format.setCurrentText(b["format"])
        self.combo_language.setEditText(b.get("language") or "")
        self.input_isbn.setText(b.get("isbn") or "")
        self.spin_progress.setValue(int(b.get("progress") or 0))
        if b.get("finish_date"):
            self.date_finish.set_optional_date(QDate.fromString(b["finish_date"], "yyyy-MM-dd"))
        if b.get("score") is not None:
            self.spin_score.setValue(float(b["score"]))
        self.chk_favorite.setChecked(bool(b.get("is_favorite")))
        self.input_notes.setText(b.get("notes") or "")
        self.on_status_changed()
        if b.get("reread_of_id"):
            self.chk_reread.setChecked(True)
        elif b.get("rereads_count"):
            self.load_briefs()  # mostra as outras leituras do grupo
        self.update_cover_preview()

    def author_list(self) -> List[str]:
        return split_authors(self.input_authors.text())

    def open_lookup(self):
        authors = self.author_list()
        dialog = LookupDialog(self.input_title.text().strip(), authors[0] if authors else "",
                              self.input_isbn.text().strip(), self)
        if dialog.exec() and dialog.selected:
            self.show_filled(self.apply_candidate(dialog.selected, download_cover=dialog.download_cover))

    def autofill(self):
        """Pega o resultado mais seguro (sem abrir a lista) e completa só os campos vazios."""
        title, isbn = self.input_title.text().strip(), self.input_isbn.text().strip()
        if not title and not isbn:
            QMessageBox.warning(self, "Aviso", "Digite o título (ou o ISBN) antes de preencher automaticamente.")
            return
        authors = self.author_list()
        self.btn_autofill.setEnabled(False)
        self.btn_autofill.setText("Buscando...")
        set_status(self.lbl_autofill, "muted", "Procurando este livro no Google Books / Open Library...")
        self.lbl_autofill.setVisible(True)
        run_async(self, api_client.lookup_best, self._on_autofill_found, self._on_autofill_failed,
                  title, authors[0] if authors else None, isbn or None, preferences.google_books_key() or None)

    def _reset_autofill_button(self):
        self.btn_autofill.setEnabled(True)
        self.btn_autofill.setText("Preencher automaticamente")

    def _on_autofill_found(self, candidate):
        self._reset_autofill_button()
        if not candidate:
            set_status(self.lbl_autofill, "error",
                       "Nada encontrado com segurança. Use \"Buscar dados online\" para escolher entre os resultados.")
            return
        self.show_filled(self.apply_candidate(candidate, download_cover=True), candidate.get("source"))

    def _on_autofill_failed(self, message: str):
        self._reset_autofill_button()
        set_status(self.lbl_autofill, "error", f"A busca falhou: {message}")

    def show_filled(self, filled: List[str], source: Optional[str] = None) -> None:
        self.lbl_autofill.setVisible(True)
        origin = f" ({source})" if source else ""
        if filled:
            set_status(self.lbl_autofill, "ok", f"Preenchido{origin}: {', '.join(filled)}. Confira antes de salvar.")
        else:
            set_status(self.lbl_autofill, "muted", f"Livro encontrado{origin}, mas os campos já estavam preenchidos.")

    @staticmethod
    def _is_blank(text: str) -> bool:
        return not (text or "").strip()

    def apply_candidate(self, candidate: dict, download_cover: bool = False) -> List[str]:
        """Completa o formulário com um resultado da busca online, só nos campos vazios.

        Devolve os nomes do que foi preenchido. O que você já digitou nunca é trocado."""
        filled = []
        if self._is_blank(self.input_title.text()) and candidate.get("title"):
            self.input_title.setText(candidate["title"])
            filled.append("título")
        if not self.author_list() and candidate.get("authors"):
            self.input_authors.setText(", ".join(candidate["authors"]))
            filled.append("autor")
        genres = candidate.get("genres") or []
        if genres and self._is_blank(self.combo_genre.currentText()) and self._is_blank(self.combo_genre2.currentText()):
            self.combo_genre.setEditText(genres[0])
            self.combo_genre2.setEditText(genres[1] if len(genres) > 1 else "")
            filled.append("gênero")
        if candidate.get("series") and self._is_blank(self.combo_series.currentText()):
            self.combo_series.setEditText(candidate["series"])
            filled.append("série")
        same_series = fold(self.combo_series.currentText().strip()) == fold(candidate.get("series") or "")
        if candidate.get("series_number") and self.spin_series_number.value() == 0 and same_series:
            self.spin_series_number.setValue(float(candidate["series_number"]))
            if "série" not in filled:
                filled.append("volume")
        if candidate.get("publisher") and self._is_blank(self.combo_publisher.currentText()):
            self.combo_publisher.setEditText(candidate["publisher"])
            filled.append("editora")
        if candidate.get("pages") and not self.spin_pages.value():
            self.spin_pages.setValue(int(candidate["pages"]))
            filled.append("páginas")
        if candidate.get("language") and self._is_blank(self.combo_language.currentText()):
            self.combo_language.setEditText(candidate["language"])
            filled.append("idioma")
        if candidate.get("isbn") and self._is_blank(self.input_isbn.text()):
            self.input_isbn.setText(candidate["isbn"])
            filled.append("ISBN")
        if download_cover and candidate.get("cover_url") and not self.cover_filename:
            self.download_cover_url(candidate["cover_url"])
            filled.append("capa")
        return filled

    # --- gravação ---
    def build_payload(self) -> dict:
        """Lê o formulário (thread da UI) e monta o payload da API."""
        status = self.combo_status.currentData()
        series = self.combo_series.currentText().strip()
        genres = []
        for text in (self.combo_genre.currentText(), self.combo_genre2.currentText()):
            text = text.strip()
            if text and fold(text) not in (fold(g) for g in genres):
                genres.append(text)
        finish = self.date_finish.date_or_none()
        is_reread = self.chk_reread.isChecked()
        return {
            "title": self.input_title.text().strip(),
            "authors": self.author_list(),
            "genres": genres,
            "series": series or None,
            "series_number": self.spin_series_number.value() if series and self.spin_series_number.value() > 0 else None,
            "publisher": self.combo_publisher.currentText().strip() or None,
            "pages": self.spin_pages.value() or None,
            "format": self.combo_format.currentText(),
            "language": self.combo_language.currentText().strip() or None,
            "isbn": self.input_isbn.text().strip() or None,
            "status": status,
            "progress": self.spin_progress.value() if status == bs.LENDO else None,
            "finish_date": finish.toString("yyyy-MM-dd") if status == bs.LIDO and finish else None,
            "score": round(self.spin_score.value(), 1) if status == bs.LIDO and self.spin_score.value() > 0 else None,
            "reread_of_id": (self.selected_reread_of() or self.book_data.get("reread_of_id")) if is_reread else None,
            "is_favorite": self.chk_favorite.isChecked(),
            "notes": self.input_notes.toPlainText().strip() or None,
            "cover_image": self.cover_filename,
        }

    def _set_busy(self, busy: bool, save_text: str = "Salvar livro"):
        self.btn_save.setEnabled(not busy)
        self.btn_save.setText(save_text)
        self.btn_cancel.setEnabled(not busy)
        if self.is_edit:
            self.btn_delete.setEnabled(not busy)
            self.btn_reread.setEnabled(not busy)

    def save_book(self):
        payload = self.build_payload()
        if not payload["title"]:
            QMessageBox.warning(self, "Aviso", "O título do livro é obrigatório.")
            return
        if self.chk_reread.isChecked() and payload["reread_of_id"] is None and self._briefs is not None:
            QMessageBox.warning(self, "Aviso", "Escolha de qual livro esta leitura é releitura (ou desmarque a opção).")
            return
        self._set_busy(True, "Salvando...")
        book_id = self.book_data["id"] if self.is_edit else None
        call = (lambda: api_client.update_book(book_id, payload)) if self.is_edit else (lambda: api_client.create_book(payload))
        run_async(self, call, self._on_book_saved, self._on_save_failed)

    def _on_book_saved(self, saved_book: dict):
        self.saved_book = saved_book
        self.is_deleted = False
        self.accept()

    def _on_save_failed(self, message: str):
        self._set_busy(False)
        QMessageBox.critical(self, "Erro", f"Erro ao salvar livro: {message}")

    def start_reread(self):
        confirm = QMessageBox.question(
            self, "Reler livro",
            f"Começar uma nova leitura de '{self.book_data.get('title')}'?\n\n"
            "Um novo registro (status Lendo) é criado e ligado a este; este registro não muda.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._set_busy(True)
        run_async(self, api_client.create_reread, self._on_reread_created, self._on_save_failed,
                  self.book_data["id"], bs.LENDO)

    def _on_reread_created(self, book: dict):
        self.reread_created = book
        self.accept()

    def delete_book(self):
        confirm = QMessageBox.question(
            self, "Confirmar exclusão",
            f"Tem certeza que deseja excluir '{self.book_data.get('title')}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self._set_busy(True)
            run_async(self, api_client.delete_book, self._on_book_deleted, self._on_delete_failed, self.book_data["id"])

    def _on_book_deleted(self, deleted: bool):
        if not deleted:
            self._on_delete_failed("o servidor não confirmou a exclusão")
            return
        self.saved_book = self.book_data
        self.is_deleted = True
        self.accept()

    def _on_delete_failed(self, message: str):
        self._set_busy(False)
        QMessageBox.critical(self, "Erro", f"Erro ao excluir livro: {message}")
