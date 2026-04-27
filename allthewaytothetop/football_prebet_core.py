from __future__ import annotations

import math
import traceback
from typing import Any, Dict, List

from core.football.api_client import FootballAPIClient
from core.football.prebets_football import (
    PLAYER_STATS,
    TEAM_STATS,
    FootballPrebetsAnalyzer,
    default_api_season_year,
)


def _pct(v: Any) -> float:
    try:
        return round(float(v) * 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _round_or_none(v: Any, ndigits: int = 2) -> float | None:
    try:
        x = float(v)
        if math.isnan(x):
            return None
        return round(x, ndigits)
    except (TypeError, ValueError):
        return None


def _fmt_fair(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(x):
        return "—"
    if math.isinf(x):
        return "inf"
    return f"{x:.3f}"


def _format_val(v: Any) -> str:
    if v is None:
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(x - int(x)) < 1e-6:
        return str(int(x))
    return f"{x:.2f}"


def _opponent_line(name: str, max_len: int = 38) -> str:
    s = (name or "—").strip() or "—"
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _last_values_lines(title: str, items1: List[Dict[str, Any]], items2: List[Dict[str, Any]]) -> List[str]:
    out = []
    if not items1 and not items2:
        return out
    out.append(title)
    width = 50
    for i in range(max(len(items1), len(items2))):
        left = ""
        right = ""
        if i < len(items1):
            it = items1[i] or {}
            left = f"  {_opponent_line(it.get('opponent', ''))} — {_format_val(it.get('value'))}"
        if i < len(items2):
            it = items2[i] or {}
            right = f"{_opponent_line(it.get('opponent', ''))} — {_format_val(it.get('value'))}"
        out.append(left.ljust(width) + ("  " + right if right else ""))
    out.append("")
    return out


def result_to_text(result: Dict[str, Any]) -> str:
    if not result:
        return ""
    if result.get("error"):
        text = [str(result.get("error") or "Sem resultado.")]
        if result.get("diagnostics"):
            text.extend(["", str(result["diagnostics"])])
        return "\n".join(text)

    mode = result.get("mode", "team")
    line = result.get("line", 0)
    stat_label = result.get("stat_label") or result.get("stat") or ""
    team1 = result.get("team1", "")
    team2 = result.get("team2", "")

    out: List[str] = []
    out.append("=" * 80)
    if mode == "player":
        out.append(f"JOGADOR — {team1} | mercado: {stat_label}")
    else:
        out.append(f"EQUIPA — {stat_label} — {team1} vs {team2}")
    out.append("=" * 80)
    out.append("")

    if result.get("stat_match_total") and mode == "team":
        out.append(
            "NOTA: mercados de CARTOES = total da partida. "
            "Total cartoes usa pontos: 1 amarelo = 1, 1 vermelho = 2."
        )
        out.append("")

    if mode == "team":
        out.append("📉 Estatisticas por time (media por jogo na amostra):")
        out.append("")
        out.append(f"🔵 {team1}")
        out.append(
            f"  • Total (ultimos {result.get('team1_games', 0)} jogos): "
            f"media {float(result.get('mean_team1', 0) or 0):.2f} "
            f"({result.get('team1_n_with_stat', 0) or 0} com stat)"
        )
        out.append(
            f"  • OVER linha {line}: {result.get('team1_over', 0)}  |  "
            f"UNDER: {result.get('team1_under', 0)}"
        )
        out.append("")
        out.append(f"🔴 {team2}")
        out.append(
            f"  • Total (ultimos {result.get('team2_games', 0)} jogos): "
            f"media {float(result.get('mean_team2', 0) or 0):.2f} "
            f"({result.get('team2_n_with_stat', 0) or 0} com stat)"
        )
        out.append(
            f"  • OVER linha {line}: {result.get('team2_over', 0)}  |  "
            f"UNDER: {result.get('team2_under', 0)}"
        )
        out.append("")
        out.extend(
            _last_values_lines(
                f"Ultimos {result.get('team1_games', 10) or 10} TOTAIS",
                result.get("last_values_team1") or [],
                result.get("last_values_team2") or [],
            )
        )
        out.append(f"Combinado: OVER {result.get('over_all', 0)}  UNDER {result.get('under_all', 0)}")
        total_with_stat = max((result.get("team1_n_with_stat") or 0) + (result.get("team2_n_with_stat") or 0), 1)
        out.append(f"  Taxa OVER linha: {100.0 * float(result.get('over_all', 0) or 0) / total_with_stat:.2f}%")
        out.append("")
    else:
        out.append("Estatisticas (jogador):")
        out.append(f"  Média: {float(result.get('mean_team1', 0) or 0):.2f} ({result.get('team1_games', 0)} jogos)")
        out.append(
            f"  OVER linha {line}: {result.get('team1_over', 0)}  |  "
            f"UNDER: {result.get('team1_under', 0)}"
        )
        out.append("")
        out.extend(_last_values_lines("Ultimos 10", result.get("last_values_team1") or [], []))

    ref = (result.get("referee_name") or "").strip()
    ref_stats = result.get("referee_stats")
    if ref or (isinstance(ref_stats, dict) and ref_stats.get("computed")):
        out.append("Juiz (medias na API, totais da partida por jogo na amostra)")
        if ref:
            out.append(f"  Nome: {ref}")
        if isinstance(ref_stats, dict) and ref_stats.get("computed"):
            if not ref_stats.get("ok"):
                out.append(f"  {ref_stats.get('message', 'Sem dados.')}")
            else:
                out.append(f"  Jogos na amostra: {ref_stats.get('n', 0)}")
                for key, label in (
                    ("avg_yellow", "Media de cartoes amarelos"),
                    ("avg_red", "Media de cartoes vermelhos"),
                    ("avg_total_cards", "Media total de cartoes"),
                    ("avg_fouls", "Media de faltas"),
                ):
                    if ref_stats.get(key) is not None:
                        out.append(f"  {label}: {float(ref_stats[key]):.2f}")
        out.append("")

    if result.get("use_h2h") and mode == "team":
        out.append("=" * 80)
        out.append("H2H")
        out.append("=" * 80)
        if result.get("h2h_games", 0) == 0 or result.get("h2h_rate") is None:
            out.append("Nenhum jogo H2H com estatistica no periodo.")
        else:
            out.append(f"Jogos H2H: {result.get('h2h_games', 0)}")
            out.append(f"Media H2H: {float(result.get('h2h_mean', 0) or 0):.2f}")
            out.append(f"OVER {line}: {result.get('h2h_over', 0)} ({_pct(result.get('h2h_rate')):.2f}%)")
            out.append(
                f"Peso H2H: {_pct(result.get('w_h2h')):.1f}%  |  "
                f"Forma: {_pct(result.get('w_form', 1)):.1f}%"
            )
        out.append("")

    out.append("=" * 80)
    out.append("📈 PROBABILIDADES")
    out.append("=" * 80)
    if mode == "team":
        out.append(f"Taxa OVER {line} (só jogos do Time 1): {_pct(result.get('p_team1')):.2f}%")
        out.append(f"Taxa OVER {line} (só jogos do Time 2): {_pct(result.get('p_team2')):.2f}%")
    out.append(f"Prob. Over {line}:  {_pct(result.get('prob_over')):.2f}%")
    out.append(f"Prob. Under {line}: {_pct(result.get('prob_under')):.2f}%")
    out.append("")

    out.append("=" * 80)
    out.append("💰 EV E FAIR ODDS (Formato Pinnacle)")
    out.append("=" * 80)
    out.append(
        f"Over  {line}: EV = {float(result.get('ev_over', 0) or 0):+.2f}u "
        f"({float(result.get('ev_over_pct', 0) or 0):+.2%}) | Fair = {_fmt_fair(result.get('fair_over'))}"
    )
    out.append(
        f"Under {line}: EV = {float(result.get('ev_under', 0) or 0):+.2f}u "
        f"({float(result.get('ev_under_pct', 0) or 0):+.2%}) | Fair = {_fmt_fair(result.get('fair_under'))}"
    )
    out.append("")
    if result.get("recommendation"):
        out.append(f"Recomendacao: {result.get('recommendation')}")
    return "\n".join(out)


def build_football_team_prebet_payload(
    team1_id: int,
    team1_name: str,
    team2_id: int,
    team2_name: str,
    stat: str,
    line: float,
    odd_over: float,
    odd_under: float,
    limit_games: int,
    h2h_months: int,
    use_h2h: bool,
    referee_name: str = "",
    referee_sample_games: int = 10,
) -> Dict[str, Any]:
    try:
        analyzer = FootballPrebetsAnalyzer()
        result = analyzer.analyze_team_bet(
            team1_id=int(team1_id),
            team1_name=team1_name,
            team2_id=int(team2_id),
            team2_name=team2_name,
            stat=stat,
            line=float(line),
            odd_over=float(odd_over),
            odd_under=float(odd_under),
            limit_games=int(limit_games),
            h2h_months=int(h2h_months),
            use_h2h=bool(use_h2h),
            referee_name=referee_name or "",
            referee_sample_games=int(referee_sample_games or 10),
        )
        result["text"] = result_to_text(result)
        return result
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "payload": {
                "team1_id": team1_id,
                "team1_name": team1_name,
                "team2_id": team2_id,
                "team2_name": team2_name,
                "stat": stat,
                "line": line,
                "odd_over": odd_over,
                "odd_under": odd_under,
                "limit_games": limit_games,
                "h2h_months": h2h_months,
                "use_h2h": use_h2h,
                "referee_name": referee_name,
                "referee_sample_games": referee_sample_games,
            },
        }


def build_football_player_prebet_payload(
    team_id: int,
    team_name: str,
    player_id: int,
    player_name: str,
    stat: str,
    line: float,
    odd_over: float,
    odd_under: float,
    limit_games: int,
) -> Dict[str, Any]:
    analyzer = FootballPrebetsAnalyzer()
    result = analyzer.analyze_player_bet(
        team_id=int(team_id),
        team_name=team_name,
        player_id=int(player_id),
        player_name=player_name,
        stat=stat,
        line=float(line),
        odd_over=float(odd_over),
        odd_under=float(odd_under),
        limit_games=int(limit_games),
    )
    result["text"] = result_to_text(result)
    return result


def search_football_teams(q: str) -> List[Dict[str, Any]]:
    client = FootballAPIClient()
    return client.search_teams(q)


def search_football_players(team_id: int, q: str, season: int | None = None) -> List[Dict[str, Any]]:
    client = FootballAPIClient()
    return client.search_players(int(team_id), q, int(season or default_api_season_year()), page=1)

