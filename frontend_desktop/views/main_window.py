import logging
from app_version import __version__
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QPushButton, QLabel, QStatusBar
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from frontend_desktop.views.components.sidebar import Sidebar
from frontend_desktop.views.components.shelf_view import ShelfView, next_queue
from frontend_desktop.views.components.book_grid import BookListView, ScrollableBookGrid
from frontend_desktop.views.components.book_table import BookTable
from frontend_desktop.views.components.next_queue_view import NextQueueView
from frontend_desktop.views.components.yearbook_view import YearbookView
from frontend_desktop.views.components.management_view import ManagementView
from frontend_desktop.views.components.category_detail_view import CategoryDetailView
from frontend_desktop.views.components.settings_view import SettingsView
from frontend_desktop.models.book_list_model import BookRole
from frontend_desktop.views.dialogs.book_dialog import BookDialog
from frontend_desktop.views.dialogs.quick_search_dialog import QuickSearchDialog
from frontend_desktop.shortcuts import SHORTCUTS
from frontend_desktop.workers import run_async
from frontend_desktop.api_client.client import api_client
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.view_ids import CATEGORY_VIEWS, ViewId, VIEW_META
from frontend_desktop.styles.tokens import COLORS
from frontend_desktop.ui_helpers import set_button_icon

logger = logging.getLogger(__name__)

# Listas completas por status (Lidos ordenados pela data de término)
LIST_VIEWS = {bs.QUERO_LER: ViewId.WANT, bs.PROXIMO: ViewId.NEXT, bs.LIDO: ViewId.READ}


class DataLoaderThread(QThread):
    """Busca os livros fora da thread da UI."""
    loaded = Signal(list)
    failed = Signal(str)

    def run(self):
        try:
            self.loaded.emit(api_client.get_books())
        except Exception as e:
            self.failed.emit(str(e))


def read_order(books: list) -> list:
    """Lidos, do término mais recente ao mais antigo."""
    done = bs.filter_books(bs.LIDO, books)
    done.sort(key=lambda b: (b.get("finish_date") or "", b.get("id") or 0), reverse=True)
    return done


