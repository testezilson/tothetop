# -*- coding: utf-8 -*-
"""
Pré-bets de futebol (API-Sports) — alinhado ao output LoL/Dota: Times e Jogadores.
"""
import re
import traceback
from typing import Any, List, Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QGroupBox,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QMessageBox,
    QCheckBox,
    QTabWidget,
    QCompleter,
    QSizePolicy,
)
from PySide6.QtCore import (
    QThread,
    Signal,
    QLocale,
    QTimer,
    QStringListModel,
    QSignalBlocker,
    Qt,
)

from core.football.api_client import FootballAPIClient, FootballAPIError
from core.football import prebets_football as pb

# Sugestões de equipa: tamanho limitado (menos carga no QCompleter) e só sénior / profissional aprox.
_MAX_TEAM_SUGGESTIONS = 25
_COMPLETER_MAX_VISIBLE = 12

# Base, futsal, notas "segunda equipa" em palavra-passe.
_BASE_YOUTH_WORDS = re.compile(
    r"(juvenil|infantil|\bmirim\b|categorias?\s+de\s+base|academy|futsal|"
    r"beach|soccer\s*7|futebol\s*7|escolinha|"
    r"torneio\s+de\s+base|copinha\s*sub|segunda\s+equipa)",
    re.IGNORECASE,
)


def _name_has_youth_age(s: str) -> bool:
    """U-20, U20, Ceara u17, sub-20, sub 17, etc. (7–23)."""
    low = s.lower()
    pats = (
        r"\bu-?(\d{1,2})\b",
        r"[\s/'\-_]u(\d{1,2})\b",  # "Time U20"
        r"^\s*u-?(\d{1,2})\b",  # começa com U20
        r"\bsub[-\s]*(\d{1,2})\b",
    )
    for pat in pats:
        m = re.search(pat, low)
        if not m:
            continue
        try:
            n = int(m.group(1))
        except (ValueError, IndexError):
            continue
        if 7 <= n <= 23:
            return True
    return False


def _is_senior_pro_club_name(name: str) -> bool:
    """
    Heurística: equipas sénior na pesquisa /teams; exclui base, futsal, filial II / B.
    """
    s = re.sub(r"\s+", " ", (name or "").strip())
    if not s:
        return False
    low = s.lower()
    if _BASE_YOUTH_WORDS.search(low):
        return False
    if _name_has_youth_age(s):
        return False
    if re.search(r"\s+ii\s*$", low) or re.search(r"\s+b\s*$", low):
        return False
    return True


def _filter_team_suggestions(teams: list) -> list:
    out = []
    for t in teams or []:
        if not isinstance(t, dict):
            continue
        nm = (t.get("name") or "").strip()
        if not nm or not _is_senior_pro_club_name(nm):
            continue
        out.append(t)
        if len(out) >= _MAX_TEAM_SUGGESTIONS:
            break
    return out


def _abbrev_team(name, max_chars=3):
    if not name or not str(name).strip():
        return "—"
    words = re.sub(r"\s+", " ", str(name).strip()).split()
    if not words:
        return "—"
    return "".join(w[0].upper() for w in words if w)[:max_chars] or "—"


def _opponent_line(name: str, max_len: int = 42) -> str:
    s = (name or "—").strip() or "—"
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _strip_team_id_suffix(name: str) -> str:
    """Remove « Nome (id 123) » do fim, para o relatório não repetir o id."""
    return re.sub(r"\s*\(id\s*\d+\)\s*$", "", (name or "").strip(), flags=re.IGNORECASE)


def _format_val(val):
    if val is None:
        return "—"
    try:
        v = float(val)
        if abs(v - int(v)) < 1e-6:
            return str(int(v))
        return f"{v:.2f}"
    except (TypeError, ValueError):
        return str(val)


class FlexibleDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.lineEdit().textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, text):
        if "," in text:
            normalized = text.replace(",", ".")
            cursor_pos = self.lineEdit().cursorPosition()
            self.lineEdit().blockSignals(True)
            self.lineEdit().setText(normalized)
            self.lineEdit().setCursorPosition(cursor_pos)
            self.lineEdit().blockSignals(False)

    def valueFromText(self, text):
        if isinstance(text, str):
            text = text.replace(",", ".")
        return super().valueFromText(text)

    def validate(self, text, pos):
        if isinstance(text, str):
            text = text.replace(",", ".")
        return super().validate(text, pos)


