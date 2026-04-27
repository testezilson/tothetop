from typing import Any, Dict


def _pct(x: Any) -> float:
    try:
        return round(float(x) * 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _round_or_none(x: Any, ndigits: int = 3) -> float | None:
    try:
        return round(float(x), ndigits)
    except (TypeError, ValueError):
        return None


def _format_summary(result: Dict[str, Any]) -> str:
    team1 = result.get("team1", "")
    team2 = result.get("team2", "")
    stat = str(result.get("stat", "")).replace("_", " ")
    is_first = bool(result.get("is_first_stat"))
    lines = [f"{stat} — {team1} vs {team2}"]

    if is_first:
        lines.append(
            f"{team1}: {_pct(result.get('mean_team1'))}% "
            f"({result.get('team1_over', 0)}/{result.get('team1_games', 0)} pegou)"
        )
        lines.append(
            f"{team2}: {_pct(result.get('mean_team2'))}% "
            f"({result.get('team2_over', 0)}/{result.get('team2_games', 0)} pegou)"
        )
        lines.append(
            f"Probabilidades: {team1} {_pct(result.get('prob_over'))}% | "
            f"{team2} {_pct(result.get('prob_under'))}%"
        )
    else:
        line = result.get("line")
        total_games = int(result.get("team1_games", 0) or 0) + int(result.get("team2_games", 0) or 0)
        lines.append(f"{team1}: média {_round_or_none(result.get('mean_team1'), 2)} ({result.get('team1_games', 0)} jogos)")
        lines.append(f"{team2}: média {_round_or_none(result.get('mean_team2'), 2)} ({result.get('team2_games', 0)} jogos)")
        lines.append(
            f"Combinado ({total_games} jogos): OVER {line} "
            f"{result.get('over_all', 0)} | UNDER {result.get('under_all', 0)}"
        )
        lines.append(
            f"Probabilidades: OVER {_pct(result.get('prob_over'))}% | "
            f"UNDER {_pct(result.get('prob_under'))}%"
        )

    if result.get("use_h2h"):
        lines.append(
            f"H2H: {result.get('h2h_games', 0)} jogos | "
            f"peso H2H {_pct(result.get('w_h2h'))}%"
        )

    lines.append(f"Recomendação: {_api_recommendation(result)}")
    return "\n".join(lines)


def _api_recommendation(result: Dict[str, Any]) -> str:
    is_first = bool(result.get("is_first_stat"))
    ev_team1 = _pct(result.get("ev_over_pct"))
    ev_team2 = _pct(result.get("ev_under_pct"))
    team1 = result.get("team1", "Time 1")
    team2 = result.get("team2", "Time 2")
    line = result.get("line")

    if ev_team1 > 0 and ev_team1 > ev_team2:
        label = team1 if is_first else f"OVER {line}"
        return f"{label} (EV {ev_team1:+.2f}%)"
    if ev_team2 > 0 and ev_team2 > ev_team1:
        label = team2 if is_first else f"UNDER {line}"
        return f"{label} (EV {ev_team2:+.2f}%)"
    return "Nenhuma aposta com EV positivo"


def build_dota_prebet_payload(
    team1: str,
    team2: str,
    stat: str,
    line: float,
    odd_team1: float,
    odd_team2: float,
    limit_games: int,
    h2h_months: int,
    use_h2h: bool,
) -> Dict[str, Any]:
    from core.dota.prebets_secondary import DotaSecondaryBetsAnalyzer

    t1, t2 = (team1 or "").strip(), (team2 or "").strip()
    if not t1 or not t2:
        raise ValueError("Preencha os dois times.")
    if t1.lower() == t2.lower():
        raise ValueError("Os times devem ser diferentes.")

    analyzer = DotaSecondaryBetsAnalyzer()
    result = analyzer.analyze_bet(
        t1,
        t2,
        stat,
        line,
        odd_team1,
        odd_team2,
        limit_games=limit_games,
        h2h_months=h2h_months,
        use_h2h=use_h2h,
    )
    if not result:
        raise ValueError("Não foi possível calcular a pré-bet Dota.")
    if result.get("error"):
        raise ValueError(str(result["error"]))

    is_first = bool(result.get("is_first_stat"))
    response = {
        "team1": result.get("team1", t1),
        "team2": result.get("team2", t2),
        "stat": result.get("stat", stat),
        "line": result.get("line", line),
        "odd_team1": odd_team1,
        "odd_team2": odd_team2,
        "limit_games": limit_games,
        "h2h_months": h2h_months,
        "use_h2h": use_h2h,
        "is_first_stat": is_first,
        "prob_team1": _pct(result.get("prob_over")),
        "prob_team2": _pct(result.get("prob_under")),
        "ev_team1": _round_or_none(result.get("ev_over"), 4),
        "ev_team2": _round_or_none(result.get("ev_under"), 4),
        "ev_team1_pct": _pct(result.get("ev_over_pct")),
        "ev_team2_pct": _pct(result.get("ev_under_pct")),
        "fair_team1": _round_or_none(result.get("fair_over"), 3),
        "fair_team2": _round_or_none(result.get("fair_under"), 3),
        "recommendation": _api_recommendation(result),
        "summary": _format_summary(result),
        "raw": result,
    }

    if not is_first:
        response.update(
            {
                "prob_over": response["prob_team1"],
                "prob_under": response["prob_team2"],
                "ev_over": response["ev_team1"],
                "ev_under": response["ev_team2"],
                "fair_over": response["fair_team1"],
                "fair_under": response["fair_team2"],
            }
        )
    return response
