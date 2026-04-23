"""
Meta-modelo Full-Game: prevê vitória final usando draft prior + estado (gold @10, @15, @20).
Features: logit(p_draft), gold_diff_10, gold_diff_15, gold_diff_20. Apenas ligas MAJOR.
Requer draft prior calibrado (model_artifacts/draft_prior_calibrator.pkl).
"""
import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from core.shared.utils import MAJOR_LEAGUES

PARTICIPANT_ID = "participantid"
RESULT = "result"
PICK_COLS = ["pick1", "pick2", "pick3", "pick4", "pick5"]
GOLD_COLS = ["golddiffat10", "golddiffat15", "golddiffat20"]


def _find_oracle_csv():
    from core.lol.db_converter import find_latest_csv
    return find_latest_csv()


def _load_raw_csv(csv_path):
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    return df


def _logit(p):
    p = np.clip(float(p), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def build_full_game_dataset(csv_path, analyzer, calibrator_model_path=None):
    """
    Uma linha por jogo (perspectiva time 1). Apenas ligas MAJOR.
    Features: logit(p_draft), gold_diff_10, gold_diff_15, gold_diff_20.
    p_draft vem do calibrador (draft_delta -> prob). Target: win (time 1).
    Retorna (X, y, feature_names) ou (None, None, None, error_msg).
    """
    from core.lol.draft_prior import load_calibrator

    if csv_path is None:
        csv_path = _find_oracle_csv()
    if not csv_path or not os.path.exists(csv_path):
        return None, None, None, "CSV não encontrado."

    need = ["gameid", "teamname", "league", RESULT] + PICK_COLS + GOLD_COLS
    df = _load_raw_csv(csv_path)
    if not all(c in df.columns for c in ["gameid", "teamname", "league", RESULT]):
        return None, None, None, "CSV sem gameid/teamname/league/result."
    if not all(p in df.columns for p in PICK_COLS):
        return None, None, None, "CSV sem pick1..pick5."
    for g in GOLD_COLS:
        if g not in df.columns:
            return None, None, None, f"CSV sem {g}."

    if PARTICIPANT_ID in df.columns:
        team_rows = df[df[PARTICIPANT_ID].astype(int).isin([100, 200])]
        if len(team_rows) < 50:
            return None, None, None, "Poucas linhas de time (participantid 100/200)."
        df = team_rows.copy()

    calib, _ = load_calibrator(calibrator_model_path)
    if calib is None:
        return None, None, None, "Calibre o draft prior primeiro (aba Comparar Composições)."

    # Filtrar MAJOR
    df = df[df["league"].astype(str).str.upper().isin([lg.upper() for lg in MAJOR_LEAGUES])].copy()
    if len(df) < 50:
        return None, None, None, "Poucos jogos em ligas MAJOR."

    key_cols = ["gameid", "teamname"]
    team_df = df[[*key_cols, "league", RESULT] + PICK_COLS + GOLD_COLS].drop_duplicates(subset=key_cols, keep="first").copy()
    team_df["win"] = team_df[RESULT].astype(str).str.lower().isin(["1", "true", "win", "w"]).astype(int)

    rows = []
    for gameid, grp in team_df.groupby("gameid"):
        if len(grp) != 2:
            continue
        grp = grp.sort_values("teamname").reset_index(drop=True)
        row1 = grp.iloc[0]
        row2 = grp.iloc[1]
        comp1 = [str(row1[p]).strip() for p in PICK_COLS if pd.notna(row1.get(p))]
        comp2 = [str(row2[p]).strip() for p in PICK_COLS if pd.notna(row2.get(p))]
        if len(comp1) != 5 or len(comp2) != 5:
            continue
        league = row1.get("league") or "MAJOR"
        try:
            score1, _ = analyzer._calculate_team_score(league, comp1)
            score2, _ = analyzer._calculate_team_score(league, comp2)
        except Exception:
            continue
        draft_delta = score1 - score2
        p_draft = float(calib.predict_proba([[draft_delta]])[0, 1])
        logit_p = _logit(p_draft)
        g10 = pd.to_numeric(row1.get("golddiffat10"), errors="coerce")
        g15 = pd.to_numeric(row1.get("golddiffat15"), errors="coerce")
        g20 = pd.to_numeric(row1.get("golddiffat20"), errors="coerce")
        if pd.isna(g10) or pd.isna(g15) or pd.isna(g20):
            continue
        rows.append({
            "logit_p_draft": logit_p,
            "gold_diff_10": int(g10),
            "gold_diff_15": int(g15),
            "gold_diff_20": int(g20),
            "win": int(row1["win"]),
        })

    if len(rows) < 50:
        return None, None, None, "Poucos jogos com drafts e gold diffs válidos (mín. 50)."

    feature_names = ["logit_p_draft", "gold_diff_10", "gold_diff_15", "gold_diff_20"]
    X = np.array([[r["logit_p_draft"], r["gold_diff_10"], r["gold_diff_15"], r["gold_diff_20"]] for r in rows], dtype=np.float64)
    y = np.array([r["win"] for r in rows], dtype=np.int64)
    return X, y, feature_names, None


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


def train_and_save_model(csv_path=None, analyzer=None, calibrator_model_path=None, test_size=0.2, random_state=42, model_path=None):
    """
    Treina regressão logística full-game. Salva em model_artifacts/win_prob_full_game.pkl.
    Retorna dict com n_samples, brier_score, n_wins, n_losses, etc., ou {"error": "..."}.
    """
    from core.shared.paths import get_models_dir
    from core.lol.compare import LoLCompareAnalyzer

    if analyzer is None:
        analyzer = LoLCompareAnalyzer()
        if not analyzer.load_data():
            return {"error": "Dados do compare (champion/synergy/comp) não carregados."}
    if csv_path is None:
        csv_path = _find_oracle_csv()

    out = build_full_game_dataset(csv_path, analyzer, calibrator_model_path)
    X, y, feature_names, err = out[0], out[1], out[2], out[3]
    if X is None:
        return {"error": err or "Dataset não construído."}

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    model = LogisticRegression(max_iter=2000, random_state=random_state)
    model.fit(X_train, y_train)

    p_test = model.predict_proba(X_test)[:, 1]
    brier = _brier_score(y_test, p_test)
    acc = model.score(X_test, y_test)
    reliability = _reliability_bins(y_test, p_test)

    if model_path is None:
        model_path = os.path.join(get_models_dir(), "win_prob_full_game.pkl")
    Path(os.path.dirname(model_path)).mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_names": feature_names}, f)

    return {
        "n_samples": len(X),
        "train_accuracy": model.score(X_train, y_train),
        "test_accuracy": acc,
        "brier_score": brier,
        "reliability_bins": reliability,
        "n_wins": int(y.sum()),
        "n_losses": int(len(y) - y.sum()),
    }


def load_full_model(model_path=None):
    from core.shared.paths import get_models_dir
    if model_path is None:
        model_path = os.path.join(get_models_dir(), "win_prob_full_game.pkl")
    if not os.path.exists(model_path):
        return None, None
    with open(model_path, "rb") as f:
        data = pickle.load(f)
    return data["model"], data.get("feature_names", [])


def predict_win_prob(p_draft, gold_10, gold_15, gold_20, model_path=None):
    """
    p_draft: probabilidade pré-jogo do Time 1 (0..1), ex.: da aba Comparar (calibrada).
    gold_10, gold_15, gold_20: diferença de ouro Time 1 − Time 2 naquele minuto.
    Retorna P(vitória Time 1) no fim do jogo, ou None se modelo não existir.
    """
    model, feature_names = load_full_model(model_path)
    if model is None:
        return None
    logit_p = _logit(float(p_draft))
    X = np.array([[logit_p, int(gold_10), int(gold_15), int(gold_20)]], dtype=np.float64)
    return float(model.predict_proba(X)[0, 1])


class FullGameWinProbCalculator:
    """Calculadora de prob de vitória full-game (draft + gold @10/15/20)."""

    def __init__(self):
        self._model_path = None
        self._model = None
        self._feature_names = None

    def get_csv_path(self):
        return _find_oracle_csv()

    def ensure_model(self):
        self._model, self._feature_names = load_full_model(self._model_path)
        return self._model is not None

    def predict(self, p_draft, gold_10, gold_15, gold_20):
        if not self.ensure_model():
            return None
        return predict_win_prob(p_draft, gold_10, gold_15, gold_20, self._model_path)

    def train_and_save(self, csv_path=None, analyzer=None):
        return train_and_save_model(csv_path=csv_path, analyzer=analyzer, calibrator_model_path=self._model_path)

    def get_coefficients(self):
        if not self.ensure_model():
            return None
        names = self._feature_names or []
        coefs = self._model.coef_.ravel()
        return list(zip(names, coefs))
