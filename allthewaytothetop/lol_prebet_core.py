"""
Integração com ``core.lol.prebets_secondary`` (cópia local em ``./core`` para deploy).
"""
import math
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

FIRST_STATS = frozenset({"firstdragon", "firsttower", "firstherald"})


def _stat_to_internal(raw: str) -> str:
    """Mesmo mapeamento que o desktop (combobox com labels legíveis)."""
    s = (raw or "").strip().lower()
    mapping = {
        "first dragon": "firstdragon",
        "first tower": "firsttower",
        "first herald": "firstherald",
    }
    if s in mapping:
        return mapping[s]
    return s if s else "kills"


def _ev_pct_points(ev_pct_frac: Any) -> float:
    try:
        return float(ev_pct_frac or 0) * 100.0
    except (TypeError, ValueError):
        return 0.0


def _safe_fair(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def _is_over(value: float, line_used: float) -> bool:
    return float(value) > float(line_used)


def _normalize_won(x: Any) -> Optional[bool]:
    """
    Converte qualquer variante vinda do CSV/SQL (0/1, True/False, \"Win\"/\"Loss\", textos) em
    True / False; None = impossível determinar.
    """
    if x is None:
        return None
    if type(x) is bool:
        return x
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        if isinstance(x, float) and math.isnan(x):
            return None
        if np.isnan(x):
            return None
    if isinstance(x, (int, np.integer)) and not isinstance(x, bool):
        try:
            iv = int(x)
        except (TypeError, ValueError, OverflowError):
            iv = None
        if iv == 1:
            return True
        if iv == 0:
            return False
    if isinstance(x, (float, np.floating)) and not isinstance(x, bool):
        try:
            fv = float(x)
        except (TypeError, ValueError):
            return None
        if fv == 1.0:
            return True
        if fv == 0.0:
            return False
        if fv > 0.5:
            return True
        if fv < 0.5:
            return False
    if isinstance(x, str):
        s = x.strip().lower()
        if not s or s in ("nan", "none", "null", "-", ""):
            return None
        winish = {
            "1",
            "1.0",
            "1.",
            "true",
            "t",
            "yes",
            "y",
            "win",
            "w",
            "v",
            "victory",
            "vitoria",
            "ganhou",
        }
        lossish = {
            "0",
            "0.0",
            "0.",
            "false",
            "f",
            "no",
            "n",
            "loss",
            "l",
            "defeat",
            "derrota",
            "perdeu",
        }
        if s in winish:
            return True
        if s in lossish:
            return False
    return None


def _rows_with_normalized_won(
    raw: List[Dict[str, Any]], debug_label: str
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in raw or []:
        w = _normalize_won(m.get("won"))
        if w is None and m.get("result_raw") is not None:
            w = _normalize_won(m.get("result_raw"))
        clean = {k: v for k, v in m.items() if k not in ("result_raw",)}
        clean["won"] = w
        out.append(clean)
    if (os.environ.get("LOL_PREBET_DEBUG_MATCHES") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
    ):
        print(f"DEBUG MATCHES [{debug_label}] n={len(out)}")
        for m in out[:10]:
            print(m)
    return out


def _format_avg(stat: str, mean_val: Optional[float]) -> str:
    if mean_val is None or (isinstance(mean_val, float) and (math.isnan(mean_val) or not math.isfinite(mean_val))):
        return "--"
    if (stat or "").lower() == "gamelength":
        total_sec = int(round(float(mean_val) * 60.0))
        mm = max(0, total_sec // 60)
        ss = total_sec % 60
        return f"{mm:d}:{ss:02d}"
    return f"{float(mean_val):.1f}"


def _summarize_matches(
    games: List[Dict[str, Any]], line_used: float, stat: str
) -> Dict[str, Any]:
    """
    Núcleo agregado: jogos, over/under e contagens, média numérica + string para UI.
    """
    if not games:
        return {
            "games": 0,
            "over": 0,
            "under": 0,
            "over_pct": 0.0,
            "under_pct": 0.0,
            "avg": None,
            "avg_display": "--",
        }
    n = len(games)
    over = sum(1 for g in games if _is_over(g["value"], line_used))
    under = n - over
    values = [float(g["value"]) for g in games]
    mean = float(np.mean(values))
    return {
        "games": n,
        "over": int(over),
        "under": int(under),
        "over_pct": (100.0 * over / n) if n else 0.0,
        "under_pct": (100.0 * under / n) if n else 0.0,
        "avg": mean,
        "avg_display": _format_avg(stat, mean),
    }


def _aggregate_slice(
    games: List[Dict[str, Any]], line_used: float, stat: str
) -> Dict[str, Any]:
    s = _summarize_matches(games, line_used, stat)
    if not games:
        return {
            "over": 0,
            "games": 0,
            "over_pct": 0.0,
            "avg": "--",
            "count": "0/0",
        }
    return {
        "over": s["over"],
        "games": s["games"],
        "over_pct": s["over_pct"],
        "avg": s["avg_display"],
        "count": f"{s['over']}/{s['games']}",
    }


def _build_recent_aggregates(
    pool: List[Dict[str, Any]], line_used: float, stat: str
) -> List[Dict[str, Any]]:
    """Barras do meio: over% nos últimos 15, 10 e 5 (sem filtro W/L), até 25 jogos de pool."""
    p = pool[:25] if len(pool) > 25 else pool
    rows: List[Dict[str, Any]] = []
    for n, label in ((15, "Últimos 15"), (10, "Últimos 10"), (5, "Últimos 5")):
        sl = p[:n] if len(p) >= n else p
        a = _aggregate_slice(sl, line_used, stat)
        rows.append(
            {
                "label": label,
                "count": a["count"],
                "pct": a["over_pct"],
                "avg": a["avg"],
            }
        )
    return rows


def _is_win_entry(g: Dict[str, Any]) -> bool:
    """``won`` já vem normalizado em ``_rows_with_normalized_won`` (True / False / None)."""
    return g.get("won") is True


def _is_loss_entry(g: Dict[str, Any]) -> bool:
    return g.get("won") is False


def _build_result_breakdown(
    raw: List[Dict[str, Any]], line_used: float, stat: str, period_games: int
) -> Optional[Dict[str, Any]]:
    """
    Modelo simples: últimos *period_games* jogos → contagens de vitórias/derrotas; em cada
    subconjunto, o valor da stat (ex. dragões totais) é comparado à ``line`` (over se ``value > line``).

    ``won`` em cada jogo vem da coluna ``result`` (normalizado para True/False). Sem isso, não há split.
    Recortes last_15/10/5 = N jogos com esse resultado mais recentes (lista ``raw`` do fetch).
    """
    if not raw:
        return None

    period = max(1, int(period_games or 10))
    mixed = raw[: min(period, len(raw))]
    wins_all = [g for g in raw if _is_win_entry(g)]
    losses_all = [g for g in raw if _is_loss_entry(g)]
    w_period = [g for g in mixed if _is_win_entry(g)]
    l_period = [g for g in mixed if _is_loss_entry(g)]

    has_wl = any(_is_win_entry(g) or _is_loss_entry(g) for g in raw)
    w_block = {**_summarize_matches(w_period, line_used, stat)}
    l_block = {**_summarize_matches(l_period, line_used, stat)}

    w_block["recent"] = {
        "last_15": _summarize_matches(wins_all[:15], line_used, stat),
        "last_10": _summarize_matches(wins_all[:10], line_used, stat),
        "last_5": _summarize_matches(wins_all[:5], line_used, stat),
    }
    l_block["recent"] = {
        "last_15": _summarize_matches(losses_all[:15], line_used, stat),
        "last_10": _summarize_matches(losses_all[:10], line_used, stat),
        "last_5": _summarize_matches(losses_all[:5], line_used, stat),
    }

    n_un = sum(1 for g in mixed if g.get("won") is None)
    w_record = f"{len(w_period)}V+{len(l_period)}D em {len(mixed)}j"
    if n_un:
        w_record += f" · {n_un} s/ W-L"

    return {
        "period_games": len(mixed),
        "line": float(line_used),
        "has_wl": has_wl,
        "win_loss_record": w_record,
        "total": _summarize_matches(mixed, line_used, stat),
        "wins": w_block,
        "losses": l_block,
    }


def _summary_lines_from_breakdown(bd: Dict[str, Any]) -> Tuple[float, str, float, str]:
    """Cartões VIT/DER: % over e textos a partir de ``breakdown``."""
    w = bd.get("wins") or {}
    l_ = bd.get("losses") or {}
    w_pct = float(w.get("over_pct") or 0.0) if w.get("games") else 0.0
    l_pct = float(l_.get("over_pct") or 0.0) if l_.get("games") else 0.0
    w_o, w_t = w.get("over") or 0, w.get("games") or 0
    l_o, l_t = l_.get("over") or 0, l_.get("games") or 0
    w_u, l_u = w_t - w_o, l_t - l_o
    w_ad = w.get("avg_display") or "--"
    l_ad = l_.get("avg_display") or "--"
    w_m = (
        f"{w_t} vitórias | {w_o}/{w_t} over, {w_u}/{w_t} under | média {w_ad}"
        if w_t
        else "0 vitórias | —"
    )
    l_m = (
        f"{l_t} derrotas | {l_o}/{l_t} over, {l_u}/{l_t} under | média {l_ad}"
        if l_t
        else "0 derrotas | —"
    )
    return w_pct, w_m, l_pct, l_m


def _enrich_from_raw_rows(
    raw: List[Dict[str, Any]],
    line_used: float,
    stat: str,
    is_first: bool,
    period_games: int,
) -> Dict[str, Any]:
    if is_first or not raw:
        return {}
    recent = _build_recent_aggregates(raw, line_used, stat)
    if all(g.get("won") is None for g in raw):
        bd = {
            "period_games": min(max(1, int(period_games or 10)), len(raw)),
            "line": float(line_used),
            "has_wl": False,
            "win_loss_record": "—",
            "total": _summarize_matches(raw[: min(len(raw), max(1, int(period_games or 10)))], line_used, stat),
            "wins": {**_summarize_matches([], line_used, stat), "recent": {}},
            "losses": {**_summarize_matches([], line_used, stat), "recent": {}},
        }
        empty_rec = _summarize_matches([], line_used, stat)
        bd["wins"]["recent"] = {"last_15": empty_rec, "last_10": empty_rec, "last_5": empty_rec}
        bd["losses"]["recent"] = {"last_15": empty_rec, "last_10": empty_rec, "last_5": empty_rec}
        return {
            "recent": recent,
            "wins_pct": None,
            "losses_pct": None,
            "wins_meta": "— (sem W/L no histórico)",
            "losses_meta": "— (sem W/L no histórico)",
            "breakdown": bd,
        }

    bd = _build_result_breakdown(raw, line_used, stat, period_games)
    if not bd:
        return {"recent": recent}
    w_pct, w_meta, l_pct, l_meta = _summary_lines_from_breakdown(bd)
    return {
        "wins_pct": w_pct,
        "losses_pct": l_pct,
        "wins_meta": w_meta,
        "losses_meta": l_meta,
        "recent": recent,
        "wl_window_games": bd.get("period_games"),
        "breakdown": bd,
    }


def _team_summary(result: Dict[str, Any], n: int) -> Dict[str, Any]:
    games = int(result.get(f"team{n}_games") or 0)
    over = int(result.get(f"team{n}_over") or 0)
    under = int(result.get(f"team{n}_under") or 0)
    over_pct = (over / games * 100.0) if games else 0.0
    under_pct = (under / games * 100.0) if games else 0.0
    mean = result.get(f"mean_team{n}")
    if mean is not None:
        stat = (result.get("stat") or "").lower()
        avg = _format_avg(stat, float(mean))
    else:
        avg = "--"
    return {
        "games": games,
        "over": over,
        "under": under,
        "over_pct": over_pct,
        "under_pct": under_pct,
        "avg": avg,
    }


def _h2h_summary(result: Dict[str, Any], use_h2h: bool) -> Optional[Dict[str, Any]]:
    if not use_h2h:
        return None
    ng = int(result.get("h2h_games") or 0)
    ho = int(result.get("h2h_over") or 0)
    hu = int(result.get("h2h_under") or 0)
    hm = result.get("h2h_mean")
    stat = (result.get("stat") or "").lower()
    avg = _format_avg(stat, float(hm)) if hm is not None else "--"
    over_pct = (ho / ng * 100.0) if ng else 0.0
    under_pct = (hu / ng * 100.0) if ng else 0.0
    return {
        "games": ng,
        "over": ho,
        "under": hu,
        "over_pct": over_pct,
        "under_pct": under_pct,
        "avg": avg,
    }


def _fetch_with_result_window(
    conn: sqlite3.Connection, team: str, stat: str, n_fetch: int
) -> List[Dict[str, Any]]:
    from core.lol.prebets_secondary import fetch_team_recent_with_opponent

    raw = fetch_team_recent_with_opponent(conn, team, stat, n_fetch) or []
    return _rows_with_normalized_won(raw, f"{team!r} / {stat}")


def _get_player_column(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(oracle_matches)")
    cols = {r[1] for r in cur.fetchall()}
    if "playername" in cols:
        return "playername"
    if "player" in cols:
        return "player"
    raise ValueError("Nenhuma coluna de jogador encontrada (playername/player).")


def _player_stat_column(stat: str) -> str:
    s = (stat or "").strip().lower()
    mapping = {
        "kills": "kills",
        "deaths": "deaths",
        "assists": "assists",
        "cs": "cs",
        "creepscore": "cs",
    }
    if s not in mapping:
        raise ValueError("Estatística de player inválida. Use: kills, deaths, assists ou cs.")
    return mapping[s]


def _fetch_player_with_result_window(
    conn: sqlite3.Connection, player_name: str, stat: str, n_fetch: int
) -> List[Dict[str, Any]]:
    from core.lol.prebets_secondary import _get_team_column

    player_col = _get_player_column(conn)
    team_col = _get_team_column(conn)
    stat_col = _player_stat_column(stat)
    limit = max(1, int(n_fetch or 10))

    query = f"""
        WITH player_games AS (
            SELECT
                o.gameid AS gameid,
                MAX(TRIM(o.date)) AS d,
                MAX(o.result) AS res,
                MAX(o.{stat_col}) AS value,
                MAX(o.{team_col}) AS my_team
            FROM oracle_matches o
            WHERE o.{player_col} IS NOT NULL
              AND TRIM(CAST(o.{player_col} AS TEXT)) != ''
              AND o.{player_col} COLLATE NOCASE = ?
              AND o.{stat_col} IS NOT NULL
              AND o.date IS NOT NULL
              AND TRIM(CAST(o.date AS TEXT)) != ''
            GROUP BY o.gameid
        ),
        opponent_side AS (
            SELECT
                pg.gameid,
                MAX(o2.{team_col}) AS opponent
            FROM player_games pg
            LEFT JOIN oracle_matches o2
              ON o2.gameid = pg.gameid
             AND o2.{team_col} IS NOT NULL
             AND o2.{team_col} != pg.my_team
            GROUP BY pg.gameid
        )
        SELECT
            pg.gameid,
            pg.value,
            pg.res,
            pg.my_team,
            COALESCE(opp.opponent, '—') AS opponent
        FROM player_games pg
        LEFT JOIN opponent_side opp ON opp.gameid = pg.gameid
        ORDER BY datetime(TRIM(pg.d)) DESC, pg.gameid DESC
        LIMIT ?
    """
    try:
        df = pd.read_sql_query(query, conn, params=(player_name, limit))
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        v = row.get("value")
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        r = row.get("res")
        w = _normalize_won(r)
        out.append(
            {
                "gameid": str(row.get("gameid") or ""),
                "value": float(v),
                "team": str(row.get("my_team") or "—").strip() or "—",
                "opponent": str(row.get("opponent") or "—").strip() or "—",
                "won": w,
                "result_raw": r,
            }
        )
    return _rows_with_normalized_won(out, f"{player_name!r} / {stat}")


def build_prebet_api_payload(
    team1: str,
    team2: str,
    stat: str,
    line: float,
    odd_over: float,
    odd_under: float,
    limit_games: int,
    h2h_months: int,
    use_h2h: bool,
) -> Dict[str, Any]:
    from core.lol.prebets_secondary import LoLSecondaryBetsAnalyzer
    from core.shared.paths import get_lol_db_path

    stat_int = _stat_to_internal(stat)
    is_first = stat_int in FIRST_STATS

    analyzer = LoLSecondaryBetsAnalyzer()
    result = analyzer.analyze_bet(
        team1=team1,
        team2=team2,
        stat=stat_int,
        line=line,
        odd_over=odd_over,
        odd_under=odd_under,
        limit_games=limit_games,
        h2h_months=h2h_months,
        use_h2h=use_h2h,
    )
    if not result or (isinstance(result, dict) and result.get("error")):
        msg = "Falha na análise."
        if isinstance(result, dict) and result.get("error"):
            msg = str(result["error"])
        raise ValueError(msg)

    p_over = float(result["prob_over"])
    p_under = float(result["prob_under"])
    evo = _ev_pct_points(result.get("ev_over_pct"))
    evu = _ev_pct_points(result.get("ev_under_pct"))
    rec = str(result.get("recommendation") or "—")

    line_used = float(result.get("line", line))
    if result.get("is_first_stat"):
        line_used = 0.5

    s1 = _team_summary(result, 1)
    s2 = _team_summary(result, 2)

    n_fetch = max(25, int(limit_games or 10), 15)
    db_path = get_lol_db_path()
    team1_breakdown: Optional[Dict[str, Any]] = None
    team2_breakdown: Optional[Dict[str, Any]] = None
    if db_path and not is_first:
        try:
            con = sqlite3.connect(db_path)
            try:
                r1 = _fetch_with_result_window(con, team1, stat_int, n_fetch)
                r2 = _fetch_with_result_window(con, team2, stat_int, n_fetch)
                s1.update(_enrich_from_raw_rows(r1, line_used, stat_int, is_first, limit_games))
                s2.update(_enrich_from_raw_rows(r2, line_used, stat_int, is_first, limit_games))
                team1_breakdown = s1.pop("breakdown", None)
                team2_breakdown = s2.pop("breakdown", None)
            finally:
                con.close()
        except OSError:
            pass

    for s, bd in ((s1, team1_breakdown), (s2, team2_breakdown)):
        if bd and bd.get("total"):
            t = bd["total"]
            s["games"] = t.get("games", s.get("games", 0))
            s["over"] = t.get("over", s.get("over", 0))
            s["under"] = t.get("under", s.get("under", 0))
            s["over_pct"] = t.get("over_pct", s.get("over_pct", 0.0))
            s["under_pct"] = t.get("under_pct", s.get("under_pct", 0.0))
            s["avg"] = t.get("avg_display", s.get("avg", "--"))

    out: Dict[str, Any] = {
        "team1": result.get("team1", team1),
        "team2": result.get("team2", team2),
        "line": result.get("line", line),
        "stat": result.get("stat", stat_int),
        "is_first_stat": bool(result.get("is_first_stat")),
        "prob_over": p_over * 100.0,
        "prob_under": p_under * 100.0,
        "ev_over": evo,
        "ev_under": evu,
        "fair_over": _safe_fair(result.get("fair_over")),
        "fair_under": _safe_fair(result.get("fair_under")),
        "fair_odd": _safe_fair(result.get("fair_over")),
        "recommendation": rec,
        "team1_summary": s1,
        "team2_summary": s2,
        "team1_breakdown": team1_breakdown,
        "team2_breakdown": team2_breakdown,
    }
    out["h2h_summary"] = _h2h_summary(result, use_h2h)
    return out


def build_player_prebet_api_payload(
    player: str,
    stat: str,
    line: float,
    odd_over: float,
    odd_under: float,
    limit_games: int,
) -> Dict[str, Any]:
    from core.shared.paths import get_lol_db_path

    player_name = (player or "").strip()
    if not player_name:
        raise ValueError("Preencha o jogador.")

    stat_int = _player_stat_column(stat)
    line_used = float(line)
    n_fetch = max(25, int(limit_games or 10), 15)

    db_path = get_lol_db_path()
    if not db_path:
        raise ValueError("Banco de dados não encontrado.")

    con = sqlite3.connect(db_path)
    try:
        raw = _fetch_player_with_result_window(con, player_name, stat_int, n_fetch)
    finally:
        con.close()

    if not raw:
        raise ValueError(f"Nenhum dado encontrado para {player_name} em {stat_int}.")

    period = max(1, int(limit_games or 10))
    period_slice = raw[: min(period, len(raw))]
    s = _summarize_matches(period_slice, line_used, stat_int)
    s.update(_enrich_from_raw_rows(raw, line_used, stat_int, False, period))
    breakdown = s.pop("breakdown", None)

    if breakdown and breakdown.get("total"):
        t = breakdown["total"]
        s["games"] = t.get("games", s.get("games", 0))
        s["over"] = t.get("over", s.get("over", 0))
        s["under"] = t.get("under", s.get("under", 0))
        s["over_pct"] = t.get("over_pct", s.get("over_pct", 0.0))
        s["under_pct"] = t.get("under_pct", s.get("under_pct", 0.0))
        s["avg"] = t.get("avg_display", s.get("avg_display", "--"))

    values = np.array([float(g["value"]) for g in period_slice], dtype=float) if period_slice else np.array([], dtype=float)
    mean_v = float(np.mean(values)) if values.size else 0.0
    median_v = float(np.median(values)) if values.size else 0.0
    std_v = float(np.std(values)) if values.size else 0.0
    min_v = float(np.min(values)) if values.size else 0.0
    max_v = float(np.max(values)) if values.size else 0.0
    over_n = int(s.get("over", 0) or 0)
    under_n = int(s.get("under", 0) or 0)

    prob_over = float(s.get("over_pct", 0.0)) / 100.0
    prob_under = max(0.0, 1.0 - prob_over)

    ev_over_frac = prob_over * (float(odd_over) - 1.0) - (1.0 - prob_over)
    ev_under_frac = prob_under * (float(odd_under) - 1.0) - (1.0 - prob_under)

    if ev_over_frac > ev_under_frac and ev_over_frac > 0:
        rec = f"OVER {line_used}"
    elif ev_under_frac > 0:
        rec = f"UNDER {line_used}"
    else:
        rec = "Nenhuma aposta com EV positivo"

    last_values = []
    for g in raw[:10]:
        v = float(g.get("value") or 0.0)
        side = "OVER" if _is_over(v, line_used) else "UNDER"
        team = str(g.get("team") or "—").strip() or "—"
        opp = str(g.get("opponent") or "—").strip() or "—"
        last_values.append(
            {
                "value": v,
                "side": side,
                "match": f"{team} vs {opp}",
            }
        )

    return {
        "player": player_name,
        "stat": stat_int,
        "line": line_used,
        "mean": mean_v,
        "median": median_v,
        "std": std_v,
        "min": min_v,
        "max": max_v,
        "over": over_n,
        "under": under_n,
        "prob_over": prob_over * 100.0,
        "prob_under": prob_under * 100.0,
        "ev_over": ev_over_frac * 100.0,
        "ev_under": ev_under_frac * 100.0,
        "fair_over": _safe_fair((1.0 / prob_over) if prob_over > 0 else None),
        "fair_under": _safe_fair((1.0 / prob_under) if prob_under > 0 else None),
        "recommendation": rec,
        "team_summary": s,
        "breakdown": breakdown,
        "last_values": last_values,
    }
