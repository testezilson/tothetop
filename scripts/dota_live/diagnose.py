#!/usr/bin/env python3
"""
Diagnóstico completo do modelo Live: sigma vs std real, draft_weight, feature importance, Brier.

PASSO 1 - Diagnóstico por minuto: real mean, pred mean, real std, sigma (200 jogos aleatórios)
PASSO 2 - Modelo com vs sem draft_weight: compara RMSE
PASSO 3 - Feature importance: Ridge coef_ (magnitude relativa)
PASSO 4 - Backtest betting: Brier e LogLoss para linhas 45.5, 50.5, 55.5

Uso:
  python scripts/dota_live/diagnose.py
  python scripts/dota_live/diagnose.py --n-games 200 --lines 45.5 50.5 55.5
"""
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_predict

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SNAPSHOTS_PATH = PROJECT_ROOT / "data" / "dota_live_snapshots.csv"
MODELS_DIR = PROJECT_ROOT / "model_artifacts"
MODEL_PATH = MODELS_DIR / "dota_live_kills_remaining.pkl"
CHECKPOINTS = [10, 15, 20, 25]
DEFAULT_LINES = [45.5, 50.5, 55.5]

FEATURE_COLS_MVP = [
    "minute",
    "kills_now",
    "kpm_now",
    "gold_per_min",
    "gold_log",
    "stomp_intensity",
    "towers_total_alive",
    "roshan_kills_so_far",
    "draft_kills_impact_weighted",
]
FEATURE_COLS_NO_DRAFT = [
    "minute",
    "kills_now",
    "kpm_now",
    "gold_per_min",
    "gold_log",
    "stomp_intensity",
    "towers_total_alive",
    "roshan_kills_so_far",
]


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def prob_over(mu: float, sigma: float, line: float, kills_now: float) -> float:
    needed = math.ceil(line - kills_now)
    if sigma <= 0:
        return 0.5
    z = (needed - mu) / sigma
    return float(1.0 - _norm_cdf(z))


def passo1_diagnostico_por_minuto(df: pd.DataFrame, model_data: dict, n_games: int = 200) -> None:
    """PASSO 1: real mean, pred mean, real std, sigma por checkpoint (N jogos aleatórios)."""
    print("=" * 60)
    print("PASSO 1 - Diagnostico por minuto")
    print("=" * 60)
    print(f"Jogos: {n_games} aleatorios (todos os checkpoints por jogo)")
    print()

    match_ids = df["match_id"].unique()
    rng = np.random.default_rng(42)
    sample_ids = rng.choice(match_ids, size=min(n_games, len(match_ids)), replace=False)
    sub = df[df["match_id"].isin(sample_ids)].copy()

    pipeline = model_data.get("pipeline")
    feats = model_data["feature_cols"]
    sigma_by = model_data["sigma_by_minute"]

    X = sub[feats].fillna(0).values
    y_true = sub["kills_remaining"].values
    mu_pred = pipeline.predict(X) if pipeline else None
    if pipeline is None:
        scaler = model_data["scaler"]
        model = model_data["model"]
        X_scaled = scaler.transform(X)
        mu_pred = model.predict(X_scaled)
    mu_pred = np.clip(mu_pred, 0, 60)

    for cp in CHECKPOINTS:
        mask = sub["minute"] == cp
        if mask.sum() < 5:
            continue
        y_cp = y_true[mask]
        pred_cp = mu_pred[mask]
        sigma = sigma_by.get(cp, 12.0)
        real_mean = float(np.mean(y_cp))
        pred_mean = float(np.mean(pred_cp))
        real_std = float(np.std(y_cp))
        print(f"Min {cp}:")
        print(f"  real mean:  {real_mean:.1f}")
        print(f"  pred mean:  {pred_mean:.1f}")
        print(f"  real std:   {real_std:.1f}")
        print(f"  sigma:      {sigma:.1f}")
        ratio = sigma / real_std if real_std > 0 else float("nan")
        print(f"  ratio sigma/std: {ratio:.2f}", end="")
        if ratio < 0.8:
            print("  -> sigma < std real: prob_over pode ficar agressivo")
        elif ratio > 1.2:
            print("  -> sigma > std real: prob_over pode ficar timido")
        else:
            print("  -> OK")
        print()


def passo2_draft_weight_impact(df: pd.DataFrame) -> None:
    """PASSO 2: Modelo com vs sem draft_weight - compara RMSE."""
    print("=" * 60)
    print("PASSO 2 - Impacto do draft_weight")
    print("=" * 60)
    print("draft_weight = max(0, 1 - minute/40)")
    print("  min 10 -> 0.75 | min 15 -> 0.625 | min 20 -> 0.5 | min 25 -> 0.375")
    print()

    missing_mvp = [c for c in FEATURE_COLS_MVP if c not in df.columns]
    missing_no = [c for c in FEATURE_COLS_NO_DRAFT if c not in df.columns]
    if missing_mvp or missing_no:
        print(f"Erro: colunas ausentes MVP={missing_mvp} NO_DRAFT={missing_no}")
        return

    y = df["kills_remaining"].values

    # Com draft
    X_mvp = df[FEATURE_COLS_MVP].fillna(0).values
    pipe_mvp = Pipeline([
        ("scaler", StandardScaler()),
        ("ridge", Ridge(alpha=1.0, random_state=42)),
    ])
    pred_mvp = cross_val_predict(pipe_mvp, X_mvp, y, cv=5)
    rmse_mvp = np.sqrt(np.mean((y - pred_mvp) ** 2))

    # Sem draft
    X_no = df[FEATURE_COLS_NO_DRAFT].fillna(0).values
    pipe_no = Pipeline([
        ("scaler", StandardScaler()),
        ("ridge", Ridge(alpha=1.0, random_state=42)),
    ])
    pred_no = cross_val_predict(pipe_no, X_no, y, cv=5)
    rmse_no = np.sqrt(np.mean((y - pred_no) ** 2))

    print("RMSE (5-fold CV):")
    print(f"  Com draft_weight:    {rmse_mvp:.3f}")
    print(f"  Sem draft_weight:    {rmse_no:.3f}")
    delta = rmse_mvp - rmse_no
    if delta < -0.01:
        print(f"  -> Draft ajuda: RMSE {abs(delta):.3f} menor com draft")
    elif delta > 0.01:
        print(f"  -> Draft piora: RMSE {delta:.3f} maior com draft")
    else:
        print(f"  -> Empate: diferenca negligivel ({delta:.3f})")
    print()


