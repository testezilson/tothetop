import math
from typing import Any, Dict


def _safe_fair(x: Any):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def _ev_pct_points(x: Any) -> float:
    try:
        return float(x or 0) * 100.0
    except Exception:
        return 0.0


def build_player_prebet_api_payload(
    player: str,
    stat: str,
    line: float,
    odd_over: float,
    odd_under: float,
    limit_games: int,
) -> Dict[str, Any]:
    analyzer = None
    # Mantém compatibilidade com diferentes nomes já usados no core local/desktop.
    try:
        from core.lol.prebets_players import LoLPlayerPrebetsAnalyzer  # type: ignore

        analyzer = LoLPlayerPrebetsAnalyzer()
    except Exception:
        from core.lol.prebets_player import LoLPlayerBetsAnalyzer

        analyzer = LoLPlayerBetsAnalyzer()

    result = None
    if hasattr(analyzer, "analyze_player_bet"):
        result = analyzer.analyze_player_bet(
            player_name=player,
            stat=stat,
            line=line,
            odd_over=odd_over,
            odd_under=odd_under,
            limit_games=limit_games,
        )
    else:
        # Fallback para implementação atual do core local.
        result = analyzer.analyze_bet(
            player_name=player,
            stat=stat,
            line=line,
            odd_over=odd_over,
            odd_under=odd_under,
            n_recent=limit_games,
        )

    if not result or result.get("error"):
        raise ValueError(result.get("error", "Falha na análise do player."))

    return {
        "player": result.get("player", result.get("player_name", player)),
        "stat": result.get("stat", stat),
        "line": result.get("line", line),
        "mean": result.get("mean"),
        "median": result.get("median"),
        "std": result.get("std"),
        "min": result.get("min"),
        "max": result.get("max"),
        "over": result.get("over", result.get("over_count")),
        "under": result.get("under", result.get("under_count")),
        "games": result.get("games", result.get("games_found")),
        "prob_over": float(result.get("prob_over", 0)) * 100,
        "prob_under": float(result.get("prob_under", 0)) * 100,
        "ev_over": _ev_pct_points(result.get("ev_over_pct")),
        "ev_under": _ev_pct_points(result.get("ev_under_pct")),
        "fair_over": _safe_fair(result.get("fair_over")),
        "fair_under": _safe_fair(result.get("fair_under")),
        "recommendation": result.get("recommendation", "—"),
        "last_values": result.get("last_values", []),
    }
