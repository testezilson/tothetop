# -*- coding: utf-8 -*-
"""
UI visual da análise de Pré-bets Secundárias LoL (HUD em duas colunas).
Apenas apresentação: números vêm do dicionário retornado por LoLSecondaryBetsAnalyzer.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from core.shared.paths import get_data_dir
import os


# Fundo comum (mesmo do styles.py#prebets)
BG_HUD = "#0e1117"

# Cores: time 1 (verde) / time 2 (dourado) — alinhado à referência
C_TEAM1 = "#34d399"
C_TEAM1_BAR = "#10b981"
C_TEAM2 = "#fbbf24"
C_TEAM2_BAR = "#d97706"
C_MUTED = "#9ca3af"
C_CARD = "#1f2937"
C_CARD_BORDER = "#374151"
C_VS = "#6b7280"


def _abbrev(name: str, n: int = 3) -> str:
    if not name or not str(name).strip():
        return "—"
    words = re.sub(r"\s+", " ", str(name).strip()).split()
    if not words:
        return "—"
    out = "".join(w[0].upper() for w in words if w)[:n]
    return out or "—"


def _format_stat_val(val, stat: str) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    s = (stat or "").lower()
    if s == "gamelength":
        m = int(v)
        s_ = int(round((v - m) * 60))
        if s_ >= 60:
            s_, m = 0, m + 1
        return f"{m}:{s_:02d}"
    return f"{v:.1f}" if (v - int(v)) > 0.01 else str(int(round(v)))


def _line_used(result: dict) -> float:
    if result.get("is_first_stat"):
        return 0.5
    return float(result.get("line", 0) or 0)


def _is_over(val: float, result: dict) -> bool:
    return val > _line_used(result)


def _mean(vals: List[float]) -> float:
    if not vals:
        return 0.0
    return float(sum(vals) / len(vals))


def _over_rate_in_slice(
    items: List[dict], n_take: int, result: dict
) -> Tuple[float, int, float]:
    """
    Sobre os últimos n_take jogos (recência) da lista `items` (já em ordem recente→antigo),
    retorna (taxa over 0-1, n, média do valor).
    """
    if not items or n_take < 1:
        return 0.0, 0, 0.0
    chunk = items[: min(n_take, len(items))]
    lv = [float(c["value"]) for c in chunk if c.get("value") is not None]
    n = len(lv)
    if n == 0:
        return 0.0, 0, 0.0
    o = sum(1 for v in lv if _is_over(v, result))
    return o / n, n, _mean(lv)


def _wins_loses(
    items: List[dict],
) -> Tuple[List[dict], List[dict]]:
    w, l_ = [], []
    for c in items:
        won = c.get("won")
        if won is True:
            w.append(c)
        elif won is False:
            l_.append(c)
    return w, l_


class _TeamAvatar(QLabel):
    """
    Tenta `data/logos/<Time>.png`; opcional carrega imagem de URL (LolFandom) por nome; senão iniciais.
    """

    def __init__(self, team_name: str, side_color: str, size: int = 56, parent=None):
        super().__init__(parent)
        self._team = team_name or ""
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background: #111827; border: 2px solid {side_color}; border-radius: 10px; color: {side_color}; font-size: 14px; font-weight: bold;"
        )
        if self._load_local_png():
            return
        if team_name and len(team_name.strip()) >= 2:
            ab = _abbrev(team_name, 2)
        else:
            ab = "?"
        self.setText(ab)

    def _load_local_png(self) -> bool:
        base = get_data_dir()
        if not base or not self._team:
            return False
        safe = re.sub(r"[^\w\-\.]", "_", self._team.strip())[:80]
        for name in (self._team.strip(), safe):
            for ext in (".png", ".jpg", ".webp"):
                p = os.path.join(base, "logos", f"{name}{ext}")
                if os.path.isfile(p):
                    pm = QPixmap(p)
                    if not pm.isNull():
                        self.setPixmap(
                            pm.scaled(
                                self._size,
                                self._size,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation,
                            )
                        )
                        return True
        return False


class _StatLine(QWidget):
    """Uma linha: label (Last 15) + barra de % + percentagem + avg."""

    def __init__(self, label: str, accent: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(f"color: {C_MUTED}; min-width: 52px;")
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(
            f"""
            QProgressBar {{ background: #1e2533; border: 1px solid #2d3648; border-radius: 4px; min-height: 10px; }}
            QProgressBar::chunk {{ background: {accent}; border-radius: 3px; min-width: 10px; }}
            """
        )
        self._pct = QLabel("—")
        self._pct.setStyleSheet("min-width: 40px; color: #e5e7eb;")
        self._avg = QLabel("")
        self._avg.setStyleSheet(f"color: {C_MUTED}; min-width: 42px;")
        row.addWidget(self._lbl)
        row.addWidget(self._bar, 1)
        row.addWidget(self._pct)
        row.addWidget(self._avg)

    def set_values(self, rate_0_1: float, n: int, avg: float, stat: str) -> None:
        if n <= 0:
            self._bar.setValue(0)
            self._pct.setText("—")
            self._avg.setText("")
            return
        pct = int(round(rate_0_1 * 100))
        self._bar.setValue(min(100, max(0, pct)))
        self._pct.setText(f"{pct:.0f}%")
        self._avg.setText(f"ø {_format_stat_val(avg, stat)}" if stat else "")


class _TopCard(QFrame):
    def __init__(self, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {C_CARD};
                border: 1px solid {C_CARD_BORDER};
                border-left: 4px solid {accent};
                border-radius: 8px;
            }}
            """
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8)
        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"color: {C_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;"
        )
        self._big = QLabel("—")
        self._big.setStyleSheet(f"color: {accent}; font-size: 26px; font-weight: bold;")
        self._sub = QLabel("")
        self._sub.setStyleSheet(f"color: {C_MUTED}; font-size: 11px;")
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet(
            f"""
            QProgressBar {{ background: #1e2533; border: 1px solid #2d3648; border-radius: 3px; min-height: 6px; }}
            QProgressBar::chunk {{ background: {accent}; border-radius: 2px; min-width: 8px; }}
            """
        )
        v.addWidget(self._title)
        v.addWidget(self._big)
        v.addWidget(self._sub)
        v.addWidget(self._bar)

    def set_data(self, over_n: int, n_games: int) -> None:
        if n_games <= 0:
            self._big.setText("—")
            self._sub.setText("sem dados")
            self._bar.setValue(0)
            return
        pct = (over_n / n_games) * 100
        self._big.setText(f"{pct:.1f}%")
        self._sub.setText(f"{over_n}/{n_games}  over na linha")
        self._bar.setValue(int(round(pct)))