class MainWindow(QMainWindow):
    def __init__(self, auto_load: bool = True):
        super().__init__()
        self.setWindowTitle("BookRoomLog — Registro de leituras")
        self.resize(1260, 790)
        self.setMinimumSize(980, 640)
        self.previous_nav_index = 0
        self.all_books = []
        self._loader = None
        self._loading = False
        self._refresh_pending = False
        self.init_ui()
        if auto_load:
            self.refresh_all_data()

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigation_changed.connect(self.switch_view)
        self.sidebar.add_book_requested.connect(self.open_add_book_dialog)
        main_layout.addWidget(self.sidebar)

        content_widget = QWidget()
        content_widget.setObjectName("contentArea")
        content_widget.setAttribute(Qt.WA_StyledBackground, True)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        self.view_title_label = QLabel(VIEW_META[ViewId.SHELF].title)
        self.view_title_label.setObjectName("viewTitle")
        header_layout.addWidget(self.view_title_label)
        header_layout.addStretch()
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setProperty("class", "small-btn")
        set_button_icon(self.btn_refresh, "refresh-cw", COLORS["text_muted"])
        self.btn_refresh.clicked.connect(self.refresh_all_data)
        header_layout.addWidget(self.btn_refresh)
        content_layout.addLayout(header_layout)

        # Telas de livros são criadas já (recebem dados); as analíticas sob demanda
        self.stack = QStackedWidget()
        self._views = {}

        self.view_shelf = self._register(ViewId.SHELF, ShelfView())
        self.view_shelf.book_selected.connect(self.open_edit_book_dialog)
        self.view_shelf.view_all_requested.connect(self.open_list_view)

        self.view_want = self._new_book_grid(ViewId.WANT, ("added", "title", "author", "series", "pages"))
        self.view_read = self._new_book_grid(ViewId.READ, ("finished", "score", "title", "author", "pages"))

        self.view_next = self._register(ViewId.NEXT, NextQueueView())
        self.view_next.book_selected.connect(self.open_edit_book_dialog)
        self.view_next.queue_changed.connect(self.apply_next_queue)
        self.view_next.book_saved.connect(lambda book, old: self.apply_book_mutation(book, old_status=old))

        self.view_table = self._register(ViewId.LIBRARY, BookTable())
        self.view_table.book_selected.connect(self.open_edit_book_dialog)

        self._lazy_factories = {
            ViewId.YEARBOOK: self._create_yearbook,
            ViewId.SETTINGS: self._create_settings,
            ViewId.CATEGORY_DETAIL: self._create_category_detail,
        }
        for kind, view_id in CATEGORY_VIEWS.items():
            self._lazy_factories[view_id] = lambda k=kind: self._create_management(k)

        content_layout.addWidget(self.stack)
        main_layout.addWidget(content_widget)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"Pronto • BookRoomLog v{__version__}")
        self._setup_shortcuts()

    # --- atalhos de teclado ---
    def _setup_shortcuts(self):
        """Cria os atalhos do registro (frontend_desktop/shortcuts.py); os nativos só são documentados lá."""
        self._shortcuts = []
        for item in SHORTCUTS:
            if item.action is None:
                continue
            shortcut = QShortcut(QKeySequence(item.keys), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(getattr(self, item.action))
            self._shortcuts.append(shortcut)

    def open_quick_search(self):
        dialog = QuickSearchDialog(self.all_books, self)
        if dialog.exec() and dialog.selected_book:
            self.open_edit_book_dialog(dialog.selected_book)

    @staticmethod
    def selected_book_in(widget):
        """Livro selecionado na lista/tabela que tem o foco (ou None)."""
        while widget is not None and not isinstance(widget, (BookListView, BookTable)):
            widget = widget.parentWidget()
        if isinstance(widget, BookListView):
            index = widget.currentIndex()
            return index.data(BookRole) if index.isValid() and widget.selectionModel().isSelected(index) else None
        if isinstance(widget, BookTable):
            index = widget.table.currentIndex()
            return index.sibling(index.row(), 0).data(BookRole) if index.isValid() else None
        return None

    def delete_selected_book(self):
        book = self.selected_book_in(QApplication.focusWidget())
        if not book:
            return
        confirm = QMessageBox.question(self, "Confirmar exclusão", f"Tem certeza que deseja excluir '{book.get('title')}'?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        run_async(self, api_client.delete_book,
                  lambda ok, bid=book["id"]: self.apply_book_deletion(bid) if ok else None,
                  lambda msg: QMessageBox.critical(self, "Erro", f"Erro ao excluir livro: {msg}"),
                  book["id"])

    def open_list_view(self, status: str):
        """"Ver todos" das faixas da Estante: abre a página completa da lista."""
        if status in LIST_VIEWS:
            self.switch_view(int(LIST_VIEWS[status]))

    # --- registro de views ---
    def _register(self, view_id: ViewId, widget: QWidget) -> QWidget:
        self._views[view_id] = widget
        self.stack.addWidget(widget)
        return widget

    def _new_book_grid(self, view_id: ViewId, sorts) -> ScrollableBookGrid:
        grid = self._register(view_id, ScrollableBookGrid(sorts=sorts))
        grid.book_selected.connect(self.open_edit_book_dialog)
        return grid

    def _ensure_view(self, view_id: ViewId) -> QWidget:
        if view_id not in self._views:
            self._register(view_id, self._lazy_factories[view_id]())
        return self._views[view_id]

    def _create_yearbook(self):
        view = YearbookView()
        view.book_selected.connect(self.open_edit_book_dialog)
        return view

    def _create_management(self, kind: str):
        view = ManagementView(kind)
        view.category_selected.connect(self.open_category_detail)
        view.data_changed.connect(self.refresh_all_data)
        return view

    def _create_settings(self):
        view = SettingsView()
        view.settings_changed.connect(self.refresh_all_data)
        view.data_imported.connect(self.refresh_all_data)
        return view

    def _create_category_detail(self):
        view = CategoryDetailView()
        view.back_requested.connect(self.return_from_category_detail)
        view.book_selected.connect(self.open_edit_book_dialog)
        view.data_changed.connect(self.refresh_all_data)
        return view

    view_yearbook = property(lambda self: self._ensure_view(ViewId.YEARBOOK))
    view_settings = property(lambda self: self._ensure_view(ViewId.SETTINGS))
    view_category_detail = property(lambda self: self._ensure_view(ViewId.CATEGORY_DETAIL))

    @property
    def current_view_id(self) -> ViewId:
        widget = self.stack.currentWidget()
        for view_id, view in self._views.items():
            if view is widget:
                return view_id
        return ViewId.SHELF

    # --- navegação ---
    DYNAMIC_VIEWS = (ViewId.YEARBOOK, *CATEGORY_VIEWS.values())

    def switch_view(self, index: int):
        view_id = ViewId(index)
        self.previous_nav_index = int(view_id)
        self.stack.setCurrentWidget(self._ensure_view(view_id))
        self.view_title_label.setText(VIEW_META[view_id].title)
        self.sidebar.set_current_index(int(view_id))

        # Limpa as buscas ao navegar entre as páginas
        self.view_shelf.clear_filters()
        for grid in (self.view_want, self.view_read):
            grid.clear_filters()

        # Só telas analíticas/dinâmicas recarregam; as demais usam o cache existente
        if view_id in self.DYNAMIC_VIEWS:
            self._views[view_id].load_data()

    def open_category_detail(self, category_type: str, item_id: int):
        self.view_category_detail.load_category(category_type, item_id)
        self.stack.setCurrentWidget(self.view_category_detail)
        self.view_title_label.setText(VIEW_META[ViewId.CATEGORY_DETAIL].title)

    def return_from_category_detail(self):
        self.switch_view(self.previous_nav_index)

    # --- carregamento ---
    def refresh_all_data(self):
        """Recarrega os livros em background; a UI continua responsiva."""
        if self._loading:
            self._refresh_pending = True
            return
        self._loading = True
        self.statusBar().showMessage("Carregando livros...")
        self._loader = DataLoaderThread(self)
        self._loader.loaded.connect(self._apply_loaded_data)
        self._loader.failed.connect(self._on_load_failed)
        self._loader.finished.connect(self._on_loader_finished)
        self._loader.start()

    def refresh_all_data_sync(self):
        """Versão bloqueante (testes e usos pontuais)."""
        try:
            self._apply_loaded_data(api_client.get_books())
        except Exception as e:
            self._on_load_failed(str(e))

    def _on_loader_finished(self):
        self._loading = False
        if self._refresh_pending:
            self._refresh_pending = False
            self.refresh_all_data()

    def _on_load_failed(self, message: str):
        self.statusBar().showMessage(f"Erro de conexão com a API: {message}")

    def closeEvent(self, event):
        if self._loader is not None and self._loader.isRunning():
            self._loader.wait(5000)
        super().closeEvent(event)

    def _apply_loaded_data(self, books: list):
        """Distribui os dados carregados pelas views (sempre na thread da UI)."""
        self.all_books = list(books)
        self.view_shelf.set_books(books)
        self.view_want.set_books(bs.filter_books(bs.QUERO_LER, books))
        self.view_next.set_books(next_queue(books))
        self.view_read.set_books(read_order(books))
        self.view_table.set_books(books)

        current = self.current_view_id
        if current in self.DYNAMIC_VIEWS:
            self._views[current].load_data()
        elif current == ViewId.CATEGORY_DETAIL and self.view_category_detail.category_id:
            detail = self.view_category_detail
            detail.load_category(detail.category_type, detail.category_id)
        self.statusBar().showMessage(f"Total de livros carregados: {len(books)}")

    # --- diálogos ---
    def open_add_book_dialog(self):
        dialog = BookDialog(parent=self)
        if dialog.exec() and dialog.saved_book:
            self.apply_book_mutation(dialog.saved_book, is_new=True)

    def open_edit_book_dialog(self, book_data: dict):
        # O card pode estar desatualizado (ex.: veio do Anuário): edita a versão mais recente em memória
        current = next((b for b in self.all_books if b.get("id") == book_data.get("id")), book_data)
        dialog = BookDialog(book_data=current, parent=self)
        if not dialog.exec():
            return
        if dialog.is_deleted:
            self.apply_book_deletion(current.get("id"))
        elif dialog.reread_created:
            self.apply_book_mutation(dialog.reread_created, is_new=True)
        elif dialog.saved_book:
            self.apply_book_mutation(dialog.saved_book, old_status=current.get("status"))

    # --- mutações in-place ---
    def _list_grids(self):
        """Pares (status, grade da lista completa) alimentados por status."""
        return [(bs.QUERO_LER, self.view_want), (bs.LIDO, self.view_read)]

    def apply_book_deletion(self, book_id: int):
        """Remove o livro in-place de todas as views sem recarregar telas."""
        deleted = next((b for b in self.all_books if b.get("id") == book_id), {})
        if deleted.get("rereads_count"):
            # Era o original de releituras: o servidor promoveu outra leitura e religou as demais
            self.refresh_all_data()
            return
        self.all_books = [b for b in self.all_books if b.get("id") != book_id]
        self._refresh_reread_originals({deleted.get("reread_of_id")})
        self.view_shelf.remove_book(book_id)
        for _, grid in self._list_grids():
            grid.remove_book(book_id)
        self.view_table.remove_book(book_id)
        if deleted.get("status") == bs.PROXIMO:
            self.refresh_next_queue()  # as posições dos que ficaram mudaram
        self.statusBar().showMessage(f"Livro removido. Total: {len(self.all_books)}")

    def _refresh_reread_originals(self, book_ids) -> None:
        """Releitura ligada/desligada/excluída: atualiza o contador de releituras dos registros originais."""
        for original_id in {i for i in book_ids if i}:
            original = next((b for b in self.all_books if b.get("id") == original_id), None)
            if original is None:
                continue
            run_async(self, api_client.get_book,
                      lambda book, status=original.get("status"): self.apply_book_mutation(book, old_status=status),
                      lambda msg: logger.warning("Falha ao atualizar o original da releitura: %s", msg),
                      original_id)

    def refresh_next_queue(self) -> None:
        run_async(self, api_client.get_books, self.apply_next_queue,
                  lambda msg: logger.warning("Falha ao atualizar a fila de próximos: %s", msg),
                  bs.PROXIMO, None, "next")

    def apply_next_queue(self, queue: list) -> None:
        """Fila de Próximos (re)ordenada: atualiza as posições em todas as telas."""
        by_id = {b["id"]: b for b in queue}
        self.all_books = [by_id.get(b.get("id"), b) for b in self.all_books]
        ordered = next_queue(queue)
        self.view_shelf.grid_next.set_books(ordered)
        self.view_shelf.apply_filter()
        self.view_next.set_books(ordered)
        for book in ordered:
            self.view_table.update_book(book)

    def apply_book_mutation(self, saved_book: dict, is_new: bool = False, old_status: str = None):
        """Aplica inserções e edições in-place sem resetar a posição de rolagem."""
        book_id = saved_book.get("id")
        new_status = saved_book.get("status")
        title = saved_book.get("title")
        previous = {} if is_new else next((b for b in self.all_books if b.get("id") == book_id), {})
        if is_new or previous.get("reread_of_id") != saved_book.get("reread_of_id"):
            self._refresh_reread_originals({previous.get("reread_of_id"), saved_book.get("reread_of_id")})
        touches_queue = bs.PROXIMO in (old_status, new_status)

        if is_new:
            self.all_books.insert(0, saved_book)
            self.view_table.insert_book(saved_book)
            self.view_shelf.insert_book_by_status(saved_book)
            for status, grid in self._list_grids():
                if status == new_status:
                    grid.insert_book(0, saved_book)
            if touches_queue:
                self.refresh_next_queue()
            self.statusBar().showMessage(f"Livro '{title}' adicionado. Total: {len(self.all_books)}")
            return

        replaced = False
        for i, b in enumerate(self.all_books):
            if b.get("id") == book_id:
                self.all_books[i] = saved_book
                replaced = True
                break
        if not replaced:
            self.all_books.insert(0, saved_book)

        # Cada lista: entra, sai ou apenas atualiza o card conforme a mudança de status
        for status, grid in self._list_grids():
            was_in, is_in = old_status == status, new_status == status
            if was_in and is_in:
                grid.update_book(saved_book)
            elif was_in:
                grid.remove_book(book_id)
            elif is_in:
                grid.insert_book(0, saved_book)

        self.view_table.update_book(saved_book)
        if old_status == new_status:
            self.view_shelf.update_book(saved_book)
            if touches_queue:
                self.view_next.set_books(next_queue(self.all_books))
            self.statusBar().showMessage(f"Livro '{title}' atualizado.")
            return

        self.view_shelf.remove_book(book_id)
        self.view_shelf.insert_book_by_status(saved_book)
        if touches_queue:
            self.refresh_next_queue()
        self.statusBar().showMessage(f"Livro '{title}' movido para '{new_status}'.")
