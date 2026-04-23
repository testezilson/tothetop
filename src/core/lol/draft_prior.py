"""
Draft Prior calibrado: transforma o score do compare_compositions em probabilidade real
via regressão logística em histórico (p_draft = σ(a·draft_delta + b)).
Inclui combinação com estado do jogo (early) via log-odds: p_final = σ(w·L(p_draft) + (1-w)·L(p_state)).
"""
import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

PARTICIPANT_ID = "participantid"
RESULT = "result"
PICK_COLS = ["pick1", "pick2", "pick3", "pick4", "pick5"]


def _find_oracle_csv():
    from core.lol.db_converter import find_latest_csv
    return find_latest_csv()


def _load_raw_csv(csv_path):
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    return df


def build_calibration_dataset(csv_path, analyzer, league_default="MAJOR"):
    """
    Para cada jogo no CSV: obtém (league, comp1, comp2, result_team1).
    Usa o analyzer para calcular score1, score2; draft_delta = score1 - score2 (perspectiva do time 1).
    Retorna (X, y) com X = draft_delta (uma coluna), y = 1 se time 1 venceu, 0 senão.
    """
    if csv_path is None:
        csv_path = _find_oracle_csv()
    if not csv_path or not os.path.exists(csv_path):
        return None, None

    df = _load_raw_csv(csv_path)
    need = ["gameid", "teamname", "league", RESULT] + [c for c in PICK_COLS if c in df.columns]
    if not all(c in df.columns for c in ["gameid", "teamname", "league", RESULT]):
        return None, None
    if not all(p in df.columns for p in PICK_COLS):
        return None, None

    # Uma linha por time por jogo (participantid 100/200 ou primeira de cada time)
    if PARTICIPANT_ID in df.columns:
        team_rows = df[df[PARTICIPANT_ID].astype(int).isin([100, 200])]
        if len(team_rows) >= 50:
            df = team_rows.copy()
    key_cols = ["gameid", "teamname"]
    team_df = df[need].drop_duplicates(subset=key_cols, keep="first").copy()

    # Resultado: 1 se este time ganhou
    res = team_df[RESULT].astype(str).str.lower()
    team_df["win"] = res.isin(["1", "true", "win", "w"]).astype(int)

    # Por jogo: dois times, ordem estável (ex.: por teamname)
    draft_deltas = []
    wins = []
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
        league = row1.get("league") or league_default
        if isinstance(league, str) and league.upper() == "MAJOR":
            league = "MAJOR"
        try:
            score1, _ = analyzer._calculate_team_score(league, comp1)
            score2, _ = analyzer._calculate_team_score(league, comp2)
        except Exception:
            continue
        draft_delta = score1 - score2
        draft_deltas.append(draft_delta)
        wins.append(int(row1["win"]))

    if len(draft_deltas) < 50:
        return None, None
    X = np.array(draft_deltas, dtype=np.float64).reshape(-1, 1)
    y = np.array(wins, dtype=np.int64)
    return X, y


def train_calibrator(csv_path=None, analyzer=None, test_size=0.2, random_state=42, model_path=None):
    """
    Treina regressão logística: win ~ draft_delta. Salva em model_artifacts/draft_prior_calibrator.pkl.
    Retorna dict com n_samples, brier_score (no teste), etc.
    """
    from core.shared.paths import get_models_dir
    from core.lol.compare import LoLCompareAnalyzer

    if analyzer is None:
        analyzer = LoLCompareAnalyzer()
        if not analyzer.load_data():
            return {"error": "Dados do compare (champion/synergy/comp winrates) não carregados."}
    if csv_path is None:
        csv_path = _find_oracle_csv()

    X, y = build_calibration_dataset(csv_path, analyzer)
    if X is None or len(X) < 50:
        return {"error": "Poucos jogos com drafts válidos para calibração."}

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    model = LogisticRegression(max_iter=1000, random_state=random_state)
    model.fit(X_train, y_train)

    p_test = model.predict_proba(X_test)[:, 1]
    brier = float(np.mean((np.asarray(y_test, dtype=np.float64) - p_test) ** 2))
    acc = model.score(X_test, y_test)

    if model_path is None:
        model_path = os.path.join(get_models_dir(), "draft_prior_calibrator.pkl")
    Path(os.path.dirname(model_path)).mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_name": "draft_delta"}, f)

    return {
        "n_samples": len(X),
        "test_accuracy": acc,
        "brier_score": brier,
        "n_wins": int(y.sum()),
        "n_losses": int(len(y) - y.sum()),
    }


def load_calibrator(model_path=None):
    """Carrega o modelo de calibração. Retorna (model, None) ou (None, None)."""
    from core.shared.paths import get_models_dir
    if model_path is None:
        model_path = os.path.join(get_models_dir(), "draft_prior_calibrator.pkl")
    if not os.path.exists(model_path):
        return None, None
    with open(model_path, "rb") as f:
        data = pickle.load(f)
    return data["model"], data.get("feature_name", "draft_delta")


def calibrated_draft_prob(score1, score2, model_path=None):
    """
    Probabilidade de vitória do time 1 (o que tem score1) dado o score do compare.
    p_draft = σ(a·draft_delta + b) com (a,b) calibrados em histórico.
    Retorna float em [0, 1] ou None se calibrator não existir.
    """
    model, _ = load_calibrator(model_path)
    if model is None:
        return None
    draft_delta = float(score1 - score2)
    return float(model.predict_proba([[draft_delta]])[0, 1])


def logit(p):
    """Log-odds: log(p/(1-p)). Evita log(0)."""
    p = np.clip(float(p), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def sigmoid(z):
    """1 / (1 + exp(-z))."""
    return float(1.0 / (1.0 + np.exp(-float(z))))


def combine_log_odds(p_draft, p_state, w=0.2):
    """
    Combina prior do draft com prob do estado (early) via log-odds.
    L_final = w * L(p_draft) + (1-w) * L(p_state),  p_final = σ(L_final).
    w=1 → só draft; w=0 → só estado. Para @15 min sugere-se w ~ 0.2.
    """
    p_draft = np.clip(float(p_draft), 1e-6, 1 - 1e-6)
    p_state = np.clip(float(p_state), 1e-6, 1 - 1e-6)
    L_draft = logit(p_draft)
    L_state = logit(p_state)
    L_final = w * L_draft + (1 - w) * L_state
    return sigmoid(L_final)


def weight_for_minute(minute):
    """Peso do draft na combinação por minuto (draft decai com o tempo)."""
    if minute <= 0:
        return 1.0
    if minute <= 10:
        return 0.35
    if minute <= 15:
        return 0.20
    if minute <= 20:
        return 0.10
    return 0.05
