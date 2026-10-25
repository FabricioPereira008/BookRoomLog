import logging
from datetime import date
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame, QScrollArea, QSizePolicy, QGridLayout,
    QPushButton, QMessageBox
)
from PySide6.QtCore import Signal, Qt
from frontend_desktop.cover_loader import cover_loader
from frontend_desktop.views import book_status as bs
from frontend_desktop.views.components.charts import BarRow, HorizontalBarChart, MonthlyBarChart
from frontend_desktop.views.components.book_card_delegate import placeholder_pixmap
from frontend_desktop.views.components.book_grid import BookGrid, MODE_FULL
from frontend_desktop.views.dialogs.top3_dialog import Top3Dialog
from frontend_desktop.api_client.client import api_client
from frontend_desktop.workers import run_async
from frontend_desktop import icons
from frontend_desktop.styles.tokens import COLORS

logger = logging.getLogger(__name__)


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def pages_text(pages) -> str:
    return f"{int(pages or 0):,}".replace(",", ".") + " págs."


class StatCard(QFrame):
    def __init__(self, title: str, value: str, icon: str = "book-open", parent=None):
        super().__init__(parent)
        self.setProperty("class", "stat-card")
        self.setFixedHeight(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon_box = QFrame()
        icon_box.setProperty("class", "stat-icon-box")
        icon_box.setFixedSize(38, 38)
        icon_layout = QVBoxLayout(icon_box)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel()
        icon_label.setPixmap(icons.pixmap(icon, COLORS["accent_text"], 20))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_layout.addWidget(icon_label)
        layout.addWidget(icon_box)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)
        info_layout.setAlignment(Qt.AlignVCenter)
        self.val_label = QLabel(value)
        self.val_label.setProperty("class", "stat-value")
        info_layout.addWidget(self.val_label)
        self.title_label = QLabel(title)
        self.title_label.setProperty("class", "stat-label")
        info_layout.addWidget(self.title_label)
        layout.addLayout(info_layout)
        layout.addStretch()

    def set_value(self, val: str):
        self.val_label.setText(val)

    def set_title(self, title: str):
        self.title_label.setText(title)


RANK_COLORS = ("#fbbf24", "#cbd5e1", "#d97706")  # ouro, prata, bronze
PODIUM_COVER = {1: (150, 225), 2: (116, 174), 3: (116, 174)}


class PodiumCard(QFrame):
    """Um lugar do pódio: capa, posição, título, autor e nota. Clique abre o livro."""
    clicked = Signal(dict)

    def __init__(self, place: int, parent=None):
        super().__init__(parent)
        self.place = place
        self.book: dict = {}
        self.setProperty("class", "podium-card")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.rank = QLabel(f"{place}º")
        self.rank.setAlignment(Qt.AlignCenter)
        self.rank.setFixedSize(34, 34)
        self.rank.setStyleSheet(
            f"color: #0b0c10; background-color: {RANK_COLORS[place - 1]}; border-radius: 17px; font-weight: 800;")
        layout.addWidget(self.rank, 0, Qt.AlignHCenter)
        w, h = PODIUM_COVER[place]
        self.cover = QLabel()
        self.cover.setFixedSize(w, h)
        self.cover.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cover, 0, Qt.AlignHCenter)
        self.title = QLabel("")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.title.setFixedWidth(max(w + 40, 170))
        self.title.setProperty("class", "podium-title")
        layout.addWidget(self.title, 0, Qt.AlignHCenter)
        self.meta = QLabel("")
        self.meta.setAlignment(Qt.AlignCenter)
        self.meta.setWordWrap(True)
        self.meta.setFixedWidth(max(w + 40, 170))
        self.meta.setProperty("class", "status-muted")
        layout.addWidget(self.meta, 0, Qt.AlignHCenter)
        cover_loader.subscribe(self._on_cover_loaded)

    def set_book(self, book: Optional[dict]) -> None:
        self.book = book or {}
        self.setVisible(bool(book))
        if not book:
            return
        self.title.setText(book.get("title") or "")
        score = book.get("score")
        parts = [bs.main_author(book)] + ([f"Nota {score:g}"] if score is not None else [])
        self.meta.setText(" · ".join(p for p in parts if p))
        self._update_cover()

    def _update_cover(self):
        w, h = PODIUM_COVER[self.place]
        filename = self.book.get("cover_image")
        pixmap = cover_loader.request(filename, w, h) if filename else None
        self.cover.setPixmap(pixmap or placeholder_pixmap(w, h))

    def _on_cover_loaded(self, filename: str):
        if self.book and filename == self.book.get("cover_image"):
            self._update_cover()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.book:
            self.clicked.emit(self.book)
        super().mousePressEvent(event)


