import pickle
import numpy as np
from lol_under_over_model.load_and_predict_v2 import predict_game

print("🚀 Carregando modelo...")

with open("lol_under_over_model/trained_models_v2.pkl", "rb") as f:
    models = pickle.load(f)
with open("lol_under_over_model/scaler_v2.pkl", "rb") as f:
    scaler = pickle.load(f)
with open("lol_under_over_model/champion_impacts_v2.pkl", "rb") as f:
    champion_impacts = pickle.load(f)
with open("lol_under_over_model/league_stats_v2.pkl", "rb") as f:
    league_stats = pickle.load(f)
with open("lol_under_over_model/feature_columns_v2.pkl", "rb") as f:
    feature_cols = pickle.load(f)

print("✅ Modelo carregado com sucesso!\n")

league = input("Liga (ex: LCK, LPL, LEC, CBLOL): ").strip()
team1 = [input(f"{role} Time 1: ") for role in ["Top", "Jungler", "Mid", "ADC", "Support"]]
team2 = [input(f"{role} Time 2: ") for role in ["Top", "Jungler", "Mid", "ADC", "Support"]]
threshold = float(input("Threshold (ex: 0.55, 0.65, 0.75): "))

game_data = {
    "league": league,
    "team1": team1,
    "team2": team2
}

predictions = predict_game(game_data, models, scaler, champion_impacts, league_stats, feature_cols, threshold)
