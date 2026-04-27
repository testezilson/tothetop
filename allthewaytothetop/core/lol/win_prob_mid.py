"""
Win Probability @20 e @25 min — só gold diff (snapshot naquele minuto).
Dois modelos separados: Model_20 e Model_25. Regressão logística, Brier/reliability no treino.
"""
import os
import pickle
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from pathlib import Path

RESULT = "result"
PARTICIPANT_ID = "participantid"
GOLD_DIFF_COL = "golddiffat{minute}"  # golddiffat20, golddiffat25


def _find_oracle_csv():
    from core.lol.db_converter import find_latest_csv
    return find_latest_csv()


def _load_raw_csv(csv_path):
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    return df


def build_dataset_at_minute(csv_path, minute):
    """
    Uma linha por (gameid, teamname). Feature: gold_diff @minute. Target: result.
    minute in (20, 25). Retorna (X, y, feature_names) ou (None, None, None).
    """
    if minute not in (20, 25):
        return None, None, None
    if csv_path is None:
        csv_path = _find_oracle_csv()
    if not csv_path or not os.path.exists(csv_path):
        return None, None, None

    df = _load_raw_csv(csv_path)
    col = f"golddiffat{minute}"
    if col not in df.columns or RESULT not in df.columns:
        return None, None, None

    if PARTICIPANT_ID in df.columns:
        team_rows = df[df[PARTICIPANT_ID].astype(int).isin([100, 200])]
        if len(team_rows) >= 50:
            df = team_rows.copy()

    key_cols = ["gameid", "teamname"]
    team_df = df[[*key_cols, col, RESULT]].drop_duplicates(subset=key_cols, keep="first").copy()

    result_raw = team_df[RESULT]
    if result_raw.dtype == object or result_raw.dtype.name == "bool":
        team_df["win"] = result_raw.astype(str).str.lower().isin(["1", "true", "win", "w"]).astype(int)
    else:
        team_df["win"] = (result_raw.astype(float) >= 0.5).astype(int)

    team_df["gold_diff"] = pd.to_numeric(team_df[col], errors="coerce").fillna(0).astype(int)
    feature_name = f"gold_diff_{minute}"
    X = team_df[["gold_diff"]].rename(columns={"gold_diff": feature_name})
    y = team_df["win"].values
    mask = ~(X.isna().any(axis=1))
    X = X[mask].values.astype(np.float64)
    y = y[mask]
    return X, y, [feature_name]


def _brier_score(y_true, y_pred_proba):
    return float(np.mean((np.asarray(y_true, dtype=np.float64) - np.asarray(y_pred_proba, dtype=np.float64)) ** 2))


def _reliability_bins(y_true, y_pred_proba, n_bins=10):
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


def train_and_save_model(csv_path, minute, test_size=0.2, random_state=42, model_path=None):
    """
    Treina modelo para o minuto (20 ou 25). Salva .pkl em model_artifacts.
    Retorna (model, feature_names, metrics_dict) com n_wins, n_losses, brier_score, reliability_bins.
    """
    from core.shared.paths import get_models_dir

    X, y, feature_names = build_dataset_at_minute(csv_path, minute)
    if X is None or len(X) < 50:
        return None, None, {"error": "Dados insuficientes ou CSV sem golddiffat" + str(minute) + "."}

    n_wins = int(np.sum(y))
    n_losses = int(len(y) - n_wins)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    model = LogisticRegression(max_iter=1000, random_state=random_state)
    model.fit(X_train, y_train)

    train_acc = model.score(X_train, y_train)
    test_acc = model.score(X_test, y_test)
    try:
        from sklearn.metrics import roc_auc_score
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
        model_path = os.path.join(get_models_dir(), f"win_prob_{minute}.pkl")
    Path(os.path.dirname(model_path)).mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_names": feature_names}, f)

    return model, feature_names, metrics


def load_model(minute, model_path=None):
    from core.shared.paths import get_models_dir
    if model_path is None:
        model_path = os.path.join(get_models_dir(), f"win_prob_{minute}.pkl")
    if not os.path.exists(model_path):
        return None, None
    with open(model_path, "rb") as f:
        data = pickle.load(f)
    return data["model"], data["feature_names"]


def predict_win_prob(minute, gold_diff, model_path=None):
    """Prediz P(vitória) dado gold diff naquele minuto. Retorna float [0,1] ou None."""
    model, names = load_model(minute, model_path)
    if model is None:
        return None
    X = np.array([[float(gold_diff)]], dtype=np.float64)
    return float(model.predict_proba(X)[0, 1])


class WinProbMidCalculator:
    """Calculadora Win Prob @20 ou @25 (só gold diff)."""

    def __init__(self, minute):
        assert minute in (20, 25)
        self.minute = minute
        self.model = None
        self.feature_names = None
        self._model_path = None

    def get_csv_path(self):
        return _find_oracle_csv()

    def _model_path_default(self):
        from core.shared.paths import get_models_dir
        return os.path.join(get_models_dir(), f"win_prob_{self.minute}.pkl")

    def ensure_model(self, force_retrain=False):
        self._model_path = self._model_path_default()
        if not force_retrain and os.path.exists(self._model_path):
            self.model, self.feature_names = load_model(self.minute, self._model_path)
            return self.model is not None
        csv_path = self.get_csv_path()
        if not csv_path or not os.path.exists(csv_path):
            return False
        model, names, _ = train_and_save_model(csv_path, self.minute, model_path=self._model_path)
        if model is None:
            return False
        self.model = model
        self.feature_names = names
        return True

    def predict(self, gold_diff):
        if not self.ensure_model():
            return None
        return predict_win_prob(self.minute, gold_diff, self._model_path)

    def train_and_save(self):
        csv_path = self.get_csv_path()
        if not csv_path or not os.path.exists(csv_path):
            return {"error": "CSV do Oracle não encontrado."}
        _, _, metrics = train_and_save_model(csv_path, self.minute, model_path=self._model_path_default())
        self.model, self.feature_names = load_model(self.minute, self._model_path_default())
        return metrics

    def get_coefficients(self):
        if not self.ensure_model() or self.model is None or self.feature_names is None:
            return []
        return list(zip(self.feature_names, self.model.coef_[0].tolist()))
