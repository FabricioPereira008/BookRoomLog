import time

from PySide6.QtCore import QDate, QEvent, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtWidgets import QWidget

from frontend_desktop import icons, theme
from frontend_desktop.cover_loader import CoverLoader, render_cover_image
from frontend_desktop.styles.tokens import COLORS, qss_mapping
from frontend_desktop.views.components.charts import BarRow, HorizontalBarChart, MonthlyBarChart
from frontend_desktop.views.components.cover_mosaic import CoverMosaic, tile_rects
from frontend_desktop.views.dialogs.optional_date_edit import OptionalDateEdit
from frontend_desktop.workers import ApiWorker, run_async


def test_theme_builds_and_applies(qapp):
    qss = theme.load_qss()
    assert "$" not in qss.replace("$$", "") and COLORS["accent"] in qss
    assert qss_mapping()["r_md"] == "10px"
    assert theme.build_palette().color(theme.QPalette.Highlight).name() == COLORS["accent"]
    assert theme.load_fonts()
    theme.apply_theme(qapp)
    theme.setup_live_stylesheet(qapp)
    qapp._force_reload_qss()
    assert theme.get_qss_path().exists()


def test_icons(qapp, tmp_path):
    assert not icons.pixmap("book-open", "#ffffff", 16).isNull()
    assert icons.pixmap("nao-existe").width() > 0
    assert not icons.icon("star", "#ffffff", 16, "#000000").isNull()
    assert icons.export_tinted_svg("book", "#123456", tmp_path).endswith("book-123456.svg")


def test_workers(qapp):
    results, errors = [], []
    ok = ApiWorker(lambda x: x * 2, 21)
    ok.succeeded.connect(results.append)
    ok.run()
    bad = ApiWorker(lambda: 1 / 0)
    bad.failed.connect(errors.append)
    bad.run()
    assert results == [42] and errors

    owner = QWidget()
    got = []
    run_async(owner, lambda: "ok", got.append, lambda msg: got.append(msg))
    for _ in range(100):
        qapp.processEvents()
        if got:
            break
        time.sleep(0.01)
    for worker in list(owner.__dict__.get("_workers", ())):
        worker.wait(2000)
    qapp.processEvents()
    assert got == ["ok"]
    from frontend_desktop.workers import shutdown_workers
    shutdown_workers(qapp, 100)


def test_cover_loader_cache(qapp, tmp_path, monkeypatch):
    from frontend_desktop import cover_loader as cl
    image = QImage(60, 90, QImage.Format_RGB32)
    image.fill(0xFF0000)
    path = tmp_path / "a.png"
    image.save(str(path))
    assert render_cover_image(str(path), 40, 60).size().width() == 40
    assert render_cover_image(str(path), 80, 60, contain=True).width() == 40  # encaixa sem recortar
    assert render_cover_image(str(tmp_path / "nada.png"), 10, 10) is None

    monkeypatch.setattr(cl.api_client, "get_cover_path", lambda name: str(path) if name == "a.png" else None)
    loader = CoverLoader(max_items=1)
    loaded = []
    loader.loaded.connect(loaded.append)
    assert loader.request("a.png", 40, 60) is None
    loader.request("b.png", 40, 60)
    loader.wait_for_done(2000)
    qapp.processEvents()
    assert loaded == ["a.png"] and loader.request("a.png", 40, 60) is not None
    assert loader.request("b.png", 40, 60) is None and len(loader._failed) == 1
    loader.request("a.png", 20, 30)
    loader.wait_for_done(2000)
    qapp.processEvents()
    assert len(loader) == 1  # LRU com 1 item
    loader.invalidate("b.png")
    assert not loader._failed
    loader.invalidate()
    assert len(loader) == 0

    owner = QWidget()
    calls = []
    owner.slot = lambda name: calls.append(name)

    class Receiver(QWidget):
        def on_loaded(self, name):
            calls.append(name)
    receiver = Receiver()
    loader.subscribe(receiver.on_loaded)
    loader.loaded.emit("x")
    assert calls == ["x"]


def test_charts_paint_and_tooltips(qapp):
    monthly = MonthlyBarChart()
    monthly.resize(600, 200)
    monthly.set_data([1, 0, 3], 2025)
    assert len(monthly.values) == 12 and monthly.tooltip_for(0) == "jan/2025: 1 livro lido"
    assert monthly.tooltip_for(2).endswith("3 livros lidos")
    monthly.grab()
    monthly.set_data([])
    monthly.grab()

    bars = HorizontalBarChart(value_format=lambda v: f"{v:g}", max_rows=2)
    bars.resize(400, 100)
    bars.set_rows([BarRow("Drama", 3, dot_color="#ff0000"), BarRow("Humor", 1, "Humor: 1"), BarRow("Extra", 1)])
    assert len(bars.rows) == 2 and bars.tooltip_for(0) == "Drama: 3" and bars.tooltip_for(1) == "Humor: 1"
    bars.grab()
    event = QMouseEvent(QEvent.MouseMove, QPointF(10, 10), QPointF(10, 10), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    bars.mouseMoveEvent(event)
    assert bars.hover_index == 0
    bars.grab()
    bars.leaveEvent(QEvent(QEvent.Leave))
    assert bars.hover_index is None
    bars.set_rows([])
    bars.grab()
    assert bars.index_at(QPointF(5, 5)) is None


def test_cover_mosaic(qapp):
    assert [r.width() for r in tile_rects(2, 206, 160)] == [100, 100]
    mosaic = CoverMosaic(["a.jpg", "b.jpg"], title="Ana", accent_color="#ff0000", badge_icon="user")
    mosaic.resize(300, 160)
    mosaic.set_corner_widget(QWidget())
    mosaic.grab()
    mosaic._on_cover_loaded("a.jpg")
    empty = CoverMosaic([], title="")
    empty.resize(200, 160)
    empty.grab()


def test_optional_date_edit(qapp):
    edit = OptionalDateEdit()
    assert edit.is_blank() and edit.date_or_none() is None
    edit.stepBy(1)  # primeiro passo só preenche com hoje
    assert edit.date() == QDate.currentDate()
    edit.stepBy(1)
    assert edit.date() == QDate.currentDate().addDays(1)
    edit.set_optional_date(None)
    assert edit.is_blank()
    edit.set_optional_date(QDate(2024, 1, 2))
    assert edit.date_or_none() == QDate(2024, 1, 2)
    from PySide6.QtGui import QKeyEvent
    edit.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert edit.is_blank()


def test_main_app_creates_window(qapp, monkeypatch):
    from frontend_desktop import main_app
    monkeypatch.setattr(main_app, "QApplication", lambda argv: qapp)
    monkeypatch.setattr(main_app.MainWindow, "refresh_all_data", lambda self: None)
    app = main_app.create_app()
    window = main_app.create_main_window(app)
    assert window.windowTitle().startswith("BookRoomLog")
    main_app.show_main_window(window)
    window.close()
