#!/usr/bin/env python3
"""
Validação A/B só de torres — sem mexer no app final.

- Checagem crítica: alinhamento treino vs inferência (build_snapshots / train_live / live_kills).
- Teste 1: modelo normal vs "zerar torres" na inferência (towers_total_alive = 22 para todos).
  Compara RMSE e Brier → mede quanto o modelo está usando torres na prática.
- Teste 2 (opcional): se rodar antes train_live.py --no-towers, compara modelo com torres
  vs modelo sem torres (RMSE/Brier por minuto e por bucket de stomp).

Uso:
  python scripts/dota_live/validate_towers_ab.py
  python scripts/dota_live/validate_towers_ab.py --snapshots data/dota_live_snapshots.csv --model model_artifacts/dota_live_kills_remaining.pkl
  # Teste 2: primeiro treine sem torres, depois rode este script com --model-no-towers
  python scripts/dota_live/train_live.py --no-towers
  python scripts/dota_live/validate_towers_ab.py --model-no-towers model_artifacts/dota_live_kills_remaining_no_towers.pkl
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
MODEL_NO_TOWERS_PATH = MODELS_DIR / "dota_live_kills_remaining_no_towers.pkl"
CHECKPOINTS = [10, 15, 20, 25]
DEFAULT_LINES = [45.5, 50.5, 55.5]
TOWERS_TOTAL = 22


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def prob_over(mu: float, sigma: float, line: float, kills_now: float) -> float:
    needed = math.ceil(line - kills_now)
    if sigma <= 0:
        return 0.5
    z = (needed - mu) / sigma
    return float(1.0 - _norm_cdf(z))


def brier_and_logloss(df: pd.DataFrame, mu_pred: np.ndarray, sigma_by_minute: dict, lines: list[float]) -> dict[str, float]:
    """Retorna Brier e LogLoss médios por linha (mu_pred e df devem estar alinhados)."""
    kills_now = df["kills_now"].values
    y_true = df["kills_remaining"].values
    total_final = kills_now + y_true
    minutes = df["minute"].values
    sigma_arr = np.array([sigma_by_minute.get(int(m), 12.0) for m in minutes])
    mu_pred = np.clip(mu_pred, 0, 60)

    eps = 1e-7
    out = {}
    for line in sorted(lines):
        brier_scores = []
        logloss_scores = []
        for i in range(len(df)):
            p = prob_over(float(mu_pred[i]), float(sigma_arr[i]), line, float(kills_now[i]))
            p = max(eps, min(1 - eps, p))
            outcome = 1.0 if total_final[i] >= line else 0.0
            brier_scores.append((p - outcome) ** 2)
            logloss_scores.append(-(outcome * math.log(p) + (1 - outcome) * math.log(1 - p)))
        out[f"brier_{line}"] = float(np.mean(brier_scores))
        out[f"logloss_{line}"] = float(np.mean(logloss_scores))
    return out


def check_alignment() -> None:
    """Checagem crítica: o que treino usa vs o que a inferência (live_kills) envia."""
    print("=" * 60)
    print("CHECAGEM CRÍTICA — Alinhamento treino vs inferência")
    print("=" * 60)
    print()
    print("build_snapshots.py:")
    print("  _towers_alive() retorna (towers_r_alive, towers_d_alive) = torres VIVAS por lado.")
    print("  towers_total_alive = towers_r + towers_d  → 0 a 22 (22 = todas de pé).")
    print("  → Treino salva: torres VIVAS.")
    print()
    print("train_live.py:")
    print("  Usa a coluna 'towers_total_alive' do snapshot (mesmo nome).")
    print("  → Treino usa: torres VIVAS (0–22).")
    print()
    print("live_kills.py (inferência no app):")
    print("  Atualmente envia: towers_feature = 22 - towers_total_alive (torres CAÍDAS).")
    print("  Ou seja: 22 vivas → passa 0; 17 vivas → passa 5.")
    print("  → Inferência envia: valor no escala de torres CAÍDAS (0–22).")
    print()
    print("CONCLUSÃO: Treino = VIVAS. Inferência = CAÍDAS (invertido).")
    print("  Se o coef do Ridge for negativo, inverter na inferência 'corrige' a direção")
    print("  (mais torres caídas → menos kills), mas a escala/interpretação fica diferente do treino.")
    print("  Se a 'correção' estiver errada, torres podem estar pesando demais ou na direção errada.")
    print()


def teste1_zerar_torres(df: pd.DataFrame, model_data: dict, lines: list[float]) -> None:
    """
    Teste 1 — Zerar torres na inferência (sem retrain).
    Roda o modelo normal (usando towers do snapshot = escala de treino = VIVAS).
    Roda o modelo com towers_total_alive fixo em 22 (todas vivas) para todos.
    Compara RMSE e Brier.
    """
    print("=" * 60)
    print("TESTE 1 — Zerar torres na inferência (towers_total_alive = 22 para todos)")
    print("=" * 60)
    print("Objetivo: medir quanto o modelo está usando torres na prática.")
    print()

    feats = model_data["feature_cols"]
    if "towers_total_alive" not in feats:
        print("  Modelo não usa towers_total_alive. Nada a zerar.")
        print()
        return

    pipeline = model_data.get("pipeline")
    sigma_by = model_data["sigma_by_minute"]

    X = df[feats].fillna(0).values
    y_true = df["kills_remaining"].values
    minutes = df["minute"].values

    if pipeline is not None:
        mu_normal = pipeline.predict(X)
    else:
        scaler = model_data["scaler"]
        model = model_data["model"]
        from sklearn.preprocessing import StandardScaler
        X_scaled = scaler.transform(X)
        mu_normal = model.predict(X_scaled)
    mu_normal = np.clip(mu_normal, 0, 60)

    # Zerar: mesma matriz, coluna towers_total_alive = 22 para todos (escala de treino = vivas)
    towers_idx = feats.index("towers_total_alive")
    X_zerar = X.copy()
    X_zerar[:, towers_idx] = TOWERS_TOTAL

    if pipeline is not None:
        mu_zerar = pipeline.predict(X_zerar)
    else:
        X_zerar_scaled = scaler.transform(X_zerar)
        mu_zerar = model.predict(X_zerar_scaled)
    mu_zerar = np.clip(mu_zerar, 0, 60)

    rmse_normal = float(np.sqrt(np.mean((y_true - mu_normal) ** 2)))
    rmse_zerar = float(np.sqrt(np.mean((y_true - mu_zerar) ** 2)))
    delta_rmse = rmse_zerar - rmse_normal

    print("RMSE (holdout = mesmo dataset, só comparação relativa):")
    print(f"  Normal (towers reais):     {rmse_normal:.3f}")
    print(f"  Zerar torres (=22 vivas):  {rmse_zerar:.3f}")
    print(f"  Delta (zerar - normal):     {delta_rmse:+.3f}")
    if abs(delta_rmse) < 0.05:
        print("  → Torres quase não mudam RMSE; modelo pouco usa torres.")
    elif delta_rmse > 0.2:
        print("  → Zerar torres piora bastante; modelo usa torres de verdade.")
    else:
        print("  → Zerar torres piora um pouco; torres têm impacto moderado.")
    print()

    brier_normal = brier_and_logloss(df, mu_normal, sigma_by, lines)
    brier_zerar = brier_and_logloss(df, mu_zerar, sigma_by, lines)
    print("Brier por linha (menor = melhor):")
    for line in sorted(lines):
        bn = brier_normal[f"brier_{line}"]
        bz = brier_zerar[f"brier_{line}"]
        print(f"  Linha {line}: normal = {bn:.4f}  zerar = {bz:.4f}  delta = {bz - bn:+.4f}")
    print("  (Se delta > 0, zerar torres piora calibração.)")
    print()


def teste2_retrain_sem_torres(
    df: pd.DataFrame,
    model_with_path: Path,
    model_no_towers_path: Path,
    lines: list[float],
) -> None:
    """
    Teste 2 — Comparar modelo com torres vs modelo treinado sem torres.
    Só roda se --model-no-towers for passado e o artefato existir.
    """
    print("=" * 60)
    print("TESTE 2 — Modelo com torres vs modelo SEM torres (retrain)")
    print("=" * 60)
    print("Objetivo: se RMSE/Brier pioram pouco sem torres (< ~0.1–0.2), dá para remover.")
    print("          Se caírem muito (0.3–0.6), torres estavam ajudando de verdade.")
    print()

    if not model_no_towers_path or not model_no_towers_path.exists():
        print("  Artefato sem torres não encontrado.")
        print("  Rode antes: python scripts/dota_live/train_live.py --no-towers")
        print()
        return

    with open(model_with_path, "rb") as f:
        data_with = pickle.load(f)
    with open(model_no_towers_path, "rb") as f:
        data_no = pickle.load(f)

    feats_with = data_with["feature_cols"]
    feats_no = data_no["feature_cols"]
    if "towers_total_alive" in feats_no:
        print("  Erro: modelo --no-towers ainda contém towers_total_alive.")
        print()
        return

    pipeline_with = data_with.get("pipeline")
    pipeline_no = data_no.get("pipeline")
    sigma_by = data_with["sigma_by_minute"]

    X_with = df[feats_with].fillna(0).values
    X_no = df[feats_no].fillna(0).values
    y_true = df["kills_remaining"].values
    minutes = df["minute"].values

    if pipeline_with is not None:
        mu_with = pipeline_with.predict(X_with)
    else:
        mu_with = data_with["model"].predict(data_with["scaler"].transform(X_with))
    if pipeline_no is not None:
        mu_no = pipeline_no.predict(X_no)
    else:
        mu_no = data_no["model"].predict(data_no["scaler"].transform(X_no))

    mu_with = np.clip(mu_with, 0, 60)
    mu_no = np.clip(mu_no, 0, 60)

    rmse_with = float(np.sqrt(np.mean((y_true - mu_with) ** 2)))
    rmse_no = float(np.sqrt(np.mean((y_true - mu_no) ** 2)))
    delta_rmse = rmse_no - rmse_with
    print("RMSE global:")
    print(f"  Com torres:    {rmse_with:.3f}")
    print(f"  Sem torres:    {rmse_no:.3f}")
    print(f"  Delta:         {delta_rmse:+.3f}")
    if delta_rmse < 0.1:
        print("  → Diferença pequena; pode remover torres sem medo.")
    elif delta_rmse > 0.3:
        print("  → Sem torres piora bastante; torres ajudam.")
    else:
        print("  → Impacto moderado.")
    print()

    # Por minuto
    print("RMSE por minuto:")
    for m in CHECKPOINTS:
        mask = df["minute"] == m
        if mask.sum() < 5:
            continue
        r_with = float(np.sqrt(np.mean((y_true[mask] - mu_with[mask]) ** 2)))
        r_no = float(np.sqrt(np.mean((y_true[mask] - mu_no[mask]) ** 2)))
        print(f"  Min {m}: com torres = {r_with:.3f}  sem torres = {r_no:.3f}  delta = {r_no - r_with:+.3f}")
    print()

    # Por bucket de stomp (gold_per_min ou stomp_intensity)
    if "gold_per_min" in df.columns:
        gp = df["gold_per_min"].values
        stomp_lo = np.abs(gp) < 200
        stomp_hi = np.abs(gp) >= 400
        print("RMSE por bucket de stomp (|gold_per_min|):")
        for name, mask in [("|gold/min| < 200", stomp_lo), ("|gold/min| >= 400", stomp_hi)]:
            if mask.sum() < 10:
                continue
            r_with = float(np.sqrt(np.mean((y_true[mask] - mu_with[mask]) ** 2)))
            r_no = float(np.sqrt(np.mean((y_true[mask] - mu_no[mask]) ** 2)))
            print(f"  {name}: com = {r_with:.3f}  sem = {r_no:.3f}  delta = {r_no - r_with:+.3f}")
    print()

    brier_with = brier_and_logloss(df, mu_with, sigma_by, lines)
    brier_no = brier_and_logloss(df, mu_no, sigma_by, lines)
    print("Brier por linha (com vs sem torres):")
    for line in sorted(lines):
        bw = brier_with[f"brier_{line}"]
        bn = brier_no[f"brier_{line}"]
        print(f"  Linha {line}: com = {bw:.4f}  sem = {bn:.4f}  delta = {bn - bw:+.4f}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validação A/B de torres (zerar na inferência + opcional retrain sem torres).")
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--model-no-towers", type=Path, default=None, help="Artefato treinado com --no-towers para Teste 2")
    parser.add_argument("--lines", type=float, nargs="+", default=DEFAULT_LINES)
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
        print(f"Erro: colunas ausentes no snapshot: {missing}")
        sys.exit(1)

    check_alignment()
    teste1_zerar_torres(df, model_data, args.lines)
    no_towers_path = args.model_no_towers if args.model_no_towers is not None else MODEL_NO_TOWERS_PATH
    teste2_retrain_sem_torres(df, args.model, no_towers_path, args.lines)

    print("Fim da validação A/B (app final não foi alterado).")


if __name__ == "__main__":
    main()