def _result_to_text(result: dict) -> str:
    if not result or "error" in result:
        return result.get("error", "Sem resultado.") if result else ""
    is_first = result.get("is_first_stat", False)
    stat = result.get("stat", "")
    stat_display = result.get("stat_label", stat)
    mode = result.get("mode", "team")
    t1, t2 = result.get("team1", ""), result.get("team2", "")
    if mode == "team":
        t1, t2 = _strip_team_id_suffix(t1), _strip_team_id_suffix(t2)
    output = []
    output.append("=" * 80)
    if mode == "player":
        output.append(f"JOGADOR — {t1} | mercado: {stat_display}")
    else:
        output.append(f"EQUIPA — {stat_display} — {t1} vs {t2}")
    output.append("=" * 80)
    output.append("")
    if result.get("stat_match_total") and mode == "team":
        st = (result.get("stat") or "").strip()
        if st == "total_cards":
            output.append(
                "NOTA: «Total cartoes» = pontos: 1 amarelo = 1, 1 vermelho = 2, por equipa; "
                "aqui a partida soma as duas equipas. Amarelos/vermelhos a solo = contagem de cartas (1 cada)."
            )
        else:
            output.append(
                "NOTA: mercados de CARTOES = total da partida (soma de ambas as equipas). "
                "Outros mercados = só a equipa indicada."
            )
        output.append("")

    if mode == "team" and not is_first:
        output.append("📉 Estatisticas por time (media por jogo na amostra):")
        output.append("")
        vspl = result.get("venue_split")
        h1, a1 = result.get("team1_split_home"), result.get("team1_split_away")
        h2, a2 = result.get("team2_split_home"), result.get("team2_split_away")
        output.append(f"🔵 {t1}")
        n1, ns1 = result.get("team1_games", 0), result.get("team1_n_with_stat", 0) or 0
        if n1 > 0:
            nm1 = ns1 if ns1 else n1
            output.append(
                f"  • Total (ultimos {result.get('team1_games', 0)} jogos, qualquer local): "
                f"media {result.get('mean_team1', 0):.2f} ({nm1} com stat)"
            )
            output.append(
                f"  • OVER linha {result.get('line', 0)}: {result.get('team1_over', 0)}  |  "
                f"UNDER: {result.get('team1_under', 0)}"
            )
            if vspl and isinstance(h1, dict) and isinstance(a1, dict):
                output.append(
                    f"  • Em casa (ultimos {h1.get('n_games', 0)} em casa): "
                    f"media {h1.get('mean', 0):.2f} ({h1.get('n_with_stat', 0)} com stat)  |  "
                    f"OVER {result.get('line', 0)}: {h1.get('over', 0)}  UNDER: {h1.get('under', 0)}"
                )
                output.append(
                    f"  • Fora (ultimos {a1.get('n_games', 0)} fora): "
                    f"media {a1.get('mean', 0):.2f} ({a1.get('n_with_stat', 0)} com stat)  |  "
                    f"OVER {result.get('line', 0)}: {a1.get('over', 0)}  UNDER: {a1.get('under', 0)}"
                )
        output.append("")
        if t2:
            output.append(f"🔴 {t2}")
            n2, ns2 = result.get("team2_games", 0), result.get("team2_n_with_stat", 0) or 0
            if n2 > 0:
                nm2 = ns2 if ns2 else n2
                output.append(
                    f"  • Total (ultimos {result.get('team2_games', 0)} jogos, qualquer local): "
                    f"media {result.get('mean_team2', 0):.2f} ({nm2} com stat)"
                )
                output.append(
                    f"  • OVER linha {result.get('line', 0)}: {result.get('team2_over', 0)}  |  "
                    f"UNDER: {result.get('team2_under', 0)}"
                )
                if vspl and isinstance(h2, dict) and isinstance(a2, dict):
                    output.append(
                        f"  • Em casa (ultimos {h2.get('n_games', 0)} em casa): "
                        f"media {h2.get('mean', 0):.2f} ({h2.get('n_with_stat', 0)} com stat)  |  "
                        f"OVER {result.get('line', 0)}: {h2.get('over', 0)}  UNDER: {h2.get('under', 0)}"
                    )
                    output.append(
                        f"  • Fora (ultimos {h2.get('n_games', 0)} fora): "
                        f"media {a2.get('mean', 0):.2f} ({a2.get('n_with_stat', 0)} com stat)  |  "
                        f"OVER {result.get('line', 0)}: {a2.get('over', 0)}  UNDER: {a2.get('under', 0)}"
                    )
        output.append("")
    elif mode == "player" and not is_first:
        if result.get("team1_games", 0) > 0:
            output.append("Estatisticas (jogador):")
            output.append(f"  Média: {result.get('mean_team1', 0):.2f} ({result['team1_games']} jogos)")
        output.append("")

    def _emit_pair_table(
        title: str,
        row1: list,
        row2: list,
        *,
        team_mode: bool,
        match_total: bool,
    ) -> None:
        if not row1 and not row2:
            return
        sub = "total da partida neste jogo" if match_total else "estatistica do teu clube"
        output.append(f"{title} (adversario a cores — {sub}):" if mode == "team" else f"{title} (adversario):")
        w = 50
        for i in range(max(len(row1), len(row2))):
            left, right = "", ""
            if i < len(row1):
                it = row1[i]
                on = _opponent_line(it.get("opponent", ""), 38)
                left = f"  {on} — {_format_val(it.get('value', ''))}"
            if i < len(row2) and team_mode:
                it = row2[i]
                on = _opponent_line(it.get("opponent", ""), 38)
                right = f"{on} — {_format_val(it.get('value', ''))}"
            if right:
                output.append(left.ljust(w) + "  " + right)
            else:
                output.append(left)
        output.append("")

    items1 = (result.get("last_values_team1") or [])[:10]
    items2 = (result.get("last_values_team2") or [])[:10]
    vspl = result.get("venue_split")
    mtot = result.get("stat_match_total")
    if mode == "team" and vspl and not is_first:
        h1b = (result.get("team1_split_home") or {}).get("last_values") or []
        a1b = (result.get("team1_split_away") or {}).get("last_values") or []
        h2b = (result.get("team2_split_home") or {}).get("last_values") or []
        a2b = (result.get("team2_split_away") or {}).get("last_values") or []
        lim = int(result.get("team1_games", 10) or 10)
        _emit_pair_table(
            f"Ultimos {lim} em CASA", h1b[:10], h2b[:10], team_mode=True, match_total=bool(mtot)
        )
        _emit_pair_table(
            f"Ultimos {lim} FORA de casa", a1b[:10], a2b[:10], team_mode=True, match_total=bool(mtot)
        )
    if mode == "team" and (items1 or items2):
        lim2 = int(result.get("team1_games", 10) or 10)
        _emit_pair_table(
            f"Ultimos {lim2} TOTAIS (mais recentes, qualquer local)",
            items1,
            items2,
            team_mode=True,
            match_total=bool(mtot),
        )
    elif mode == "player" and (result.get("last_values_team1") or []):
        row1p = (result.get("last_values_team1") or [])[:10]
        _emit_pair_table("Ultimos 10", row1p, [], team_mode=False, match_total=bool(mtot))

    if mode == "player":
        tg = result.get("team1_games", 0)
    else:
        tg = result.get("team1_games", 0) + result.get("team2_games", 0)
    if not is_first and tg > 0 and mode == "team":
        nstat = (result.get("team1_n_with_stat") or 0) + (result.get("team2_n_with_stat") or 0)
        output.append(
            f"Combinado: OVER {result.get('over_all', 0)}  UNDER {result.get('under_all', 0)}"
        )
        output.append(
            f"  Taxa OVER linha: {100.0 * result.get('over_all', 0) / max(nstat, 1):.2f}%"
        )
        output.append("")
    elif not is_first and tg > 0 and mode == "player":
        output.append(
            f"Amostra: OVER {result.get('team1_over', 0)}  UNDER {result.get('team1_under', 0)} "
            f"(taxa OVER: {100.0 * result.get('team1_over', 0) / max(tg, 1):.2f}%)"
        )
        output.append("")

    ref = (result.get("referee_name") or "").strip()
    rs = result.get("referee_stats")
    if ref or (isinstance(rs, dict) and rs.get("computed")):
        output.append("Juiz (medias na API, totais **da partida** por jogo na amostra)")
        if ref:
            output.append(f"  Nome: {ref}")
        if isinstance(rs, dict) and rs.get("computed"):
            if not rs.get("ok"):
                output.append(f"  {rs.get('message', 'Sem dados.')}")
            else:
                output.append(f"  Jogos na amostra: {rs.get('n', 0)}")
                if rs.get("avg_yellow") is not None:
                    output.append(f"  Media de cartoes amarelos: {rs['avg_yellow']:.2f}")
                if rs.get("avg_red") is not None:
                    output.append(f"  Media de cartoes vermelhos: {rs['avg_red']:.2f}")
                if rs.get("avg_total_cards") is not None:
                    output.append(f"  Media total de cartoes: {rs['avg_total_cards']:.2f}")
                if rs.get("avg_fouls") is not None:
                    output.append(f"  Media de faltas: {rs['avg_fouls']:.2f}")
                matches = rs.get("matches") or []
                if matches:
                    output.append("  Jogos apitados (mais recentes):")
                    for it in matches:
                        yc = it.get("yellow")
                        rc = it.get("red")
                        tc = it.get("total_cards")
                        ytxt = f"{float(yc):.0f}" if yc is not None else "—"
                        rtxt = f"{float(rc):.0f}" if rc is not None else "—"
                        ttxt = f"{float(tc):.0f}" if tc is not None else "—"
                        output.append(
                            f"    {it.get('date', '?')} - {it.get('home', '?')} vs {it.get('away', '?')} | "
                            f"Amarelos: {ytxt} | Vermelhos: {rtxt} | Total: {ttxt}"
                        )
        output.append("")

    if result.get("use_h2h") and mode == "team":
        output.append("=" * 80)
        h2h_title = "H2H (valor do Time 1 nos confrontos A vs B)"
        if result.get("stat_match_total"):
            h2h_title = "H2H (total da partida em cartoes — confrontos A vs B)"
        output.append(h2h_title)
        output.append("=" * 80)
        if result.get("h2h_games", 0) == 0 or result.get("h2h_rate") is None:
            output.append("Nenhum jogo H2H com estatistica no periodo.")
        else:
            output.append(f"Jogos H2H: {result.get('h2h_games', 0)}")
            output.append(f"Media H2H: {result.get('h2h_mean',0):.2f}")
            output.append(
                f"OVER {result.get('line')}: {result.get('h2h_over',0)} ({100*result.get('h2h_rate',0):.2f}%)"
            )
            output.append(
                f"Peso H2H: {100*result.get('w_h2h',0):.1f}%  |  Forma: {100*result.get('w_form',1):.1f}%"
            )
        output.append("")

    line = result.get("line", 0)

    def _fmt_fair(x: Any) -> str:
        try:
            xf = float(x)
            if xf != xf:  # nan
                return "—"
            if abs(xf) == float("inf"):
                return "inf"
        except (TypeError, ValueError):
            return "—"
        return f"{xf:.3f}"

    output.append("=" * 80)
    output.append("📈 PROBABILIDADES")
    output.append("=" * 80)
    if mode == "team":
        if result.get("use_h2h") and result.get("h2h_rate") is not None:
            output.append(f"Prob. empirica (forma, amostra combinada): {100*result.get('prob_form',0):.2f}%")
            output.append(f"Taxa H2H OVER: {100*result.get('h2h_rate',0):.2f}%")
        p1, p2 = result.get("p_team1", 0), result.get("p_team2", 0)
        output.append(f"Taxa OVER {line} (só jogos do Time 1): {100*p1:.2f}%")
        output.append(f"Taxa OVER {line} (só jogos do Time 2): {100*p2:.2f}%")
        output.append(f"Prob. Over {line} (modelo / combinada):  {100*result.get('prob_over',0):.2f}%")
        output.append(f"Prob. Under {line} (modelo / combinada): {100*result.get('prob_under',0):.2f}%")
    else:
        output.append(f"Prob. Over {line}:  {100*result.get('prob_over',0):.2f}%")
        output.append(f"Prob. Under {line}: {100*result.get('prob_under',0):.2f}%")
    output.append("")

    if mode == "team" and result.get("venue_split"):
        t1n = _strip_team_id_suffix(result.get("team1", ""))
        t2n = _strip_team_id_suffix(result.get("team2", ""))
        h1, a1b = result.get("team1_split_home"), result.get("team1_split_away")
        t1tot = result.get("team1_split_total_emp")
        h2, a2b = result.get("team2_split_home"), result.get("team2_split_away")
        t2tot = result.get("team2_split_total_emp")
        output.append("=" * 80)
        output.append("FAIR ODDS POR CENARIO (empirico: 1 / taxa na amostra com stat)")
        output.append("=" * 80)

        def _emp_lines(label: str, hblk: Any, ablk: Any, tbl: Any) -> None:
            if not isinstance(hblk, dict) or not isinstance(ablk, dict) or not isinstance(tbl, dict):
                return

            def _lines_block(prefix: str, blk: dict) -> None:
                po = blk.get("p_over_emp")
                pu = blk.get("p_under_emp")
                if po is not None:
                    output.append(
                        f"{label} {prefix} | Over {line}: taxa {100.0 * float(po):.1f}%  |  fair {_fmt_fair(blk.get('fair_over_emp'))}"
                    )
                if pu is not None:
                    output.append(
                        f"{label} {prefix} | Under {line}: taxa {100.0 * float(pu):.1f}%  |  fair {_fmt_fair(blk.get('fair_under_emp'))}"
                    )

            _lines_block("— mandante", hblk)
            _lines_block("— visitante", ablk)
            ntot = int(tbl.get("n_games", 0) or 0)
            po = tbl.get("p_over_emp")
            pu = tbl.get("p_under_emp")
            if po is not None:
                output.append(
                    f"{label} — total (ultimos {ntot} jogos) | Over {line}: taxa {100.0 * float(po):.1f}%  |  fair {_fmt_fair(tbl.get('fair_over_emp'))}"
                )
            if pu is not None:
                output.append(
                    f"{label} — total (ultimos {ntot} jogos) | Under {line}: taxa {100.0 * float(pu):.1f}%  |  fair {_fmt_fair(tbl.get('fair_under_emp'))}"
                )
            output.append("")

        if t1n and h1 and a1b and t1tot:
            _emp_lines(t1n, h1, a1b, t1tot)
        if t2n and h2 and a2b and t2tot:
            _emp_lines(t2n, h2, a2b, t2tot)
        output.append("")

    output.append("=" * 80)
    output.append("💰 EV E FAIR ODDS (Formato Pinnacle)")
    output.append("=" * 80)
    if mode == "team":
        t1, t2 = result.get("team1", "Time 1"), result.get("team2", "Time 2")
        output.append(f"{t1} — Over {line}: EV = {result.get('t1_ev_over',0):+.2f}u ({result.get('t1_ev_over_pct',0):+.2%}) | Fair = {_fmt_fair(result.get('t1_fair_over'))}")
        output.append(
            f"{t1} — Under {line}: EV = {result.get('t1_ev_under',0):+.2f}u ({result.get('t1_ev_under_pct',0):+.2%}) | Fair = {_fmt_fair(result.get('t1_fair_under'))}"
        )
        output.append(f"{t2} — Over {line}: EV = {result.get('t2_ev_over',0):+.2f}u ({result.get('t2_ev_over_pct',0):+.2%}) | Fair = {_fmt_fair(result.get('t2_fair_over'))}")
        output.append(
            f"{t2} — Under {line}: EV = {result.get('t2_ev_under',0):+.2f}u ({result.get('t2_ev_under_pct',0):+.2%}) | Fair = {_fmt_fair(result.get('t2_fair_under'))}"
        )
        output.append("---  Mercado O/U (prob. combinada dos dois times)  ---")
    output.append(
        f"Over  {line}: EV = {result.get('ev_over',0):+.2f}u ({result.get('ev_over_pct',0):+.2%}) | Fair = {_fmt_fair(result.get('fair_over'))}"
    )
    output.append(
        f"Under {line}: EV = {result.get('ev_under',0):+.2f}u ({result.get('ev_under_pct',0):+.2%}) | Fair = {_fmt_fair(result.get('fair_under'))}"
    )
    output.append("")
    rec = result.get("recommendation", "")
    if rec:
        if "Nenhuma" in rec or "positivo" in rec:
            output.append(f"{rec}")
        else:
            output.append(f"Recomendacao: {rec}")
    return "\n".join(output)


