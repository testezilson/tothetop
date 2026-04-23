import os
import pickle
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, brier_score_loss

# Caminhos
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ORACLE_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
IMPACTS_PATH = os.path.join(BASE_DIR, "data", "champion_impacts.csv")
LEAGUE_STATS_PATH = os.path.join(BASE_DIR, "data", "league_stats_v3.pkl")
TRAINSET_OUT = os.path.join(BASE_DIR, "data", "trainset_v3.csv")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "model_artifacts")

# Linhas de kills
LINES = [25.5, 26.5, 27.5, 28.5, 29.5, 30.5, 31.5, 32.5]


def lookup_impact(df_imp, league, champ):
    if pd.isna(champ) or champ == "":
        return 0.0
    m = df_imp[
        (df_imp["league"].str.casefold() == str(league).casefold()) &
        (df_imp["champion"].str.casefold() == str(champ).casefold())
    ]
    return float(m["impact"].iloc[0]) if not m.empty else 0.0


def build_trainset(df_oracle, df_imp):
    """
    Constrói um dataset no formato "1 linha por partida", contendo:
      - picks dos dois times,
      - impactos por posição/time,
      - agregados (total_impact, impact_diff, etc.),
      - total_kills (target contínuo).
    """
    required = ["league", "gameid", "teamname", "teamkills",
                "pick1", "pick2", "pick3", "pick4", "pick5", "total_kills"]
    miss = [c for c in required if c not in df_oracle.columns]
    if miss:
        raise ValueError(f"Colunas faltando no oracle_prepared.csv: {miss}")

    # Garantir pares por partida (2 linhas por gameid)
    games = []
    for (league, gameid), g in df_oracle.groupby(["league", "gameid"]):
        if len(g) != 2:
            # pula partidas incompletas
            continue
        t1 = g.iloc[0]
        t2 = g.iloc[1]

        row = {
            "league": league,
            "gameid": gameid,
            "t1": t1["teamname"],
            "t2": t2["teamname"],
            "total_kills": float(t1["total_kills"]),  # já é total do jogo
        }
        for i in range(1, 6):
            row[f"t1_pos{i}"] = t1[f"pick{i}"]
            row[f"t2_pos{i}"] = t2[f"pick{i}"]
        games.append(row)

    df_games = pd.DataFrame(games)

    # Impactos individuais por posição/time
    for i in range(1, 6):
        df_games[f"impact_t1_pos{i}"] = [
            lookup_impact(df_imp, lg, ch) for lg, ch in zip(df_games["league"], df_games[f"t1_pos{i}"])
        ]
        df_games[f"impact_t2_pos{i}"] = [
            lookup_impact(df_imp, lg, ch) for lg, ch in zip(df_games["league"], df_games[f"t2_pos{i}"])
        ]

    # Agregados
    df_games["total_impact_t1"] = df_games[[f"impact_t1_pos{i}" for i in range(1, 6)]].sum(axis=1)
    df_games["total_impact_t2"] = df_games[[f"impact_t2_pos{i}" for i in range(1, 6)]].sum(axis=1)
    df_games["total_impact"] = df_games["total_impact_t1"] + df_games["total_impact_t2"]
    df_games["impact_diff"] = df_games["total_impact_t1"] - df_games["total_impact_t2"]
    df_games["mean_impact_team1"] = df_games["total_impact_t1"] / 5.0
    df_games["mean_impact_team2"] = df_games["total_impact_t2"] / 5.0

    # Codificação leve da liga (estável, mas simples)
    df_games["league_encoded"] = [hash(lg) % 1000 for lg in df_games["league"]]

    return df_games


def build_features(df_games, league_stats):
    # mean/std por liga
    means = []
    stds = []
    for lg in df_games["league"]:
        s = league_stats.get(lg, {"mean_kills": 28.0, "std_kills": 8.0})
        means.append(float(s["mean_kills"]))
        stds.append(float(s["std_kills"]))

    X = pd.DataFrame({
        "league_encoded": df_games["league_encoded"].astype(float),
        "mean_league_kills": means,
        "std_league_kills": stds,
        "mean_impact_team1": df_games["mean_impact_team1"],
        "mean_impact_team2": df_games["mean_impact_team2"],
        "total_impact": df_games["total_impact"],
        "impact_diff": df_games["impact_diff"],
    })

    # manter impactos por posição (consistência com a engine de predição)
    for i in range(1, 5 + 1):
        X[f"impact_t1_pos{i}"] = df_games[f"impact_t1_pos{i}"]
        X[f"impact_t2_pos{i}"] = df_games[f"impact_t2_pos{i}"]

    return X


def main():
    print("=== 🚀 Build Trainset + Train Model (Oracle v3) ===")

    # Carregar bases
    df_oracle = pd.read_csv(ORACLE_PATH)
    df_imp = pd.read_csv(IMPACTS_PATH)
    with open(LEAGUE_STATS_PATH, "rb") as f:
        league_stats = pickle.load(f)

    print(f"📂 oracle_prepared.csv: {len(df_oracle)} linhas")
    print(f"📊 champion_impacts.csv: {len(df_imp)} entradas (já filtrado por jogos)")

    # 1) Trainset
    print("🧱 Construindo trainset...")
    df_games = build_trainset(df_oracle, df_imp)
    print(f"✅ Partidas consolidadas: {len(df_games)}")

    # 2) Features
    X = build_features(df_games, league_stats)
    feature_cols = list(X.columns)
    y_cont = df_games["total_kills"].astype(float)

    # salvar trainset completo para auditoria
    out = df_games.copy()
    out[feature_cols] = X
    out.to_csv(TRAINSET_OUT, index=False)
    print(f"💾 Trainset salvo: {TRAINSET_OUT} (colunas de features anexadas)")

    # 3) Escalonamento
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    # 4) Treino por linha
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    models = {}
    metrics = {}

    print("\n🎯 Treinando regressões (UNDER por linha)...\n")
    for line in LINES:
        y = (y_cont < line).astype(int)  # 1 = UNDER, 0 = OVER
        X_tr, X_te, y_tr, y_te = train_test_split(X_scaled, y, test_size=0.2, random_state=42, stratify=y)

        clf = LogisticRegression(max_iter=400, n_jobs=None)
        clf.fit(X_tr, y_tr)

        p = clf.predict_proba(X_te)[:, 1]
        auc = roc_auc_score(y_te, p)
        brier = brier_score_loss(y_te, p)

        models[str(line)] = clf
        metrics[str(line)] = {"roc_auc": round(float(auc), 4), "brier": round(float(brier), 4)}
        print(f"🔹 Linha {line:>4}: AUC={auc:.3f} | Brier={brier:.3f} (n={len(y_te)})")

    # 5) Salvar artefatos
    with open(os.path.join(ARTIFACTS_DIR, "trained_models_v3.pkl"), "wb") as f:
        pickle.dump(models, f)
    with open(os.path.join(ARTIFACTS_DIR, "scaler_v3.pkl"), "wb") as f:
        pickle.dump(scaler, f)
    with open(os.path.join(ARTIFACTS_DIR, "feature_columns_v3.pkl"), "wb") as f:
        pickle.dump(feature_cols, f)

    # 6) Resumo
    print("\n✅ Artefatos salvos em:", ARTIFACTS_DIR)
    print("📈 Métricas:")
    for ln, m in metrics.items():
        print(f"  {ln}: AUC={m['roc_auc']:.3f} | Brier={m['brier']:.3f}")


if __name__ == "__main__":
    main()
