import logging
import sys

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication

from app_logging import setup_logging
from frontend_desktop.theme import apply_theme, setup_live_stylesheet
from frontend_desktop.views.main_window import MainWindow
from frontend_desktop.workers import shutdown_workers

logger = logging.getLogger(__name__)


def create_app() -> QApplication:
    """Cria a QApplication já com tema, fontes e live reload (dev)."""
    app = QApplication(sys.argv)
    app.setApplicationName("BookRoomLog")
    app.setOrganizationName("BookRoom")
    apply_theme(app)
    setup_live_stylesheet(app)
    app.aboutToQuit.connect(lambda: shutdown_workers(app))
    return app


def create_main_window(app: QApplication) -> MainWindow:
    """Janela principal; ela sempre abre maximizada na Estante (ver show_main_window)."""
    window = MainWindow()
    if not getattr(sys, "frozen", False):
        # Só em desenvolvimento: F5 recarrega os estilos (não é um atalho do app, não aparece na aba Atalhos)
        shortcut_f5 = QShortcut(QKeySequence("F5"), window)
        shortcut_f5.activated.connect(lambda: getattr(app, "_force_reload_qss", lambda: None)())
    return window


def show_main_window(window: MainWindow) -> None:
    window.showMaximized()


def main():
    setup_logging()
    app = create_app()
    # Se o backend estiver offline, a janela abre e a barra de status informa (carregamento é assíncrono)
    window = create_main_window(app)
    show_main_window(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
