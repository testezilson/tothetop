"""
Over/Under ao vivo: estima P(Over) / P(Under) para linhas de kills usando estado do jogo.

Prioridade 1: buckets empíricos (λ condicionado ao ritmo: jogos com poucas kills até t
têm média de kills restantes menor). Evita "regressão à média" que inflava λ em jogos lentos.
Prioridade 2: modelo Poisson (fallback).
Moduladores: gold_diff (leve, condicionado) e draft_multiplier.
"""
from __future__ import annotations

import math
import os
import pickle
import numpy as np
from scipy import stats

try:
    from core.shared.paths import path_in_models
except ImportError:
    def path_in_models(name):
        return os.path.join(os.path.dirname(__file__), "..", "..", "..", "model_artifacts", name)

# Artefatos (prioridade: tabelas conjuntas > buckets > Poisson)
TABLES_NAME = "live_ou_tables.pkl"
BUCKETS_NAME = "live_ou_buckets.pkl"
MODEL_NAME = "live_ou_poisson_model.pkl"
SCALER_NAME = "live_ou_scaler.pkl"
FEATURE_COLS_NAME = "live_ou_feature_columns.pkl"
MEAN_KILLS_NAME = "live_ou_mean_kills.pkl"

CHECKPOINTS = [10, 15, 20, 25]
DRAFT_MULTIPLIER_CAP = (0.8, 1.2)
# Gold diff: modulador leve. Em jogos lentos (kpm < 0.6) NÃO aplicar — gold não acelera jogo morto.
GOLD_DIFF_SCALE = 3000.0
GOLD_DIFF_ALPHA = 0.05
KPM_GOLD_THRESHOLD = 0.6  # abaixo disso gold_alpha = 0
# Draft: NÃO cria ritmo. Abaixo de 0.5 kpm = zero influência (mult 1.0).
KPM_LOW_THRESHOLD = 0.5   # abaixo disso: draft não aplicado (mult = 1.0)
KPM_HIGH_THRESHOLD = 0.9  # acima disso: draft completo ±20%
DRAFT_CAP_LOW = 0.05
DRAFT_CAP_HIGH = 0.20
# Cap absoluto + cap contextual por ritmo (cap "mole": não esmaga jogos lentos early/mid)
LAM_RESTANTES_CAP = 25.0
MINUTES_LEFT_BASE = 33  # estimativa duração típica para cap contextual
KPM_CAP_FACTOR = 1.3    # lam_cap = minutes_left * kpm_eff * KPM_CAP_FACTOR
# Ritmo mínimo por checkpoint: mesmo jogos lentos têm baseline de fights (evita λ colado em 0)
KPM_FLOOR_BY_CHECKPOINT = {10: 0.45, 15: 0.50, 20: 0.55, 25: 0.60}
# NegBin: dispersão por checkpoint (menor k = mais cauda; evita P(Over)=0% rígido em estados lentos)
K_NEGBIN_BY_CHECKPOINT = {10: 3, 15: 4, 20: 6, 25: 8}
# Draft -> duração: só atua em 10/15 min; ajusta minutes_left (horizonte), não λ. Clamp ±10%.
DRAFT_LENGTH_ARTIFACT = "draft_length_buckets.pkl"
TIME_MULTIPLIER_CLAMP = (0.9, 1.1)
CHECKPOINTS_DRAFT_LENGTH = (10, 15)  # draft só ajusta tempo nesses checkpoints


def _select_checkpoint(minute: float) -> int:
    """
    Checkpoint pelo tempo decorrido (floor). Nunca usar informação "do futuro":
    aos 20:08 usamos tabela @20, não @25 (que assume jogo mais desenvolvido e infla λ).
    """
    if minute >= 25:
        return 25
    if minute >= 20:
        return 20
    if minute >= 15:
        return 15
    return 10


def _bucket_index(value: float, edges: list) -> int:
    """Índice do bucket: edges[i] <= value < edges[i+1]."""
    for i in range(len(edges) - 1):
        if edges[i] <= value < edges[i + 1]:
            return i
    return max(0, len(edges) - 2)


