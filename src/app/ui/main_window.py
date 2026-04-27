"""
Janela principal: barra lateral + conteúdo (tema escuro, LoL Pré-bets em primeiro).
"""
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from app.ui.pages.lol_prebets_secondary import LoLSecondaryBetsPage
from app.ui.pages.lol_prebets_player import LoLPlayerBetsPage
from app.ui.pages.lol_draft import LoLDraftPage
from app.ui.pages.lol_compare import LoLComparePage
try:
    from app.ui.pages.dota_prebets_secondary import DotaSecondaryBetsPage
except ImportError:
    DotaSecondaryBetsPage = None
DotaDraftPage = None
try:
    from app.ui.pages.dota_draft_teste import DotaDraftTestePage
except ImportError:
    DotaDraftTestePage = None
try:
    from app.ui.pages.dota_live_esports import DotaLiveEsportsPage
except ImportError:
    DotaLiveEsportsPage = None
try:
    from app.ui.pages.dota_live_test import DotaLiveTestPage
except ImportError:
    DotaLiveTestPage = None
try:
    from app.ui.pages.lol_live_test import LoLLiveTestPage
except ImportError:
    LoLLiveTestPage = None
try:
    from app.ui.pages.database_update import DatabaseUpdatePage
except ImportError:
    DatabaseUpdatePage = None
LoLWinProbUnifiedPage = None
try:
    from app.ui.pages.football_prebets import FootballPrebetsPage
except ImportError:
    FootballPrebetsPage = None


class MainWindow(QMainWindow):
    """Janela principal: navegação lateral + QStackedWidget (Pré-bets LoL = página inicial)."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoL, Dota & Futebol Oracle ML")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 880)
        self.app_state = {"draft_prior_pct": None}

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # —— Sidebar ——
        self._sidebar = QFrame()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(256)
        side = QVBoxLayout(self._sidebar)
        side.setContentsMargins(12, 16, 12, 16)
        side.setSpacing(0)

        self._title = QLabel("Oracle ML")
        self._title.setObjectName("sidebarTitle")
        side.addWidget(self._title)
        self._sub = QLabel("Pré-bets, draft e análise")
        self._sub.setObjectName("sidebarSub")
        self._sub.setWordWrap(True)
        side.addWidget(self._sub)

        self._nav = QListWidget()
        self._nav.setObjectName("nav")
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._nav.setSpacing(2)
        side.addWidget(self._nav, 1)

        # —— Conteúdo ——
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_wrap = QFrame()
        content_wrap.setObjectName("contentHost")
        cw = QVBoxLayout(content_wrap)
        cw.setContentsMargins(12, 12, 12, 12)
        cw.addWidget(self._stack)

        root_layout.addWidget(self._sidebar, 0)
        root_layout.addWidget(content_wrap, 1)

        self._create_pages()

        self._nav.setCurrentRow(0)
        self._stack.setCurrentIndex(0)

        self._nav.currentRowChanged.connect(self._on_nav_changed)
        self.statusBar().showMessage("Pronto — Pré-bets LoL")

    def _add_page(self, label: str, widget: QWidget) -> None:
        item = QListWidgetItem(label)
        item.setSizeHint(QSize(0, 40))
        self._nav.addItem(item)
        self._stack.addWidget(widget)

    def _create_pages(self) -> None:
        self.lol_secondary_bets_page = LoLSecondaryBetsPage()
        self._add_page("Pré-bets LoL", self.lol_secondary_bets_page)

        self.lol_player_bets_page = LoLPlayerBetsPage()
        self._add_page("Pré-bets players LoL", self.lol_player_bets_page)

        self.lol_draft_page = LoLDraftPage()
        self._add_page("Draft LoL", self.lol_draft_page)

        self.lol_compare_page = LoLComparePage()
        self._add_page("Comparar LoL", self.lol_compare_page)

        if DotaSecondaryBetsPage is not None:
            self.dota_secondary_bets_page = DotaSecondaryBetsPage()
            self._add_page("Pré-bets Dota", self.dota_secondary_bets_page)

        if FootballPrebetsPage is not None:
            self.football_prebets_page = FootballPrebetsPage()
            self._add_page("Futebol", self.football_prebets_page)

        if DotaLiveEsportsPage is not None:
            self.dota_live_esports_page = DotaLiveEsportsPage()
            self._add_page("Dota ao vivo", self.dota_live_esports_page)

        if DotaLiveTestPage is not None:
            self.dota_live_test_page = DotaLiveTestPage()
            self._add_page("Teste Dota live", self.dota_live_test_page)

        if LoLLiveTestPage is not None:
            self.lol_live_test_page = LoLLiveTestPage()
            self._add_page("Teste LoL live", self.lol_live_test_page)

        if DotaDraftTestePage is not None:
            self.dota_draft_teste_page = DotaDraftTestePage()
            self._add_page("Teste", self.dota_draft_teste_page)

        if DatabaseUpdatePage is not None:
            self.database_update_page = DatabaseUpdatePage()
            self._add_page("Atualizar bancos", self.database_update_page)

    def _on_nav_changed(self, index: int) -> None:
        if index < 0:
            return
        self._stack.setCurrentIndex(index)
        if 0 <= index < self._nav.count():
            name = self._nav.item(index).text()
            self.statusBar().showMessage(f"Secção: {name}")

    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)

    def show_info(self, title, message):
        QMessageBox.information(self, title, message)