def passo3_feature_importance(model_data: dict) -> None:
    """PASSO 3: Ridge coef_ - magnitude relativa das features."""
    print("=" * 60)
    print("PASSO 3 - Feature importance (Ridge coef)")
    print("=" * 60)
    print("Coeficientes em espaco escalado. Magnitude relativa indica impacto.")
    print()

    ridge = model_data.get("model")
    feats = model_data.get("feature_cols", [])
    if ridge is None:
        pipeline = model_data.get("pipeline")
        if pipeline:
            ridge = pipeline.named_steps.get("ridge")
        feats = model_data.get("feature_cols", [])
    if ridge is None:
        print("Modelo Ridge nao encontrado.")
        return

    coef = ridge.coef_
    if len(feats) != len(coef):
        feats = [f"f{i}" for i in range(len(coef))]
    pairs = list(zip(feats, coef))
    pairs.sort(key=lambda x: abs(x[1]), reverse=True)
    for name, c in pairs:
        print(f"  {name}: {c:.4f}")
    draft_idx = next((i for i, (n, _) in enumerate(pairs) if "draft" in n.lower()), None)
    if draft_idx is not None:
        name, c = pairs[draft_idx]
        if abs(c) < 0.1:
            print(f"\n  -> {name} tem coef proximo de zero: pode nao estar ajudando")
    print()


def passo4_backtest_betting(df: pd.DataFrame, model_data: dict, lines: list[float]) -> None:
    """PASSO 4: Brier e LogLoss para linhas - mais importante que RMSE."""
    print("=" * 60)
    print("PASSO 4 - Backtest betting (Brier / LogLoss)")
    print("=" * 60)
    print("Linhas: 45.5, 50.5, 55.5")
    print("P(Over) vs outcome real -> Brier e LogLoss")
    print()

    pipeline = model_data.get("pipeline")
    scaler = model_data.get("scaler")
    model = model_data.get("model")
    feats = model_data["feature_cols"]
    sigma_by = model_data["sigma_by_minute"]

    X = df[feats].fillna(0).values
    y_true = df["kills_remaining"].values
    kills_now = df["kills_now"].values
    total_final = kills_now + y_true
    minutes = df["minute"].values

    if pipeline is not None:
        mu_pred = pipeline.predict(X)
    else:
        X_scaled = scaler.transform(X)
        mu_pred = model.predict(X_scaled)
    mu_pred = np.clip(mu_pred, 0, 60)
    sigma_arr = np.array([sigma_by.get(int(m), 12.0) for m in minutes])

    eps = 1e-7
    for line in sorted(lines):
        brier_scores = []
        logloss_scores = []
        for i in range(len(df)):
            p = prob_over(float(mu_pred[i]), float(sigma_arr[i]), line, float(kills_now[i]))
            p = max(eps, min(1 - eps, p))
            outcome = 1.0 if total_final[i] >= line else 0.0
            brier_scores.append((p - outcome) ** 2)
            logloss_scores.append(-(outcome * math.log(p) + (1 - outcome) * math.log(1 - p)))
        brier = float(np.mean(brier_scores))
        logloss = float(np.mean(logloss_scores))
        print(f"  Linha {line}: Brier = {brier:.4f}, LogLoss = {logloss:.4f} (n={len(df)})")
    print("  (Brier/LogLoss menores = melhor calibracao)")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--n-games", type=int, default=200, help="Jogos para PASSO 1")
    parser.add_argument("--lines", type=float, nargs="+", default=DEFAULT_LINES, help="Linhas para PASSO 4")
    args = parser.parse_args()

    if not args.snapshots.exists():
        print(f"Erro: {args.snapshots} nao encontrado. Rode build_snapshots.py primeiro.")
        sys.exit(1)
    if not args.model.exists():
        print(f"Erro: {args.model} nao encontrado. Rode train_live.py primeiro.")
        sys.exit(1)

    df = pd.read_csv(args.snapshots)
    with open(args.model, "rb") as f:
        model_data = pickle.load(f)

    feats = model_data.get("feature_cols", [])
    missing = [c for c in feats if c not in df.columns]
    if missing:
        print(f"Erro: colunas ausentes: {missing}")
        sys.exit(1)

    passo1_diagnostico_por_minuto(df, model_data, args.n_games)
    passo2_draft_weight_impact(df)
    passo3_feature_importance(model_data)
    passo4_backtest_betting(df, model_data, args.lines)

    print("Fim do diagnostico.")


if __name__ == "__main__":
    main()
