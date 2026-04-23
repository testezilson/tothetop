"""
Janela principal da aplicação com abas para LoL/Dota e Pré-bets/Draft.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QMessageBox
)
from PySide6.QtCore import Qt
from app.ui.pages.lol_prebets_secondary import LoLSecondaryBetsPage
from app.ui.pages.lol_prebets_player import LoLPlayerBetsPage
from app.ui.pages.lol_draft import LoLDraftPage
from app.ui.pages.lol_compare import LoLComparePage
# Aba "LoL - Ao vivo" desativada (reviver: descomentar import e bloco em _create_pages)
# from app.ui.pages.lol_live_esports import LoLLiveEsportsPage
try:
    from app.ui.pages.dota_prebets_secondary import DotaSecondaryBetsPage
except ImportError:
    DotaSecondaryBetsPage = None
# Aba "Dota - Draft Live" desativada (reviver: descomentar import e bloco em _create_pages)
# try:
#     from app.ui.pages.dota_draft import DotaDraftPage
# except ImportError:
#     DotaDraftPage = None
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
# Aba "LoL - Prob. de Vitória" desativada (reviver: descomentar import e bloco em _create_pages)
# try:
#     from app.ui.pages.lol_win_prob_unified import LoLWinProbUnifiedPage
# except ImportError:
#     LoLWinProbUnifiedPage = None
LoLWinProbUnifiedPage = None
try:
    from app.ui.pages.football_prebets import FootballPrebetsPage
except ImportError:
    FootballPrebetsPage = None


class MainWindow(QMainWindow):
    """Janela principal com sistema de abas."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoL, Dota & Futebol Oracle ML - Desktop App")
        self.setMinimumSize(1200, 800)
        # Estado compartilhado entre abas (ex.: prior do draft da Comparar → Early-Game / Full-Game)
        self.app_state = {"draft_prior_pct": None}
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Sistema de abas
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Criar páginas
        self._create_pages()
        
        # Status bar
        self.statusBar().showMessage("Pronto")
        
        # Conectar sinais
        self.tabs.currentChanged.connect(self._on_tab_changed)
    
    def _create_pages(self):
        """Cria todas as páginas da aplicação."""
        # LoL Pré-bets Secundárias (Kills, Torres, Dragons, etc.)
        self.lol_secondary_bets_page = LoLSecondaryBetsPage()
        self.tabs.addTab(self.lol_secondary_bets_page, "LoL - Pré-bets Secundárias")
        
        # LoL Pré-bets Players (Kills, Deaths, Assists)
        self.lol_player_bets_page = LoLPlayerBetsPage()
        self.tabs.addTab(self.lol_player_bets_page, "LoL - Pré-bets Players")
        
        # LoL Draft Live
        self.lol_draft_page = LoLDraftPage()
        self.tabs.addTab(self.lol_draft_page, "LoL - Draft Live")
        
        # LoL Comparar Composições
        self.lol_compare_page = LoLComparePage()
        self.tabs.addTab(self.lol_compare_page, "LoL - Comparar Composições")
        # LoL Esports ao vivo (desativado — reviver: descomentar import e bloco abaixo)
        # self.lol_live_esports_page = LoLLiveEsportsPage()
        # self.tabs.addTab(self.lol_live_esports_page, "LoL - Ao vivo")
        # LoL Prob. de Vitória (desativado — reviver: descomentar import e bloco abaixo)
        # if LoLWinProbUnifiedPage is not None:
        #     self.lol_win_prob_unified_page = LoLWinProbUnifiedPage()
        #     self.tabs.addTab(self.lol_win_prob_unified_page, "LoL - Prob. de Vitória")
        
        # Dota Pré-bets Secundárias
        if DotaSecondaryBetsPage is not None:
            self.dota_secondary_bets_page = DotaSecondaryBetsPage()
            self.tabs.addTab(self.dota_secondary_bets_page, "Dota - Pré-bets Secundárias")

        # Futebol (API-Sports)
        if FootballPrebetsPage is not None:
            self.football_prebets_page = FootballPrebetsPage()
            self.tabs.addTab(self.football_prebets_page, "Futebol - Pré-bets")
        
        # Dota Draft Live (desativado — reviver: descomentar import e bloco abaixo)
        # if DotaDraftPage is not None:
        #     self.dota_draft_page = DotaDraftPage()
        #     self.tabs.addTab(self.dota_draft_page, "Dota - Draft Live")
        
        # Dota Ao vivo (apenas profissionais, OpenDota)
        if DotaLiveEsportsPage is not None:
            self.dota_live_esports_page = DotaLiveEsportsPage()
            self.tabs.addTab(self.dota_live_esports_page, "Dota - Ao vivo")

        # TESTE DOTA LIVE GAME (modelo kills_remaining + Over/Under)
        if DotaLiveTestPage is not None:
            self.dota_live_test_page = DotaLiveTestPage()
            self.tabs.addTab(self.dota_live_test_page, "TESTE DOTA LIVE GAME")

        # TESTE LOL LIVE GAME (modelo kills_remaining + Over/Under)
        if LoLLiveTestPage is not None:
            self.lol_live_test_page = LoLLiveTestPage()
            self.tabs.addTab(self.lol_live_test_page, "TESTE LOL LIVE GAME")
        
        # TESTE (testezudo v2.7 - mesmo layout, nova matemática)
        if DotaDraftTestePage is not None:
            self.dota_draft_teste_page = DotaDraftTestePage()
            self.tabs.addTab(self.dota_draft_teste_page, "TESTE")
        
        # Atualização de Bancos de Dados
        if DatabaseUpdatePage is not None:
            self.database_update_page = DatabaseUpdatePage()
            self.tabs.addTab(self.database_update_page, "🔄 Atualizar Bancos")
    
    def _on_tab_changed(self, index):
        """Chamado quando a aba é alterada."""
        tab_name = self.tabs.tabText(index)
        self.statusBar().showMessage(f"Aba ativa: {tab_name}")
    
    def show_error(self, title, message):
        """Mostra uma mensagem de erro."""
        QMessageBox.critical(self, title, message)
    
    def show_info(self, title, message):
        """Mostra uma mensagem informativa."""
        QMessageBox.information(self, title, message)
