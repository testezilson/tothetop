"""
Página TESTE DOTA LIVE GAME: entrada manual completa para predição kills_remaining.

Usa o projeto dota_live (hero_impacts + Ridge). Sem busca automática de jogos ao vivo.
"""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QSpinBox, QTextEdit, QComboBox, QFrame,
)

from core.shared.paths import path_in_data
from core.dota.live_kills import predict, prob_over, line_fair


def _load_hero_names() -> list[str]:
    """Carrega nomes de heróis do hero_impacts.json (ordenados)."""
    path = path_in_data("hero_impacts.json")
    if not path or not Path(path).exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        heroes = data.get("hero_impacts", data)
        if isinstance(heroes, dict):
            return sorted(heroes.keys())
    except Exception:
        pass
    return []


class DotaLiveTestPage(QWidget):
    """Aba TESTE DOTA LIVE GAME: entrada manual completa (draft + métricas ao vivo)."""

    def __init__(self):
        super().__init__()
        self._hero_names = _load_hero_names()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("TESTE DOTA LIVE GAME — Kills restantes / Over-Under")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        desc = QLabel(
            "Entrada manual: preencha draft (heróis) e métricas ao vivo. "
            "O modelo Ridge + draft priors calcula kills restantes e P(Over) por linha."
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
        live_layout.addWidget(QLabel("Gold diff (Radiant):"))
        self.manual_gold = QSpinBox()
        self.manual_gold.setRange(-50000, 50000)
        self.manual_gold.setValue(0)
        live_layout.addWidget(self.manual_gold)
        live_layout.addWidget(QLabel("Roshan:"))
        self.manual_roshan = QSpinBox()
        self.manual_roshan.setRange(0, 5)
        live_layout.addWidget(self.manual_roshan)
        live_layout.addStretch()
        live_group.setLayout(live_layout)
        layout.addWidget(live_group)

        # --- Draft ---
        draft_group = QGroupBox("Draft (5 Radiant + 5 Dire)")
        draft_layout = QHBoxLayout()
        radiant_frame = QFrame()
        radiant_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        rl = QVBoxLayout(radiant_frame)
        rl.addWidget(QLabel("Radiant:"))
        self.radiant_combos = []
        for i in range(5):
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItem("")
            cb.addItems(self._hero_names)
            cb.setMinimumWidth(140)
            self.radiant_combos.append(cb)
            rl.addWidget(cb)
        draft_layout.addWidget(radiant_frame)
        dire_frame = QFrame()
        dire_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        dl = QVBoxLayout(dire_frame)
        dl.addWidget(QLabel("Dire:"))
        self.dire_combos = []
        for i in range(5):
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItem("")
            cb.addItems(self._hero_names)
            cb.setMinimumWidth(140)
            self.dire_combos.append(cb)
            dl.addWidget(cb)
        draft_layout.addWidget(dire_frame)
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

    def _get_draft_heroes(self) -> tuple[list[str], list[str]]:
        radiant = []
        dire = []
        for cb in self.radiant_combos:
            t = (cb.currentText() or "").strip()
            if t:
                radiant.append(t)
        for cb in self.dire_combos:
            t = (cb.currentText() or "").strip()
            if t:
                dire.append(t)
        return radiant, dire

    def _on_analyze(self):
        radiant_heroes, dire_heroes = self._get_draft_heroes()
        mu, sigma, total_pred = predict(
            minute=self.manual_minute.value(),
            kills_now=self.manual_kills.value(),
            gold_diff_now=self.manual_gold.value(),
            roshan_kills_so_far=self.manual_roshan.value(),
            radiant_heroes=radiant_heroes,
            dire_heroes=dire_heroes,
        )
        if mu is None:
            self.results_text.setPlainText(
                "Modelo não encontrado. Rode os scripts:\n"
                "  1. python scripts/compute_hero_metrics_dota.py -o data/hero_impacts.json\n"
                "  2. python scripts/dota_live/build_snapshots.py\n"
                "  3. python scripts/dota_live/train_live.py"
            )
            return
        kills_now = self.manual_kills.value()
        gold_diff = self.manual_gold.value()
        minute = self.manual_minute.value()
        lines = [39.5, 44.5, 45.5, 46.5, 47.5, 48.5, 49.5, 50.5, 52.5, 54.5, 55.5]
        fair = line_fair(mu, kills_now)
        buf = []
        buf.append(f"Minuto: {minute} | Kills: {kills_now} | Gold diff (Radiant): {gold_diff:+d}")
        buf.append(f"Roshan: {self.manual_roshan.value()}")
        buf.append(f"Draft: {len(radiant_heroes)} Radiant, {len(dire_heroes)} Dire")
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
