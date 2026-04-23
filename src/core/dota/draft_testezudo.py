"""
Módulo core para análise de draft Dota 2 usando a matemática do projeto testezudo (v2.7).
- Draft Strength Multiplier (S), min_games, curva isotônica + interpolação.
- Sem fator times: apenas draft (impactos bayesianos + média global).
"""
import pickle
import numpy as np
import os
from sklearn.isotonic import IsotonicRegression

# Diretório do projeto testezudo (onde estão os .pkl)
TESTEZUDO_DIR = r"C:\Users\Lucas\Documents\testezudo"

# Linhas para exibição: 39.5, 44.5, 45.5, ..., 59.5 (over/under: 45 kills = under 45.5, 46 = over 45.5)
LINHAS_FINAS = np.array([39.5] + list(np.arange(44.5, 60, 1.0)))


def _carregar_pkl(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def _calcular_confianca(prob):
    """Confiança pela distância de prob a 0.5 (OVER ou UNDER)."""
    dist = abs(prob - 0.5)
    if dist >= 0.30:
        return "Very High"
    elif dist >= 0.20:
        return "High"
    elif dist >= 0.10:
        return "Medium"
    return "Low"


def _get_hero_impact_single(hero, impacts, min_games=0):
    """
    Retorna (impacto, jogos) do herói.
    Formato único: hero_impacts_bayesian_single.pkl — { hero: { "impact", "games" } } (sem lado).
    """
    hero_norm = hero.strip()
    for name, data in impacts.items():
        if name.lower() != hero_norm.lower() or not isinstance(data, dict):
            continue
        games = data.get("games", 0) or 0
        impact = data.get("impact", 0.0) or 0.0
        if games < min_games:
            return 0.0, games
        return impact, games
    return 0.0, 0


def _calcular_draft_score(radiant_heroes, dire_heroes, impacts, min_games=0):
    """Totais usando um único impacto por herói (mesmo valor para Radiant e Dire)."""
    radiant_total = 0.0
    dire_total = 0.0
    for hero in radiant_heroes:
        imp, _ = _get_hero_impact_single(hero, impacts, min_games)
        radiant_total += imp
    for hero in dire_heroes:
        imp, _ = _get_hero_impact_single(hero, impacts, min_games)
        dire_total += imp
    draft_total = radiant_total + dire_total
    return radiant_total, dire_total, draft_total


def _build_features(radiant_total, dire_total, draft_total, diff, S, feature_set):
    r_eff = radiant_total * S
    d_eff = dire_total * S
    t_eff = draft_total * S
    diff_eff = diff * S
    if feature_set == "full":
        return [r_eff, d_eff, t_eff, diff_eff]
    if feature_set == "total_only":
        return [t_eff]
    if feature_set == "total_and_diff":
        return [t_eff, diff_eff]
    return [r_eff, d_eff, t_eff, diff_eff]


def _curva_probabilidades(models, X, linhas_finas):
    """
    Curva de P(over): coleta probs nas linhas treinadas, aplica isotonic
    (linha sobe -> p_over desce), interpola para linhas_finas.
    Retorna: (linhas_finas, probs_interp)
    """
    linhas_trained = sorted(models.keys())
    if not linhas_trained:
        return linhas_finas, np.full(len(linhas_finas), 0.5)
    probs_raw = np.array([models[l].predict_proba(X)[0, 1] for l in linhas_trained])
    linhas_arr = np.array(linhas_trained)
    iso = IsotonicRegression(out_of_bounds="clip", increasing=False)
    probs_iso = iso.fit_transform(linhas_arr, probs_raw)
    probs_interp = np.interp(linhas_finas, linhas_arr, probs_iso)
    return linhas_finas, probs_interp


class DotaDraftTestezudoAnalyzer:
    """Analisador de draft Dota 2 com matemática testezudo v2.7 (sem fator times)."""

    def __init__(self):
        self.models = None
        self.hero_impacts = None
        self.config = None
        self._loaded = False
        self.last_error = None
        self.testezudo_dir = TESTEZUDO_DIR

    def _path(self, filename):
        return os.path.join(self.testezudo_dir, filename)

    def reload_models(self):
        """Invalida o cache para que a próxima análise recarregue os .pkl do disco (útil após atualizar pelo programa)."""
        self._loaded = False

    def load_models(self):
        """Carrega modelos e config do projeto testezudo."""
        if self._loaded:
            return True
        try:
            models_path = self._path("models_dota_v2_7.pkl")
            impacts_path = self._path("hero_impacts_bayesian_single.pkl")
            config_path = self._path("config_dota_v2_7.pkl")

            if not os.path.exists(models_path):
                self.last_error = f"Arquivo não encontrado: {models_path}"
                return False
            if not os.path.exists(impacts_path):
                self.last_error = (
                    f"Arquivo não encontrado: {impacts_path}\n\n"
                    "Use apenas impacto único (sem Radiant/Dire). "
                    "Rode no testezudo: python compute_hero_impacts_bayesian_v2_5.py"
                )
                return False
            if not os.path.exists(config_path):
                self.last_error = f"Arquivo não encontrado: {config_path}"
                return False

            self.models = _carregar_pkl(models_path)
            self.hero_impacts = _carregar_pkl(impacts_path)
            self.config = _carregar_pkl(config_path)

            if self.hero_impacts and "_meta" in self.hero_impacts:
                del self.hero_impacts["_meta"]

            self._loaded = True
            return True
        except Exception as e:
            self.last_error = str(e)
            import traceback
            self.last_error += "\n\n" + traceback.format_exc()
            return False

    def get_hero_impact(self, hero_name, side="radiant"):
        """
        Retorna (impacto, jogos) para exibição. Um único impacto por herói (igual para Radiant e Dire).
        side é ignorado; mantido por compatibilidade de API.
        """
        if not self._loaded and not self.load_models():
            return 0.0, 0
        min_games = self.config.get("min_games", 0) if self.config else 0
        return _get_hero_impact_single(hero_name, self.hero_impacts, min_games)

    def get_available_heroes(self):
        """Retorna lista de heróis disponíveis (chaves dos impactos bayesianos)."""
        if not self._loaded and not self.load_models():
            return []
        if not self.hero_impacts:
            return []
        return sorted(k for k in self.hero_impacts.keys() if k != "_meta")

    def analyze_draft(
        self,
        radiant_picks,
        dire_picks,
        radiant_team_name=None,
        dire_team_name=None,
        n_games=15,
    ):
        """
        Analisa o draft com a matemática v2.7 (curva isotônica, S, min_games).
        Usa apenas impactos bayesianos do testezudo (hero_impacts_bayesian_single.pkl — sem lado).
        radiant_team_name / dire_team_name / n_games são ignorados (sem fator times).
        Retorna o mesmo formato do DotaDraftAnalyzer para a UI.
        """
        if not self._loaded and not self.load_models():
            return {"error": "Não foi possível carregar os modelos."}

        min_games = self.config.get("min_games", 0)
        S = self.config.get("draft_strength_multiplier", 1.0)
        feature_set = self.config.get("feature_set", "full")
        global_mean = self.config.get("global_mean", 47.0)

        # Impactos por herói (exibição) e totais — um único impacto por herói (Radiant e Dire)
        radiant_impacts = []
        for hero in radiant_picks:
            impact, games = _get_hero_impact_single(hero, self.hero_impacts, min_games)
            radiant_impacts.append({"hero": hero, "impact": impact, "games": games})
        dire_impacts = []
        for hero in dire_picks:
            impact, games = _get_hero_impact_single(hero, self.hero_impacts, min_games)
            dire_impacts.append({"hero": hero, "impact": impact, "games": games})
        radiant_total, dire_total, draft_total = _calcular_draft_score(
            radiant_picks, dire_picks, self.hero_impacts, min_games
        )
        diff = radiant_total - dire_total
        feat = _build_features(radiant_total, dire_total, draft_total, diff, S, feature_set)
        X = np.array([feat])

        linhas_f, probs_f = _curva_probabilidades(self.models, X, LINHAS_FINAS)
        kills_estimadas = global_mean + draft_total

        predictions = {}
        for linha, prob_over in zip(linhas_f, probs_f):
            prob_over = float(prob_over)
            prob_under = 1.0 - prob_over
            favorite = "OVER" if prob_over >= 0.5 else "UNDER"
            prob = prob_over if favorite == "OVER" else prob_under
            confidence = _calcular_confianca(prob)
            predictions[float(linha)] = {
                "line": float(linha),
                "prob_over": prob_over,
                "prob_under": prob_under,
                "prob_draft_over": prob_over,
                "prob_times_over": None,
                "favorite": favorite,
                "confidence": confidence,
            }

        return {
            "radiant_picks": radiant_picks,
            "dire_picks": dire_picks,
            "radiant_total": float(radiant_total),
            "dire_total": float(dire_total),
            "total_geral": float(draft_total),
            "radiant_impacts": radiant_impacts,
            "dire_impacts": dire_impacts,
            "kills_estimadas": float(kills_estimadas),
            "predictions": predictions,
            "team_factor": None,
        }
