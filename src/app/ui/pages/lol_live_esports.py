"""
Página LoL Esports ao vivo: lista jogos em tempo real e detalhes via API Lolesports.
Inspirado em: https://github.com/AndyDanger/live-lol-esports
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QMessageBox, QTextEdit,
    QHeaderView, QSplitter, QCheckBox, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
import json

from core.lol.live_esports import LiveEsportsClient, format_live_event_summary
from app.ui.pages.lol_live_hud import LiveHudDialog


class FetchLiveThread(QThread):
    """Thread para buscar jogos ao vivo sem travar a UI."""
    finished = Signal(list)  # list of raw events
    error = Signal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        try:
            events = self.client.get_live()
            self.finished.emit(events)
        except Exception as e:
            self.error.emit(str(e))


class FetchEventDetailsThread(QThread):
    """Thread para buscar detalhes de um evento."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, client, event_id):
        super().__init__()
        self.client = client
        self.event_id = event_id

    def run(self):
        try:
            details = self.client.get_event_details(self.event_id)
            self.finished.emit(details or {})
        except Exception as e:
            self.error.emit(str(e))


def _fetch_window_sync(client, game_id, max_len=8000):
    """
    Busca janela ao vivo na thread atual. Retorna (texto, None) em sucesso ou (None, mensagem_erro).
    Usado na thread principal para evitar crashes ao passar dados entre threads.
    """
    try:
        window = client.get_window(game_id)
        if not window:
            return "(Resposta vazia)", None
        text = json.dumps(window, indent=2, ensure_ascii=True, default=str)
        if len(text) > max_len:
            text = text[:max_len] + "\n\n... (truncado)"
        return text, None
    except BaseException as e:
        return None, str(e)


