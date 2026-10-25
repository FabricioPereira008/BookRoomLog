"""BookDialog: cartão da capa (busca automática, link e arquivo)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QInputDialog, QLabel, QMessageBox, QPushButton

from frontend_desktop import preferences
from frontend_desktop.api_client.client import api_client
from frontend_desktop.cover_loader import cover_loader
from frontend_desktop.ui_helpers import set_button_icon, set_status
from frontend_desktop.workers import run_async

COVER_PREVIEW_SIZE = (160, 240)
NO_COVER_TEXT = "Nenhuma imagem selecionada"


class CoverMixin:
    """Parte do BookDialog que cuida da capa; usa `cover_filename`, `input_title`, `input_authors`,
    `input_isbn` e `_card` do diálogo."""

    def _build_cover_card(self) -> QFrame:
        card, grid = self._card("Capa")
        card.setFixedWidth(210)

        self.lbl_cover_preview = QLabel("Sem\ncapa")
        self.lbl_cover_preview.setFixedSize(*COVER_PREVIEW_SIZE)
        self.lbl_cover_preview.setProperty("class", "cover-preview")
        self.lbl_cover_preview.setAlignment(Qt.AlignCenter)
        grid.addWidget(self.lbl_cover_preview, 0, 0, 1, 2, Qt.AlignHCenter)

        self.lbl_cover_status = QLabel("" if self.cover_filename else NO_COVER_TEXT)
        self.lbl_cover_status.setProperty("class", "status-muted")
        self.lbl_cover_status.setWordWrap(True)
        grid.addWidget(self.lbl_cover_status, 1, 0, 1, 2)

        self.btn_auto_cover = QPushButton("Buscar automático")
        set_button_icon(self.btn_auto_cover, "wand-sparkles")
        self.btn_auto_cover.setToolTip("Procura a capa pelo ISBN ou pelo título e autor (Google Books / Open Library)")
        self.btn_auto_cover.clicked.connect(self.auto_search_cover)

        self.btn_url_cover = QPushButton("Link / URL…")
        set_button_icon(self.btn_url_cover, "link")
        self.btn_url_cover.clicked.connect(self.choose_cover_url)

        self.btn_select_cover = QPushButton("Arquivo…")
        set_button_icon(self.btn_select_cover, "folder-open")
        self.btn_select_cover.clicked.connect(self.choose_cover_image)

        self.btn_remove_cover = QPushButton("Remover capa")
        set_button_icon(self.btn_remove_cover, "x")
        self.btn_remove_cover.setVisible(bool(self.cover_filename))
        self.btn_remove_cover.clicked.connect(self.remove_cover)

        buttons = (self.btn_auto_cover, self.btn_url_cover, self.btn_select_cover, self.btn_remove_cover)
        for row, btn in enumerate(buttons, 2):
            btn.setProperty("class", "small-btn")
            grid.addWidget(btn, row, 0, 1, 2)
        return card

    def set_cover(self, filename, message: str = "") -> None:
        self.cover_filename = filename
        self.btn_remove_cover.setVisible(bool(filename))
        if filename:
            if message:
                set_status(self.lbl_cover_status, "ok", message)
            self.update_cover_preview()
        else:
            self.lbl_cover_preview.clear()
            self.lbl_cover_preview.setText("Sem\ncapa")
            set_status(self.lbl_cover_status, "muted", NO_COVER_TEXT)

    def remove_cover(self):
        self.set_cover(None)

    def auto_search_cover(self):
        title = self.input_title.text().strip()
        isbn = self.input_isbn.text().strip()
        if not title and not isbn:
            QMessageBox.warning(self, "Aviso", "Digite o título (ou o ISBN) antes de buscar a capa.")
            return
        authors = self.author_list()
        self.btn_auto_cover.setEnabled(False)
        self.btn_auto_cover.setText("Buscando...")
        set_status(self.lbl_cover_status, "muted", "Pesquisando capas...")
        run_async(
            self, api_client.auto_search_cover,
            lambda filename: self._on_auto_cover_done(title, filename),
            lambda _msg: self._on_auto_cover_done(title, None),
            title, authors[0] if authors else None, isbn or None, preferences.google_books_key() or None,
        )

    def _on_auto_cover_done(self, title: str, filename):
        self.btn_auto_cover.setEnabled(True)
        self.btn_auto_cover.setText("Buscar automático")
        if filename:
            self.set_cover(filename, "Capa baixada com sucesso.")
        else:
            set_status(self.lbl_cover_status, "error", "Capa não encontrada automaticamente.")
            QMessageBox.warning(
                self, "Não encontrada",
                f"Não foi possível encontrar automaticamente uma capa para '{title}'.\n"
                "Você pode colar o link direto da imagem pelo botão 'Link / URL'."
            )

    def choose_cover_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar imagem de capa", "", "Imagens (*.png *.jpg *.jpeg *.webp)"
        )
        if not file_path:
            return
        filename = api_client.upload_cover(file_path)
        if filename:
            self.set_cover(filename, "Imagem enviada.")
        else:
            QMessageBox.warning(self, "Erro", "Não foi possível enviar a imagem.")

    def choose_cover_url(self):
        url, ok = QInputDialog.getText(self, "Importar capa por URL", "Cole o link/URL da imagem:")
        if ok and url.strip():
            self.download_cover_url(url.strip())

    def download_cover_url(self, url: str) -> None:
        """Baixa a capa em background (usado pelo botão de link e pela busca de dados)."""
        set_status(self.lbl_cover_status, "muted", "Baixando a capa...")
        run_async(self, api_client.upload_cover_url, self._on_url_cover_done,
                  lambda _msg: self._on_url_cover_done(None), url)

    def _on_url_cover_done(self, filename):
        if filename:
            self.set_cover(filename, "Capa baixada.")
        else:
            set_status(self.lbl_cover_status, "error", "Não foi possível baixar a imagem do link.")

    def update_cover_preview(self):
        """Mostra a capa atual; o download/escala acontece em background (cover_loader)."""
        if not self.cover_filename:
            return
        if self.lbl_cover_status.text() == NO_COVER_TEXT:
            self.lbl_cover_status.setText("")
        pixmap = cover_loader.request(self.cover_filename, *COVER_PREVIEW_SIZE)
        if pixmap is not None:
            self.lbl_cover_preview.setPixmap(pixmap)

    def _on_cover_loaded(self, filename: str):
        if filename == self.cover_filename:
            self.update_cover_preview()
