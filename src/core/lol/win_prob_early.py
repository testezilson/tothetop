"""
Early-Game Win Probability Calculator (até 15 min).
Baseado nos artigos Oracle's Elixir (Early-Game Rating 2.0 e What Are the Odds).
Features: gold_diff@15, first_tower, first_dragon (sem first_herald nem first_to_three_towers).
"""
import os
import pickle
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from pathlib import Path

# Colunas do CSV Oracle's Elixir
GOLD_DIFF_15 = "golddiffat15"
FIRST_TOWER = "firsttower"
FIRST_DRAGON = "firstdragon"
RESULT = "result"
PARTICIPANT_ID = "participantid"


def _find_oracle_csv():
    """Encontra o CSV mais recente do Oracle (db2026 ou data/)."""
    from core.lol.db_converter import find_latest_csv
    return find_latest_csv()


def _load_raw_csv(csv_path):
    """Carrega CSV e normaliza colunas."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    return df


def build_early_game_dataset(csv_path=None):
    """
    Monta dataset para early-game: uma linha por time por jogo.
    Features: gold_diff_15, first_tower, first_dragon (sem herald nem first to 3 towers).
    Target: result (1=vitória, 0=derrota).
    """
    if csv_path is None:
        csv_path = _find_oracle_csv()
    if not csv_path or not os.path.exists(csv_path):
        return None, None

    df = _load_raw_csv(csv_path)

    if PARTICIPANT_ID in df.columns:
        team_rows = df[df[PARTICIPANT_ID].astype(int).isin([100, 200])]
        if len(team_rows) >= 50:
            df = team_rows.copy()

    key_cols = ["gameid", "teamname"]
    need = [GOLD_DIFF_15, FIRST_TOWER, FIRST_DRAGON, RESULT]
    if GOLD_DIFF_15 not in df.columns or RESULT not in df.columns:
        return None, None
    need = [c for c in need if c in df.columns]

    subset = key_cols + need
    team_df = df[subset].drop_duplicates(subset=key_cols, keep="first").copy()

    result_raw = team_df[RESULT]
    if result_raw.dtype == object or result_raw.dtype.name == "bool":
        team_df["win"] = result_raw.astype(str).str.lower().isin(["1", "true", "win", "w"]).astype(int)
    else:
        team_df["win"] = (result_raw.astype(float) >= 0.5).astype(int)

    team_df["gold_diff_15"] = pd.to_numeric(team_df[GOLD_DIFF_15], errors="coerce").fillna(0).astype(int)
    for col, name in [(FIRST_TOWER, "first_tower"), (FIRST_DRAGON, "first_dragon")]:
        if col in team_df.columns:
            team_df[name] = (pd.to_numeric(team_df[col], errors="coerce").fillna(0) > 0).astype(int)
        else:
            team_df[name] = 0

    feature_cols = ["gold_diff_15", "first_tower", "first_dragon"]
    X = team_df[feature_cols].copy()
    y = team_df["win"].values

    mask = ~(X.isna().any(axis=1))
    X = X[mask].values.astype(np.float64)
    y = y[mask]
    return X, y, feature_cols


def _brier_score(y_true, y_pred_proba):
    """Brier score = mean((y_true - p)^2). Quanto menor, mais calibrado."""
    return float(np.mean((np.asarray(y_true, dtype=np.float64) - np.asarray(y_pred_proba, dtype=np.float64)) ** 2))


def _reliability_bins(y_true, y_pred_proba, n_bins=10):
    """Retorna lista de (bin_center, mean_pred, mean_actual, count) para reliability diagram."""
    y_true = np.asarray(y_true)
    y_pred_proba = np.asarray(y_pred_proba)
    bins = np.linspace(0, 1, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_pred_proba >= lo) & (y_pred_proba < hi) if i < n_bins - 1 else (y_pred_proba >= lo) & (y_pred_proba <= hi)
        if mask.sum() == 0:
            continue
        mean_pred = float(y_pred_proba[mask].mean())
        mean_actual = float(y_true[mask].mean())
        out.append((float((lo + hi) / 2), mean_pred, mean_actual, int(mask.sum())))
    return out


def train_and_save_model(csv_path=None, test_size=0.2, random_state=42, model_path=None):
    """
    Treina regressão logística e salva o modelo em model_artifacts.
    Retorna (model, feature_names, metrics_dict). metrics inclui n_wins, n_losses, brier_score, reliability_bins.
    """
    from core.shared.paths import get_models_dir

    X, y, feature_names = build_early_game_dataset(csv_path)
    if X is None or len(X) < 50:
        return None, None, {"error": "Dados insuficientes ou CSV não encontrado."}

    n_wins = int(np.sum(y))
    n_losses = int(len(y) - n_wins)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    model = LogisticRegression(max_iter=1000, random_state=random_state)
    model.fit(X_train, y_train)

    train_acc = model.score(X_train, y_train)
    test_acc = model.score(X_test, y_test)
    from sklearn.metrics import roc_auc_score
    try:
        auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    except Exception:
        auc = 0.0

    p_test = model.predict_proba(X_test)[:, 1]
    brier = _brier_score(y_test, p_test)
    reliability = _reliability_bins(y_test, p_test, n_bins=10)

    metrics = {
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "roc_auc": auc,
        "n_samples": len(X),
        "n_wins": n_wins,
        "n_losses": n_losses,
        "brier_score": brier,
        "reliability_bins": reliability,
    }

    if model_path is None:
        model_path = os.path.join(get_models_dir(), "win_prob_early_game.pkl")
    Path(os.path.dirname(model_path)).mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_names": feature_names}, f)

    return model, feature_names, metrics


def load_model(model_path=None):
    """Carrega modelo salvo. Retorna (model, feature_names) ou (None, None)."""
    from core.shared.paths import get_models_dir

    if model_path is None:
        model_path = os.path.join(get_models_dir(), "win_prob_early_game.pkl")
    if not os.path.exists(model_path):
        return None, None
    with open(model_path, "rb") as f:
        data = pickle.load(f)
    return data["model"], data["feature_names"]


def predict_win_prob(gold_diff_15, first_tower=0, first_dragon=0, model_path=None):
    """
    Prediz P(vitória) para o time (perspectiva Time 1).
    first_tower / first_dragon: 1 se este time, 0 caso contrário.
    Retorna float em [0, 1] ou None se modelo não carregar.
    """
    model, names = load_model(model_path)
    if model is None:
        return None
    X = np.array([[gold_diff_15, first_tower, first_dragon]], dtype=np.float64)
    proba = model.predict_proba(X)[0, 1]
    return float(proba)


class EarlyGameWinProbCalculator:
    """
    Calculadora de probabilidade de vitória no early game.
    Usa CSV do Oracle para treinar e modelo salvo em model_artifacts.
    """

    def __init__(self):
        self.model = None
        self.feature_names = None
        self._model_path = None

    def get_csv_path(self):
        return _find_oracle_csv()

    def ensure_model(self, force_retrain=False):
        """Carrega modelo existente ou treina e salva. Retorna True se pronto."""
        from core.shared.paths import get_models_dir
        self._model_path = os.path.join(get_models_dir(), "win_prob_early_game.pkl")

        if not force_retrain and os.path.exists(self._model_path):
            self.model, self.feature_names = load_model(self._model_path)
            return self.model is not None

        csv_path = self.get_csv_path()
        if not csv_path or not os.path.exists(csv_path):
            return False
        model, names, _ = train_and_save_model(csv_path=csv_path, model_path=self._model_path)
        if model is None:
            return False
        self.model = model
        self.feature_names = names
        return True

    def predict(self, gold_diff_15, first_tower=0, first_dragon=0):
        """Retorna P(vitória) em [0, 1] ou None."""
        if not self.ensure_model():
            return None
        return predict_win_prob(gold_diff_15, first_tower, first_dragon, self._model_path)

    def train_and_save(self):
        """Força novo treino e salva. Retorna dict de métricas ou erro."""
        csv_path = self.get_csv_path()
        if not csv_path or not os.path.exists(csv_path):
            return {"error": "CSV do Oracle não encontrado."}
        _, _, metrics = train_and_save_model(csv_path=csv_path, model_path=self._model_path)
        self.model, self.feature_names = load_model(self._model_path)
        return metrics

    def get_coefficients(self):
        """
        Retorna os coeficientes da regressão logística (interpretação: positivo = mais associado a vitória).
        Retorna list of (feature_name, coefficient) ou [] se modelo não carregado.
        """
        if not self.ensure_model() or self.model is None or self.feature_names is None:
            return []
        coef = self.model.coef_[0]
        return list(zip(self.feature_names, coef.tolist()))