def _lambda_from_tables(tables: dict, checkpoint: int, kills_now: float, gold_diff: float) -> float | None:
    """
    Lookup em E[kills_remaining | kills_bucket, gold_bucket].
    Backoff hierárquico: célula (n>=20) -> row_means (só kills) -> checkpoint_mean.
    """
    if checkpoint not in tables:
        return None
    data = tables[checkpoint]
    kill_edges = data["kill_edges"]
    gold_edges = data["gold_edges"]
    table = data["table"]
    row_means = data.get("row_means")
    checkpoint_mean = data.get("checkpoint_mean")
    i = _bucket_index(float(kills_now), kill_edges)
    j = _bucket_index(float(gold_diff), gold_edges)
    i = min(i, len(table) - 1)
    j = min(j, len(table[0]) - 1)
    cell = table[i][j]
    if cell is not None and cell.get("n", 0) >= 20:
        return max(0.1, float(cell["mean_remaining"]))
    if row_means and 0 <= i < len(row_means):
        return max(0.1, float(row_means[i]))
    if checkpoint_mean is not None:
        return max(0.1, float(checkpoint_mean))
    return None


def _lambda_from_buckets(buckets: dict, checkpoint: int, kills_now: float) -> float | None:
    """Fallback: buckets só por kills (sem gold)."""
    if checkpoint not in buckets:
        return None
    data = buckets[checkpoint]
    edges = data["edges"]
    means = data["means"]
    idx = _bucket_index(float(kills_now), edges)
    idx = min(idx, len(means) - 1)
    return max(0.1, float(means[idx]))


