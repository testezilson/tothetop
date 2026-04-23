#!/usr/bin/env python3
"""
Testa predict de kills finais em todos os jogos da DB.

Parte 1: Cenários com gold override (5k, 10k, 0) aos 10/15/20 min.

Parte 2: Jogos por faixa de gold real:
  0~1k, 1k~2k, 2k~3k, ..., 9k~10k (positivo = Radiant ahead)
  -1k~0, ..., -10k~-9k (negativo = Dire ahead)

Para cada faixa × minuto: n, MAE, mean_pred, mean_real.
Predição usa gold real do snapshot (inclui draft, towers, roshan, etc).
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
MODEL_PATH = PROJECT_ROOT / "model_artifacts" / "dota_live_kills_remaining.pkl"
CHECKPOINTS = [10, 15, 20]
MU_CLAMP_MIN = 0
MU_CLAMP_MAX = 60


def gold_to_features(gold_diff: float, minute: int) -> tuple[float, float, float]:
    """gold_per_min, gold_log, stomp_intensity a partir de gold_diff."""
    m = max(1, minute)
    gpm = gold_diff / m
    glog = math.copysign(math.log1p(abs(gold_diff)), gold_diff) if gold_diff != 0 else 0.0
    pressure = abs(gold_diff) / m
    stomp = max(0.0, pressure - 250)
    return gpm, glog, stomp


def run_test(df: pd.DataFrame, model_data: dict) -> dict:
    pipeline = model_data.get("pipeline")
    feats = model_data["feature_cols"]
    if pipeline is None:
        raise ValueError("Pipeline não encontrado")

    X_full = df[feats].fillna(0).values
    actual_total = df["kills_now"].values + df["kills_remaining"].values

    # Índices das colunas gold para override
    gpm_idx = feats.index("gold_per_min") if "gold_per_min" in feats else None
    glog_idx = feats.index("gold_log") if "gold_log" in feats else None
    stomp_idx = feats.index("stomp_intensity") if "stomp_intensity" in feats else None
    if gpm_idx is None or glog_idx is None:
        raise ValueError("gold_per_min ou gold_log não está em feature_cols")

    scenarios = [
        ("real", None),
        ("5k", 5000),
        ("10k", 10000),
        ("0", 0),
    ]
    results = {f"{name}@{m}": {"errors": [], "pred": [], "actual": []}
               for name, _ in scenarios for m in CHECKPOINTS}

    for i in range(len(df)):
        row = df.iloc[i]
        minute = int(row["minute"])
        if minute not in CHECKPOINTS:
            continue
        kills_now = row["kills_now"]
        act = actual_total[i]
        x = X_full[i].copy()

        for scenario_name, gold_override in scenarios:
            key = f"{scenario_name}@{minute}"
            if gold_override is not None:
                gpm, glog, stomp = gold_to_features(gold_override, minute)
                x[gpm_idx] = gpm
                x[glog_idx] = glog
                if stomp_idx is not None:
                    x[stomp_idx] = stomp
            mu = float(pipeline.predict(x.reshape(1, -1))[0])
            mu = max(MU_CLAMP_MIN, min(MU_CLAMP_MAX, mu))
            pred_total = kills_now + mu
            err = abs(pred_total - act)
            results[key]["errors"].append(err)
            results[key]["pred"].append(pred_total)
            results[key]["actual"].append(act)

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Testa predict com gold override em todos os jogos")
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    args = parser.parse_args()

    if not args.snapshots.exists():
        print(f"Erro: {args.snapshots} não encontrado. Rode build_snapshots.py primeiro.")
        sys.exit(1)
    if not args.model.exists():
        print(f"Erro: {args.model} não encontrado. Rode train_live.py primeiro.")
        sys.exit(1)

    df = pd.read_csv(args.snapshots)
    df = df[df["minute"].isin(CHECKPOINTS)].copy()
    if len(df) == 0:
        print("Nenhum snapshot nos checkpoints 10/15/20.")
        sys.exit(1)

    with open(args.model, "rb") as f:
        model_data = pickle.load(f)

    feats = model_data.get("feature_cols", [])
    missing = [c for c in feats if c not in df.columns]
    if missing:
        print(f"Erro: colunas ausentes: {missing}")
        sys.exit(1)

    print("=" * 70)
    print("Teste: predict kills finais vs real (gold override)")
    print("=" * 70)
    print(f"Snapshots: {len(df)} linhas (checkpoints 10/15/20)")
    print("Cenários: real (gold do jogo), 5k lead, 10k lead, 0")
    print()

    results = run_test(df, model_data)

    print("MAE e RMSE por cenário (|predicted_total - actual_total|)")
    print("-" * 70)
    print(f"{'Cenário':<12} {'n':>6} {'MAE':>8} {'RMSE':>8} {'mean_pred':>10} {'mean_real':>10}")
    print("-" * 70)

    for scenario_name in ["real", "5k", "10k", "0"]:
        for m in CHECKPOINTS:
            key = f"{scenario_name}@{m}"
            r = results[key]
            if not r["errors"]:
                continue
            errs = np.array(r["errors"])
            preds = np.array(r["pred"])
            actuals = np.array(r["actual"])
            mae = float(np.mean(errs))
            rmse = float(np.sqrt(np.mean(errs**2)))
            mean_pred = float(np.mean(preds))
            mean_real = float(np.mean(actuals))
            print(f"{key:<12} {len(errs):>6} {mae:>8.2f} {rmse:>8.2f} {mean_pred:>10.1f} {mean_real:>10.1f}")

    print("-" * 70)
    print()
    print("2. Jogos por FAIXA DE GOLD real (predicao com gold real vs total real):")
    print("-" * 70)

    # Faixas: 0~1k, 1k~2k, ..., 9k~10k (positivo) e -1k~0, ..., -10k~-9k (negativo)
    GOLD_BUCKETS = [
        ("<-10k", -999999, -10000),
        ("-10k~-9k", -10000, -9000),
        ("-9k~-8k", -9000, -8000),
        ("-8k~-7k", -8000, -7000),
        ("-7k~-6k", -7000, -6000),
        ("-6k~-5k", -6000, -5000),
        ("-5k~-4k", -5000, -4000),
        ("-4k~-3k", -4000, -3000),
        ("-3k~-2k", -3000, -2000),
        ("-2k~-1k", -2000, -1000),
        ("-1k~0", -1000, 0),
        ("0~1k", 0, 1000),
        ("1k~2k", 1000, 2000),
        ("2k~3k", 2000, 3000),
        ("3k~4k", 3000, 4000),
        ("4k~5k", 4000, 5000),
        ("5k~6k", 5000, 6000),
        ("6k~7k", 6000, 7000),
        ("7k~8k", 7000, 8000),
        ("8k~9k", 8000, 9000),
        ("9k~10k", 9000, 10000),
        (">10k", 10000, 999999),
    ]

    pipeline = model_data.get("pipeline")

    for minute in CHECKPOINTS:
        sub = df[df["minute"] == minute]
        if len(sub) == 0:
            continue
        gold = sub["gold_diff_now"].values
        actual = sub["kills_now"].values + sub["kills_remaining"].values

        X = sub[feats].fillna(0).values
        mu = np.clip(pipeline.predict(X), MU_CLAMP_MIN, MU_CLAMP_MAX)
        pred_total = sub["kills_now"].values + mu

        print(f"\n  Minuto {minute}:")
        print(f"  {'Faixa gold':<12} {'n':>6} {'MAE':>7} {'mean_pred':>10} {'mean_real':>10}")
        print("  " + "-" * 50)

        for label, lo, hi in GOLD_BUCKETS:
            mask = (gold >= lo) & (gold < hi)
            if mask.sum() < 3:
                continue
            err = np.abs(pred_total[mask] - actual[mask])
            mae = float(np.mean(err))
            mp = float(np.mean(pred_total[mask]))
            mr = float(np.mean(actual[mask]))
            print(f"  {label:<12} {mask.sum():>6} {mae:>7.2f} {mp:>10.1f} {mr:>10.1f}")

    print("-" * 70)


if __name__ == "__main__":
    main()
