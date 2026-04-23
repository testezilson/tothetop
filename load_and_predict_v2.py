import numpy as np
import pandas as pd


def _get_prob_under(model, features_scaled):
    proba = model.predict_proba(features_scaled)[0]
    classes = getattr(model, "classes_", None)

    if classes is not None:
        classes_list = list(classes)
        if "UNDER" in classes_list:
            return float(proba[classes_list.index("UNDER")])
        if "Over" in classes_list and "Under" in classes_list:
            return float(proba[classes_list.index("Under")])
        if 1 in classes_list:
            return float(proba[classes_list.index(1)])
        if 0 in classes_list and len(classes_list) == 2:
            hi_idx = classes_list.index(max(classes_list))
            return float(proba[hi_idx])

    return float(proba[1]) if len(proba) > 1 else float(proba[0])


def predict_game(
    game_data,
    models,
    scaler,
    champion_impacts,
    league_stats,
    feature_cols,
    threshold=0.55,
):
    """
    game_data exige:
      - league: string (pode ser combinada, ex: 'LCK-LPL') → usada para média-base de kills
      - team1: [5 champs]
      - team2: [5 champs]
    opcional:
      - league_t1: liga real do Blue (ex: 'LCK')
      - league_t2: liga real do Red  (ex: 'LPL')
    """

    league_for_base = game_data["league"]
    team1 = game_data["team1"]
    team2 = game_data["team2"]

    # ligas para impactos (fallback para a liga base, se não vierem)
    league_t1 = game_data.get("league_t1", league_for_base)
    league_t2 = game_data.get("league_t2", league_for_base)

    impacts_t1 = []
    impacts_t2 = []
    missing = 0

    print("\n--- IMPACTO DOS CAMPEÕES ---")

    # BLUE SIDE
    print("\nBlue Side:")
    for champ in team1:
        imp = champion_impacts.get(league_t1, {}).get(champ)
        if imp is None:
            imp = 0
            missing += 1
            print(f"• {champ} (+0.00) ← ⚠️ sem dados suficientes ou nome incorreto")
        else:
            print(f"• {champ} ({imp:+.2f})")
        impacts_t1.append(imp)

    # RED SIDE
    print("\nRed Side:")
    for champ in team2:
        imp = champion_impacts.get(league_t2, {}).get(champ)
        if imp is None:
            imp = 0
            missing += 1
            print(f"• {champ} (+0.00) ← ⚠️ sem dados suficientes ou nome incorreto")
        else:
            print(f"• {champ} ({imp:+.2f})")
        impacts_t2.append(imp)

    if missing > 0:
        print(f"\n⚠️ Aviso: {missing} campeões sem dados suficientes ou com nome incorreto.\n")

    total_t1 = sum(impacts_t1)
    total_t2 = sum(impacts_t2)

    # média-base: usa a liga combinada (ou simples)
    league_info = league_stats.get(league_for_base, {})
    if isinstance(league_info, dict):
        base = league_info.get("mean_kills", 28.0)
    else:
        base = float(league_info) if isinstance(league_info, (int, float)) else 28.0

    # heurística para kills estimados
    kills_estimados = round(max(5, base + ((total_t1 + total_t2) / 2)), 2)

    print(f"\n⚖️ Impacto total: Blue = {total_t1:+.2f} | Red = {total_t2:+.2f}")
    print(f"📊 Média base da liga {league_for_base}: {base:.2f}")
    print(f"🎯 Kills estimados: {kills_estimados:.2f}\n")

    # === FEATURES esperadas pelo modelo ===
    features = {
        "league_encoded": hash(league_for_base) % 1000,  # usa a liga base (combinada)
        "mean_league_kills": base,
        "std_league_kills": 2.5,  # neutro
        "mean_impact_team1": total_t1 / 5,
        "mean_impact_team2": total_t2 / 5,
        "total_impact": total_t1 + total_t2,
        "impact_diff": total_t1 - total_t2,
    }
    for i in range(5):
        features[f"impact_t1_pos{i+1}"] = impacts_t1[i] if i < len(impacts_t1) else 0.0
        features[f"impact_t2_pos{i+1}"] = impacts_t2[i] if i < len(impacts_t2) else 0.0

    features_df = pd.DataFrame([features])

    # garante todas as colunas esperadas
    missing_cols = [col for col in feature_cols if col not in features_df.columns]
    for col in missing_cols:
        features_df[col] = 0.0
    features_df = features_df[feature_cols]

    # escalamento
    features_scaled = scaler.transform(features_df)

    # predição por linha
    preds = {}
    print("--- RESULTADOS COMPLETOS ---")
    for line in sorted(models.keys(), key=lambda x: float(x)):
        model = models[line]
        prob_under = _get_prob_under(model, features_scaled)
        prob_over = 1.0 - prob_under

        delta = abs(prob_under - 0.5)
        conf = "High" if delta >= 0.20 else "Medium" if delta >= 0.10 else "Low"

        # regra: UNDER se prob_under >= threshold
        escolha = "UNDER" if prob_under >= threshold else "OVER"

        preds[line] = {"UNDER": prob_under, "OVER": prob_over, "Conf": conf}
        print(f"Linha {float(line):5.1f}: {escolha:5} | Prob(UNDER): {prob_under*100:6.1f}% | Confiança: {conf}")

    return preds
