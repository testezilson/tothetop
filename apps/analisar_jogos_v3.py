import os
import sys
import pickle
import pandas as pd

# 🔧 Corrige o caminho para importar src
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from src.load_and_predict_v3 import predict_game  # assinatura: (game_data, models, scaler, champion_impacts, league_stats, feature_cols, threshold)

# Caminhos base
MODEL_PATH = os.path.join(ROOT_DIR, "model_artifacts")
DATA_PATH = os.path.join(ROOT_DIR, "data")


def main():
    print("=== 🎯 LoL Oracle ML v3 - Análise de Draft ===\n")

    # === Entrada do usuário ===
    league = input("Liga (ex: LCK, LPL, LEC, CBLOL, MSI, WORLDS): ").strip()
    threshold = float(input("Threshold (ex: 0.55): ").strip() or 0.55)

    print("\n🟦 Digite os 5 campeões do Time 1:")
    team1 = [input(f"  Campeão {i+1}: ").strip() for i in range(5)]

    print("\n🟥 Digite os 5 campeões do Time 2:")
    team2 = [input(f"  Campeão {i+1}: ").strip() for i in range(5)]

    # === Carregar modelos e dados ===
    try:
        with open(os.path.join(MODEL_PATH, "trained_models_v3.pkl"), "rb") as f:
            models = pickle.load(f)
        with open(os.path.join(MODEL_PATH, "scaler_v3.pkl"), "rb") as f:
            scaler = pickle.load(f)
        with open(os.path.join(MODEL_PATH, "feature_columns_v3.pkl"), "rb") as f:
            feature_cols = pickle.load(f)
        with open(os.path.join(DATA_PATH, "league_stats_v3.pkl"), "rb") as f:
            league_stats = pickle.load(f)

        impacts = pd.read_csv(os.path.join(DATA_PATH, "champion_impacts.csv"))
        impacts.columns = impacts.columns.str.strip().str.lower()

        print("🚀 Modelos e dados carregados com sucesso! (8 linhas de regressão)\n")

    except Exception as e:
        print("❌ Erro ao carregar arquivos do modelo ou dados:")
        print(e)
        return

    # === Mostrar impactos individuais (com n=...) ===
    print("🟦 Time 1:")
    for champ in team1:
        row = impacts[
            (impacts["league"].str.lower() == league.lower())
            & (impacts["champion"].str.lower() == champ.lower())
        ]
        if not row.empty:
            imp = float(row["impact"].iloc[0])
            n_games = int(row["games_played"].iloc[0])
            color = "🟢" if imp > 0 else ("🔴" if imp < 0 else "⚪")
            print(f"   {color} {champ:<15} → {imp:+.2f}  (n={n_games})")
        else:
            print(f"   ⚪ {champ:<15} → +0.00  (n=0)")

    print("\n🟥 Time 2:")
    for champ in team2:
        row = impacts[
            (impacts["league"].str.lower() == league.lower())
            & (impacts["champion"].str.lower() == champ.lower())
        ]
        if not row.empty:
            imp = float(row["impact"].iloc[0])
            n_games = int(row["games_played"].iloc[0])
            color = "🟢" if imp > 0 else ("🔴" if imp < 0 else "⚪")
            print(f"   {color} {champ:<15} → {imp:+.2f}  (n={n_games})")
        else:
            print(f"   ⚪ {champ:<15} → +0.00  (n=0)")

    # === Predição ===
    try:
        game_data = {"league": league, "team1": team1, "team2": team2}
        result = predict_game(
            game_data,
            models,
            scaler,
            impacts,
            league_stats,
            feature_cols,
            threshold,
        )
    except Exception as e:
        print("\n❌ Erro durante a previsão:")
        print(e)
        return

    # === Exibir resultados ===
    print(f"\n📊 Resultados para a liga {league}")
    print(f"🔵 Impacto total Time 1: {result['impacto_t1']:+.2f}")
    print(f"🔴 Impacto total Time 2: {result['impacto_t2']:+.2f}")
    print(f"🎯 Kills estimados: {result['kills_estimados']:.2f}\n")

    print("=== RESULTADOS POR LINHA ===")
    for line, r in sorted(result["resultados"].items(), key=lambda kv: float(kv[0])):
        print(
            f"Linha {float(line):>5.1f}: {r['Escolha']:6} | Prob(UNDER): {r['Prob(UNDER)']:6.2f}% | Confiança: {r['Confiança']}"
        )


if __name__ == "__main__":
    main()
