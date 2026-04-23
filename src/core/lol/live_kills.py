"""
Modelo Live LoL: prevê kills_remaining e P(Over) para jogos ao vivo.

Sem torres/barons/dragons. Regime lento via slow_intensity = max(0, 0.33 - kpm_now).
Usa lol_live_kills_remaining.pkl e champion_impacts_lol.json (ou champion_impacts.csv).
"""
import json
import math
import pickle
import os

import pandas as pd

from core.shared.paths import path_in_models, path_in_data

MODEL_FILENAME = "lol_live_kills_remaining.pkl"
CHAMPION_IMPACTS_JSON = "champion_impacts_lol.json"
CHAMPION_IMPACTS_CSV = "champion_impacts.csv"
CHECKPOINTS = [10, 15, 20, 25]
DRAFT_WEIGHT_MAX_MIN = 40


def _load_model():
    path = path_in_models(MODEL_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def _load_champion_impacts_full() -> dict[str, dict]:
    """Carrega os 4 impactos por campeão (como Dota). Prioridade: JSON. Fallback: CSV (só kills)."""
    jpath = path_in_data(CHAMPION_IMPACTS_JSON)
    if jpath and os.path.exists(jpath):
        try:
            with open(jpath, encoding="utf-8") as f:
                data = json.load(f)
            imp = data.get("champion_impacts", data)
            if isinstance(imp, dict):
                return imp
        except Exception:
            pass
    # Fallback: champion_impacts.csv (só kills)
    cpath = path_in_data(CHAMPION_IMPACTS_CSV)
    if cpath and os.path.exists(cpath):
        df = pd.read_csv(cpath)
        df.columns = df.columns.str.strip().str.lower()
        if "champion" in df.columns and "impact" in df.columns:
            agg = df.groupby("champion")["impact"].mean()
            return {
                str(c): {
                    "impact_kills": float(v),
                    "impact_duration": 0.0,
                    "impact_kpm": 0.0,
                    "impact_conversion": 0.0,
                }
                for c, v in agg.items()
            }
    return {}


def _draft_impacts_weighted(blue_champions: list[str], red_champions: list[str], minute: int) -> dict:
    """Soma os 4 impactos do draft com peso. weight = max(0, 1 - minute/40)."""
    impacts = _load_champion_impacts_full()
    weight = max(0.0, 1.0 - minute / DRAFT_WEIGHT_MAX_MIN)
    out = {"kills": 0.0, "duration": 0.0, "kpm": 0.0, "conversion": 0.0}
    for name in list(blue_champions or [])[:5] + list(red_champions or [])[:5]:
        n = str(name).strip() if name else ""
        if not n:
            continue
        data = impacts.get(n) or impacts.get(n.replace(" ", "")) or impacts.get(n.replace(".", ""))
        if isinstance(data, dict):
            out["kills"] += (data.get("impact_kills") or 0) * weight
            out["duration"] += (data.get("impact_duration") or 0) * weight
            out["kpm"] += (data.get("impact_kpm") or 0) * weight
            out["conversion"] += (data.get("impact_conversion") or 0) * weight
        elif isinstance(data, (int, float)):
            out["kills"] += float(data) * weight
    return out


def _sigma_for_minute(sigma_by_minute: dict, minute: int) -> float:
    best = min(CHECKPOINTS, key=lambda m: abs(m - minute))
    return sigma_by_minute.get(best, 5.0)


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


MU_CLAMP_MIN = 0
MU_CLAMP_MAX = 60


def predict(
    minute: int | float,
    kills_now: int | float,
    gold_diff_now: float,
    towers_total_alive: int = 22,
    baron_kills_so_far: int = 0,
    blue_champions: list[str] | None = None,
    red_champions: list[str] | None = None,
):
    """
    Predição para estado do jogo ao vivo LoL (sem torres/barons/dragons).
    Regime lento via slow_intensity. Retorna (mu, sigma, total_pred) ou (None, None, None).
    """
    data = _load_model()
    if data is None:
        return None, None, None

    draft = _draft_impacts_weighted(blue_champions, red_champions, int(minute))
    kpm_now = kills_now / minute if minute > 0 else 0

    m = max(1, int(minute))
    gold_per_min = gold_diff_now / m
    gold_log = math.copysign(math.log1p(abs(gold_diff_now)), gold_diff_now) if gold_diff_now != 0 else 0.0
    gold_pressure = abs(gold_diff_now) / m
    stomp_intensity = max(0.0, gold_pressure - 250)
    slow_intensity = max(0.0, 0.33 - kpm_now)

    feats = data["feature_cols"]
    sigma_by = data["sigma_by_minute"]

    row_dict = {
        "minute": float(minute),
        "kills_now": float(kills_now),
        "kpm_now": float(kpm_now),
        "gold_diff_now": float(gold_diff_now),
        "gold_per_min": gold_per_min,
        "gold_log": gold_log,
        "stomp_intensity": stomp_intensity,
        "slow_intensity": slow_intensity,
        "draft_kills_impact_weighted": float(draft["kills"]),
        "draft_duration_impact_weighted": float(draft["duration"]),
        "draft_kpm_impact_weighted": float(draft["kpm"]),
        "draft_conversion_impact_weighted": float(draft["conversion"]),
    }
    row = [row_dict.get(c, 0.0) for c in feats]

    import numpy as np
    X = np.array([row])
    pipeline = data.get("pipeline")
    if pipeline is not None:
        mu = float(pipeline.predict(X)[0])
    else:
        scaler = data["scaler"]
        model = data["model"]
        X_scaled = scaler.transform(X)
        mu = float(model.predict(X_scaled)[0])

    mu = max(MU_CLAMP_MIN, min(MU_CLAMP_MAX, mu))
    sigma = _sigma_for_minute(sigma_by, int(minute))
    total_pred = kills_now + mu
    return mu, sigma, total_pred


def prob_over(mu: float, sigma: float, line: float, kills_now: float) -> float:
    """P(kills_remaining >= needed). needed = ceil(line - kills_now)."""
    needed = math.ceil(line - kills_now)
    if sigma <= 0:
        return 0.5
    z = (needed - mu) / sigma
    return float(1.0 - _norm_cdf(z))


def line_fair(mu: float, kills_now: float) -> float:
    """Linha onde P(over) ≈ 0.5."""
    raw = kills_now + mu
    return round(raw * 2) / 2