def _build_small_table(title: str, color: str) -> Tuple[QWidget, QTableWidget]:
    t = QTableWidget(0, 4)
    t.setHorizontalHeaderLabels(["Amostra", "Jogos", "Over %", "Média"])
    t.setStyleSheet(
        f"""
        QTableWidget {{ gridline-color: {C_CARD_BORDER}; background: #0f1419; color: #e5e7eb; border: 1px solid {C_CARD_BORDER}; border-radius: 6px; }}
        QHeaderView::section {{ background: {C_CARD}; color: {color}; font-weight: 600; border: none; padding: 4px; }}
        QTableWidget::item {{ padding: 4px; }}
        """
    )
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(t.EditTrigger.NoEditTriggers)
    t.setMaximumHeight(200)
    hl = QLabel(title)
    hl.setStyleSheet(
        f"color: {color}; font-size: 12px; font-weight: bold; margin-top:6px; margin-bottom:2px;"
    )
    outer = QWidget()
    w_l = QVBoxLayout(outer)
    w_l.setContentsMargins(0, 0, 0, 0)
    w_l.addWidget(hl)
    w_l.addWidget(t)
    return outer, t


def _fill_table(
    t: QTableWidget,
    rows: List[Tuple[str, int, str, str]],
) -> None:
    t.setRowCount(len(rows))
    for r, (lab, n, overp, avg) in enumerate(rows):
        t.setItem(r, 0, QTableWidgetItem(lab))
        t.setItem(r, 1, QTableWidgetItem(str(n) if n else "—"))
        t.setItem(r, 2, QTableWidgetItem(overp))
        t.setItem(r, 3, QTableWidgetItem(avg))


