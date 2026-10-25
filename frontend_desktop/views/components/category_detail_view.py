import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QColorDialog, QMessageBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from frontend_desktop.views.components.book_grid import ScrollableBookGrid
from frontend_desktop.views.components.management_view import CATEGORY_LABELS, DEFAULT_GENRE_COLOR
from frontend_desktop.views.components.yearbook_view import StatCard
from frontend_desktop.api_client.client import api_client
from frontend_desktop.workers import run_async
from frontend_desktop.ui_helpers import set_button_icon, style_color_dot
from frontend_desktop.preferences import SCOPE_ALL, SCOPE_READ, category_scope

logger = logging.getLogger(__name__)


class CategoryDetailView(QWidget):
    back_requested = Signal()
    book_selected = Signal(dict)
    data_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("categoryDetailView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.category_type = ""
        self.category_id = None
        self.category_data = {}
        self.scope = SCOPE_READ
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        top_bar = QHBoxLayout()
        self.btn_back = QPushButton("Voltar")
        set_button_icon(self.btn_back, "arrow-left")
        self.btn_back.setProperty("class", "cancel-btn")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self.btn_back)
        top_bar.addStretch()
        self.btn_edit_color = QPushButton("Alterar cor da tag")
        set_button_icon(self.btn_edit_color, "tags")
        self.btn_edit_color.setProperty("class", "small-btn")
        self.btn_edit_color.setCursor(Qt.PointingHandCursor)
        self.btn_edit_color.setVisible(False)
        self.btn_edit_color.clicked.connect(self.on_change_color)
        top_bar.addWidget(self.btn_edit_color)
        main_layout.addLayout(top_bar)

        self.title_layout = QHBoxLayout()
        self.color_dot = QLabel()
        self.color_dot.setFixedSize(16, 16)
        self.color_dot.setVisible(False)
        self.kind_label = QLabel("")
        self.kind_label.setProperty("class", "settings-desc")
        self.title_label = QLabel("")
        self.title_label.setProperty("class", "view-title-xl")
        self.title_layout.addWidget(self.color_dot)
        self.title_layout.addWidget(self.title_label)
        self.title_layout.addWidget(self.kind_label, 0, Qt.AlignBottom)
        self.title_layout.addStretch()
        main_layout.addLayout(self.title_layout)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self.card_all_books = StatCard("Livros", "0", "library")  # só no modo "todos os livros"
        self.card_all_books.setVisible(False)
        self.card_read_books = StatCard("Livros lidos", "0", "circle-check")
        self.card_pages = StatCard("Páginas lidas", "0", "file-text")
        stats_layout.addWidget(self.card_all_books)
        stats_layout.addWidget(self.card_read_books)
        stats_layout.addWidget(self.card_pages)
        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

        self.section_label = QLabel("Livros lidos")
        self.section_label.setProperty("class", "section-header-small")
        main_layout.addWidget(self.section_label)

        self.book_grid = ScrollableBookGrid(sorts=("finished", "score", "series", "title", "pages"))
        self.book_grid.book_selected.connect(self.book_selected.emit)
        main_layout.addWidget(self.book_grid)

    def load_category(self, category_type: str, category_id: int):
        if (category_type, category_id) != (self.category_type, self.category_id):
            self.book_grid.clear_filters()  # busca de outra categoria não deve vazar para esta
        self.category_type = category_type
        self.category_id = category_id
        self.scope = category_scope()
        run_async(
            self, api_client.get_category_details,
            lambda data: self._on_category_loaded(category_type, category_id, data),
            lambda msg: logger.error("Erro ao carregar detalhes da categoria: %s", msg),
            category_type, category_id, self.scope,
        )

    def _on_category_loaded(self, category_type: str, category_id: int, data: dict):
        if (category_type, category_id) != (self.category_type, self.category_id):
            return  # usuário já navegou para outra categoria
        self.title_label.setText(data.get("name") or "")
        self.kind_label.setText(CATEGORY_LABELS.get(category_type, ("",))[0])
        is_genre = category_type == "genre"
        self.color_dot.setVisible(is_genre)
        self.btn_edit_color.setVisible(is_genre)
        if is_genre:
            style_color_dot(self.color_dot, data.get("color") or DEFAULT_GENRE_COLOR, 16)

        self.category_data = data
        show_all = self.scope == SCOPE_ALL
        self.card_all_books.setVisible(show_all)
        self.card_all_books.set_value(str(data.get("total_books", 0)))
        self.card_read_books.set_value(str(data.get("read_books", 0)))
        self.card_pages.set_value(f"{data.get('total_pages', 0):,}".replace(",", "."))
        self.section_label.setText("Todos os livros" if show_all else "Livros lidos")
        self.book_grid.set_books(data.get("books", []))

    def on_change_color(self):
        if self.category_type != "genre" or not self.category_id:
            return
        current_color = self.category_data.get("color") or DEFAULT_GENRE_COLOR
        qcolor = QColorDialog.getColor(QColor(current_color), self, "Escolher nova cor do gênero")
        if not qcolor.isValid():
            return
        category_id = self.category_id
        run_async(
            self, api_client.update_category,
            lambda _res: self._on_color_saved(category_id),
            lambda msg: QMessageBox.critical(self, "Erro", f"Não foi possível atualizar a cor: {msg}"),
            "genre", category_id, None, qcolor.name(),
        )

    def _on_color_saved(self, category_id: int):
        if self.category_type == "genre" and self.category_id == category_id:
            self.load_category(self.category_type, self.category_id)
        self.data_changed.emit()
