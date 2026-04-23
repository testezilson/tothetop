"""
Modelo Live Dota: prevê kills_remaining e P(Over) para jogos ao vivo.

- draft_kills_impact: mesmo impacto da aba TESTE (hero_impacts_bayesian_single.pkl, testezudo, sem lado).
- draft_duration/kpm/conversion: hero_impacts.json (compute_hero_metrics_dota.py).
"""
import json
import math
import pickle
import os

from core.shared.paths import path_in_models, path_in_data

MODEL_FILENAME = "dota_live_kills_remaining.pkl"
HERO_IMPACTS_FILENAME = "hero_impacts.json"
# Impacto de kills = mesmo da aba TESTE (testezudo)
TESTEZUDO_DIR = os.path.join(os.path.expanduser("~"), "Documents", "testezudo")
CHECKPOINTS = [10, 15, 20, 25]
DRAFT_WEIGHT_MAX_MIN = 40


def _load_model():
    path = path_in_models(MODEL_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def _load_hero_impacts():
    """Impactos duration/kpm/conversion (hero_impacts.json)."""
    path = path_in_data(HERO_IMPACTS_FILENAME)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("hero_impacts", data)


def _load_bayesian_impacts():
    """Impactos de kills: apenas hero_impacts_bayesian_single.pkl (sem lado)."""
    path = os.path.join(TESTEZUDO_DIR, "hero_impacts_bayesian_single.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        data = pickle.load(f)
    if isinstance(data, dict) and "_meta" in data:
        data = {k: v for k, v in data.items() if k != "_meta"}
    return data


def _get_bayesian_impact_single(hero: str, impacts: dict) -> float:
    """Retorna o impacto do herói (hero_impacts_bayesian_single.pkl — um valor, sem lado)."""
    if not impacts:
        return 0.0
    hero_norm = hero.strip() if hero else ""
    if not hero_norm:
        return 0.0
    for name, entry in impacts.items():
        if name.lower() != hero_norm.lower() or not isinstance(entry, dict):
            continue
        return float(entry.get("impact", 0.0) or 0.0)
    return 0.0


def _draft_impacts_weighted(
    radiant_heroes: list[str], dire_heroes: list[str], minute: int
) -> dict:
    """
    Soma impactos do draft com peso. weight = max(0, 1 - minute/40).
    kills: um único impacto por herói (média Radiant/Dire, testezudo).
    duration/kpm/conversion: hero_impacts.json.
    """
    json_impacts = _load_hero_impacts()
    bayesian = _load_bayesian_impacts()
    weight = max(0.0, 1.0 - minute / DRAFT_WEIGHT_MAX_MIN)
    out = {"kills": 0.0, "duration": 0.0, "kpm": 0.0, "conversion": 0.0}

    rad = list(radiant_heroes or [])[:5]
    dire = list(dire_heroes or [])[:5]
    all_heroes = rad + dire

    for h in rad:
        name = str(h).strip() if h else ""
        out["kills"] += _get_bayesian_impact_single(name, bayesian or {}) * weight
    for h in dire:
        name = str(h).strip() if h else ""
        out["kills"] += _get_bayesian_impact_single(name, bayesian or {}) * weight

    for h in all_heroes:
        name = str(h).strip() if h else ""
        data = json_impacts.get(name, {})
        out["duration"] += (data.get("impact_duration") or 0) * weight
        out["kpm"] += (data.get("impact_kpm") or 0) * weight
        out["conversion"] += (data.get("impact_conversion") or 0) * weight

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
    roshan_kills_so_far: int = 0,
    radiant_heroes: list[str] | None = None,
    dire_heroes: list[str] | None = None,
):
    """
    Predição para estado do jogo ao vivo.
    Retorna (mu, sigma, total_pred) ou (None, None, None) se modelo indisponível.
    total_pred = kills_now + mu (total kills final estimado).
    mu é clampado em [0, 60] para evitar prob quebrada em stomps.
    Torres não são mais usadas como parâmetro; se o modelo tiver a feature, usamos valor fixo.
    """
    data = _load_model()
    if data is None:
        return None, None, None

    draft = _draft_impacts_weighted(
        list(radiant_heroes or []), list(dire_heroes or []), int(minute)
    )
    kpm_now = kills_now / minute if minute > 0 else 0

    # Gold contextual: gold_per_min, gold_log, stomp_intensity (regime terminal)
    m = max(1, int(minute))
    gold_per_min = gold_diff_now / m
    gold_log = math.copysign(math.log1p(abs(gold_diff_now)), gold_diff_now) if gold_diff_now != 0 else 0.0
    gold_pressure = abs(gold_diff_now) / m
    stomp_intensity = max(0.0, gold_pressure - 250)

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
        "towers_total_alive": 22.0,  # não usado: valor fixo para compatibilidade com pkl que ainda tem a feature
        "roshan_kills_so_far": int(roshan_kills_so_far),
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
