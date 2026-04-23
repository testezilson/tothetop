"""
Página Dota ao vivo: lista jogos profissionais em andamento via OpenDota API (GET /live).
Apenas jogos com league_id > 0 ou times nomeados (profissionais).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QMessageBox, QTextEdit,
    QHeaderView, QCheckBox, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer

from core.dota.live_esports import (
    OpenDotaLiveClient,
    format_live_game_summary,
    format_live_game_details,
)


class FetchDotaLiveThread(QThread):
    """Thread para buscar jogos ao vivo (pro) e heróis sem travar a UI."""
    finished = Signal(list, dict)  # (pro_games, heroes_map)
    error = Signal(str)

    def __init__(self, client: OpenDotaLiveClient):
        super().__init__()
        self.client = client

    def run(self):
        try:
            heroes = self.client.get_heroes()
            games = self.client.get_pro_live()
            self.finished.emit(games, heroes)
        except Exception as e:
            self.error.emit(str(e))


class DotaLiveEsportsPage(QWidget):
    """Página que exibe jogos de Dota 2 profissionais ao vivo (OpenDota)."""

    def __init__(self):
        super().__init__()
        self.client = OpenDotaLiveClient()
        self._pro_games = []
        self._heroes_map = {}
        self._fetch_thread = None
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._on_refresh_clicked)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Dota 2 — Ao vivo (apenas profissionais)")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        desc = QLabel(
            "Jogos profissionais em andamento. Dados da API OpenDota (GET /live). "
            "Somente partidas de ligas (league_id) ou com times nomeados. "
            "Clique em \"Atualizar\" para carregar e selecione um jogo para ver detalhes."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(desc)

        ctrl = QHBoxLayout()
        self.refresh_btn = QPushButton("Atualizar jogos ao vivo")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.refresh_btn.setToolTip("Busca partidas profissionais em andamento.")
        ctrl.addWidget(self.refresh_btn)

        self.auto_refresh_check = QCheckBox("Atualizar automaticamente a cada")
        self.auto_refresh_check.stateChanged.connect(self._on_auto_refresh_changed)
        ctrl.addWidget(self.auto_refresh_check)
        self.auto_refresh_interval = QSpinBox()
        self.auto_refresh_interval.setMinimum(30)
        self.auto_refresh_interval.setMaximum(300)
        self.auto_refresh_interval.setValue(60)
        self.auto_refresh_interval.setSuffix(" s")
        ctrl.addWidget(self.auto_refresh_interval)
        ctrl.addWidget(QLabel(""))
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.status_label = QLabel("Clique em \"Atualizar jogos ao vivo\" para carregar.")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        table_group = QGroupBox("Jogos ao vivo (profissionais)")
        table_layout = QVBoxLayout()
        self.games_table = QTableWidget()
        self.games_table.setColumnCount(8)
        self.games_table.setHorizontalHeaderLabels([
            "Liga", "Radiant", "Placar", "x", "Placar", "Dire", "Tempo", "Vant. ouro"
        ])
        self.games_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.games_table.horizontalHeader().setStretchLastSection(True)
        self.games_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.games_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.games_table.setAlternatingRowColors(True)
        self.games_table.itemSelectionChanged.connect(self._on_selection_changed)
        table_layout.addWidget(self.games_table)
        table_group.setLayout(table_layout)
        layout.addWidget(table_group)

        details_group = QGroupBox("Detalhes do jogo selecionado")
        details_layout = QVBoxLayout()
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFontFamily("Consolas")
        self.details_text.setMinimumHeight(180)
        self.details_text.setPlaceholderText("Selecione um jogo na tabela para ver detalhes (tempo, placar, jogadores e heróis).")
        details_layout.addWidget(self.details_text)
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)

    def _on_auto_refresh_changed(self, state):
        if state == Qt.CheckState.Checked.value or state == 2:
            interval_ms = self.auto_refresh_interval.value() * 1000
            self._auto_refresh_timer.start(interval_ms)
        else:
            self._auto_refresh_timer.stop()

    def _on_refresh_clicked(self):
        self.status_label.setText("Buscando jogos ao vivo (apenas profissionais)...")
        self.refresh_btn.setEnabled(False)
        self._fetch_thread = FetchDotaLiveThread(self.client)
        self._fetch_thread.finished.connect(self._on_live_fetched)
        self._fetch_thread.error.connect(self._on_live_error)
        self._fetch_thread.start()

    def _on_live_fetched(self, games, heroes_map):
        self._fetch_thread = None
        self.refresh_btn.setEnabled(True)
        self._pro_games = games
        self._heroes_map = heroes_map or {}
        self._fill_games_table()
        if not games:
            self.status_label.setText("Nenhum jogo profissional ao vivo no momento.")
        else:
            self.status_label.setText(f"Encontrados {len(games)} jogo(s) profissional(is) ao vivo.")

    def _on_live_error(self, msg):
        self._fetch_thread = None
        self.refresh_btn.setEnabled(True)
        self.status_label.setText("Erro ao buscar.")
        QMessageBox.warning(self, "Erro", f"Não foi possível buscar jogos ao vivo:\n{msg}")

    def _fill_games_table(self):
        self.games_table.setRowCount(len(self._pro_games))
        for row, game in enumerate(self._pro_games):
            s = format_live_game_summary(game, self._heroes_map)
            self.games_table.setItem(row, 0, QTableWidgetItem(s["league_display"]))
            self.games_table.setItem(row, 1, QTableWidgetItem(s["radiant_name"]))
            self.games_table.setItem(row, 2, QTableWidgetItem(str(s["radiant_score"])))
            self.games_table.setItem(row, 3, QTableWidgetItem("x"))
            self.games_table.setItem(row, 4, QTableWidgetItem(str(s["dire_score"])))
            self.games_table.setItem(row, 5, QTableWidgetItem(s["dire_name"]))
            self.games_table.setItem(row, 6, QTableWidgetItem(s["game_time_str"]))
            self.games_table.setItem(row, 7, QTableWidgetItem(f"{s['radiant_lead']:+d}"))

    def _on_selection_changed(self):
        row = self.games_table.currentRow()
        if row < 0 or row >= len(self._pro_games):
            self.details_text.clear()
            return
        game = self._pro_games[row]
        text = format_live_game_details(game, self._heroes_map)
        self.details_text.setPlainText(text)
        self.details_text.setPlaceholderText("")
