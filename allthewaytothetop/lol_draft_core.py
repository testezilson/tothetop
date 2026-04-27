from typing import Any, Dict, List, Union


def _resultados_to_rows(
    resultados: Any, threshold: float, _fmt_pct, _recommendation
) -> List[Dict[str, Any]]:
    """Converte o dict `resultados` de load_and_predict_v3 (chave = linha) em lista para a API."""
    if not isinstance(resultados, dict) or not resultados:
        return []
    out: List[Dict[str, Any]] = []
    for line_key, r in sorted(
        resultados.items(), key=lambda kv: float(str(kv[0]).replace(",", "."))
    ):
        try:
            line_val: Union[float, Any] = float(str(line_key).replace(",", "."))
        except (TypeError, ValueError):
            line_val = line_key
        pu = r.get("Prob(UNDER)")
        if pu is None:
            pu = r.get("prob_under") or r.get("p_under")
        po = r.get("Prob(OVER)")
        if po is None:
            po = r.get("prob_over") or r.get("p_over")
        pu = _fmt_pct(pu) if pu is not None else 0.0
        po = _fmt_pct(po) if po is not None else 0.0
        esc, conf = r.get("Escolha"), r.get("Confiança")
        rec = None
        if esc is not None:
            c = str(conf) if conf is not None else "Low"
            rec = f"{esc} ({c})"
        out.append(
            {
                "line": line_val,
                "prob_under": pu,
                "prob_over": po,
                "recommendation": rec or _recommendation(pu, po, threshold),
            }
        )
    return out


def build_lol_draft_payload(
    league: str,
    threshold: float,
    team1_picks: List[str],
    team2_picks: List[str],
) -> Dict[str, Any]:
    from core.lol.draft import LoLDraftAnalyzer

    def _fmt_pct(x: Any) -> float:
        try:
            v = float(x)
            return v * 100.0 if 0 <= v <= 1 else v
        except Exception:
            return 0.0

    def _recommendation(prob_under: float, prob_over: float, thr: float) -> str:
        if prob_over >= thr * 100:
            strength = "Medium" if prob_over >= 60 else "Low"
            return f"OVER ({strength})"
        if prob_under >= thr * 100:
            strength = "Medium" if prob_under >= 60 else "Low"
            return f"UNDER ({strength})"
        return "NO BET"

    analyzer = LoLDraftAnalyzer()
    result = analyzer.analyze_draft(
        league=league,
        team1=team1_picks,
        team2=team2_picks,
        threshold=threshold,
    )

    if not result:
        raise ValueError(
            "Não foi possível carregar/analisar o draft. Verifique model_artifacts e data."
        )

    rows: List[Dict[str, Any]] = []
    # load_and_predict_v3 devolve o dict "resultados" (linhas/under/over), não "predictions"/"rows"
    if result.get("resultados"):
        rows = _resultados_to_rows(
            result["resultados"], threshold, _fmt_pct, _recommendation
        )
    else:
        for r in (
            result.get("predictions")
            or result.get("rows")
            or result.get("lines")
            or []
        ):
            line = r.get("line") or r.get("linha")
            pu = _fmt_pct(
                r.get("prob_under") or r.get("under_prob") or r.get("p_under")
            )
            po = _fmt_pct(
                r.get("prob_over") or r.get("over_prob") or r.get("p_over")
            )
            rows.append(
                {
                    "line": line,
                    "prob_under": pu,
                    "prob_over": po,
                    "recommendation": r.get("recommendation")
                    or _recommendation(pu, po, threshold),
                }
            )

    summary_lines = []
    impacts = result.get("impactos_individuais") or {}

    summary_lines.append("=== IMPACTOS INDIVIDUAIS ===")
    summary_lines.append("Time 1:")
    for x in impacts.get("team1", []):
        summary_lines.append(
            f"  {x.get('champion')}: {float(x.get('impact') or 0):+.2f} (n={int(x.get('n_games') or 0)})"
        )

    summary_lines.append("")
    summary_lines.append("Time 2:")
    for x in impacts.get("team2", []):
        summary_lines.append(
            f"  {x.get('champion')}: {float(x.get('impact') or 0):+.2f} (n={int(x.get('n_games') or 0)})"
        )

    summary_lines.append("")
    summary_lines.append("=== ANÁLISE DE DRAFT ===")
    summary_lines.append(f"Liga: {result.get('league', league)}")
    kills_disp = (
        result.get("kills_estimados")
        or result.get("predicted_kills")
        or result.get("kills_estimate")
        or result.get("expected_kills")
    )
    if kills_disp is not None and kills_disp != "":
        try:
            kills_disp = f"{float(kills_disp):.2f}"
        except (TypeError, ValueError):
            kills_disp = str(kills_disp)
    else:
        kills_disp = "--"
    summary_lines.append(f"Kills Estimados: {kills_disp}")
    summary_lines.append(
        f"Impacto Time 1: {sum(float(x.get('impact') or 0) for x in impacts.get('team1', [])):+.2f}"
    )
    summary_lines.append(
        f"Impacto Time 2: {sum(float(x.get('impact') or 0) for x in impacts.get('team2', [])):+.2f}"
    )

    ke = result.get("kills_estimados")
    if ke is None:
        ke = result.get("predicted_kills") or result.get("kills_estimate")
    return {
        "league": result.get("league", league),
        "threshold": threshold,
        "team1_picks": team1_picks,
        "team2_picks": team2_picks,
        "rows": rows,
        "kills_estimados": ke,
        "summary": "\n".join(summary_lines),
        "raw_keys": list(result.keys()),
    }