class LoLLiveEsportsPage(QWidget):
    """Página que exibe jogos de LoL Esports ao vivo e informações em tempo real."""

    def __init__(self):
        super().__init__()
        self.client = LiveEsportsClient()
        self._live_events = []  # lista de eventos brutos (getLive)
        self._fetch_thread = None
        self._details_thread = None
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._on_refresh_clicked)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Título
        title = QLabel("LoL Esports ao vivo")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        desc = QLabel(
            "Jogos profissionais em andamento. Dados da API não-oficial Lolesports. "
            "Clique em \"Atualizar\" para carregar e selecione um jogo para ver detalhes."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(desc)

        # Controles
        ctrl = QHBoxLayout()
        self.refresh_btn = QPushButton("Atualizar jogos ao vivo")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.refresh_btn.setToolTip("Busca partidas em andamento agora.")
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

        # Tabela de jogos ao vivo
        table_group = QGroupBox("Jogos ao vivo")
        table_layout = QVBoxLayout()
        self.games_table = QTableWidget()
        self.games_table.setColumnCount(6)
        self.games_table.setHorizontalHeaderLabels([
            "Liga", "Time 1", "Placar 1", "x", "Placar 2", "Time 2"
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

        # Detalhes + Live stats
        splitter = QSplitter(Qt.Orientation.Vertical)

        details_group = QGroupBox("Detalhes do jogo selecionado")
        details_layout = QVBoxLayout()
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFontFamily("Consolas")
        self.details_text.setMinimumHeight(120)
        self.details_text.setPlaceholderText("Selecione um jogo na tabela para ver detalhes e, se estiver em andamento, estatísticas ao vivo.")
        details_layout.addWidget(self.details_text)
        details_group.setLayout(details_layout)
        splitter.addWidget(details_group)

        live_group = QGroupBox("Estatísticas ao vivo (janela do jogo)")
        live_layout = QVBoxLayout()
        btn_row = QHBoxLayout()
        self.live_stats_btn = QPushButton("Atualizar estatísticas ao vivo deste jogo")
        self.live_stats_btn.clicked.connect(self._on_refresh_window_clicked)
        self.live_stats_btn.setEnabled(False)
        btn_row.addWidget(self.live_stats_btn)
        self.open_hud_btn = QPushButton("Abrir HUD (como no site)")
        self.open_hud_btn.setToolTip("Abre uma janela com HUD ao vivo: timer, times, K/T/D/G/B, barra de ouro e tabela de jogadores.")
        self.open_hud_btn.clicked.connect(self._on_open_hud_clicked)
        self.open_hud_btn.setEnabled(False)
        btn_row.addWidget(self.open_hud_btn)
        live_layout.addLayout(btn_row)
        self.live_stats_text = QTextEdit()
        self.live_stats_text.setReadOnly(True)
        self.live_stats_text.setFontFamily("Consolas")
        self.live_stats_text.setMinimumHeight(100)
        self.live_stats_text.setPlaceholderText("Clique em \"Atualizar estatísticas ao vivo\" para o jogo atual da série.")
        live_layout.addWidget(self.live_stats_text)
        live_group.setLayout(live_layout)
        splitter.addWidget(live_group)

        splitter.setSizes([200, 180])
        layout.addWidget(splitter)

    def _on_auto_refresh_changed(self, state):
        if state == Qt.CheckState.Checked.value or state == 2:  # 2 = Checked
            interval_ms = self.auto_refresh_interval.value() * 1000
            self._auto_refresh_timer.start(interval_ms)
        else:
            self._auto_refresh_timer.stop()

    def _on_refresh_clicked(self):
        self.status_label.setText("Buscando jogos ao vivo...")
        self.refresh_btn.setEnabled(False)
        self._fetch_thread = FetchLiveThread(self.client)
        self._fetch_thread.finished.connect(self._on_live_fetched)
        self._fetch_thread.error.connect(self._on_live_error)
        self._fetch_thread.start()

    def _on_live_fetched(self, events):
        self._fetch_thread = None
        self.refresh_btn.setEnabled(True)
        self._live_events = events
        self._fill_games_table()
        if not events:
            self.status_label.setText("Nenhum jogo ao vivo no momento.")
        else:
            self.status_label.setText(f"Encontrados {len(events)} jogo(s) ao vivo.")

    def _on_live_error(self, msg):
        self._fetch_thread = None
        self.refresh_btn.setEnabled(True)
        self.status_label.setText("Erro ao buscar.")
        QMessageBox.warning(self, "Erro", f"Não foi possível buscar jogos ao vivo:\n{msg}")

    def _fill_games_table(self):
        self.games_table.setRowCount(len(self._live_events))
        for row, event in enumerate(self._live_events):
            s = format_live_event_summary(event)
            self.games_table.setItem(row, 0, QTableWidgetItem(s["league_name"]))
            self.games_table.setItem(row, 1, QTableWidgetItem(s["team1"]))
            self.games_table.setItem(row, 2, QTableWidgetItem(str(s["score1"])))
            self.games_table.setItem(row, 3, QTableWidgetItem("x"))
            self.games_table.setItem(row, 4, QTableWidgetItem(str(s["score2"])))
            self.games_table.setItem(row, 5, QTableWidgetItem(s["team2"]))

    def _on_selection_changed(self):
        row = self.games_table.currentRow()
        if row < 0 or row >= len(self._live_events):
            self.details_text.clear()
            self.live_stats_btn.setEnabled(False)
            self.open_hud_btn.setEnabled(False)
            return
        event = self._live_events[row]
        self.live_stats_btn.setEnabled(True)
        self.open_hud_btn.setEnabled(True)
        self._details_thread = FetchEventDetailsThread(self.client, event.get("id"))
        self._details_thread.finished.connect(self._on_details_fetched)
        self._details_thread.error.connect(self._on_details_error)
        self._details_thread.start()
        self.details_text.setPlaceholderText("Carregando detalhes...")
        self.details_text.clear()

    def _on_details_fetched(self, event_data):
        self._details_thread = None
        if not event_data:
            self.details_text.setPlainText("Sem detalhes para este evento.")
            return
        self._last_event_details = event_data
        text = self._format_event_details(event_data)
        self.details_text.setPlainText(text)
        self.details_text.setPlaceholderText("")

    def _on_details_error(self, msg):
        self._details_thread = None
        self.details_text.setPlainText(f"Erro ao carregar detalhes: {msg}")

    def _format_event_details(self, event):
        lines = []
        lines.append(f"Evento: {event.get('id', '?')}")
        lines.append(f"Tipo: {event.get('type', '?')}")
        league = event.get("league") or {}
        lines.append(f"Liga: {league.get('name') or league.get('slug') or '?'}")
        match = event.get("match") or {}
        strategy = match.get("strategy") or {}
        lines.append(f"Série: {strategy.get('type', '?')} — {strategy.get('count', '?')} jogo(s)")
        teams = match.get("teams") or []
        for i, t in enumerate(teams):
            name = t.get("name") or t.get("slug") or "?"
            res = t.get("result") or {}
            wins = res.get("gameWins", 0)
            outcome = res.get("outcome")
            lines.append(f"  Time {i+1}: {name} — {wins} vitória(s)" + (f" ({outcome})" if outcome else ""))
        games = match.get("games") or []
        lines.append("")
        lines.append("Jogos da série:")
        for j, g in enumerate(games):
            gid = g.get("id")
            state = g.get("state", "?")
            number = g.get("number")
            lines.append(f"  Jogo {number or j+1}: id={gid} estado={state}")
        return "\n".join(lines)

    def _get_current_game_id(self):
        """Retorna (game_id, event_details) do jogo em andamento da seleção atual, ou (None, None)."""
        row = self.games_table.currentRow()
        if row < 0 or row >= len(self._live_events):
            return None, None
        details = getattr(self, "_last_event_details", None)
        if not details:
            return None, None
        match = details.get("match") or {}
        games = match.get("games") or []
        for g in games:
            if (g.get("state") or "").lower() == "inprogress":
                return g.get("id"), details
        # Se não há jogo em andamento, retornar último jogo (para HUD mostrar estado final)
        if games:
            return games[-1].get("id"), details
        return None, None

    def _on_refresh_window_clicked(self):
        try:
            current_game_id, details = self._get_current_game_id()
            if not details:
                self.live_stats_text.setPlainText("Carregue os detalhes do jogo primeiro (selecione o jogo).")
                return
            if not current_game_id:
                self.live_stats_text.setPlainText(
                    "Nenhum jogo da série está em andamento no momento. "
                    "As estatísticas ao vivo só existem durante um jogo ativo."
                )
                return
            self.live_stats_text.setPlaceholderText("Buscando estatísticas ao vivo... (aguarde alguns segundos)")
            self.live_stats_btn.setEnabled(False)
            # Executar a requisição na thread principal após um pequeno delay (evita crash em QThread)
            QTimer.singleShot(100, lambda: self._do_fetch_window_on_main_thread(current_game_id))
        except BaseException as e:
            try:
                self.live_stats_text.setPlainText(f"Erro: {e}")
                self.live_stats_text.setPlaceholderText("")
            except Exception:
                pass

    def _on_open_hud_clicked(self):
        try:
            current_game_id, event_details = self._get_current_game_id()
            if not event_details:
                QMessageBox.information(
                    self,
                    "HUD",
                    "Selecione um jogo na tabela e aguarde os detalhes carregarem."
                )
                return
            if not current_game_id:
                QMessageBox.information(
                    self,
                    "HUD",
                    "Nenhum jogo da série com dados disponíveis. A HUD funciona melhor com um jogo em andamento."
                )
                return
            dlg = LiveHudDialog(event_details, current_game_id, client=self.client, parent=self.window())
            dlg.exec()
        except BaseException as e:
            QMessageBox.warning(self, "HUD", f"Erro ao abrir HUD: {e}")

    def _do_fetch_window_on_main_thread(self, game_id):
        """Chamado na thread principal; faz a requisição e atualiza o texto (UI pode travar 2–10 s)."""
        try:
            text, err = _fetch_window_sync(self.client, game_id)
            if err:
                self.live_stats_text.setPlainText(f"Erro: {err}")
            else:
                safe = (text or "").strip() or "Resposta vazia."
                if len(safe) > 10000:
                    safe = safe[:10000] + "\n\n... (truncado)"
                self.live_stats_text.setPlainText(safe)
        except BaseException as e:
            try:
                self.live_stats_text.setPlainText(f"Erro: {e}")
            except Exception:
                pass
        try:
            self.live_stats_text.setPlaceholderText("")
            self.live_stats_btn.setEnabled(True)
        except Exception:
            pass
