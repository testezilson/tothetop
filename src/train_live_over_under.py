"""
Treina modelo de kills restantes para Over/Under ao vivo.

Dois outputs:
1) Buckets empíricos (Fase 1): por checkpoint, bucketizar por kills_até_t e guardar
   média de kills_restantes nesse bucket. λ_base condicionado ao ritmo atual.
2) Poisson (opcional/Fase 3): mantido para compatibilidade; buckets têm prioridade.
"""
import os
import pickle
import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_poisson_deviance, mean_squared_error

# Caminhos (rodar na raiz do projeto ou com PYTHONPATH=.)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "model_artifacts")

# CSV OraclesElixir com colunas de timeline
ORACLE_ELIXIR_CSV = os.path.join(DATA_DIR, "2026_LoL_esports_match_data_from_OraclesElixir.csv")

CHECKPOINTS = [10, 15, 20, 25]
FEATURE_COLS = ["minute", "kills_now", "kpm", "gold_diff"]
BUCKETS_FILENAME = "live_ou_buckets.pkl"
TABLES_FILENAME = "live_ou_tables.pkl"

# Tabelas condicionais: E[kills_remaining | kills_bucket, gold_bucket]
# Bins de kills_at_t (total de kills no jogo até t): 0-5, 6-10, 11-15, 16-20, 21-25, 26+
KILL_EDGES = [0, 6, 11, 16, 21, 26, 100]
# Bins de gold_diff_t (em unidades): interpretável e estável
GOLD_EDGES = [-1e9, -5000, -3000, -1500, 1500, 3000, 5000, 1e9]
MIN_N_CELL = 20  # backoff se n < 20 na célula


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    return df


def build_checkpoint_dataset(csv_path: str) -> pd.DataFrame:
    """
    Lê o CSV OraclesElixir e gera uma linha por (jogo, checkpoint).

    IMPORTANTE: o CSV tem uma linha por jogador e uma linha por time (position='team').
    killsat{t} / opp_killsat{t} nas linhas de jogador são do INDIVÍDUO; nas linhas 'team'
    já são totais do time. Usar apenas position=='team' para que kills_now = total de
    kills do jogo até t (time A + time B). Caso contrário treinamos com 0–2 kills e o
    modelo aprende que "aos 10 min quase sempre tem 0–2 kills".
    """
    df = pd.read_csv(csv_path, low_memory=False)
    df = _normalize_columns(df)

    need = ["gameid", "league", "gamelength", "teamkills", "teamdeaths", "position"]
    for t in CHECKPOINTS:
        need.extend([f"killsat{t}", f"opp_killsat{t}", f"golddiffat{t}"])
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes no CSV: {missing}")

    # Apenas linhas de nível TIME: killsat{t} e opp_killsat{t} são totais do time
    df_team = df[df["position"].astype(str).str.strip().str.lower() == "team"].copy()
    if df_team.empty:
        # Fallback: agregar por (gameid, team). Somar killsat{t} dos 5 jogadores; por jogo, total = soma dos dois times.
        team_col = "teamname" if "teamname" in df.columns else "team" if "teamname" in df.columns else "team"
        if team_col not in df.columns:
            raise ValueError("CSV sem position='team' e sem coluna team/teamname para agregação.")
        per_team = (
            df[df["position"].astype(str).str.strip().str.lower() != "team"]
            .groupby(["gameid", team_col], dropna=False)
            .agg(
                **{f"killsat{t}": (f"killsat{t}", "sum") for t in CHECKPOINTS},
                **{f"opp_killsat{t}": (f"opp_killsat{t}", "first") for t in CHECKPOINTS},
                **{f"golddiffat{t}": (f"golddiffat{t}", "first") for t in CHECKPOINTS},
                league=("league", "first"),
                gamelength=("gamelength", "first"),
                teamkills=("teamkills", "first"),
                teamdeaths=("teamdeaths", "first"),
            )
            .reset_index()
        )
        # Total do jogo em t = soma dos dois times (cada time: sum(killsat{t}) do time)
        per_game = (
            per_team.groupby("gameid")
            .agg(
                **{f"killsat{t}": (f"killsat{t}", "sum") for t in CHECKPOINTS},
                **{f"golddiffat{t}": (f"golddiffat{t}", "first") for t in CHECKPOINTS},
                league=("league", "first"),
                gamelength=("gamelength", "first"),
                teamkills=("teamkills", "first"),
                teamdeaths=("teamdeaths", "first"),
            )
            .reset_index()
        )
        team_rows = per_game
    else:
        # Uma linha por jogo (uma das duas linhas 'team' por gameid)
        team_rows = df_team.drop_duplicates(subset=["gameid"], keep="first").copy()

    rows = []
    for _, row in team_rows.iterrows():
        gameid = row["gameid"]
        league = row.get("league", "MAJOR")
        try:
            gamelength_sec = float(row["gamelength"])
        except (TypeError, ValueError):
            continue
        gamelength_min = gamelength_sec / 60.0
        total_kills = float(row["teamkills"]) + float(row["teamdeaths"])

        for t in CHECKPOINTS:
            if gamelength_min < t:
                continue
            try:
                k10 = row.get(f"killsat{t}")
                k_opp = row.get(f"opp_killsat{t}")
                if pd.isna(k10):
                    continue
                # Com position=='team': k10 + k_opp = total do jogo. Fallback (agregado): só killsat = total.
                kills_at_t = float(k10) + (float(k_opp) if (k_opp is not None and not pd.isna(k_opp)) else 0)
                gold_diff = float(row.get(f"golddiffat{t}", 0) or 0)
            except (TypeError, ValueError):
                continue
            k_future = total_kills - kills_at_t
            if k_future < 0:
                continue
            kpm = kills_at_t / t if t else 0
            rows.append({
                "gameid": gameid,
                "league": league,
                "minute": t,
                "kills_now": kills_at_t,
                "kpm": kpm,
                "gold_diff": gold_diff,
                "kills_future": k_future,
            })

    return pd.DataFrame(rows)


