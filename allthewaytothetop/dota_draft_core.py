from typing import Any, Dict, List


def _pct(x: Any) -> float:
    try:
        v = float(x)
        return round(v * 100.0 if 0 <= v <= 1 else v, 2)
    except (TypeError, ValueError):
        return 0.0


def _round(x: Any, ndigits: int = 2) -> float:
    try:
        return round(float(x), ndigits)
    except (TypeError, ValueError):
        return 0.0


def _build_text(result: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    radiant_impacts = result.get("radiant_impacts") or []
    dire_impacts = result.get("dire_impacts") or []

    lines = ["=== IMPACTOS DO DRAFT DOTA ===", "Radiant:"]
    for x in radiant_impacts:
        lines.append(
            f"  {x.get('hero')}: {_round(x.get('impact'), 2):+.2f} "
            f"(n={int(x.get('games') or 0)})"
        )

    lines.append("")
    lines.append("Dire:")
    for x in dire_impacts:
        lines.append(
            f"  {x.get('hero')}: {_round(x.get('impact'), 2):+.2f} "
            f"(n={int(x.get('games') or 0)})"
        )

    lines.append("")
    lines.append("=== ANÁLISE DE DRAFT ===")
    lines.append(f"Impacto Radiant: {_round(result.get('radiant_total'), 2):+.2f}")
    lines.append(f"Impacto Dire: {_round(result.get('dire_total'), 2):+.2f}")
    lines.append(f"Impacto Total: {_round(result.get('total_geral'), 2):+.2f}")
    lines.append(f"Kills Estimadas: {_round(result.get('kills_estimadas'), 2):.2f}")

    team_factor = result.get("team_factor") or {}
    if team_factor:
        lines.append("")
        lines.append("=== FATOR TIMES ===")
        lines.append(
            f"Radiant: {team_factor.get('radiant_team_name') or '--'} "
            f"(n={team_factor.get('radiant_n_games') or 0})"
        )
        lines.append(
            f"Dire: {team_factor.get('dire_team_name') or '--'} "
            f"(n={team_factor.get('dire_n_games') or 0})"
        )
        lines.append(
            f"Pesos: Draft {float(team_factor.get('weight_draft') or 0) * 100:.0f}% | "
            f"Times {float(team_factor.get('weight_times') or 0) * 100:.0f}%"
        )

    if rows:
        best = max(rows, key=lambda r: max(float(r["prob_over"]), float(r["prob_under"])))
        lines.append("")
        lines.append("=== MELHOR LINHA ===")
        lines.append(
            f"Linha {best['line']}: {best['recommendation']} "
            f"| OVER {best['prob_over']:.2f}% | UNDER {best['prob_under']:.2f}%"
        )

    return "\n".join(lines)


def build_dota_draft_payload(
    radiant_team: str,
    dire_team: str,
    limit_games: int,
    radiant_picks: List[str],
    dire_picks: List[str],
) -> Dict[str, Any]:
    from core.dota.draft_testezudo import DotaDraftTestezudoAnalyzer

    radiant = [str(x).strip() for x in (radiant_picks or []) if str(x).strip()]
    dire = [str(x).strip() for x in (dire_picks or []) if str(x).strip()]
    if not radiant and not dire:
        raise ValueError("Informe ao menos um pick Radiant ou Dire.")

    analyzer = DotaDraftTestezudoAnalyzer()
    if not analyzer.load_models():
        detail = analyzer.last_error or "Não foi possível carregar os modelos/impactos do Draft Dota."
        raise ValueError(detail)

    result = analyzer.analyze_draft(
        radiant,
        dire,
        radiant_team_name=None,
        dire_team_name=None,
        n_games=int(limit_games or 15),
    )
    if not result:
        raise ValueError("Não foi possível analisar o draft Dota.")
    if result.get("error"):
        raise ValueError(str(result["error"]))

    raw_predictions = result.get("predictions") or {}
    rows: List[Dict[str, Any]] = []
    for _, pred in sorted(raw_predictions.items(), key=lambda kv: float(kv[0])):
        line = pred.get("line")
        prob_over_raw = pred.get("prob_over")
        prob_under_raw = pred.get("prob_under")
        try:
            prob_over_float = float(prob_over_raw)
        except (TypeError, ValueError):
            prob_over_float = 0.0
        try:
            prob_under_float = float(prob_under_raw)
        except (TypeError, ValueError):
            prob_under_float = 1.0 - prob_over_float
        prob_over = _pct(prob_over_float)
        prob_under = _pct(prob_under_float)
        favorite = "OVER" if prob_over_float >= 0.5 else "UNDER"
        p_fav = max(prob_over_float, prob_under_float)
        if p_fav >= 0.80:
            confidence = "Very High"
        elif p_fav >= 0.70:
            confidence = "High"
        elif p_fav >= 0.60:
            confidence = "Medium"
        else:
            confidence = "Low"
        rows.append(
            {
                "line": line,
                "prob_over": prob_over,
                "prob_under": prob_under,
                "recommendation": favorite,
                "confidence": confidence,
            }
        )

    if not rows:
        raise ValueError(
            "Draft Dota carregou impactos, mas não gerou linhas. Verifique models_dota_v2_7.pkl e config_dota_v2_7.pkl."
        )

    return {
        "radiant_team": radiant_team,
        "dire_team": dire_team,
        "limit_games": int(limit_games or 15),
        "radiant_picks": radiant,
        "dire_picks": dire,
        "radiant_total": _round(result.get("radiant_total"), 2),
        "dire_total": _round(result.get("dire_total"), 2),
        "draft_total": _round(result.get("total_geral"), 2),
        "estimated_kills": _round(result.get("kills_estimadas"), 2),
        "lines": rows,
        "text": _build_text(result, rows),
        "team_factor": None,
        "team_factor_used": False,
        "weight_draft": 1.0,
        "weight_times": 0.0,
        "global_mean": _round(result.get("global_mean"), 2),
        "draft_multiplier": _round(result.get("draft_multiplier"), 2),
        "draft_strength_multiplier": _round(result.get("draft_strength_multiplier"), 2),
        "feature_set": result.get("feature_set"),
        "min_games": int(result.get("min_games") or 0),
        "raw_predictions": raw_predictions,
        "raw": result,
    }


def analyze_dota_draft(payload: Any) -> Dict[str, Any]:
    """Adapter usado pela rota FastAPI; mantém a API simples e chama o core real."""
    return build_dota_draft_payload(
        radiant_team=payload.radiant_team,
        dire_team=payload.dire_team,
        limit_games=payload.limit_games,
        radiant_picks=payload.radiant_picks,
        dire_picks=payload.dire_picks,
    )