class LiveOverUnderPredictor:
    """
    λ_base condicionado ao ritmo (buckets) quando disponível; senão Poisson.
    Moduladores: gold_diff (leve) e draft_multiplier. Nunca criam ritmo do zero.
    """

    def __init__(self, models_dir: str | None = None):
        self._models_dir = models_dir
        self._tables = None
        self._buckets = None
        self._model = None
        self._scaler = None
        self._feature_cols = None
        self._mean_kills = 28.0
        self._loaded = False

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return True
        base = self._models_dir or os.path.dirname(path_in_models(""))
        if self._models_dir:
            tables_path = os.path.join(self._models_dir, TABLES_NAME)
            buckets_path = os.path.join(self._models_dir, BUCKETS_NAME)
            model_path = os.path.join(self._models_dir, MODEL_NAME)
            scaler_path = os.path.join(self._models_dir, SCALER_NAME)
            feat_path = os.path.join(self._models_dir, FEATURE_COLS_NAME)
            mean_path = os.path.join(self._models_dir, MEAN_KILLS_NAME)
        else:
            tables_path = path_in_models(TABLES_NAME)
            buckets_path = path_in_models(BUCKETS_NAME)
            model_path = path_in_models(MODEL_NAME)
            scaler_path = path_in_models(SCALER_NAME)
            feat_path = path_in_models(FEATURE_COLS_NAME)
            mean_path = path_in_models(MEAN_KILLS_NAME)
        try:
            if os.path.exists(tables_path):
                with open(tables_path, "rb") as f:
                    self._tables = pickle.load(f)
            if os.path.exists(buckets_path):
                with open(buckets_path, "rb") as f:
                    self._buckets = pickle.load(f)
            if os.path.exists(model_path):
                with open(model_path, "rb") as f:
                    self._model = pickle.load(f)
                with open(scaler_path, "rb") as f:
                    self._scaler = pickle.load(f)
                with open(feat_path, "rb") as f:
                    self._feature_cols = pickle.load(f)
            if os.path.exists(mean_path):
                with open(mean_path, "rb") as f:
                    self._mean_kills = float(pickle.load(f))
            self._loaded = True
            return self._tables is not None or self._buckets is not None or self._model is not None
        except Exception:
            return False

    def is_available(self) -> bool:
        return self._ensure_loaded()

    def predict_lambda(
        self,
        minute: float,
        kills_now: int | float,
        gold_diff: float,
        draft_multiplier: float | None = None,
        time_multiplier_from_draft: float | None = None,
    ) -> float:
        """
        λ_base condicionado ao ritmo (bucket de kills_now no checkpoint).
        Depois: modulador leve de gold_diff; draft_multiplier (kills).
        Draft -> duração: time_multiplier_from_draft só ajusta minutes_left em checkpoint 10/15 (clamp 0.9–1.1).
        """
        if not self._ensure_loaded():
            return 10.0  # fallback
        kills_now = float(kills_now)
        gold_diff = float(np.clip(gold_diff, -15_000, 15_000))
        kpm = kills_now / minute if minute > 0 else 0

        # Checkpoint por floor: 20:08 -> 20, nunca 25 (evita usar info "do futuro")
        checkpoint = _select_checkpoint(minute)

        # 1) λ_base: tabelas (kills+gold) > buckets (só kills) > Poisson
        lam_base = None
        if self._tables:
            lam_base = _lambda_from_tables(self._tables, checkpoint, kills_now, gold_diff)
        if lam_base is None and self._buckets:
            lam_base = _lambda_from_buckets(self._buckets, checkpoint, kills_now)
        if lam_base is None and self._model is not None and self._scaler is not None:
            X = np.array([[float(checkpoint), kills_now, kpm, gold_diff]])
            X = self._scaler.transform(X)
            lam_base = float(self._model.predict(X)[0])
        if lam_base is None:
            lam_base = 10.0
        lam_base = max(0.1, lam_base)

        # 2) Gold diff: só modula em jogos já rápidos. Em jogo morto (kpm < 0.6) gold NÃO acelera.
        gold_alpha = 0.0 if kpm < KPM_GOLD_THRESHOLD else GOLD_DIFF_ALPHA
        lam = lam_base * (1.0 + gold_alpha * np.tanh(gold_diff / GOLD_DIFF_SCALE))

        # 3) Draft: NÃO cria ritmo. kpm < 0.5 -> zero influência (mult = 1.0).
        if kpm < KPM_LOW_THRESHOLD:
            pass  # lam unchanged
        elif draft_multiplier is not None:
            mult = np.clip(float(draft_multiplier), DRAFT_MULTIPLIER_CAP[0], DRAFT_MULTIPLIER_CAP[1])
            if kpm < KPM_HIGH_THRESHOLD:
                frac = (kpm - KPM_LOW_THRESHOLD) / (KPM_HIGH_THRESHOLD - KPM_LOW_THRESHOLD)
                cap = DRAFT_CAP_LOW + frac * (DRAFT_CAP_HIGH - DRAFT_CAP_LOW)
                mult = 1.0 + np.clip(mult - 1.0, -cap, cap)
            lam = lam * mult

        # 4) Cap contextual "mole": kpm_eff = max(kpm, floor); draft só ajusta horizonte em 10/15
        minutes_left = max(5, MINUTES_LEFT_BASE - minute)
        if (
            time_multiplier_from_draft is not None
            and checkpoint in CHECKPOINTS_DRAFT_LENGTH
        ):
            mult = np.clip(float(time_multiplier_from_draft), TIME_MULTIPLIER_CLAMP[0], TIME_MULTIPLIER_CLAMP[1])
            minutes_left = max(5.0, minutes_left * mult)
        kpm_floor = KPM_FLOOR_BY_CHECKPOINT.get(checkpoint, 0.5)
        kpm_eff = max(kpm, kpm_floor)
        lam_cap_by_kpm = minutes_left * kpm_eff * KPM_CAP_FACTOR
        lam = min(float(lam), lam_cap_by_kpm, LAM_RESTANTES_CAP)
        return max(0.1, lam)

    def prob_over_under(
        self,
        kills_now: float,
        line: float,
        lam: float,
    ) -> tuple[float, float]:
        """
        λ = expectativa de KILLS RESTANTES. Para linha 28.5 e kills_now 7:
        needed = ceil(28.5 - 7) = 22 kills ainda para Over.
        P(Over) = P(K_future >= needed) = 1 - PoissonCDF(needed - 1; lam)
        """
        needed_float = line - kills_now
        if needed_float <= 0:
            return 1.0, 0.0  # já passou da linha, Over certo
        needed = int(math.ceil(needed_float))
        # P(K_future >= needed) = 1 - P(K_future <= needed - 1)
        p_at_most = stats.poisson.cdf(needed - 1, lam)
        p_over = 1.0 - p_at_most
        p_under = 1.0 - p_over
        return max(0.0, min(1.0, p_over)), max(0.0, min(1.0, p_under))

    def prob_over_under_nb(
        self,
        kills_now: float,
        line: float,
        lam: float,
        k: int | float,
    ) -> tuple[float, float]:
        """
        P(Over)/P(Under) com Negative Binomial (overdispersion): Var = λ + λ²/k.
        Evita "0.0% Over" rígido em estados lentos; cauda mais gorda sem mudar λ.
        scipy: nbinom(n, p) com média λ => n=k, p=k/(k+λ).
        """
        needed_float = line - kills_now
        if needed_float <= 0:
            return 1.0, 0.0
        needed = int(math.ceil(needed_float))
        lam_safe = max(lam, 1e-6)
        k_f = float(k)
        p_nb = k_f / (k_f + lam_safe)
        # P(K_future >= needed) = 1 - P(K_future <= needed - 1)
        p_at_most = stats.nbinom.cdf(needed - 1, k_f, p_nb)
        p_over = 1.0 - p_at_most
        p_under = 1.0 - p_over
        return max(0.0, min(1.0, p_over)), max(0.0, min(1.0, p_under))


