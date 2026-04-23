#!/usr/bin/env python3
"""
Predição Live: kills_remaining + P(Over) para qualquer linha.

Uso:
  from scripts.dota_live.predict import predict_kills_remaining, prob_over

  mu, sigma = predict_kills_remaining(minute=15, kills_now=12, ...)
  p_over = prob_over(mu, sigma, line=45.5, kills_now=12)
"""
import math
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MODEL_PATH = PROJECT_ROOT / "model_artifacts" / "dota_live_kills_remaining.pkl"
CHECKPOINTS = [10, 15, 20, 25]


def _load_model():
    import pickle
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def _sigma_for_minute(sigma_by_minute: dict, minute: int) -> float:
    """Retorna sigma do checkpoint mais próximo."""
    best = min(CHECKPOINTS, key=lambda m: abs(m - minute))
    return sigma_by_minute.get(best, 5.0)


def predict_kills_remaining(
    minute: int | float,
    kills_now: int | float,
    kpm_now: float,
    gold_diff_now: float,
    towers_total_alive: int,
    roshan_kills_so_far: int,
    draft_kills_impact_weighted: float,
    draft_duration_impact_weighted: float = 0.0,
    draft_kpm_impact_weighted: float = 0.0,
    draft_conversion_impact_weighted: float = 0.0,
    model_path: Path | None = None,
):
    """
    Retorna (mu, sigma) — predição de kills_remaining e desvio estimado.
    """
    import pickle
    path = model_path or MODEL_PATH
    with open(path, "rb") as f:
        data = pickle.load(f)
    model = data["model"]
    scaler = data["scaler"]
    feats = data["feature_cols"]
    sigma_by = data["sigma_by_minute"]

    row = [
        float(minute),
        float(kills_now),
        float(kpm_now),
        float(gold_diff_now),
        int(towers_total_alive),
        int(roshan_kills_so_far),
        float(draft_kills_impact_weighted),
    ]
    if "draft_duration_impact_weighted" in feats:
        row.extend([
            float(draft_duration_impact_weighted),
            float(draft_kpm_impact_weighted),
            float(draft_conversion_impact_weighted),
        ])
    X = np.array([row])
    X_scaled = scaler.transform(X)
    mu = float(model.predict(X_scaled)[0])
    sigma = _sigma_for_minute(sigma_by, int(minute))
    return mu, sigma


def _norm_cdf(z: float) -> float:
    """CDF normal padrão via math.erfc."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def prob_over(mu: float, sigma: float, line: float, kills_now: float) -> float:
    """
    P(kills_remaining >= needed) onde needed = ceil(line - kills_now).
    Assumindo normal: P_over = 1 - Φ((needed - mu) / sigma)
    """
    needed = math.ceil(line - kills_now)
    if sigma <= 0:
        return 0.5
    z = (needed - mu) / sigma
    return float(1.0 - _norm_cdf(z))


def line_fair(mu: float, kills_now: float) -> float:
    """Linha onde P(over) ≈ 0.5: L_fair ≈ kills_now + mu. Arredonda para .5."""
    raw = kills_now + mu
    return round(raw * 2) / 2