def build_prebets_hud(result: dict) -> QWidget:
    """Constroi a HUD completa a partir do dict de analyze_bet."""
    root = QWidget()
    root.setObjectName("prebetsHudRoot")
    try:
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    except Exception:
        pass
    root.setStyleSheet(f"QWidget#prebetsHudRoot {{ background: {BG_HUD}; border: none; }}")
    root_l = QVBoxLayout(root)
    root_l.setSpacing(10)
    root_l.setContentsMargins(4, 4, 4, 4)

    stat = result.get("stat", "") or ""
    items1: List[dict] = list(result.get("last_values_team1") or [])
    items2: List[dict] = list(result.get("last_values_team2") or [])

    # —— Duas colunas ——
    mid = QHBoxLayout()
    col1w = _team_column(
        result.get("team1", "T1"), items1, result, C_TEAM1, C_TEAM1_BAR, stat, side="1"
    )
    vs = QLabel("VS")
    vs.setAlignment(Qt.AlignCenter)
    vs.setStyleSheet(
        f"color: {C_VS}; font-size: 12px; font-weight: bold; min-width: 32px; padding: 0 4px;"
    )
    col2w = _team_column(
        result.get("team2", "T2"), items2, result, C_TEAM2, C_TEAM2_BAR, stat, side="2"
    )
    mid.addWidget(col1w, 1)
    mid.addWidget(vs, 0)
    mid.addWidget(col2w, 1)
    root_l.addLayout(mid)
    note = QLabel(
        "<span style='color:#6b7280; font-size:10px;'>VIT/DER: usa a coluna <b>result</b> do banco; "
        "se estiver vazia, infere por ouro do time vs adversário, depois por kills. "
        "Reimporte o CSV (Atualizar bancos) após corrigir o ficheiro, para gravar <b>result</b> corretamente.</span>"
    )
    note.setWordWrap(True)
    note.setTextFormat(Qt.RichText)
    root_l.addWidget(note)

    # —— H2H + Probs + EV (mantém o mesmo conteúdo do texto antigo) ——
    bottom = QFrame()
    bottom.setStyleSheet(
        f"background: {C_CARD}; border: 1px solid {C_CARD_BORDER}; border-radius: 8px; padding: 8px;"
    )
    b_l = QVBoxLayout(bottom)
    lines = _format_summary_blocks(result, stat)
    for block in lines:
        lab = QLabel(block)
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.RichText)
        lab.setStyleSheet("color: #e5e7eb; font-size: 12px;")
        b_l.addWidget(lab)

    root_l.addWidget(bottom)
    return root


def _team_column(
    team_name: str,
    items: List[dict],
    result: dict,
    accent: str,
    bar_g: str,
    stat: str,
    side: str,
) -> QFrame:
    w = QFrame()
    w.setStyleSheet(
        f"QFrame {{ background: {BG_HUD}; border: none; border-radius: 4px; }}"
    )
    try:
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    except Exception:
        pass
    vl = QVBoxLayout(w)
    vl.setSpacing(6)

    head = QHBoxLayout()
    av = _TeamAvatar(team_name, accent, 56, w)
    tstack = QVBoxLayout()
    nm = QLabel((team_name or "—").upper()[:50])
    nm.setStyleSheet(f"color: {accent}; font-size: 16px; font-weight: 800; letter-spacing:1px;")
    sub = QLabel(f"Estat: {stat}")
    sub.setStyleSheet(f"color: {C_MUTED}; font-size: 10px;")
    tstack.addWidget(nm)
    tstack.addWidget(sub)
    head.addWidget(av)
    head.addLayout(tstack, 1)
    vl.addLayout(head)

    tover = int(result.get("team1_over" if side == "1" else "team2_over", 0) or 0)
    t_n = int(result.get("team1_games" if side == "1" else "team2_games", 0) or 0)

    wins, losses = _wins_loses(items)
    n_wa = len(wins)
    n_la = len(losses)
    c_total = _TopCard("TOTAL", accent, w)
    c_total.set_data(tover, t_n)
    c_vit = _TopCard("VITÓRIAS", accent, w)
    if n_wa == 0:
        c_vit.set_data(0, 0)
        c_vit._sub.setText("Sem vitórias na amostra" if items else "—")
    else:
        own = sum(1 for c in wins if c.get("value") is not None and _is_over(float(c["value"]), result))
        c_vit.set_data(own, n_wa)
    c_der = _TopCard("DERROTAS", accent, w)
    if n_la == 0:
        c_der.set_data(0, 0)
        c_der._sub.setText("Sem derrotas na amostra" if items else "—")
    else:
        oln = sum(
            1
            for c in losses
            if c.get("value") is not None and _is_over(float(c["value"]), result)
        )
        c_der.set_data(oln, n_la)
    g3 = QHBoxLayout()
    g3.addWidget(c_total, 1)
    g3.addWidget(c_vit, 1)
    g3.addWidget(c_der, 1)
    vl.addLayout(g3)

    # Tendência Last 15/10/5
    tlab = QLabel("Tendência (últimos N jogos da amostra, mais recentes primeiro)")
    tlab.setStyleSheet(f"color: {C_MUTED}; font-size: 11px; font-weight: 600;")
    tlab.setWordWrap(True)
    vl.addWidget(tlab)
    for n_label, nmax in (("Last 15", 15), ("Last 10", 10), ("Last 5", 5)):
        n_take = min(nmax, len(items))
        line = _StatLine(n_label, bar_g, w)
        if n_take == 0:
            line.set_values(0, 0, 0, stat)
        else:
            r, n, m = _over_rate_in_slice(items, n_take, result)
            line.set_values(r, n, m, stat)
        vl.addWidget(line)

    cutoffs: List[Tuple[str, int]] = [("Total", 9999), ("Last 15", 15), ("Last 10", 10), ("Last 5", 5)]
    c1, t_v = _build_small_table("Nos jogos vencidos", accent)
    w_v = _rows_split_table(items, result, cutoffs, stat, True)
    _fill_table(t_v, w_v)
    c2, t_d = _build_small_table("Nos jogos perdidos", accent)
    w_d = _rows_split_table(items, result, cutoffs, stat, False)
    _fill_table(t_d, w_d)
    tab_row = QHBoxLayout()
    tab_row.addWidget(c1, 1)
    tab_row.addWidget(c2, 1)
    vl.addLayout(tab_row)
    return w