def _scaling_score(champ: str, scores_dict: dict) -> float:
    if not champ or (isinstance(champ, float) and np.isnan(champ)):
        return 0.5
    key = str(champ).strip().lower()
    return scores_dict.get(key, 0.5)


def get_time_multiplier_from_draft(
    team1_champs: list[str],
    team2_champs: list[str],
    models_dir: str | None = None,
) -> float:
    """
    Multiplicador de horizonte temporal (minutes_left) a partir do draft.
    Retorna valor em [0.9, 1.1]. Só deve ser usado em checkpoint 10 ou 15.
    Se o artefato não existir, retorna 1.0.
    """
    path = os.path.join(models_dir, DRAFT_LENGTH_ARTIFACT) if models_dir else path_in_models(DRAFT_LENGTH_ARTIFACT)
    if not path or not os.path.exists(path):
        return 1.0
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
    except Exception:
        return 1.0
    scores = data.get("scaling_scores") or {}
    edges = data.get("bucket_edges", [0.0, 0.4, 0.6, 1.01])
    bucket_means = data.get("bucket_means") or {}
    global_mean = data.get("global_mean") or 33.0
    all_champs = (list(team1_champs)[:5] + list(team2_champs)[:5])[:10]
    if len(all_champs) < 10:
        return 1.0
    scaling_mean = float(np.mean([_scaling_score(c, scores) for c in all_champs]))
    idx = len(edges) - 2
    for i in range(len(edges) - 1):
        if edges[i] <= scaling_mean < edges[i + 1]:
            idx = i
            break
    predicted = bucket_means.get(idx, global_mean)
    mult = predicted / global_mean
    return float(np.clip(mult, TIME_MULTIPLIER_CLAMP[0], TIME_MULTIPLIER_CLAMP[1]))


def draft_multiplier_from_estimated_kills(kills_estimados_draft: float, mean_league_kills: float) -> float:
    """
    Recomendado: usar kills do seu modelo de draft e média da liga.
    draft_multiplier = kills_estimados_draft / mean_league_kills, limitado em [0.8, 1.2].
    """
    if mean_league_kills <= 0:
        return 1.0
    mult = kills_estimados_draft / mean_league_kills
    return float(np.clip(mult, DRAFT_MULTIPLIER_CAP[0], DRAFT_MULTIPLIER_CAP[1]))
