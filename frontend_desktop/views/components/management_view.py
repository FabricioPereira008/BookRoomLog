"""Páginas de autores, gêneros, séries e editoras: cards com mosaico de capas, busca, criar/editar/excluir."""
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QGridLayout, QFrame, QMessageBox, QInputDialog, QColorDialog, QSizePolicy, QToolButton, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from frontend_desktop.api_client.client import api_client
from frontend_desktop.text_search import fold, fold_query
from frontend_desktop.workers import run_async
from frontend_desktop.ui_helpers import add_search_icon
from frontend_desktop.views.components.cover_mosaic import CoverMosaic
from frontend_desktop.preferences import SCOPE_ALL, SCOPE_READ, category_scope

logger = logging.getLogger(__name__)

DEFAULT_GENRE_COLOR = "#b45309"
# Rótulos por tipo de categoria: (singular, plural, "novo/nova", ícone do selo)
CATEGORY_LABELS = {
    "author": ("Autor", "Autores", "Novo autor", "user"),
    "genre": ("Gênero", "Gêneros", "Novo gênero", None),
    "series": ("Série", "Séries", "Nova série", "layers"),
    "publisher": ("Editora", "Editoras", "Nova editora", "building-2"),
}


def card_count_text(item: dict, scope: str) -> str:
    """"3 livros · 900 págs." (só lidos) ou "30 livros · 4 lidos · 900 págs." (todos); páginas são as dos lidos."""
    count = item.get("books_count", 0) or 0
    pages = item.get("total_pages", 0) or 0
    text = f"{count} {'livro' if count == 1 else 'livros'}"
    if scope == SCOPE_ALL:
        done = item.get("read_count", 0) or 0
        text += f" · {done} {'lido' if done == 1 else 'lidos'}"
    if pages:
        text += f" · {pages:,} págs.".replace(",", ".")
    return text


