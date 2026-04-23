import pandas as pd
import pickle

def lookup_impact(df_imp, league, champ):
    """Busca o impacto de um campeão dentro da liga correspondente."""
    if pd.isna(champ):
        return 0.0
    match = df_imp[
        (df_imp["league"] == league) &
        (df_imp["champion"].str.casefold() == str(champ).casefold())
    ]
    return float(match["impact"].iloc[0]) if not match.empty else 0.0

def predict_game(game_data, models, scaler, champion_impacts, league_stats, feature_cols, threshold=0.55):
    """
    Calcula probabilidades de UNDER/OVER kills baseado no draft.
    game_data = {"league": "LCK", "team1": [champs], "team2": [champs]}
    
    Para ligas agregadas, pode conter:
    - "league_stats_override": dict com stats agregadas
    - "impacts_override": {"team1": [impacts], "team2": [impacts]}
    """
    league = game_data["league"].strip()
    team1 = game_data["team1"]
    team2 = game_data["team2"]
    
    # Verificar se há impactos sobrescritos (para ligas agregadas)
    if "impacts_override" in game_data:
        impacts_t1 = game_data["impacts_override"]["team1"]
        impacts_t2 = game_data["impacts_override"]["team2"]
    else:
        # Impactos individuais (buscar na liga)
        impacts_t1 = [lookup_impact(champion_impacts, league, c) for c in team1]
        impacts_t2 = [lookup_impact(champion_impacts, league, c) for c in team2]

    total_t1 = sum(impacts_t1)
    total_t2 = sum(impacts_t2)

    # Estatísticas da liga (usar override se disponível)
    if "league_stats_override" in game_data:
        stats = game_data["league_stats_override"]
    else:
        stats = league_stats.get(league, {"mean_kills": 28.0, "std_kills": 8.0})
    mean_kills = stats["mean_kills"]
    std_kills = stats["std_kills"]

    # Kills estimados (mesma heurística do v2)
    kills_estimados = round(mean_kills + (total_t1 + total_t2) / 2, 2)

    # Monta vetor de features igual ao usado no treino
    feats = {
        "league_encoded": hash(league) % 1000,
        "mean_league_kills": mean_kills,
        "std_league_kills": std_kills,
        "mean_impact_team1": total_t1 / 5,
        "mean_impact_team2": total_t2 / 5,
        "total_impact": total_t1 + total_t2,
        "impact_diff": total_t1 - total_t2,
    }

    for i in range(5):
        feats[f"impact_t1_pos{i+1}"] = impacts_t1[i] if i < len(impacts_t1) else 0.0
        feats[f"impact_t2_pos{i+1}"] = impacts_t2[i] if i < len(impacts_t2) else 0.0

    X = pd.DataFrame([feats])
    for col in feature_cols:
        if col not in X.columns:
            X[col] = 0.0
    X = X[feature_cols]

    X_scaled = scaler.transform(X.values)

    results = {}
    for line, model in models.items():
        p_under = float(model.predict_proba(X_scaled)[0][1])
        p_over = 1 - p_under
        diff = abs(p_under - 0.5)
        conf = "High" if diff >= 0.20 else ("Medium" if diff >= 0.10 else "Low")
        choice = "UNDER" if p_under >= threshold else "OVER"
        results[line] = {
            "Prob(UNDER)": round(p_under * 100, 2),
            "Prob(OVER)": round(p_over * 100, 2),
            "Confiança": conf,
            "Escolha": choice,
        }

    return {
        "kills_estimados": kills_estimados,
        "impacto_t1": round(total_t1, 2),
        "impacto_t2": round(total_t2, 2),
        "resultados": results,
    }

if __name__ == "__main__":
    # Teste manual opcional
    with open("../model_artifacts/trained_models_v3.pkl", "rb") as f:
        models = pickle.load(f)
    with open("../model_artifacts/scaler_v3.pkl", "rb") as f:
        scaler = pickle.load(f)
    with open("../model_artifacts/feature_columns_v3.pkl", "rb") as f:
        feature_cols = pickle.load(f)
    with open("../data/league_stats_v3.pkl", "rb") as f:
        league_stats = pickle.load(f)
    champion_impacts = pd.read_csv("../data/champion_impacts.csv")

    game = {
        "league": "LCK",
        "team1": ["Lee Sin", "Azir", "Xayah", "Rakan", "Renekton"],
        "team2": ["Vi", "Orianna", "Kai'Sa", "Nautilus", "Sion"],
    }

    result = predict_game(game, models, scaler, champion_impacts, league_stats, feature_cols, threshold=0.55)

    print(f"\n🎯 Liga: {game['league']}")
    print(f"🔵 Impacto T1: {result['impacto_t1']} | 🔴 Impacto T2: {result['impacto_t2']}")
    print(f"📈 Kills estimados: {result['kills_estimados']}")
    print("\n--- RESULTADOS ---")
    for line, r in sorted(result["resultados"].items(), key=lambda kv: float(kv[0])):
        print(f"Linha {line:>5}: {r['Escolha']:6} | Prob(UNDER): {r['Prob(UNDER)']:6.2f}% | Confiança: {r['Confiança']}")
