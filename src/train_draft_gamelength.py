"""
Treina predição de duração do jogo a partir do draft (10 campeões).

Draft -> expected_gamelength; usado só cedo (10/15 min) para ajustar minutes_left
no cap contextual do live O/U. Não altera λ diretamente; só o horizonte temporal.

Target: gamelength_minutes.
Features: scaling_score médio do draft (bucket empírico por scaling_mean).
Output: draft_length_buckets.pkl (mean por bucket, global_mean, scaling_scores).
"""

import os
import pickle
import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "model_artifacts")
ORACLE_ELIXIR_CSV = os.path.join(DATA_DIR, "2026_LoL_esports_match_data_from_OraclesElixir.csv")
ARTIFACT_NAME = "draft_length_buckets.pkl"

# Heurística: scaling 0 = early/snowball, 1 = late. Default 0.5 para desconhecidos.
CHAMPION_SCALING_SCORE = {
    "ornn": 0.92, "azir": 0.90, "aphelios": 0.88, "kayle": 0.95, "kassadin": 0.92,
    "vayne": 0.85, "jinx": 0.82, "kog'maw": 0.88, "veigar": 0.88, "nasus": 0.90,
    "renekton": 0.25, "nidalee": 0.35, "lucian": 0.30, "elise": 0.35, "pantheon": 0.30,
    "lee sin": 0.35, "draven": 0.25, "reksai": 0.35, "xin zhao": 0.45, "warwick": 0.40,
    "gnar": 0.55, "ahri": 0.50, "corki": 0.55, "leona": 0.45, "diana": 0.50,
    "sivir": 0.50, "braum": 0.45, "ekko": 0.55, "dr. mundo": 0.50,
    "mel": 0.55, "zaahen": 0.50,
    # adicione mais conforme necessário
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    return df


def scaling_score(champ: str) -> float:
    if not champ or (isinstance(champ, float) and pd.isna(champ)):
        return 0.5
    key = str(champ).strip().lower()
    return CHAMPION_SCALING_SCORE.get(key, 0.5)


def build_draft_gamelength_dataset(csv_path: str) -> pd.DataFrame:
    """
    Uma linha por jogo: gameid, league, gamelength_min, scaling_mean (média dos 10 champs).
    """
    df = pd.read_csv(csv_path, low_memory=False)
    df = _normalize_columns(df)
    for c in ["gameid", "side", "position", "champion", "gamelength", "league"]:
        if c not in df.columns:
            raise ValueError(f"Coluna ausente: {c}")

    players = df[df["position"].isin(["top", "jng", "mid", "bot", "sup"])].copy()
    team_rows = df[df["position"].astype(str).str.strip().str.lower() == "team"].copy()
    if team_rows.empty:
        raise ValueError("CSV sem linhas position='team' para gamelength.")

    # gamelength por gameid (uma linha team por jogo)
    gl = team_rows.drop_duplicates(subset=["gameid"], keep="first")[["gameid", "gamelength", "league"]].copy()
    gl["gamelength_min"] = gl["gamelength"].astype(float) / 60.0

    rows = []
    for gameid, grp in players.groupby("gameid"):
        if len(grp) != 10:
            continue
        champs = grp["champion"].astype(str).tolist()
        scores = [scaling_score(c) for c in champs]
        scaling_mean = float(np.mean(scores))
        row_gl = gl[gl["gameid"] == gameid]
        if row_gl.empty:
            continue
        gamelength_min = float(row_gl.iloc[0]["gamelength_min"])
        league = row_gl.iloc[0].get("league", "MAJOR")
        rows.append({
            "gameid": gameid,
            "league": league,
            "gamelength_min": gamelength_min,
            "scaling_mean": scaling_mean,
        })
    return pd.DataFrame(rows)


def train_buckets(df: pd.DataFrame) -> dict:
    """
    Buckets por scaling_mean; cada bucket guarda média de gamelength.
    Bordas: [0, 0.4, 0.6, 1.0] -> early / misto / scaling.
    """
    edges = [0.0, 0.4, 0.6, 1.01]
    bucket_means = {}
    bucket_counts = {}
    for i in range(len(edges) - 1):
        low, high = edges[i], edges[i + 1]
        sub = df[(df["scaling_mean"] >= low) & (df["scaling_mean"] < high)]
        if len(sub) >= 5:
            bucket_means[i] = float(sub["gamelength_min"].mean())
            bucket_counts[i] = len(sub)
        else:
            bucket_means[i] = float(df["gamelength_min"].mean())
            bucket_counts[i] = 0
    global_mean = float(df["gamelength_min"].mean())
    return {
        "bucket_edges": edges,
        "bucket_means": bucket_means,
        "bucket_counts": bucket_counts,
        "global_mean": global_mean,
        "scaling_scores": dict(CHAMPION_SCALING_SCORE),
    }


def main():
    print("=== Treino Draft -> Gamelength (buckets) ===\n")
    if not os.path.exists(ORACLE_ELIXIR_CSV):
        print(f"CSV nao encontrado: {ORACLE_ELIXIR_CSV}")
        return
    df = build_draft_gamelength_dataset(ORACLE_ELIXIR_CSV)
    if df.empty or len(df) < 30:
        print("Poucos jogos com draft/gamelength.")
        return
    print(f"  Jogos: {len(df)}")
    print(f"  Gamelength medio (min): {df['gamelength_min'].mean():.1f}")
    data = train_buckets(df)
    os.makedirs(MODELS_DIR, exist_ok=True)
    out_path = os.path.join(MODELS_DIR, ARTIFACT_NAME)
    with open(out_path, "wb") as f:
        pickle.dump(data, f)
    print(f"  Salvo: {out_path}")
    print(f"  Buckets: edges={data['bucket_edges']}, means={data['bucket_means']}, global_mean={data['global_mean']:.1f}")
    print("\nUso no live: time_multiplier = predicted_length / global_mean, clamp [0.9, 1.1]; so em 10/15 min.")


if __name__ == "__main__":
    main()