class FootballTeamThread(QThread):
    """
    Não emitir o dict de resultado no Signal (pode crashear o Qt entre threads).
    Sinal vazio: o análise fica em self._payload, lida no slot no thread de UI.
    """
    analysis_done = Signal()
    error = Signal(str)

    def __init__(self, analyzer, kwargs: dict):
        super().__init__()
        self.analyzer = analyzer
        self.kwargs = kwargs
        self._payload: Optional[dict] = None

    def run(self):
        self._payload = None
        try:
            self._payload = self.analyzer.analyze_team_bet(**self.kwargs)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")
            return
        self.analysis_done.emit()


class FootballPlayerThread(QThread):
    analysis_done = Signal()
    error = Signal(str)

    def __init__(self, analyzer, kwargs: dict):
        super().__init__()
        self.analyzer = analyzer
        self.kwargs = kwargs
        self._payload: Optional[dict] = None

    def run(self):
        self._payload = None
        try:
            self._payload = self.analyzer.analyze_player_bet(**self.kwargs)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")
            return
        self.analysis_done.emit()


class RefereeLookupThread(QThread):
    """Busca árbitro do próximo jogo entre duas equipas (API)."""
    done = Signal(int, object)  # seq, str | None

    def __init__(self, client: FootballAPIClient, seq: int, t1: int, t2: int):
        super().__init__()
        self._client = client
        self._seq = seq
        self._t1 = t1
        self._t2 = t2

    def run(self) -> None:
        try:
            r = self._client.find_referee_next_match_between(
                self._t1, self._t2, pb.default_api_season_year()
            )
            self.done.emit(self._seq, r)
        except Exception:
            self.done.emit(self._seq, None)


