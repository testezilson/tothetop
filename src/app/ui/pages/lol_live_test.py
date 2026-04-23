"""
Página TESTE LOL LIVE GAME: entrada manual completa para predição kills_remaining.

Usa o projeto lol_live (champion_impacts + Ridge). Sem busca automática de jogos ao vivo.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QSpinBox, QTextEdit, QComboBox, QFrame,
)

from core.shared.paths import path_in_data
from core.lol.live_kills import predict, prob_over, line_fair


def _load_champion_names() -> list[str]:
    """Carrega nomes de campeões na mesma base do LoL - Draft Live: champion_impacts.csv + oracle_prepared.csv (pick1..pick5)."""
    import pandas as pd
    names = set()

    # 1) champion_impacts.csv (mesma fonte de impactos do Draft Live)
    path_csv = path_in_data("champion_impacts.csv")
    if path_csv and Path(path_csv).exists():
        try:
            df = pd.read_csv(path_csv)
            df.columns = df.columns.str.strip().str.lower()
            if "champion" in df.columns:
                for c in df["champion"].dropna().unique():
                    s = str(c).strip()
                    if s:
                        names.add(s)
        except Exception:
            pass

    # 2) oracle_prepared.csv (pick1..pick5) — mesmo histórico que o Draft Live usa para n_games/fallback
    path_oracle = path_in_data("oracle_prepared.csv")
    if path_oracle and Path(path_oracle).exists():
        try:
            df = pd.read_csv(path_oracle, low_memory=False)
            df.columns = df.columns.str.strip().str.lower()
            pick_cols = [c for c in ["pick1", "pick2", "pick3", "pick4", "pick5"] if c in df.columns]
            for col in pick_cols:
                for c in df[col].dropna().unique():
                    s = str(c).strip()
                    if s:
                        names.add(s)
        except Exception:
            pass

    return sorted(names) if names else []


class LoLLiveTestPage(QWidget):
    """Aba TESTE LOL LIVE GAME: entrada manual completa (draft + métricas ao vivo)."""

    def __init__(self):
        super().__init__()
        self._champion_names = _load_champion_names()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("TESTE LOL LIVE GAME — Kills restantes / Over-Under")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        desc = QLabel(
            "Entrada manual: draft + minuto, kills, gold diff. "
            "Modelo sem torres/barons/dragons; prevê ritmo (kpm_future) e converte para kills restantes."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(desc)

        # --- Métricas ao vivo ---
        live_group = QGroupBox("Métricas ao vivo")
        live_layout = QHBoxLayout()
        live_layout.addWidget(QLabel("Minuto:"))
        self.manual_minute = QSpinBox()
        self.manual_minute.setRange(10, 60)
        self.manual_minute.setValue(15)
        live_layout.addWidget(self.manual_minute)
        live_layout.addWidget(QLabel("Kills:"))
        self.manual_kills = QSpinBox()
        self.manual_kills.setRange(0, 100)
        live_layout.addWidget(self.manual_kills)
        live_layout.addWidget(QLabel("Gold diff (Blue):"))
        self.manual_gold = QSpinBox()
        self.manual_gold.setRange(-50000, 50000)
        self.manual_gold.setValue(0)
        live_layout.addWidget(self.manual_gold)
        live_layout.addStretch()
        live_group.setLayout(live_layout)
        layout.addWidget(live_group)

        # --- Draft ---
        draft_group = QGroupBox("Draft (5 Blue + 5 Red)")
        draft_layout = QHBoxLayout()
        blue_frame = QFrame()
        blue_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        bl = QVBoxLayout(blue_frame)
        bl.addWidget(QLabel("Blue:"))
        self.blue_combos = []
        for i in range(5):
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItem("")
            cb.addItems(self._champion_names)
            cb.setMinimumWidth(140)
            self.blue_combos.append(cb)
            bl.addWidget(cb)
        draft_layout.addWidget(blue_frame)
        red_frame = QFrame()
        red_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        rl = QVBoxLayout(red_frame)
        rl.addWidget(QLabel("Red:"))
        self.red_combos = []
        for i in range(5):
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItem("")
            cb.addItems(self._champion_names)
            cb.setMinimumWidth(140)
            self.red_combos.append(cb)
            rl.addWidget(cb)
        draft_layout.addWidget(red_frame)
        draft_group.setLayout(draft_layout)
        layout.addWidget(draft_group)

        # --- Botão analisar ---
        btn_layout = QHBoxLayout()
        self.analyze_btn = QPushButton("Analisar")
        self.analyze_btn.clicked.connect(self._on_analyze)
        self.analyze_btn.setStyleSheet("padding: 8px 24px; font-weight: bold;")
        btn_layout.addWidget(self.analyze_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # --- Resultados ---
        results_group = QGroupBox("Resultados — Predição kills_remaining")
        rl = QVBoxLayout()
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFontFamily("Consolas")
        self.results_text.setMinimumHeight(200)
        self.results_text.setPlaceholderText(
            "Preencha as métricas e o draft, depois clique em 'Analisar'."
        )
        rl.addWidget(self.results_text)
        results_group.setLayout(rl)
        layout.addWidget(results_group)

    def _get_draft_champions(self) -> tuple[list[str], list[str]]:
        blue = []
        red = []
        for cb in self.blue_combos:
            t = (cb.currentText() or "").strip()
            if t:
                blue.append(t)
        for cb in self.red_combos:
            t = (cb.currentText() or "").strip()
            if t:
                red.append(t)
        return blue, red

    def _on_analyze(self):
        blue_champions, red_champions = self._get_draft_champions()
        mu, sigma, total_pred = predict(
            minute=self.manual_minute.value(),
            kills_now=self.manual_kills.value(),
            gold_diff_now=self.manual_gold.value(),
            blue_champions=blue_champions,
            red_champions=red_champions,
        )
        if mu is None:
            self.results_text.setPlainText(
                "Modelo não encontrado. Rode os scripts:\n"
                "  1. python scripts/lol_live/build_snapshots.py\n"
                "  2. python scripts/lol_live/train_live.py"
            )
            return
        kills_now = self.manual_kills.value()
        gold_diff = self.manual_gold.value()
        minute = self.manual_minute.value()
        lines = [39.5, 44.5, 45.5, 46.5, 47.5, 48.5, 49.5, 50.5, 52.5, 54.5, 55.5]
        fair = line_fair(mu, kills_now)
        buf = []
        buf.append(f"Minuto: {minute} | Kills: {kills_now} | Gold diff (Blue): {gold_diff:+d}")
        buf.append(f"Draft: {len(blue_champions)} Blue, {len(red_champions)} Red")
        buf.append("")
        buf.append(f"Kills restantes predito: {mu:.1f}")
        buf.append(f"Total final estimado: {total_pred:.1f}")
        buf.append(f"Linha fair (P=0.5): {fair}")
        buf.append("")
        buf.append("P(Over) por linha:")
        buf.append("-" * 40)
        for L in lines:
            p = prob_over(mu, sigma, L, kills_now)
            buf.append(f"  Linha {L}: P(Over) = {p:.1%}")
        self.results_text.setPlainText("\n".join(buf))
