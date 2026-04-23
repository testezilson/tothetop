import pandas as pd
import numpy as np
import pickle
import os
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, brier_score_loss

# Caminhos
TRAIN_PATH = "../data/trainset_v3.csv"
LEAGUE_STATS_PATH = "../data/league_stats_v3.pkl"
MODEL_DIR = "../model_artifacts"

# Linhas de kills a serem treinadas
LINES = [25.5, 26.5, 27.5, 28.5, 29.5, 30.5, 31.5, 32.5]

def build_features(df, league_stats):
    mean = []
    std = []
    for lg in df["league"]:
        stat = league_stats.get(lg, {"mean_kills": 28.0, "std_kills": 8.0})
        mean.append(stat["mean_kills"])
        std.append(stat["std_kills"])
    
    X = pd.DataFrame({
        "league_encoded": df["league_encoded"].astype(float),
        "mean_league_kills": mean,
        "std_league_kills": std,
        "mean_impact_team1": df["mean_impact_team1"],
        "mean_impact_team2": df["mean_impact_team2"],
        "total_impact": df["total_impact"],
        "impact_diff": df["impact_diff"],
    })
    
    # Adiciona impactos por posição (para compatibilidade com predict_game)
    for i in range(1, 6):
        X[f"impact_t1_pos{i}"] = df[f"impact_t1_pos{i}"]
        X[f"impact_t2_pos{i}"] = df[f"impact_t2_pos{i}"]
    
    return X

def main():
    print("📊 Carregando dataset e estatísticas de ligas...")
    df = pd.read_csv(TRAIN_PATH)
    with open(LEAGUE_STATS_PATH, "rb") as f:
        league_stats = pickle.load(f)

    X = build_features(df, league_stats)
    feature_cols = list(X.columns)

    print(f"✅ Features geradas: {len(feature_cols)} colunas")

    os.makedirs(MODEL_DIR, exist_ok=True)

    # Normalizador global (como no v2)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    models = {}
    metrics = {}

    print("🚀 Iniciando treinamento por linha de kills...\n")

    for line in LINES:
        y = (df["total_kills"] < line).astype(int)
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42
        )

        model = LogisticRegression(max_iter=300)
        model.fit(X_train, y_train)

        y_pred = model.predict_proba(X_test)[:, 1]  # Probabilidade de UNDER
        auc = roc_auc_score(y_test, y_pred)
        brier = brier_score_loss(y_test, y_pred)

        models[str(line)] = model
        metrics[str(line)] = {"roc_auc": round(float(auc), 4), "brier": round(float(brier), 4)}

        print(f"🔹 Linha {line:.1f} → AUC={auc:.3f} | Brier={brier:.3f}")

    # Salvar artefatos
    with open(f"{MODEL_DIR}/trained_models_v3.pkl", "wb") as f:
        pickle.dump(models, f)
    with open(f"{MODEL_DIR}/scaler_v3.pkl", "wb") as f:
        pickle.dump(scaler, f)
    with open(f"{MODEL_DIR}/feature_columns_v3.pkl", "wb") as f:
        pickle.dump(feature_cols, f)

    print("\n✅ Modelos treinados e salvos em:", MODEL_DIR)
    print("📈 Métricas por linha:")
    for line, m in metrics.items():
        print(f"  {line}: AUC={m['roc_auc']:.3f} | Brier={m['brier']:.3f}")

if __name__ == "__main__":
    main()
