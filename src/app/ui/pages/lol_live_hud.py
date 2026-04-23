"""
HUD ao vivo no estilo live-lol-esports: timer, times, estatísticas e tabelas de jogadores.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QFrame, QScrollArea, QDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush
from datetime import datetime

from core.lol.live_esports import LiveEsportsClient, parse_window_for_hud
from core.lol.live_over_under import LiveOverUnderPredictor, _select_checkpoint, K_NEGBIN_BY_CHECKPOINT


def _game_time_str_to_minutes(game_time_str: str) -> float:
    """Converte 'M:SS' ou 'H:MM:SS' para minutos (float)."""
    if not game_time_str or game_time_str == "0:00":
        return 0.0
    parts = game_time_str.strip().split(":")
    try:
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return m + s / 60.0
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 60 + m + s / 60.0
    except (ValueError, IndexError):
        pass
    return 0.0


def _elapsed_game_time_str(start_rfc460: str, end_rfc460: str) -> str:
    """
    Calcula tempo decorrido entre dois timestamps RFC460 (como getInGameTime do andydanger).
    Retorna "M:SS" ou "H:MM:SS".
    """
    if not start_rfc460 or not end_rfc460:
        return "0:00"
    try:
        t0 = datetime.fromisoformat(start_rfc460.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(end_rfc460.replace("Z", "+00:00"))
        sec = int((t1 - t0).total_seconds())
        if sec < 0:
            sec = 0
        m = sec // 60
        s = sec % 60
        h = m // 60
        m = m % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except Exception:
        return "0:00"


# Estilo tema claro (fundo branco, texto preto) para boa leitura
HUD_STYLE = """
    QWidget#hudRoot { background-color: #f5f5f5; }
    QLabel { color: #1a1a1a; font-size: 13px; }
    QLabel#titleLabel { font-size: 16px; font-weight: bold; color: #0d47a1; }
    QLabel#timerLabel { font-size: 18px; font-weight: bold; color: #000; }
    QLabel#teamLabel { font-size: 14px; font-weight: bold; color: #1a1a1a; }
    QGroupBox { color: #333; font-weight: bold; border: 1px solid #bdbdbd; border-radius: 4px; margin-top: 8px; background: #fff; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QTableWidget { background-color: #fff; color: #1a1a1a; gridline-color: #e0e0e0; }
    QTableWidget::item { padding: 4px; color: #1a1a1a; }
    QHeaderView::section { background-color: #1976d2; color: #fff; padding: 6px; }
    QProgressBar { border: 1px solid #bdbdbd; border-radius: 3px; text-align: center; background: #e0e0e0; }
    QProgressBar::chunk { background-color: #4caf50; }
    QPushButton { background-color: #1976d2; color: #fff; border: 1px solid #1565c0; padding: 6px 12px; border-radius: 4px; }
    QPushButton:hover { background-color: #1e88e5; }
    QPushButton:disabled { color: #9e9e9e; background: #e0e0e0; border-color: #bdbdbd; }
    QScrollArea { background: #f5f5f5; }
"""


class LiveHudWidget(QWidget):
    """Widget da HUD: timer, times, stats e tabelas de jogadores."""

    def __init__(self, client=None, event_details=None, game_id=None, parent=None):
        super().__init__(parent)
        self.setObjectName("hudRoot")
        self.client = client or LiveEsportsClient()
        self._event_details = event_details or {}
        self._game_id = game_id
        self._parsed = None
        # Primeiro timestamp do primeiro frame (por game_id), como no andydanger, para calcular tempo de jogo
        self._first_frame_ts_by_game = {}
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._ou_predictor = LiveOverUnderPredictor()
        self.setStyleSheet(HUD_STYLE)
        self._build_ui()

    def set_event_and_game(self, event_details, game_id):
        self._event_details = event_details or {}
        self._game_id = game_id
        self._update_team_names_from_event()
        self._refresh_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Linha do título e timer (tempo de jogo = cronômetro da partida)
        top_row = QHBoxLayout()
        self.league_label = QLabel("—")
        self.league_label.setObjectName("titleLabel")
        top_row.addWidget(self.league_label)
        top_row.addStretch()
        self.game_state_label = QLabel("IN GAME")
        self.game_state_label.setObjectName("timerLabel")
        top_row.addWidget(self.game_state_label)
        time_desc = QLabel("Tempo de jogo:")
        time_desc.setStyleSheet("color: #424242; font-size: 12px;")
        top_row.addWidget(time_desc)
        self.timer_label = QLabel("0:00")
        self.timer_label.setObjectName("timerLabel")
        self.timer_label.setToolTip("Cronômetro da partida (min:seg). Atualiza a cada atualização da HUD.")
        top_row.addWidget(self.timer_label)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Nomes dos times (esquerda = blue, direita = red)
        teams_row = QHBoxLayout()
        self.blue_team_label = QLabel("Time 1 (Azul)")
        self.blue_team_label.setObjectName("teamLabel")
        self.blue_team_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        teams_row.addWidget(self.blue_team_label, 1)
        vs = QLabel("  VS  ")
        vs.setStyleSheet("color: #424242; font-size: 12px;")
        teams_row.addWidget(vs)
        self.red_team_label = QLabel("Time 2 (Vermelho)")
        self.red_team_label.setObjectName("teamLabel")
        self.red_team_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        teams_row.addWidget(self.red_team_label, 1)
        layout.addLayout(teams_row)

        # Estatísticas dos times (por extenso: Kill, Torre, Dragão, Ouro, Barão)
        stats_row = QHBoxLayout()
        self.blue_stats_label = QLabel("Kill: 0  Torre: 0  Dragão: 0  Ouro: 0  Barão: 0")
        self.blue_stats_label.setStyleSheet("color: #1565c0; font-weight: bold;")
        stats_row.addWidget(self.blue_stats_label, 1)
        stats_row.addWidget(QLabel(""), 1)
        self.red_stats_label = QLabel("Kill: 0  Torre: 0  Dragão: 0  Ouro: 0  Barão: 0")
        self.red_stats_label.setStyleSheet("color: #c62828; font-weight: bold;")
        stats_row.addWidget(self.red_stats_label, 1)
        layout.addLayout(stats_row)

        # Barra de vantagem de ouro (proporção do ouro total: Time 1 vs Time 2)
        gold_bar_label = QLabel("Vantagem de ouro (proporção do ouro total de cada time):")
        gold_bar_label.setStyleSheet("color: #424242; font-size: 11px;")
        layout.addWidget(gold_bar_label)
        self.gold_bar = QProgressBar()
        self.gold_bar.setRange(0, 100)
        self.gold_bar.setValue(50)
        self.gold_bar.setTextVisible(True)
        self.gold_bar.setFormat("%v% Time 1 | Time 2")
        self.gold_bar.setToolTip(
            "Proporção do ouro total: a parte esquerda (verde) é o % do ouro do Time 1 (azul), "
            "a direita é do Time 2 (vermelho). 50% = empate em ouro."
        )
        layout.addWidget(self.gold_bar)

        # Over/Under (kills) ao vivo
        ou_frame = QFrame()
        ou_frame.setStyleSheet("QFrame { border: 1px solid #bdbdbd; border-radius: 4px; padding: 6px; background: #fff; }")
        ou_layout = QVBoxLayout(ou_frame)
        ou_title = QLabel("Over/Under (kills) — probabilidade ao vivo")
        ou_title.setStyleSheet("font-weight: bold; color: #0d47a1; font-size: 13px;")
        ou_layout.addWidget(ou_title)
        ou_inner = QHBoxLayout()
        self.ou_lambda_label = QLabel("λ (kills rest. esperadas): —")
        self.ou_lambda_label.setStyleSheet("color: #424242; font-size: 12px;")
        ou_inner.addWidget(self.ou_lambda_label)
        ou_inner.addStretch()
        self.ou_lines_label = QLabel("")
        self.ou_lines_label.setStyleSheet("color: #1a1a1a; font-size: 12px;")
        self.ou_lines_label.setWordWrap(True)
        ou_inner.addWidget(self.ou_lines_label, 1)
        ou_layout.addLayout(ou_inner)
        layout.addWidget(ou_frame)

        # Tabelas de jogadores (scroll)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        # Time azul
        blue_group = QFrame()
        blue_layout = QVBoxLayout(blue_group)
        blue_layout.addWidget(QLabel("TIME 1 (AZUL)"))
        self.blue_table = QTableWidget()
        self.blue_table.setColumnCount(10)
        self.blue_table.setHorizontalHeaderLabels(
            ["Nível", "Campeão", "Jogador", "Vida", "CS", "Kill", "Death", "Assist", "Ouro", "+/-"]
        )
        self.blue_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.blue_table.setAlternatingRowColors(True)
        blue_layout.addWidget(self.blue_table)
        inner_layout.addWidget(blue_group)

        # Time vermelho
        red_group = QFrame()
        red_layout = QVBoxLayout(red_group)
        red_layout.addWidget(QLabel("TIME 2 (VERMELHO)"))
        self.red_table = QTableWidget()
        self.red_table.setColumnCount(10)
        self.red_table.setHorizontalHeaderLabels(
            ["Nível", "Campeão", "Jogador", "Vida", "CS", "Kill", "Death", "Assist", "Ouro", "+/-"]
        )
        self.red_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.red_table.setAlternatingRowColors(True)
        red_layout.addWidget(self.red_table)
        inner_layout.addWidget(red_group)

        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        # Rodapé: patch e botão
        foot = QHBoxLayout()
        self.patch_label = QLabel("Patch: —")
        self.patch_label.setStyleSheet("color: #424242; font-size: 11px;")
        foot.addWidget(self.patch_label)
        foot.addStretch()
        self.refresh_btn = QPushButton("Atualizar HUD")
        self.refresh_btn.clicked.connect(self._refresh_data)
        foot.addWidget(self.refresh_btn)
        self.auto_refresh_check = QLabel("")
        foot.addWidget(self.auto_refresh_check)
        layout.addLayout(foot)

        self._update_team_names_from_event()

    def _update_team_names_from_event(self):
        match = self._event_details.get("match") or {}
        teams = match.get("teams") or []
        if len(teams) >= 1:
            self.blue_team_label.setText(teams[0].get("name") or teams[0].get("slug") or "Time 1")
        if len(teams) >= 2:
            self.red_team_label.setText(teams[1].get("name") or teams[1].get("slug") or "Time 2")
        league = self._event_details.get("league") or {}
        self.league_label.setText(league.get("name") or league.get("slug") or "—")

    def _refresh_data(self):
        """Dispara atualização: primeiro mostra feedback, depois busca dados (evita parecer que nada acontece)."""
        if not self._game_id:
            self._set_empty_state()
            return
        self.refresh_btn.setEnabled(False)
        self.auto_refresh_check.setText("(atualizando...)")
        orig_league = self.league_label.text()
        self.league_label.setText("Atualizando...")
        QTimer.singleShot(80, lambda: self._do_refresh_hud_sync(orig_league))

    def _do_refresh_hud_sync(self, orig_league_text):
        """Executa a requisição e aplica o resultado na UI (rodando na thread principal)."""
        try:
            gid = self._game_id
            # Primeira vez neste jogo: buscar janela inicial (sem startingTime) para tempo real desde 0:00 (getFirstWindow)
            if gid is not None and gid not in self._first_frame_ts_by_game:
                try:
                    first_window = self.client.get_window(gid, first_window=True)
                    first_parsed = parse_window_for_hud(first_window)
                    if first_parsed and first_parsed.get("first_frame_rfc460"):
                        self._first_frame_ts_by_game[gid] = first_parsed["first_frame_rfc460"]
                except Exception:
                    pass  # segue com refresh normal; tempo usará primeiro frame da janela atual
            window = self.client.get_window(gid)
            self._parsed = parse_window_for_hud(window)
            if self._parsed:
                self._apply_parsed()
                self.league_label.setText(orig_league_text or (self._event_details.get("league") or {}).get("name") or "—")
            else:
                self._set_empty_state("Resposta sem dados válidos (frames vazios?).")
        except Exception as e:
            self._set_empty_state(str(e))
        finally:
            self.refresh_btn.setEnabled(True)
            try:
                interval = getattr(self, "_refresh_interval_seconds", 2)
                self.auto_refresh_check.setText(f"(atualiza a cada {interval}s)" if self._refresh_timer.isActive() else "")
            except Exception:
                self.auto_refresh_check.setText("")

    def _on_refresh_tick(self):
        self._refresh_data()

    def start_auto_refresh(self, interval_seconds=2):
        self._refresh_interval_seconds = interval_seconds
        self._refresh_timer.stop()
        self._refresh_timer.start(interval_seconds * 1000)
        self.auto_refresh_check.setText(f"(atualiza a cada {interval_seconds}s)")

    def stop_auto_refresh(self):
        self._refresh_timer.stop()
        self.auto_refresh_check.setText("")

    def _set_empty_state(self, error_msg=None):
        self._parsed = None
        self.timer_label.setText("0:00")
        self.game_state_label.setText("—")
        self.blue_stats_label.setText("Kill: 0  Torre: 0  Dragão: 0  Ouro: 0  Barão: 0")
        self.red_stats_label.setText("Kill: 0  Torre: 0  Dragão: 0  Ouro: 0  Barão: 0")
        self.gold_bar.setValue(50)
        self.blue_table.setRowCount(0)
        self.red_table.setRowCount(0)
        self.patch_label.setText("Patch: —")
        self.ou_lambda_label.setText("λ (kills rest. esperadas): —")
        self.ou_lines_label.setText("")
        if error_msg:
            self.league_label.setText(f"Erro: {error_msg[:40]}")

    # Linhas de kills para exibir O/U (podem ser configuráveis depois)
    OVER_UNDER_LINES = [26.5, 28.5, 30.5]

    def _update_over_under(self, p: dict, game_time_str: str) -> None:
        """Atualiza os labels de Over/Under com base no estado atual do jogo."""
        if not self._ou_predictor.is_available():
            self.ou_lambda_label.setText("λ (kills rest. esperadas): modelo não carregado")
            self.ou_lines_label.setText("Treine com: python src/train_live_over_under.py")
            return
        minute = _game_time_str_to_minutes(game_time_str)
        if minute < 10:
            self.ou_lambda_label.setText("λ (kills rest. esperadas): —")
            self.ou_lines_label.setText("Aguarde 10 min para previsão O/U.")
            return
        blue = p.get("blue_team") or {}
        red = p.get("red_team") or {}
        kills_now = (blue.get("totalKills") or 0) + (red.get("totalKills") or 0)
        gold_blue = blue.get("totalGold") or 0
        gold_red = red.get("totalGold") or 0
        gold_diff = gold_blue - gold_red
        lam = self._ou_predictor.predict_lambda(minute, kills_now, gold_diff)
        self.ou_lambda_label.setText(f"λ (kills rest. esperadas): {lam:.1f}")
        checkpoint = _select_checkpoint(minute)
        k_nb = K_NEGBIN_BY_CHECKPOINT.get(checkpoint, 6)
        parts = []
        for line in self.OVER_UNDER_LINES:
            p_over, p_under = self._ou_predictor.prob_over_under_nb(kills_now, line, lam, k_nb)
            parts.append(f"Linha {line}: Over {p_over*100:.0f}% | Under {p_under*100:.0f}%")
        self.ou_lines_label.setText("  ·  ".join(parts))

    def _apply_parsed(self):
        if not self._parsed:
            return
        p = self._parsed
        # Tempo de jogo como andydanger: primeiro frame (guardado) vs último frame (atual)
        first_ts = p.get("first_frame_rfc460") or ""
        last_ts = p.get("last_frame_rfc460") or ""
        gid = self._game_id
        if gid is not None and first_ts and gid not in self._first_frame_ts_by_game:
            self._first_frame_ts_by_game[gid] = first_ts
        start_ts = self._first_frame_ts_by_game.get(gid) or first_ts
        game_time_str = _elapsed_game_time_str(start_ts, last_ts) if (start_ts and last_ts) else p.get("game_time_str", "0:00")
        self.timer_label.setText(game_time_str)
        self._update_over_under(p, game_time_str)
        state = (p.get("game_state") or "in_game").replace("_", " ").upper()
        self.game_state_label.setText(state)
        blue = p.get("blue_team") or {}
        red = p.get("red_team") or {}
        self.blue_stats_label.setText(
            f"Kill: {blue.get('totalKills', 0)}  Torre: {blue.get('towers', 0)}  "
            f"Dragão: {len(blue.get('dragons') or [])}  Ouro: {(blue.get('totalGold') or 0):,}  "
            f"Barão: {blue.get('barons', 0)}".replace(",", ".")
        )
        self.red_stats_label.setText(
            f"Kill: {red.get('totalKills', 0)}  Torre: {red.get('towers', 0)}  "
            f"Dragão: {len(red.get('dragons') or [])}  Ouro: {(red.get('totalGold') or 0):,}  "
            f"Barão: {red.get('barons', 0)}".replace(",", ".")
        )
        total_gold = (blue.get("totalGold") or 0) + (red.get("totalGold") or 0)
        if total_gold > 0:
            blue_pct = int(100 * (blue.get("totalGold") or 0) / total_gold)
            self.gold_bar.setValue(blue_pct)
            self.gold_bar.setFormat(f"{blue_pct}% Time 1 | Time 2")
        else:
            self.gold_bar.setValue(50)
        self.patch_label.setText(f"Patch: {p.get('patch_version') or '—'}")

        # Tabelas de jogadores (com coluna +/- diferença de ouro vs oponente da rota)
        blue_players = p.get("blue_participants") or []
        red_players = p.get("red_participants") or []
        self.blue_table.setRowCount(len(blue_players))
        for row, pl in enumerate(blue_players):
            self.blue_table.setItem(row, 0, QTableWidgetItem(str(pl.get("level", 1))))
            self.blue_table.setItem(row, 1, QTableWidgetItem(str(pl.get("championId", "?"))))
            self.blue_table.setItem(row, 2, QTableWidgetItem(str(pl.get("summonerName", "?"))))
            hp = pl.get("maxHealth") or 0
            cur = pl.get("currentHealth") or 0
            vida_txt = f"{cur}/{hp}" if (hp > 1 or cur > 0) else "—"
            self.blue_table.setItem(row, 3, QTableWidgetItem(vida_txt))
            self.blue_table.setItem(row, 4, QTableWidgetItem(str(pl.get("creepScore", 0))))
            self.blue_table.setItem(row, 5, QTableWidgetItem(str(pl.get("kills", 0))))
            self.blue_table.setItem(row, 6, QTableWidgetItem(str(pl.get("deaths", 0))))
            self.blue_table.setItem(row, 7, QTableWidgetItem(str(pl.get("assists", 0))))
            self.blue_table.setItem(row, 8, QTableWidgetItem(f"{pl.get('totalGold', 0):,}".replace(",", ".")))
            # +/- ouro vs oponente da mesma rota (blue[i] vs red[i])
            gold_b = pl.get("totalGold") or 0
            gold_r = red_players[row].get("totalGold", 0) if row < len(red_players) else 0
            diff = gold_b - gold_r
            diff_item = QTableWidgetItem(f"{'+' if diff >= 0 else ''}{diff:,}".replace(",", "."))
            diff_item.setForeground(QBrush(QColor("#2e7d32") if diff >= 0 else QColor("#c62828")))
            self.blue_table.setItem(row, 9, diff_item)
        self.red_table.setRowCount(len(red_players))
        for row, pl in enumerate(red_players):
            self.red_table.setItem(row, 0, QTableWidgetItem(str(pl.get("level", 1))))
            self.red_table.setItem(row, 1, QTableWidgetItem(str(pl.get("championId", "?"))))
            self.red_table.setItem(row, 2, QTableWidgetItem(str(pl.get("summonerName", "?"))))
            hp = pl.get("maxHealth") or 0
            cur = pl.get("currentHealth") or 0
            vida_txt = f"{cur}/{hp}" if (hp > 1 or cur > 0) else "—"
            self.red_table.setItem(row, 3, QTableWidgetItem(vida_txt))
            self.red_table.setItem(row, 4, QTableWidgetItem(str(pl.get("creepScore", 0))))
            self.red_table.setItem(row, 5, QTableWidgetItem(str(pl.get("kills", 0))))
            self.red_table.setItem(row, 6, QTableWidgetItem(str(pl.get("deaths", 0))))
            self.red_table.setItem(row, 7, QTableWidgetItem(str(pl.get("assists", 0))))
            self.red_table.setItem(row, 8, QTableWidgetItem(f"{pl.get('totalGold', 0):,}".replace(",", ".")))
            gold_r = pl.get("totalGold") or 0
            gold_b = blue_players[row].get("totalGold", 0) if row < len(blue_players) else 0
            diff = gold_r - gold_b
            diff_item = QTableWidgetItem(f"{'+' if diff >= 0 else ''}{diff:,}".replace(",", "."))
            diff_item.setForeground(QBrush(QColor("#2e7d32") if diff >= 0 else QColor("#c62828")))
            self.red_table.setItem(row, 9, diff_item)


class LiveHudDialog(QDialog):
    """Diálogo que exibe a HUD ao vivo para um jogo selecionado."""

    def __init__(self, event_details, game_id, client=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LoL Esports — HUD ao vivo")
        self.setMinimumSize(900, 700)
        layout = QVBoxLayout(self)
        self.hud = LiveHudWidget(client=client, event_details=event_details, game_id=game_id, parent=self)
        layout.addWidget(self.hud)
        self.hud.set_event_and_game(event_details, game_id)
        self.hud.start_auto_refresh(2)

    def reject(self):
        self.hud.stop_auto_refresh()
        super().reject()

    def accept(self):
        self.hud.stop_auto_refresh()
        super().accept()
