import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget, QHBoxLayout
)

from app_version import __version__
from frontend_desktop import icons
from frontend_desktop.styles.tokens import COLORS
from frontend_desktop.ui_helpers import set_button_icon
from frontend_desktop.views.view_ids import NAV_SECTIONS, VIEW_META, ViewId


class Sidebar(QWidget):
    navigation_changed = Signal(int)
    add_book_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(236)
        self.init_ui()

    def _nav_button(self, view_id: ViewId) -> QPushButton:
        meta = VIEW_META[view_id]
        btn = QPushButton(meta.nav_label)
        btn.setProperty("class", "nav-btn")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(btn, meta.icon, COLORS["text_muted"], COLORS["accent_text"], 18)
        self.button_group.addButton(btn, int(view_id))
        return btn

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 18, 14, 14)
        main_layout.setSpacing(4)

        # Marca do app
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.pixmap("book-open", COLORS["accent"], 26))
        brand.addWidget(logo)
        title = QLabel("BookRoomLog")
        title.setObjectName("appTitle")
        brand.addWidget(title)
        brand.addStretch()
        main_layout.addLayout(brand)

        subtitle = QLabel("Suas leituras, em ordem")
        subtitle.setObjectName("appSubtitle")
        main_layout.addWidget(subtitle)
        main_layout.addSpacing(12)

        self.btn_add = QPushButton("Adicionar livro")
        self.btn_add.setObjectName("btnAddBook")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        set_button_icon(self.btn_add, "plus", COLORS["on_accent"], size=18)
        self.btn_add.clicked.connect(self.add_book_requested.emit)
        self.btn_add.setToolTip("Adicionar livro (Ctrl+N) · Buscar livro: Ctrl+F")
        main_layout.addWidget(self.btn_add)
        main_layout.addSpacing(8)

        scroll = QScrollArea()
        scroll.setObjectName("sidebarScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setObjectName("sidebarNavContainer")
        scroll_content.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.nav_buttons = []

        for section_title, view_ids in NAV_SECTIONS:
            label = QLabel(section_title.upper())
            label.setProperty("class", "nav-section")
            layout.addWidget(label)
            for view_id in view_ids:
                btn = self._nav_button(view_id)
                layout.addWidget(btn)
                self.nav_buttons.append(btn)

        self.button_group.button(int(ViewId.SHELF)).setChecked(True)
        layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Configurações fixas na parte inferior
        self.btn_settings = self._nav_button(ViewId.SETTINGS)
        main_layout.addWidget(self.btn_settings)

        self.button_group.idClicked.connect(self.on_nav_clicked)

        platform_name = "Windows" if sys.platform == "win32" else ("macOS" if sys.platform == "darwin" else "Linux")
        version_label = QLabel(f"v{__version__} · {platform_name}")
        version_label.setObjectName("appVersion")
        main_layout.addWidget(version_label)

    def on_nav_clicked(self, nav_id: int):
        self.navigation_changed.emit(nav_id)

    def set_current_index(self, index: int):
        btn = self.button_group.button(index)
        if btn:
            btn.setChecked(True)