def _rows_split_table(
    items: List[dict],
    result: dict,
    cutoffs: List[Tuple[str, int]],
    stat: str,
    wins: bool,
) -> List[Tuple[str, int, str, str]]:
    base = [c for c in items if (c.get("won") is True if wins else c.get("won") is False)]
    rows: List[Tuple[str, int, str, str]] = []
    for label, nmax in cutoffs:
        if nmax == 9999:
            r, n, a = _over_rate_in_slice(base, len(base) if base else 0, result)
        else:
            r, n, a = _over_rate_in_slice(base, nmax, result)
        rows.append(
            (label, n, f"{r*100:.1f}%" if n else "—", _format_stat_val(a, stat) if n else "—")
        )
    return rows


def _format_summary_blocks(result: dict, stat: str) -> List[str]:
    is_first = result.get("is_first_stat", False)
    stat_display = (
        str(stat).replace("firstdragon", "first dragon")
        .replace("firsttower", "first tower")
        .replace("firstherald", "first herald")
    )
    out = []
    out.append(
        f"<b style='color:#93c5fd'>{stat_display.upper()}</b> — {result.get('team1', '')} vs {result.get('team2', '')} — "
        f"Linha: <b>{result.get('line', '—')}</b>"
    )

    total_g = result.get("team1_games", 0) + result.get("team2_games", 0)
    if is_first:
        out.append(
            f"<b>Modelo (first):</b> P(time1)={result.get('prob_over', 0)*100:.2f}% — "
            f"P(time2)={result.get('prob_under', 0)*100:.2f}%"
        )
    else:
        if total_g:
            out.append(
                f"<b>Combina os dois times</b> ({total_g} jogos amostrados no core): "
                f"over na linha {result.get('line', '')}: {result.get('over_all', 0)} / "
                f"under: {result.get('under_all', 0)}"
            )

    if result.get("use_h2h"):
        ng = result.get("h2h_games", 0)
        if ng == 0:
            out.append("<b>H2H:</b> nenhum jogo no período")
        elif result.get("h2h_rate") is not None:
            h2h = result.get("h2h_rate", 0) * 100
            out.append(
                f"<b>H2H:</b> {ng} jogos — over ~ {h2h:.1f}% — "
                f"média H2H: {result.get('h2h_mean', 0):.2f} — "
                f"peso H2H: {result.get('w_h2h',0)*100:.0f}% / forma: {result.get('w_form',1)*100:.0f}%"
            )

    out.append(
        f"<b>Prob. final (mercado O/U):</b> Over {result.get('line', '—')}: <b>{result.get('prob_over',0)*100:.2f}%</b> — "
        f"Under: <b>{result.get('prob_under',0)*100:.2f}%</b>"
    )
    o = result.get("line", "")
    if is_first:
        ev_block = (
            f"<b>Fair &amp; EV (Pinnacle):</b><br>"
            f"Time1: fair <b>{result.get('fair_over', 0):.3f}</b> — "
            f"EV = {result.get('ev_over',0):+.2f}u ({result.get('ev_over_pct',0):+.1%})<br>"
            f"Time2: fair <b>{result.get('fair_under', 0):.3f}</b> — "
            f"EV = {result.get('ev_under',0):+.2f}u ({result.get('ev_under_pct',0):+.1%})<br>"
            f"<b>{result.get('recommendation','')}</b>"
        )
    else:
        ev_block = (
            f"<b>Fair &amp; EV (Pinnacle):</b><br>"
            f"Over {o}: fair <b>{result.get('fair_over', 0):.3f}</b> — "
            f"EV = {result.get('ev_over',0):+.2f}u ({result.get('ev_over_pct',0):+.1%})<br>"
            f"Under {o}: fair <b>{result.get('fair_under', 0):.3f}</b> — "
            f"EV = {result.get('ev_under',0):+.2f}u ({result.get('ev_under_pct',0):+.1%})<br>"
            f"<span style='color:#86efac'><b>{result.get('recommendation','')}</b></span>"
        )
    out.append(ev_block)
    return out