class TeamSearchThread(QThread):
    """
    /teams?search= na background — evita bloquear a UI e reduz crash do Qt ao
    actualizar o QCompleter/QStringListModel com pedidos HTTP na thread de UI.
    """
    done = Signal(int, int, object)  # seq, which (1|2|3), list[dict] | None

    def __init__(
        self, client: FootballAPIClient, seq: int, which: int, query: str, parent=None
    ):
        super().__init__(parent)
        self._client = client
        self._seq = seq
        self._which = int(which)
        self._q = (query or "").strip()

    def run(self) -> None:
        if len(self._q) < 2:
            self.done.emit(self._seq, self._which, None)
            return
        out: Optional[List[Any]] = None
        try:
            raw = self._client.search_teams(self._q)
        except Exception:
            self.done.emit(self._seq, self._which, None)
            return
        if not isinstance(raw, list):
            self.done.emit(self._seq, self._which, None)
            return
        try:
            out = _filter_team_suggestions(raw)
        except Exception:
            out = None
        self.done.emit(self._seq, self._which, out)


class FootballPrebetsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.api = FootballAPIClient()
        self.analyzer = pb.FootballPrebetsAnalyzer(self.api)
        self._team_threads: list = []
        # id por texto exibido na sugestão (igual "Nome (id 123)")
        self._map_t1: dict = {}
        self._map_t2: dict = {}
        self._map_pt: dict = {}
        self._map_player: dict = {}
        self._deb_t1 = QTimer(self)
        self._deb_t1.setSingleShot(True)
        self._deb_t1.setInterval(450)
        self._deb_t1.timeout.connect(lambda: self._fetch_team_suggestions(1))
        self._deb_t2 = QTimer(self)
        self._deb_t2.setSingleShot(True)
        self._deb_t2.setInterval(450)
        self._deb_t2.timeout.connect(lambda: self._fetch_team_suggestions(2))
        self._deb_pt = QTimer(self)
        self._deb_pt.setSingleShot(True)
        self._deb_pt.setInterval(450)
        self._deb_pt.timeout.connect(self._fetch_team_suggestions_for_player)
        self._deb_pl = QTimer(self)
        self._deb_pl.setSingleShot(True)
        self._deb_pl.setInterval(450)
        self._deb_pl.timeout.connect(self._fetch_player_suggestions)
        self._ref_seq = 0
        # Seq. monotónica por campo (Time1, Time2, equipa na aba Jogadores) para ignorar respostas antigas
        self._team_search_seq = [0, 0, 0]
        self._deb_ref = QTimer(self)
        self._deb_ref.setSingleShot(True)
        self._deb_ref.setInterval(700)
        self._deb_ref.timeout.connect(self._do_fetch_referee)
        self._ref_thread: Optional[RefereeLookupThread] = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Chave API (sobrescreve env / data/football_api_key.txt):"))
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Opcional — deixe vazio para usar ficheiro ou variavel de ambiente")
        key_row.addWidget(self.key_edit, 1)
        root.addLayout(key_row)

        self.tabs_inner = QTabWidget()
        self._w_teams = self._build_teams_tab()
        self._w_players = self._build_players_tab()
        self.tabs_inner.addTab(self._w_teams, "Equipas")
        self.tabs_inner.addTab(self._w_players, "Jogadores")
        root.addWidget(self.tabs_inner, 1)
        self._out_text = QTextEdit()
        self._out_text.setReadOnly(True)
        self._out_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self._out_text, 1)

    def _apply_api_key(self):
        k = self.key_edit.text().strip()
        if k:
            self.api.set_key(k)

    def _build_teams_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        top = QHBoxLayout()

        g1 = QGroupBox("Time 1")
        f1 = QFormLayout()
        self.t1_q = QLineEdit()
        self.t1_q.setPlaceholderText("Escreve o nome — as sugestões aparecem ao carregar (min. 2 letras)")
        self.t1_q.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._m1 = QStringListModel()
        self._comp1 = QCompleter()
        self._comp1.setModel(self._m1)
        self._comp1.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        if hasattr(self._comp1, "setFilterMode"):
            try:
                self._comp1.setFilterMode(Qt.MatchFlag.MatchContains)
            except (AttributeError, TypeError):
                pass
        self.t1_q.setCompleter(self._comp1)
        self._comp1.setMaxVisibleItems(_COMPLETER_MAX_VISIBLE)
        self.t1_q.textChanged.connect(self._on_t1_text)
        self.t1_q.editingFinished.connect(self._schedule_ref_lookup)
        try:
            self._comp1.activated[str].connect(self._schedule_ref_lookup)
        except (TypeError, AttributeError):
            self._comp1.activated.connect(self._schedule_ref_lookup)
        f1.addRow("Equipa:", self.t1_q)
        g1.setLayout(f1)
        top.addWidget(g1)

        g2 = QGroupBox("Time 2")
        f2 = QFormLayout()
        self.t2_q = QLineEdit()
        self.t2_q.setPlaceholderText("Escreve o nome — as sugestões aparecem ao carregar (min. 2 letras)")
        self.t2_q.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._m2 = QStringListModel()
        self._comp2 = QCompleter()
        self._comp2.setModel(self._m2)
        self._comp2.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        if hasattr(self._comp2, "setFilterMode"):
            try:
                self._comp2.setFilterMode(Qt.MatchFlag.MatchContains)
            except (AttributeError, TypeError):
                pass
        self.t2_q.setCompleter(self._comp2)
        self._comp2.setMaxVisibleItems(_COMPLETER_MAX_VISIBLE)
        self.t2_q.textChanged.connect(self._on_t2_text)
        self.t2_q.editingFinished.connect(self._schedule_ref_lookup)
        try:
            self._comp2.activated[str].connect(self._schedule_ref_lookup)
        except (TypeError, AttributeError):
            self._comp2.activated.connect(self._schedule_ref_lookup)
        f2.addRow("Equipa:", self.t2_q)
        g2.setLayout(f2)
        top.addWidget(g2)

        g3 = QGroupBox("Mercado")
        f3 = QFormLayout()
        self.st_team = QComboBox()
        for k, label in pb.TEAM_STATS.items():
            self.st_team.addItem(label, k)
        f3.addRow("Estatistica:", self.st_team)
        g3.setLayout(f3)
        top.addWidget(g3)

        layout.addLayout(top)

        mid = QHBoxLayout()
        bg = QGroupBox("Dados da aposta")
        bf = QFormLayout()
        self.line_t = FlexibleDoubleSpinBox()
        self.line_t.setRange(0, 5000)
        self.line_t.setDecimals(1)
        self.line_t.setValue(9.5)
        bf.addRow("Linha:", self.line_t)
        self.oo_t = QDoubleSpinBox()
        self.oo_t.setRange(1.01, 100.0)
        self.oo_t.setDecimals(2)
        self.oo_t.setValue(1.90)
        self.ou_t = QDoubleSpinBox()
        self.ou_t.setRange(1.01, 100.0)
        self.ou_t.setDecimals(2)
        self.ou_t.setValue(1.90)
        bf.addRow("Odd Over:", self.oo_t)
        bf.addRow("Odd Under:", self.ou_t)
        self.lim_t = QSpinBox()
        self.lim_t.setRange(1, 100)
        self.lim_t.setValue(10)
        self.lim_t.setToolTip(
            "Quantos jogos concluídos (FT) usar por clube, dos mais recentes, "
            "juntando épocas/torneios se a API não tiver todos na mesma lista."
        )
        bf.addRow("Jogos recentes a analisar (por clube):", self.lim_t)
        bg.setLayout(bf)
        mid.addWidget(bg)

        hg = QGroupBox("H2H")
        hf = QFormLayout()
        self.h2h_m = QSpinBox()
        self.h2h_m.setRange(1, 36)
        self.h2h_m.setValue(6)
        hf.addRow("Meses H2H:", self.h2h_m)
        self.h2h_chk = QCheckBox()
        self.h2h_chk.setToolTip("Mistura taxa H2H (Time 1 nos A vs B) com forma geral")
        hf.addRow("Incluir peso H2H:", self.h2h_chk)
        hg.setLayout(hf)
        mid.addWidget(hg)

        jg = QGroupBox("Juiz")
        jf = QFormLayout()
        self._ref_hint = QLabel(
            "O nome do próximo A vs B preenche sozinho quando a API já o tiver. No relatório, "
            "as médias (amarelos, vermelhos, cartões totais e faltas) são **calculadas na API** "
            "sobre a amostra de jogos abaixo — todos como total da partida (duas equipas)."
        )
        self._ref_hint.setWordWrap(True)
        jf.addRow(self._ref_hint)
        self.ref_name = QLineEdit()
        self.ref_name.setPlaceholderText("Automático (API) ou escreve o nome como na API")
        jf.addRow("Nome:", self.ref_name)
        self.ref_ng = QSpinBox()
        self.ref_ng.setRange(5, 50)
        self.ref_ng.setValue(20)
        self.ref_ng.setToolTip("Quantos jogos FT procurar para o perfil de arbitragem (ligas top na API).")
        jf.addRow("Jogos do juiz a usar:", self.ref_ng)
        jg.setLayout(jf)
        mid.addWidget(jg)

        layout.addLayout(mid)

        self.run_t = QPushButton("Calcular (equipas)")
        self.run_t.clicked.connect(self._run_teams)
        layout.addWidget(self.run_t)
        return w

    def _build_players_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        top = QHBoxLayout()
        gt = QGroupBox("Equipa do jogador")
        ft = QFormLayout()
        self.pt_q = QLineEdit()
        self.pt_q.setPlaceholderText("Escreve a equipa (sugestões com min. 2 letras)")
        self._mpt = QStringListModel()
        self._compt = QCompleter()
        self._compt.setModel(self._mpt)
        self._compt.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        if hasattr(self._compt, "setFilterMode"):
            try:
                self._compt.setFilterMode(Qt.MatchFlag.MatchContains)
            except (AttributeError, TypeError):
                pass
        self.pt_q.setCompleter(self._compt)
        self._compt.setMaxVisibleItems(_COMPLETER_MAX_VISIBLE)
        self.pt_q.textChanged.connect(self._on_pt_text)
        ft.addRow("Equipa:", self.pt_q)
        gt.setLayout(ft)
        top.addWidget(gt)

        gp = QGroupBox("Jogador")
        fp = QFormLayout()
        self.pname_q = QLineEdit()
        self.pname_q.setPlaceholderText("Nome do jogador (depois de escolher a equipa)")
        self._mpl = QStringListModel()
        self._compl = QCompleter()
        self._compl.setModel(self._mpl)
        self._compl.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        if hasattr(self._compl, "setFilterMode"):
            try:
                self._compl.setFilterMode(Qt.MatchFlag.MatchContains)
            except (AttributeError, TypeError):
                pass
        self.pname_q.setCompleter(self._compl)
        self._compl.setMaxVisibleItems(_COMPLETER_MAX_VISIBLE)
        self.pname_q.textChanged.connect(self._on_pname_text)
        fp.addRow("Nome:", self.pname_q)
        self.st_pl = QComboBox()
        for k, label in pb.PLAYER_STATS.items():
            self.st_pl.addItem(label, k)
        fp.addRow("Estatistica:", self.st_pl)
        gp.setLayout(fp)
        top.addWidget(gp)

        bg = QGroupBox("Aposta")
        bf = QFormLayout()
        self.line_p = FlexibleDoubleSpinBox()
        self.line_p.setRange(0, 5000)
        self.line_p.setDecimals(2)
        self.line_p.setValue(1.5)
        bf.addRow("Linha:", self.line_p)
        self.oo_p = QDoubleSpinBox()
        self.oo_p.setRange(1.01, 100.0)
        self.oo_p.setDecimals(2)
        self.oo_p.setValue(1.90)
        self.ou_p = QDoubleSpinBox()
        self.ou_p.setRange(1.01, 100.0)
        self.ou_p.setValue(1.90)
        bf.addRow("Odd Over:", self.oo_p)
        bf.addRow("Odd Under:", self.ou_p)
        self.lim_p = QSpinBox()
        self.lim_p.setRange(1, 100)
        self.lim_p.setValue(10)
        self.lim_p.setToolTip(
            "Jogos FT consecutivos a usar na forma do jogador; pode cruzar épocas."
        )
        bf.addRow("Jogos recentes a analisar:", self.lim_p)
        bg.setLayout(bf)
        top.addWidget(bg)

        layout.addLayout(top)
        self.run_p = QPushButton("Calcular (jogador)")
        self.run_p.clicked.connect(self._run_player)
        layout.addWidget(self.run_p)
        return w

    def _ref_kwargs(self) -> dict:
        return {
            "referee_name": self.ref_name.text().strip(),
            "referee_sample_games": int(self.ref_ng.value()),
        }

    @staticmethod
    def _id_from_end(text: str):
        m = re.search(r"\(id\s*(\d+)\)\s*$", (text or "").strip(), re.IGNORECASE)
        return int(m.group(1)) if m else None

    @staticmethod
    def _display_team(nm: str, tid: int) -> str:
        return f"{nm}  (id {tid})"

    def _resolve_from_map(self, text: str, id_map: dict) -> int | None:
        s = (text or "").strip()
        if not s:
            return None
        if s in id_map:
            return id_map[s]
        return self._id_from_end(s)

    @staticmethod
    def _norm_player_query(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").lower().strip())

    def _resolve_player_by_api(self, team_id: int, query: str) -> int | None:
        """
        Com equipa resolvida (id), procura o jogador na API por nome quando
        não veio da lista (min. 2 letras).
        """
        end_id = self._id_from_end(query)
        if end_id is not None:
            return int(end_id)
        q = (query or "").strip()
        if len(q) < 2:
            return None
        season = int(pb.default_api_season_year())
        trials = [q]
        if " " in q:
            w0 = q.split()[0]
            if len(w0) >= 2:
                trials.append(w0)
        found: list = []
        seen: set = set()
        for part in trials:
            try:
                chunk = self.api.search_players(int(team_id), part, season, page=1)
            except (FootballAPIError, OSError):
                continue
            for pl in chunk or []:
                pid = pl.get("id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                found.append(pl)
            if found:
                break
        nq = self._norm_player_query(q)
        tokens = nq.split()
        for pl in found:
            nm = self._norm_player_query(str(pl.get("name") or ""))
            if nm == nq:
                return int(pl["id"])
        for pl in found:
            nm = self._norm_player_query(str(pl.get("name") or ""))
            if nq in nm or (tokens and all(t in nm for t in tokens)):
                return int(pl["id"])
        if len(found) == 1:
            return int(found[0]["id"])
        return None

    def _schedule_ref_lookup(self, *_args) -> None:
        # QCompleter.activated e activated[str] passam o texto/índice; editingFinished() não.
        # Sem *args, escolher da lista dava TypeError e podia derrubar o processo Qt.
        self._deb_ref.start()

    def _do_fetch_referee(self) -> None:
        try:
            self._apply_api_key()
            if not self.api.has_key():
                return
            n1, n2 = self.t1_q.text().strip(), self.t2_q.text().strip()
            t1 = self._resolve_from_map(n1, self._map_t1)
            t2 = self._resolve_from_map(n2, self._map_t2)
            if t1 is None and n1:
                t1 = self._id_from_end(n1)
            if t2 is None and n2:
                t2 = self._id_from_end(n2)
            if t1 is None or t2 is None or t1 == t2:
                self.ref_name.setText("")
                return
            self._ref_seq += 1
            seq = self._ref_seq
            th = RefereeLookupThread(self.api, seq, int(t1), int(t2))
            self._ref_thread = th
            th.done.connect(self._on_ref_lookup_done, Qt.ConnectionType.QueuedConnection)
            th.finished.connect(th.deleteLater)
            th.start()
        except Exception:
            if hasattr(self, "ref_name") and self.ref_name is not None:
                self.ref_name.setText("")

    def _on_ref_lookup_done(self, seq: int, name: object) -> None:
        if seq != self._ref_seq:
            return
        if isinstance(name, str) and name.strip():
            self.ref_name.setText(name.strip())
        else:
            self.ref_name.setText("")

    def _on_t1_text(self, _s: str) -> None:
        # Não disparar procura de árbitro a cada tecla (sobrepor-se à pesquisa = mesmo Session HTTP
        # em duas threads + risco de crash). Árbitro: ao sair do campo, escolher da lista ou completer.
        q = self.t1_q.text().strip()
        if len(q) < 2:
            try:
                p1 = self._comp1.popup()
                if p1 is not None and p1.isVisible():
                    p1.hide()
            except (RuntimeError, AttributeError, TypeError):
                pass
            with QSignalBlocker(self.t1_q):
                self._m1.setStringList([])
            self._map_t1.clear()
        else:
            self._deb_t1.start()

    def _on_t2_text(self, _s: str) -> None:
        q = self.t2_q.text().strip()
        if len(q) < 2:
            try:
                p2 = self._comp2.popup()
                if p2 is not None and p2.isVisible():
                    p2.hide()
            except (RuntimeError, AttributeError, TypeError):
                pass
            with QSignalBlocker(self.t2_q):
                self._m2.setStringList([])
            self._map_t2.clear()
        else:
            self._deb_t2.start()

    def _on_pt_text(self, _s: str) -> None:
        self.pname_q.setText("")
        self._mpl.setStringList([])
        self._map_player.clear()
        q = self.pt_q.text().strip()
        if len(q) < 2:
            try:
                p3 = self._compt.popup()
                if p3 is not None and p3.isVisible():
                    p3.hide()
            except (RuntimeError, AttributeError, TypeError):
                pass
            with QSignalBlocker(self.pt_q):
                self._mpt.setStringList([])
            self._map_pt.clear()
            return
        self._deb_pt.start()

    def _on_pname_text(self, _s: str) -> None:
        if self._resolve_from_map(self.pt_q.text(), self._map_pt) is None:
            self._mpl.setStringList([])
            self._map_player.clear()
            return
        if len(self.pname_q.text().strip()) < 2:
            self._mpl.setStringList([])
            self._map_player.clear()
            return
        self._deb_pl.start()

    def _on_team_search_result(self, seq: int, which: int, teams_obj: object) -> None:
        # 1) Evita actualizar o QStringListModel enquanto o QCompleter está a desenhar o popup
        #    (crash conhecido no Windows/Qt). 2) Adia 1 tick para sair de pilha de eventos reentrante.
        QTimer.singleShot(
            0,
            lambda s=seq, w=which, t=teams_obj: self._apply_team_search_result(s, w, t),
        )

    def _apply_team_search_result(self, seq: int, which: int, teams_obj: object) -> None:
        try:
            ix = int(which) - 1
            if ix < 0 or ix > 2:
                return
            if seq != self._team_search_seq[ix]:
                return
            if which in (1, 2):
                w = self.t1_q if which == 1 else self.t2_q
                model = self._m1 if which == 1 else self._m2
                mref = self._map_t1 if which == 1 else self._map_t2
                comp = self._comp1 if which == 1 else self._comp2
            else:
                w = self.pt_q
                model = self._mpt
                mref = self._map_pt
                comp = self._compt
            try:
                pop = comp.popup()
                if pop is not None and pop.isVisible():
                    pop.hide()
            except (RuntimeError, AttributeError, TypeError):
                pass
            if w.text().strip() == "" or len(w.text().strip()) < 2:
                mref.clear()
                with QSignalBlocker(w):
                    model.setStringList([])
                return
            if teams_obj is None:
                mref.clear()
                with QSignalBlocker(w):
                    model.setStringList([])
                return
            teams = teams_obj
            if not isinstance(teams, list):
                mref.clear()
                with QSignalBlocker(w):
                    model.setStringList([])
                return
            mref.clear()
            sl: list = []
            for t in teams:
                if not isinstance(t, dict):
                    continue
                tid, nm = t.get("id"), t.get("name") or "?"
                if not tid:
                    continue
                try:
                    disp = self._display_team(str(nm), int(tid))
                    mref[disp] = int(tid)
                    sl.append(disp)
                except (TypeError, ValueError):
                    continue
            with QSignalBlocker(w):
                model.setStringList(sl)
        except Exception:
            try:
                if which in (1, 2):
                    m = self._map_t1 if which == 1 else self._map_t2
                    mod = self._m1 if which == 1 else self._m2
                    ww = self.t1_q if which == 1 else self.t2_q
                else:
                    m, mod = self._map_pt, self._mpt
                    ww = self.pt_q
                m.clear()
                with QSignalBlocker(ww):
                    mod.setStringList([])
            except Exception:
                pass

    def _fetch_team_suggestions(self, which: int) -> None:
        self._apply_api_key()
        if not self.api.has_key():
            return
        w = self.t1_q if which == 1 else self.t2_q
        q = w.text().strip()
        if len(q) < 2:
            return
        ix = int(which) - 1
        self._team_search_seq[ix] += 1
        seq = self._team_search_seq[ix]
        th = TeamSearchThread(self.api, seq, which, q, self)
        th.done.connect(
            self._on_team_search_result, Qt.ConnectionType.QueuedConnection
        )
        th.finished.connect(th.deleteLater)
        th.start()

    def _fetch_team_suggestions_for_player(self) -> None:
        self._apply_api_key()
        if not self.api.has_key():
            return
        q = self.pt_q.text().strip()
        if len(q) < 2:
            return
        self._team_search_seq[2] += 1
        seq = self._team_search_seq[2]
        th = TeamSearchThread(self.api, seq, 3, q, self)
        th.done.connect(
            self._on_team_search_result, Qt.ConnectionType.QueuedConnection
        )
        th.finished.connect(th.deleteLater)
        th.start()

    def _fetch_player_suggestions(self) -> None:
        self._apply_api_key()
        if not self.api.has_key():
            return
        tid = self._resolve_from_map(self.pt_q.text(), self._map_pt)
        if tid is None:
            self._map_player.clear()
            self._mpl.setStringList([])
            return
        nq = self.pname_q.text().strip()
        if len(nq) < 2:
            return
        try:
            plist = self.api.search_players(
                int(tid), nq, int(pb.default_api_season_year()), page=1
            )
        except Exception:
            self._map_player.clear()
            self._mpl.setStringList([])
            return
        self._map_player.clear()
        sl = []
        for p in plist[:50]:
            pid, nm = p.get("id"), p.get("name") or "?"
            if not pid:
                continue
            try:
                disp = self._display_team(str(nm), int(pid))
                self._map_player[disp] = int(pid)
                sl.append(disp)
            except (TypeError, ValueError):
                continue
        try:
            self._mpl.setStringList(sl)
        except Exception:
            self._map_player.clear()
            self._mpl.setStringList([])

    def _run_teams(self):
        self._apply_api_key()
        if not self.api.has_key():
            QMessageBox.warning(self, "Chave", "Defina a chave API (ou data/football_api_key.txt)")
            return
        n1, n2 = self.t1_q.text().strip(), self.t2_q.text().strip()
        t1 = self._resolve_from_map(n1, self._map_t1)
        t2 = self._resolve_from_map(n2, self._map_t2)
        if t1 is None and n1:
            t1 = self._id_from_end(n1)
        if t2 is None and n2:
            t2 = self._id_from_end(n2)
        if t1 is None or t2 is None:
            QMessageBox.warning(
                self,
                "Times",
                "Escolhe um clube da lista (ou uma linha completa com «(id …)» no fim).",
            )
            return
        stat = self.st_team.currentData()
        rkw = self._ref_kwargs()
        kw = dict(
            team1_id=int(t1),
            team1_name=n1,
            team2_id=int(t2),
            team2_name=n2,
            stat=stat,
            line=float(self.line_t.value()),
            odd_over=float(self.oo_t.value()),
            odd_under=float(self.ou_t.value()),
            limit_games=int(self.lim_t.value()),
            h2h_months=int(self.h2h_m.value()),
            use_h2h=self.h2h_chk.isChecked(),
            **rkw,
        )
        self.run_t.setEnabled(False)
        self.run_t.setText("A calcular...")

        th = FootballTeamThread(self.analyzer, kw)

        def on_analysis_done() -> None:
            self.run_t.setEnabled(True)
            self.run_t.setText("Calcular (equipas)")
            d = getattr(th, "_payload", None)
            try:
                if d is None:
                    self._out_text.setPlainText("Erro interno: resultado vazio.")
                elif d.get("error"):
                    err = str(d.get("error") or "")
                    dia = d.get("diagnostics")
                    if isinstance(dia, str) and dia.strip():
                        err = f"{err}\n\n{dia.strip()}"
                    self._out_text.setPlainText(err)
                else:
                    self._out_text.setPlainText(_result_to_text(d))
            except Exception:
                self._out_text.setPlainText(
                    "Erro ao formatar o resultado:\n" + traceback.format_exc()
                )
            self._out_text.verticalScrollBar().setValue(0)
            th.deleteLater()

        th.analysis_done.connect(on_analysis_done, Qt.ConnectionType.QueuedConnection)
        th.error.connect(
            lambda m, t=th: self._on_football_team_err(m, t),
            Qt.ConnectionType.QueuedConnection,
        )
        th.start()

    def _on_football_team_err(self, msg: str, thread: "FootballTeamThread") -> None:
        self.run_t.setEnabled(True)
        self.run_t.setText("Calcular (equipas)")
        if len(msg) < 800:
            QMessageBox.critical(self, "Erro na análise", msg)
        else:
            self._out_text.setPlainText(msg)
        self._out_text.verticalScrollBar().setValue(0)
        thread.deleteLater()

    def _run_player(self):
        self._apply_api_key()
        if not self.api.has_key():
            QMessageBox.warning(self, "Chave", "Defina a chave API")
            return
        et, jt = self.pt_q.text().strip(), self.pname_q.text().strip()
        tid = self._resolve_from_map(et, self._map_pt)
        pid = self._resolve_from_map(jt, self._map_player)
        if tid is None and et:
            tid = self._id_from_end(et)
        if pid is None and jt:
            pid = self._id_from_end(jt)
        if tid is not None and pid is None and len((jt or "").strip()) >= 2:
            self._apply_api_key()
            if self.api.has_key():
                try:
                    pid = self._resolve_player_by_api(int(tid), jt)
                except (FootballAPIError, OSError, TypeError, ValueError):
                    pid = None
        if tid is None or pid is None:
            QMessageBox.warning(
                self,
                "Jogador",
                "Escolhe a equipa (lista ou «(id …)» no fim) e o jogador na lista, "
                "ou escreve o nome completo (min. 2 letras) com a equipa já resolvida, "
                "ou «Nome (id …)» no jogador.",
            )
            return
        tnm, pnm = et, jt
        kw = dict(
            team_id=int(tid),
            team_name=tnm,
            player_id=int(pid),
            player_name=pnm,
            stat=self.st_pl.currentData(),
            line=float(self.line_p.value()),
            odd_over=float(self.oo_p.value()),
            odd_under=float(self.ou_p.value()),
            limit_games=int(self.lim_p.value()),
        )
        self.run_p.setEnabled(False)
        self.run_p.setText("A calcular...")

        th = FootballPlayerThread(self.analyzer, kw)

        def on_analysis_done() -> None:
            self.run_p.setEnabled(True)
            self.run_p.setText("Calcular (jogador)")
            d = getattr(th, "_payload", None)
            try:
                if d is None:
                    self._out_text.setPlainText("Erro interno: resultado vazio.")
                elif d.get("error"):
                    err = str(d.get("error") or "")
                    dia = d.get("diagnostics")
                    if isinstance(dia, str) and dia.strip():
                        err = f"{err}\n\n{dia.strip()}"
                    self._out_text.setPlainText(err)
                else:
                    self._out_text.setPlainText(_result_to_text(d))
            except Exception:
                self._out_text.setPlainText(
                    "Erro ao formatar o resultado:\n" + traceback.format_exc()
                )
            self._out_text.verticalScrollBar().setValue(0)
            th.deleteLater()

        th.analysis_done.connect(on_analysis_done, Qt.ConnectionType.QueuedConnection)
        th.error.connect(
            lambda m, t=th: self._on_football_player_err(m, t),
            Qt.ConnectionType.QueuedConnection,
        )
        th.start()

    def _on_football_player_err(self, msg: str, thread: "FootballPlayerThread") -> None:
        self.run_p.setEnabled(True)
        self.run_p.setText("Calcular (jogador)")
        if len(msg) < 800:
            QMessageBox.critical(self, "Erro na análise", msg)
        else:
            self._out_text.setPlainText(msg)
        self._out_text.verticalScrollBar().setValue(0)
        thread.deleteLater()