def _bucket_index(value: float, edges: list) -> int:
    """Retorna índice do bucket: edges[i] <= value < edges[i+1]."""
    for i in range(len(edges) - 1):
        if edges[i] <= value < edges[i + 1]:
            return i
    return len(edges) - 2


def build_joint_tables(df: pd.DataFrame) -> dict:
    """
    Tabelas condicionais por checkpoint: E[kills_remaining | kills_bucket, gold_bucket].
    Cada célula (i, j) guarda mean_remaining, median_remaining, n.
    Backoff: row_means[i] (só kills_bucket) e checkpoint_mean (média global do t).
    """
    result = {}
    for t in CHECKPOINTS:
        sub = df[df["minute"] == t].copy()
        if len(sub) < 30:
            continue
        k_now = sub["kills_now"].values
        g_diff = sub["gold_diff"].values
        k_fut = sub["kills_future"].values
        n_k, n_g = len(KILL_EDGES) - 1, len(GOLD_EDGES) - 1
        table = [[None] * n_g for _ in range(n_k)]
        for i in range(n_k):
            for j in range(n_g):
                mask = (
                    (k_now >= KILL_EDGES[i]) & (k_now < KILL_EDGES[i + 1]) &
                    (g_diff >= GOLD_EDGES[j]) & (g_diff < GOLD_EDGES[j + 1])
                )
                n = int(mask.sum())
                if n >= MIN_N_CELL:
                    table[i][j] = {
                        "mean_remaining": float(np.mean(k_fut[mask])),
                        "median_remaining": float(np.median(k_fut[mask])),
                        "n": n,
                    }
        # Backoff: média por linha (só kills_bucket)
        row_means = []
        for i in range(n_k):
            mask = (k_now >= KILL_EDGES[i]) & (k_now < KILL_EDGES[i + 1])
            if mask.sum() >= MIN_N_CELL:
                row_means.append(float(np.mean(k_fut[mask])))
            else:
                row_means.append(float(np.mean(k_fut)))
        result[t] = {
            "kill_edges": list(KILL_EDGES),
            "gold_edges": list(GOLD_EDGES),
            "table": table,
            "row_means": row_means,
            "checkpoint_mean": float(np.mean(k_fut)),
        }
    return result


