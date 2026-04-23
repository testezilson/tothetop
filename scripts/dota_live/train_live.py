#!/usr/bin/env python3
"""
Treina modelo Ridge para prever kills_remaining (target).

Features MVP: minute, kills_now, kpm_now, gold_diff_now, towers_total_alive,
             roshan_kills_so_far, draft_kills_impact_weighted

Salva: model, scaler, sigma por checkpoint (calibração), feature_cols.

Uso:
  python scripts/dota_live/train_live.py
  python scripts/dota_live/train_live.py --snapshots data/dota_live_snapshots.csv
"""
import json
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
CHECKPOINTS = [10, 15, 20, 25]

# MVP Gold: gold_per_min, gold_log, stomp_intensity (regime terminal: gold_pressure > 250)
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
FEATURE_COLS_MVP_NO_TOWERS = [c for c in FEATURE_COLS_MVP if c != "towers_total_alive"]
FEATURE_COLS_FULL = FEATURE_COLS_MVP + [
    "draft_duration_impact_weighted",
    "draft_kpm_impact_weighted",
    "draft_conversion_impact_weighted",
]
FEATURE_COLS_FULL_NO_TOWERS = [c for c in FEATURE_COLS_FULL if c != "towers_total_alive"]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS_PATH)
    parser.add_argument("--features", choices=["mvp", "full"], default="mvp")
    parser.add_argument("--no-towers", action="store_true", help="Remove towers_total_alive das features (para Teste 2 A/B)")
    parser.add_argument("--alpha", type=float, default=1.0, help="Ridge alpha")
    args = parser.parse_args()

    if not args.snapshots.exists():
        print(f"Erro: {args.snapshots} não encontrado. Rode build_snapshots.py primeiro.")
        sys.exit(1)

    df = pd.read_csv(args.snapshots)
    if args.no_towers:
        feats = (FEATURE_COLS_MVP_NO_TOWERS if args.features == "mvp" else FEATURE_COLS_FULL_NO_TOWERS)
    else:
        feats = FEATURE_COLS_MVP if args.features == "mvp" else FEATURE_COLS_FULL
    missing = [c for c in feats if c not in df.columns]
    if missing:
        print(f"Erro: colunas ausentes: {missing}")
        sys.exit(1)

    X = df[feats].fillna(0).values
    y = df["kills_remaining"].values

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("ridge", Ridge(alpha=args.alpha, random_state=42)),
    ])
    pipeline.fit(X, y)

    y_pred = cross_val_predict(pipeline, X, y, cv=5)
    residuals = y - y_pred
    rmse = np.sqrt(np.mean(residuals**2))

    sigma_by_minute = {}
    for m in CHECKPOINTS:
        mask = df["minute"] == m
        if mask.sum() > 10:
            sigma_by_minute[m] = float(np.std(residuals[mask]))
        else:
            sigma_by_minute[m] = float(np.std(residuals))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "pipeline": pipeline,
        "model": pipeline.named_steps["ridge"],
        "scaler": pipeline.named_steps["scaler"],
        "feature_cols": feats,
        "sigma_by_minute": sigma_by_minute,
        "checkpoints": CHECKPOINTS,
    }
    if args.no_towers:
        pkl_path = MODELS_DIR / "dota_live_kills_remaining_no_towers.pkl"
        print("Treino SEM torres (para validação A/B).")
    else:
        pkl_path = MODELS_DIR / "dota_live_kills_remaining.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(out, f)

    print(f"Modelo salvo: {pkl_path}")
    print(f"RMSE (5-fold CV): {rmse:.3f}")
    print("Sigma por checkpoint:", sigma_by_minute)
    return out


if __name__ == "__main__":
    main()