class ManageItemCard(QFrame):
    """Card de uma categoria. Coleta nome/cor/confirmação; a chamada à API fica com a ManagementView
    (o card é recriado após cada mudança, então não pode ser dono de threads)."""
    clicked = Signal(str, int)  # category_type, item_id
    edit_requested = Signal(dict, dict)  # item, campos novos ({"name", "color"?})
    delete_requested = Signal(dict)

    def __init__(self, category_type: str, item_data: dict, parent=None, scope: str = SCOPE_READ):
        super().__init__(parent)
        self.category_type = category_type
        self.item_data = item_data
        self.scope = scope
        self.setProperty("class", "manage-card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(230)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 12)
        layout.setSpacing(10)

        # Capa em mosaico (livros do item); gênero ganha faixa de cor, os demais um selo com o ícone do tipo
        is_genre = self.category_type == "genre"
        self.mosaic = CoverMosaic(
            self.item_data.get("cover_samples") or [],
            title=self.item_data.get("name", ""),
            accent_color=(self.item_data.get("color") or DEFAULT_GENRE_COLOR) if is_genre else None,
            badge_icon=CATEGORY_LABELS[self.category_type][3],
        )
        layout.addWidget(self.mosaic)

        # Editar/Excluir ficam num menu "⋯" que só aparece no hover (também no clique direito)
        self.menu_btn = QToolButton()
        self.menu_btn.setText("⋯")
        self.menu_btn.setProperty("class", "card-menu-btn")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setFixedSize(30, 26)
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu = QMenu(self.menu_btn)
        self.menu.addAction("Editar", self.on_edit)
        self.menu.addAction("Excluir", self.on_delete)
        self.menu_btn.setMenu(self.menu)
        self.mosaic.set_corner_widget(self.menu_btn)
        self.menu_btn.setVisible(False)

        info = QVBoxLayout()
        info.setContentsMargins(8, 0, 8, 0)
        info.setSpacing(2)
        name_label = QLabel(self.item_data.get("name", ""))
        name_label.setProperty("class", "manage-card-title")
        name_label.setToolTip(self.item_data.get("name", ""))
        info.addWidget(name_label)
        count_label = QLabel(card_count_text(self.item_data, self.scope))
        count_label.setProperty("class", "manage-card-count")
        info.addWidget(count_label)
        layout.addLayout(info)

    def enterEvent(self, event):
        self.menu_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.menu.isVisible():
            self.menu_btn.setVisible(False)
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        self.menu.exec(event.globalPos())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.category_type, self.item_data["id"])
        super().mousePressEvent(event)

    def on_edit(self):
        name, ok = QInputDialog.getText(self, "Editar", "Novo nome:", text=self.item_data["name"])
        if not ok or not name.strip():
            return
        fields = {"name": name.strip()}
        if self.category_type == "genre":
            color = self.item_data.get("color") or DEFAULT_GENRE_COLOR
            qcolor = QColorDialog.getColor(QColor(color), self, "Escolha a cor da tag")
            fields["color"] = qcolor.name() if qcolor.isValid() else color
        self.edit_requested.emit(self.item_data, fields)

    def on_delete(self):
        name = self.item_data["name"]
        count = self.item_data.get("books_count", 0)
        warn_text = f"Tem certeza que deseja excluir '{name}'?"
        if count > 0:
            warn_text += f"\n\n{count} livro(s) vinculado(s) ficarão sem esse dado (os livros não são apagados)."
        confirm = QMessageBox.question(self, "Confirmar exclusão", warn_text, QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            self.delete_requested.emit(self.item_data)


class ManagementView(QWidget):
    category_selected = Signal(str, int)  # category_type, item_id
    data_changed = Signal()

    def __init__(self, category_type: str, parent=None):
        super().__init__(parent)
        self.setObjectName("managementView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.category_type = category_type
        self.singular, self.plural, self.new_label, _ = CATEGORY_LABELS[category_type]
        self.items = []
        self.scope = SCOPE_READ
        self.current_cols = 4
        self._load_seq = 0
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        header = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(f"Buscar em {self.plural.lower()}...")
        add_search_icon(self.search_input)
        self.search_input.setFixedWidth(280)
        self.search_input.textChanged.connect(self.render_items)
        header.addWidget(self.search_input)
        header.addStretch()
        self.btn_new = QPushButton(f"+ {self.new_label}")
        self.btn_new.setProperty("class", "action-btn")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.clicked.connect(self.on_create_new)
        header.addWidget(self.btn_new)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("managementScrollArea")
        self.scroll.setAttribute(Qt.WA_StyledBackground, True)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container.setObjectName("managementScrollContainer")
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

    def calculate_cols(self) -> int:
        available_width = self.scroll.width()
        if available_width <= 200:
            available_width = self.width()
        if available_width <= 200:
            available_width = 1200
        return max(2, (available_width - 32) // (250 + 16))

    def load_data(self):
        """Busca os itens em background e renderiza ao terminar (descarta respostas antigas)."""
        self._load_seq += 1
        seq = self._load_seq
        self.scope = category_scope()
        run_async(
            self, api_client.get_categories,
            lambda items: self._on_items_loaded(seq, items),
            lambda msg: logger.error("Erro ao carregar %s: %s", self.category_type, msg),
            self.category_type, self.scope,
        )

    def _on_items_loaded(self, seq: int, items: list):
        if seq != self._load_seq:
            return
        self.items = items
        self.render_items()

    def visible_items(self) -> list:
        """Itens que passam na busca; no modo "só lidos", categorias sem nenhum lido ficam de fora."""
        term = fold_query(self.search_input.text())
        items = [i for i in self.items if term in fold(i.get("name"))]
        if self.scope != SCOPE_ALL and not term:
            items = [i for i in items if i.get("books_count")]
        return items

    def render_items(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        filtered = self.visible_items()
        if not filtered:
            text = f"Nenhum registro encontrado em {self.plural}."
            if self.items and self.scope != SCOPE_ALL:
                text += " Só aparecem os que têm livros lidos (veja Configurações → Aparência)."
            empty = QLabel(text)
            empty.setWordWrap(True)
            empty.setProperty("class", "empty-state-text")
            self.grid_layout.addWidget(empty, 0, 0)
            return

        self.current_cols = cols = self.calculate_cols()
        for col in range(self.grid_layout.columnCount()):
            self.grid_layout.setColumnStretch(col, 0)
        for col in range(cols):  # colunas iguais: um card sozinho não ocupa a linha toda
            self.grid_layout.setColumnStretch(col, 1)
        for idx, itm in enumerate(filtered):
            card = ManageItemCard(self.category_type, itm, scope=self.scope)
            card.clicked.connect(self.category_selected.emit)
            card.edit_requested.connect(self.on_edit_requested)
            card.delete_requested.connect(self.on_delete_requested)
            self.grid_layout.addWidget(card, idx // cols, idx % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.calculate_cols() != self.current_cols:
            self.render_items()

    def on_item_changed(self, *_):
        self.load_data()
        self.data_changed.emit()

    def _on_failed(self, action: str, message: str):
        QMessageBox.critical(self, "Erro", f"Falha ao {action}: {message}")

    def on_edit_requested(self, item: dict, fields: dict):
        run_async(self, api_client.update_category, self.on_item_changed, lambda m: self._on_failed("editar", m),
                  self.category_type, item["id"], fields.get("name"), fields.get("color"))

    def on_delete_requested(self, item: dict):
        run_async(self, api_client.delete_category, self.on_item_changed, lambda m: self._on_failed("excluir", m),
                  self.category_type, item["id"])

    def on_create_new(self):
        name, ok = QInputDialog.getText(self, self.new_label, "Nome:")
        if not ok or not name.strip():
            return
        color = None
        if self.category_type == "genre":
            qcolor = QColorDialog.getColor(QColor(DEFAULT_GENRE_COLOR), self, "Escolha a cor da tag")
            color = qcolor.name() if qcolor.isValid() else DEFAULT_GENRE_COLOR
        run_async(self, api_client.create_category, self.on_item_changed, lambda m: self._on_failed("criar", m),
                  self.category_type, name.strip(), color)