def build_buckets(df: pd.DataFrame) -> dict:
    """
    Buckets simples (só kills) por checkpoint — mantido para compatibilidade.
    Prioridade no predictor: tabelas conjuntas (live_ou_tables.pkl) > buckets > Poisson.
    """
    result = {}
    percentiles = [0, 20, 40, 60, 80, 100]
    for t in CHECKPOINTS:
        sub = df[df["minute"] == t].copy()
        if len(sub) < 20:
            continue
        k_now = sub["kills_now"].values
        k_fut = sub["kills_future"].values
        edges = np.percentile(k_now, percentiles)
        edges[0] = max(0, edges[0] - 0.01)
        edges[-1] = edges[-1] + 0.01
        n_b = len(edges) - 1
        means, stds, counts = [], [], []
        for i in range(n_b):
            mask = (k_now >= edges[i]) & (k_now < edges[i + 1])
            if mask.sum() > 0:
                means.append(float(np.mean(k_fut[mask])))
                stds.append(float(np.std(k_fut[mask])) if mask.sum() > 1 else 0.0)
                counts.append(int(mask.sum()))
            else:
                means.append(float(np.mean(k_fut)))
                stds.append(float(np.std(k_fut)))
                counts.append(0)
        result[t] = {"edges": edges.tolist(), "means": means, "stds": stds, "counts": counts}
    return result


def main():
    print("=== Treinamento Live Over/Under (kills restantes) ===\n")
    if not os.path.exists(ORACLE_ELIXIR_CSV):
        print(f"CSV nao encontrado: {ORACLE_ELIXIR_CSV}")
        print("   Use o CSV OraclesElixir com colunas: gamelength, killsat10/15/20/25, opp_killsat10/15/20/25, golddiffat10/15/20/25, teamkills, teamdeaths.")
        return

    print("Construindo dataset de checkpoints...")
    df = build_checkpoint_dataset(ORACLE_ELIXIR_CSV)
    print(f"   Linhas: {len(df)}")

    # Fase 1: tabelas condicionais (kills_bucket, gold_bucket) por checkpoint
    print("Construindo tabelas conjuntas (kills + gold_diff) por checkpoint...")
    tables = build_joint_tables(df)
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(os.path.join(MODELS_DIR, TABLES_FILENAME), "wb") as f:
        pickle.dump(tables, f)
    print(f"   Tabelas salvos: {list(tables.keys())}")
    # Buckets simples (fallback legado)
    buckets = build_buckets(df)
    with open(os.path.join(MODELS_DIR, BUCKETS_FILENAME), "wb") as f:
        pickle.dump(buckets, f)

    X = df[FEATURE_COLS].astype(float)
    y = df["kills_future"].astype(float)

    # Clip gold_diff para evitar outliers extremos (em milhares)
    X["gold_diff"] = X["gold_diff"].clip(-15_000, 15_000)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

    print("Treinando PoissonRegressor...")
    model = PoissonRegressor(max_iter=500)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    dev = mean_poisson_deviance(y_test, np.clip(y_pred, 1e-6, None))
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    print(f"   Poisson deviance (test): {dev:.4f} | RMSE: {rmse:.4f}")

    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(os.path.join(MODELS_DIR, "live_ou_poisson_model.pkl"), "wb") as f:
        pickle.dump(model, f)
    with open(os.path.join(MODELS_DIR, "live_ou_scaler.pkl"), "wb") as f:
        pickle.dump(scaler, f)
    with open(os.path.join(MODELS_DIR, "live_ou_feature_columns.pkl"), "wb") as f:
        pickle.dump(FEATURE_COLS, f)

    mean_kills_global = float(y.mean())
    with open(os.path.join(MODELS_DIR, "live_ou_mean_kills.pkl"), "wb") as f:
        pickle.dump(mean_kills_global, f)

    print(f"\nModelo e artefatos salvos em {MODELS_DIR}")
    print("   - live_ou_tables.pkl (prioridade: tabelas kills+gold por checkpoint)")
    print("   - live_ou_buckets.pkl (fallback: só kills)")
    print("   - live_ou_poisson_model.pkl (fallback)")
    print("   - live_ou_scaler.pkl")
    print("   - live_ou_feature_columns.pkl")
    print("   - live_ou_mean_kills.pkl")
    print("\nPronto para uso no live_over_under.py")


if __name__ == "__main__":
    main()