class HighlightTile(QFrame):
    """Destaque do ano: rótulo pequeno em cima e o valor (ex.: "Duna · 680 págs.")."""

    def __init__(self, label: str, icon: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "highlight-tile")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        icon_label = QLabel()
        icon_label.setPixmap(icons.pixmap(icon, COLORS["accent_text"], 18))
        layout.addWidget(icon_label, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(1)
        caption = QLabel(label)
        caption.setProperty("class", "stat-label")
        text.addWidget(caption)
        self.value = QLabel("—")
        self.value.setProperty("class", "highlight-value")
        self.value.setWordWrap(True)
        text.addWidget(self.value)
        layout.addLayout(text, 1)

    def set_value(self, text: str) -> None:
        self.value.setText(text or "—")


class YearbookView(QWidget):
    book_selected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("yearbookView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.current_year = date.today().year
        self.summary: dict = {}
        self._year_seq = 0
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setObjectName("yearbookScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setAttribute(Qt.WA_StyledBackground, True)

        container = QWidget()
        container.setObjectName("yearbookScrollContainer")
        container.setAttribute(Qt.WA_StyledBackground, True)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 10, 12, 16)
        container_layout.setSpacing(14)
        container_layout.setAlignment(Qt.AlignTop)

        # 1. Cabeçalho com seletor de ano
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)
        header_title = QLabel("Resumo do ano")
        header_title.setProperty("class", "section-header")
        header.addWidget(header_title)
        header.addStretch()
        year_label = QLabel("Ano:")
        year_label.setProperty("class", "yearbook-year")
        header.addWidget(year_label)
        self.year_combo = QComboBox()
        self.year_combo.setFixedWidth(100)
        self.year_combo.currentIndexChanged.connect(self.on_year_changed)
        header.addWidget(self.year_combo)
        container_layout.addLayout(header)

        # 2. Números do ano
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(12)
        self.card_read = StatCard("Livros lidos", "0", "circle-check")
        self.card_pages = StatCard("Páginas lidas", "0", "file-text")
        self.card_avg = StatCard("Média de nota", "N/A", "star")
        self.card_rereads = StatCard("Releituras", "0", "repeat")
        for card in (self.card_read, self.card_pages, self.card_avg, self.card_rereads):
            stats_layout.addWidget(card)
        container_layout.addLayout(stats_layout)

        # 3. Pódio do ano (top 3)
        podium = self._section("Pódio do ano")
        self.podium_hint = QLabel("")
        self.podium_hint.setProperty("class", "status-muted")
        podium.header.addWidget(self.podium_hint)
        podium.header.addStretch()
        self.btn_top3 = QPushButton("Escolher top 3")
        self.btn_top3.setProperty("class", "small-btn")
        self.btn_top3.setCursor(Qt.PointingHandCursor)
        self.btn_top3.clicked.connect(self.choose_top3)
        podium.header.addWidget(self.btn_top3)
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addStretch()
        self.podium_cards = {place: PodiumCard(place) for place in (1, 2, 3)}
        for place in (2, 1, 3):  # 1º no centro, mais alto
            card = self.podium_cards[place]
            card.clicked.connect(self.book_selected.emit)
            row.addWidget(card, 0, Qt.AlignBottom)
        row.addStretch()
        podium.body.addLayout(row)
        self.podium_empty = QLabel("Nenhum livro lido neste ano.")
        self.podium_empty.setProperty("class", "empty-state-text")
        self.podium_empty.setAlignment(Qt.AlignCenter)
        podium.body.addWidget(self.podium_empty)
        container_layout.addWidget(podium)

        # 4. Ritmo do ano + destaques
        row = QHBoxLayout()
        row.setSpacing(14)
        monthly = self._section("Livros lidos por mês")
        self.monthly_chart = MonthlyBarChart()
        monthly.body.addWidget(self.monthly_chart)
        row.addWidget(monthly, 3)
        highlights = self._section("Destaques")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.tile_longest = HighlightTile("Mais longo", "file-text")
        self.tile_shortest = HighlightTile("Mais curto", "bookmark")
        self.tile_best = HighlightTile("Melhor nota", "star")
        self.tile_author = HighlightTile("Autor do ano", "user")
        self.tile_series = HighlightTile("Série do ano", "layers")
        self.tile_averages = HighlightTile("Por livro", "timer")
        for i, tile in enumerate((self.tile_longest, self.tile_shortest, self.tile_best,
                                  self.tile_author, self.tile_series, self.tile_averages)):
            grid.addWidget(tile, i // 2, i % 2)
        highlights.body.addLayout(grid)
        row.addWidget(highlights, 2)
        container_layout.addLayout(row)

        # 5. Gêneros, autores e formatos
        row = QHBoxLayout()
        row.setSpacing(14)
        genres = self._section("Gêneros do ano")
        self.genre_chart = HorizontalBarChart(value_format=lambda v: f"{int(v)}")
        genres.body.addWidget(self.genre_chart)
        genres.body.addStretch()
        row.addWidget(genres, 1)
        authors = self._section("Autores mais lidos")
        self.author_chart = HorizontalBarChart(value_format=lambda v: f"{int(v)}", max_rows=5)
        authors.body.addWidget(self.author_chart)
        authors.body.addStretch()
        row.addWidget(authors, 1)
        formats = self._section("Formatos")
        self.format_chart = HorizontalBarChart(value_format=lambda v: f"{int(v)}", max_rows=3)
        formats.body.addWidget(self.format_chart)
        formats.body.addStretch()
        row.addWidget(formats, 1)
        container_layout.addLayout(row)

        # 6. Livros lidos
        self.books_section = self._section("Livros lidos")
        self.books_section.setObjectName("yearbookBooksSection")
        self.sub_label = self.books_section.title
        self.book_grid = BookGrid(mode=MODE_FULL)
        self.book_grid.book_selected.connect(self.book_selected.emit)
        self.books_section.body.addWidget(self.book_grid)
        container_layout.addWidget(self.books_section)
        container_layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    @staticmethod
    def _section(title: str) -> QFrame:
        """Card de seção com cabeçalho (título + espaço para ações) e corpo."""
        frame = QFrame()
        frame.setProperty("class", "section-card")
        frame.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        frame.header = QHBoxLayout()
        frame.title = QLabel(title)
        frame.title.setProperty("class", "section-header")
        frame.header.addWidget(frame.title)
        layout.addLayout(frame.header)
        frame.body = QVBoxLayout()
        frame.body.setSpacing(10)
        layout.addLayout(frame.body)
        return frame

    def load_data(self):
        run_async(
            self, api_client.get_overall_stats, self._on_overall_loaded,
            lambda msg: logger.error("Erro ao carregar anuário: %s", msg),
        )

    def _on_overall_loaded(self, overall: dict):
        available_years = overall.get("available_years", []) or [date.today().year]
        keep = self.current_year if self.current_year in available_years else available_years[0]
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for y in available_years:
            self.year_combo.addItem(str(y), y)
        self.year_combo.setCurrentIndex(max(0, self.year_combo.findData(keep)))
        self.year_combo.blockSignals(False)
        self.load_year(keep)

    def on_year_changed(self):
        year = self.year_combo.currentData()
        if year:
            self.load_year(year)

    def load_year(self, year: int):
        self._year_seq += 1
        seq = self._year_seq
        run_async(
            self, api_client.get_yearbook,
            lambda summary: self._on_year_loaded(seq, year, summary),
            lambda msg: logger.error("Erro ao carregar dados do ano %s: %s", year, msg),
            year,
        )

    def _on_year_loaded(self, seq: int, year: int, summary: dict):
        if seq != self._year_seq:
            return
        self.current_year = year
        self.summary = summary
        count = summary.get("total_books_read", 0)
        avg = summary.get("average_score")
        self.card_read.set_value(str(count))
        self.card_read.set_title(self.compare_text(count, summary.get("previous_year_read"), year))
        self.card_pages.set_value(f"{summary.get('total_pages_read', 0):,}".replace(",", "."))
        self.card_avg.set_value(f"{avg:.1f}/10" if avg is not None else "N/A")
        self.card_rereads.set_value(str(summary.get("rereads", 0)))

        self._show_podium(summary)
        self.monthly_chart.set_data(summary.get("monthly_read") or [0] * 12, year)
        self._show_highlights(summary)
        self.genre_chart.set_rows([
            BarRow(g["name"], g["count"], f"{g['name']}: {plural(g['count'], 'livro', 'livros')}", g.get("color"))
            for g in summary.get("genres", [])])
        self.author_chart.set_rows([
            BarRow(a["name"], a["count"], f"{a['name']}: {plural(a['count'], 'livro', 'livros')} · {pages_text(a.get('pages'))}")
            for a in summary.get("authors", [])])
        self.format_chart.set_rows([
            BarRow(f["name"], f["count"], f"{f['name']}: {plural(f['count'], 'livro', 'livros')}")
            for f in summary.get("formats", [])])

        books = summary.get("books", [])
        self.sub_label.setText(f"Livros lidos em {year} ({plural(len(books), 'livro', 'livros')})")
        self.book_grid.set_books(books)

    @staticmethod
    def compare_text(count: int, previous, year: int) -> str:
        if previous is None:
            return "Livros lidos"
        diff = count - previous
        if diff == 0:
            return f"Livros lidos · igual a {year - 1}"
        return f"Livros lidos · {'+' if diff > 0 else ''}{diff} vs {year - 1}"

    def _show_podium(self, summary: dict):
        top3 = summary.get("top3", [])
        for place, card in self.podium_cards.items():
            card.set_book(top3[place - 1] if len(top3) >= place else None)
        self.podium_empty.setVisible(not top3)
        self.btn_top3.setEnabled(bool(summary.get("books")))
        if not top3:
            self.podium_hint.setText("")
        elif summary.get("top3_custom"):
            self.podium_hint.setText("Escolhido por você")
        else:
            self.podium_hint.setText("Sugestão pelas notas — escolha o seu")

    def _show_highlights(self, summary: dict):
        def book_text(book, extra):
            return f"{book['title']} · {extra}" if book else ""
        longest, shortest, best = summary.get("longest_book"), summary.get("shortest_book"), summary.get("best_book")
        self.tile_longest.set_value(book_text(longest, pages_text((longest or {}).get("pages"))))
        self.tile_shortest.set_value(book_text(shortest, pages_text((shortest or {}).get("pages"))))
        self.tile_best.set_value(book_text(best, f"nota {(best or {}).get('score', 0):g}"))
        authors, series = summary.get("authors", []), summary.get("series", [])
        self.tile_author.set_value(f"{authors[0]['name']} · {plural(authors[0]['count'], 'livro', 'livros')}" if authors else "")
        self.tile_series.set_value(f"{series[0]['name']} · {plural(series[0]['count'], 'livro', 'livros')}" if series else "")
        parts = []
        if summary.get("average_pages") is not None:
            parts.append(f"{pages_text(summary['average_pages'])} em média")
        if summary.get("favorites"):
            parts.append(plural(summary["favorites"], "favorito", "favoritos"))
        self.tile_averages.set_value(" · ".join(parts))

    def choose_top3(self):
        books = self.summary.get("books", [])
        if not books:
            return
        current = [b["id"] for b in self.summary.get("top3", [])] if self.summary.get("top3_custom") else []
        dialog = Top3Dialog(self.current_year, books, current, self)
        if dialog.exec() and dialog.selected_ids is not None:
            self._save_top3(dialog.selected_ids)

    def _save_top3(self, book_ids: list):
        year = self.current_year
        self._year_seq += 1
        seq = self._year_seq
        run_async(
            self, api_client.set_yearbook_top3,
            lambda summary: self._on_year_loaded(seq, year, summary),
            lambda msg: QMessageBox.critical(self, "Pódio", f"Não foi possível salvar o pódio: {msg}"),
            year, book_ids,
        )
