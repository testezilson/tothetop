#!/usr/bin/env python3
"""
Backtest do modelo Live: RMSE, erro do total final, Brier e LogLoss para linhas.

Métricas:
- RMSE de kills_remaining por checkpoint
- MAE do total final: |(kills_now + mu) - total_final| por checkpoint
- Brier e LogLoss para linhas 45.5, 50.5, 55.5 (P(Over) vs outcome)

Uso:
  python scripts/dota_live/backtest.py
  python scripts/dota_live/backtest.py --snapshots data/dota_live_snapshots.csv --lines 45.5 50.5 55.5 60.5
"""
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SNAPSHOTS_PATH = PROJECT_ROOT / "data" / "dota_live_snapshots.csv"
MODELS_DIR = PROJECT_ROOT / "model_artifacts"
MODEL_PATH = MODELS_DIR / "dota_live_kills_remaining.pkl"
CHECKPOINTS = [10, 15, 20, 25]
DEFAULT_LINES = [45.5, 50.5, 55.5]


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def prob_over(mu: float, sigma: float, line: float, kills_now: float) -> float:
    """P(kills_remaining >= needed). needed = ceil(line - kills_now)."""
    needed = math.ceil(line - kills_now)
    if sigma <= 0:
        return 0.5
    z = (needed - mu) / sigma
    return float(1.0 - _norm_cdf(z))


def run_backtest(df: pd.DataFrame, model_data: dict, lines: list[float]) -> dict:
    """Executa backtest e retorna métricas."""
    pipeline = model_data.get("pipeline")
    scaler = model_data.get("scaler")
    model = model_data.get("model")
    feats = model_data["feature_cols"]
    sigma_by = model_data["sigma_by_minute"]

    X = df[feats].fillna(0).values
    y_true = df["kills_remaining"].values
    kills_now = df["kills_now"].values
    total_final = kills_now + y_true  # kills_now + kills_remaining = total_final

    # Predição
    if pipeline is not None:
        mu_pred = pipeline.predict(X)
    else:
        X_scaled = scaler.transform(X)
        mu_pred = model.predict(X_scaled)

    mu_pred = np.clip(mu_pred, 0, 60)
    total_pred = kills_now + mu_pred

    # Sigma por minuto
    minutes = df["minute"].values
    sigma_arr = np.array([sigma_by.get(int(m), 12.0) for m in minutes])

    results = {
        "rmse_by_checkpoint": {},
        "mae_total_by_checkpoint": {},
        "lines": {},
    }

    # RMSE e MAE por checkpoint
    for cp in CHECKPOINTS:
        mask = df["minute"] == cp
        if mask.sum() < 5:
            continue
        err_rem = y_true[mask] - mu_pred[mask]
        err_total = total_final[mask] - total_pred[mask]
        results["rmse_by_checkpoint"][cp] = float(np.sqrt(np.mean(err_rem**2)))
        results["mae_total_by_checkpoint"][cp] = float(np.mean(np.abs(err_total)))

    # Brier e LogLoss por linha
    eps = 1e-7
    for line in lines:
        brier_scores = []
        logloss_scores = []
        for i in range(len(df)):
            p = prob_over(float(mu_pred[i]), float(sigma_arr[i]), line, float(kills_now[i]))
            p = max(eps, min(1 - eps, p))
            outcome = 1.0 if total_final[i] >= line else 0.0
            brier_scores.append((p - outcome) ** 2)
            logloss_scores.append(-(outcome * math.log(p) + (1 - outcome) * math.log(1 - p)))
        results["lines"][line] = {
            "brier": float(np.mean(brier_scores)),
            "logloss": float(np.mean(logloss_scores)),
            "n": len(df),
        }

    results["overall_rmse"] = float(np.sqrt(np.mean((y_true - mu_pred) ** 2)))
    results["overall_mae_total"] = float(np.mean(np.abs(total_final - total_pred)))
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--lines", type=float, nargs="+", default=DEFAULT_LINES,
                        help="Linhas para Brier/LogLoss (ex: 45.5 50.5 55.5)")
    args = parser.parse_args()

    if not args.snapshots.exists():
        print(f"Erro: {args.snapshots} não encontrado. Rode build_snapshots.py primeiro.")
        sys.exit(1)
    if not args.model.exists():
        print(f"Erro: {args.model} não encontrado. Rode train_live.py primeiro.")
        sys.exit(1)

    df = pd.read_csv(args.snapshots)
    with open(args.model, "rb") as f:
        model_data = pickle.load(f)
    feats = model_data.get("feature_cols", [])
    missing = [c for c in feats if c not in df.columns]
    if missing:
        print(f"Erro: colunas ausentes: {missing}")
        sys.exit(1)

    print("=" * 60)
    print("Backtest - Dota Live Kills Remaining")
    print("=" * 60)
    print(f"Snapshots: {len(df)} linhas")
    print(f"Linhas: {args.lines}")
    print()

    res = run_backtest(df, model_data, args.lines)

    print("1. RMSE de kills_remaining por checkpoint")
    for cp, rmse in sorted(res["rmse_by_checkpoint"].items()):
        print(f"   min {cp}: RMSE = {rmse:.3f}")
    print(f"   Overall: RMSE = {res['overall_rmse']:.3f}")
    print()

    print("2. MAE do total final |(kills_now+mu) - total_final| por checkpoint")
    for cp, mae in sorted(res["mae_total_by_checkpoint"].items()):
        print(f"   min {cp}: MAE = {mae:.3f}")
    print(f"   Overall: MAE = {res['overall_mae_total']:.3f}")
    print()

    print("3. Brier e LogLoss (P(Over) vs outcome) por linha")
    for line, m in sorted(res["lines"].items()):
        print(f"   Linha {line}: Brier = {m['brier']:.4f}, LogLoss = {m['logloss']:.4f} (n={m['n']})")
    print()

    print("Fim do backtest.")


if __name__ == "__main__":
    main()
