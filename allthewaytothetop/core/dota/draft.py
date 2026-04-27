"""
Módulo core para análise de draft do Dota 2.
Contém toda a lógica de cálculo, sem dependência de UI.
"""
import pickle
import numpy as np
import os
import sqlite3
from core.shared.paths import path_in_data, path_in_models, BASE_DIR
from core.dota.prebets_secondary import get_dota_db_path, fetch_team_recent
from core.dota.draft_testezudo import TESTEZUDO_DIR


class DotaDraftAnalyzer:
    """Analisador de draft do Dota 2."""
    
    def __init__(self):
        self.models = None
        self.scaler = None
        self.feature_cols = None
        self.hero_impacts = None
        self._loaded = False
        self.last_error = None  # Armazenar último erro para exibição
        # Caminhos possíveis (prioridade: projeto > caminho absoluto)
        self.dota_draft_dir = r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\dota_draft_ml_v1"
    
    def _find_file(self, filename):
        """
        Procura um arquivo em múltiplos locais possíveis.
        Prioridade: model_artifacts/ > data/ > caminho absoluto original
        """
        # Prioridade 1: model_artifacts/
        path = path_in_models(filename)
        print(f"[DOTA] Procurando {filename} em: {path}")
        if os.path.exists(path):
            print(f"[DOTA] [OK] Encontrado {filename} em: {path}")
            return path
        else:
            print(f"[DOTA] [X] Nao encontrado em: {path}")
        
        # Prioridade 2: data/
        path = path_in_data(filename)
        print(f"[DOTA] Procurando {filename} em: {path}")
        if os.path.exists(path):
            print(f"[DOTA] [OK] Encontrado {filename} em: {path}")
            return path
        else:
            print(f"[DOTA] [X] Nao encontrado em: {path}")

        # Prioridade 3: diretório forçado por ambiente (útil em Railway/volume)
        env_dir = (os.environ.get("DOTA_DRAFT_DIR") or "").strip()
        if env_dir:
            path = os.path.join(env_dir, filename)
            print(f"[DOTA] Procurando {filename} em: {path}")
            if os.path.exists(path):
                print(f"[DOTA] [OK] Encontrado {filename} em: {path}")
                return path
            else:
                print(f"[DOTA] [X] Nao encontrado em: {path}")

        # Prioridade 4: caminho absoluto original
        path = os.path.join(self.dota_draft_dir, filename)
        print(f"[DOTA] Procurando {filename} em: {path}")
        if os.path.exists(path):
            print(f"[DOTA] [OK] Encontrado {filename} em: {path}")
            return path
        else:
            print(f"[DOTA] [X] Nao encontrado em: {path}")
        
        print(f"[DOTA] [X] {filename} nao encontrado em nenhum local")
        return None
    
    def load_models(self):
        """Carrega todos os modelos e dados necessários."""
        if self._loaded:
            return True
        
        try:
            # Impactos: no backend web, preferir artefato versionado no app antes do caminho desktop.
            impacts_path = self._find_file("hero_impacts_bayesian_single.pkl")
            if not impacts_path:
                testezudo_dir = TESTEZUDO_DIR if isinstance(TESTEZUDO_DIR, str) else str(TESTEZUDO_DIR)
                impacts_path = os.path.join(testezudo_dir, "hero_impacts_bayesian_single.pkl")
                if not os.path.exists(impacts_path):
                    impacts_path = None
            # Demais arquivos (modelos Draft Live)
            model_path = self._find_file("trained_models_dota_v2.pkl")
            scaler_path = self._find_file("scaler_dota_v2.pkl")
            features_path = self._find_file("feature_columns_dota_v2.pkl")
            
            # Verificar arquivos obrigatórios
            if not model_path:
                print(f"[ERRO] trained_models_dota_v2.pkl não encontrado em nenhum local")
                return False
            
            if not impacts_path:
                print(f"[ERRO] hero_impacts_bayesian_single.pkl (testezudo) não encontrado. Rode compute_hero_impacts_bayesian_v2_5.py no testezudo.")
                return False
            
            if not scaler_path:
                print(f"[AVISO] scaler_dota_v2.pkl não encontrado, continuando sem scaler")
            
            print(f"[DOTA DRAFT DEBUG] Carregando modelos...")
            
            # Carregar modelos ML
            try:
                with open(model_path, "rb") as f:
                    self.models = pickle.load(f)
                print(f"[DEBUG] Modelos Dota carregados com sucesso de: {model_path}")
            except Exception as e:
                error_msg = f"Erro ao carregar trained_models_dota_v2.pkl: {str(e)}"
                print(f"[ERRO] {error_msg}")
                import traceback
                self.last_error = error_msg + "\n\n" + traceback.format_exc()
                traceback.print_exc()
                return False
            
            # Carregar scaler
            if scaler_path:
                try:
                    with open(scaler_path, "rb") as f:
                        self.scaler = pickle.load(f)
                    print(f"[DEBUG] Scaler Dota carregado com sucesso de: {scaler_path}")
                except Exception as e:
                    print(f"[AVISO] Falha ao carregar scaler: {e}, continuando sem scaler")
                    self.scaler = None
            else:
                print(f"[AVISO] Scaler não encontrado, continuando sem scaler")
            
            # Carregar feature columns (opcional)
            if features_path:
                try:
                    with open(features_path, "rb") as f:
                        self.feature_cols = pickle.load(f)
                    print(f"[DEBUG] Feature columns Dota carregadas com sucesso de: {features_path}")
                except Exception as e:
                    print(f"[AVISO] Falha ao carregar feature columns: {e}")
            
            # Carregar impactos de heróis (bayesian testezudo)
            try:
                with open(impacts_path, "rb") as f:
                    self.hero_impacts = pickle.load(f)
                if isinstance(self.hero_impacts, dict) and "_meta" in self.hero_impacts:
                    self.hero_impacts = {k: v for k, v in self.hero_impacts.items() if k != "_meta"}
                print(f"[DEBUG] Hero impacts Dota (testezudo bayesian) carregados de: {impacts_path}")
            except Exception as e:
                error_msg = f"Erro ao carregar hero_impacts_bayesian_single.pkl: {str(e)}"
                print(f"[ERRO] {error_msg}")
                import traceback
                self.last_error = error_msg + "\n\n" + traceback.format_exc()
                traceback.print_exc()
                return False
            
            self._loaded = True
            return True
            
        except Exception as e:
            error_msg = f"Erro geral ao carregar modelos Dota: {str(e)}"
            print(f"[ERRO] {error_msg}")
            import traceback
            self.last_error = error_msg + "\n\n" + traceback.format_exc()
            traceback.print_exc()
            return False
    
    def get_hero_impact(self, hero_name, side=None):
        """
        Retorna o impacto de um herói (hero_impacts_bayesian_single.pkl — sem lado).
        """
        if not self.hero_impacts:
            return 0.0, 0
        hero_lower = hero_name.strip().lower()
        for nome, valor in self.hero_impacts.items():
            if nome.lower() != hero_lower or not isinstance(valor, dict):
                continue
            return valor.get("impact", 0.0) or 0.0, valor.get("games", 0) or 0
        return 0.0, 0
    
    def analyze_draft(self, radiant_picks, dire_picks, radiant_team_name=None, dire_team_name=None, n_games=15):
        """
        Analisa um draft completo com opção de incluir fator times.
        
        Args:
            radiant_picks: Lista de heróis do Radiant (5 heróis)
            dire_picks: Lista de heróis do Dire (5 heróis)
            radiant_team_name: Nome do time Radiant (opcional, para fator times)
            dire_team_name: Nome do time Dire (opcional, para fator times)
            n_games: Número de jogos para calcular média dos times (mínimo 15)
        
        Returns:
            Dict com análise completa
        """
        if not self._loaded:
            if not self.load_models():
                return {"error": "Não foi possível carregar os modelos."}
        
        # Calcular impactos totais do draft
        radiant_total = 0.0
        dire_total = 0.0
        radiant_impacts = []
        dire_impacts = []
        
        for hero in radiant_picks:
            impact, games = self.get_hero_impact(hero, "radiant")
            radiant_total += impact
            radiant_impacts.append({
                "hero": hero,
                "impact": impact,
                "games": games
            })
        
        for hero in dire_picks:
            impact, games = self.get_hero_impact(hero, "dire")
            dire_total += impact
            dire_impacts.append({
                "hero": hero,
                "impact": impact,
                "games": games
            })
        
        total_geral = radiant_total + dire_total
        
        # Linhas para análise
        lines = [39.5, 44.5, 45.5, 46.5, 47.5, 48.5, 49.5, 50.5, 52.5, 54.5, 55.5, 57.5, 59.5]
        
        # Calcular probabilidades empíricas dos times por linha (se nomes foram fornecidos)
        radiant_probs = None
        dire_probs = None
        n_games_radiant = 0
        n_games_dire = 0
        
        if radiant_team_name and dire_team_name:
            radiant_probs, n_games_radiant = self._get_team_empirical_probs_by_line(radiant_team_name, lines, n_games)
            dire_probs, n_games_dire = self._get_team_empirical_probs_by_line(dire_team_name, lines, n_games)
        
        # Calcular probabilidades do draft para cada linha
        predictions = {}
        draft_probs = {}  # Armazenar probabilidades do draft por linha
        
        if self.models and self.scaler:
            X = np.array([[radiant_total, dire_total, total_geral, radiant_total - dire_total]])
            X_scaled = self.scaler.transform(X)
            trained_lines = sorted(self.models.keys())
            
            for linha in lines:
                # Calcular probabilidade do draft para esta linha
                if linha in self.models:
                    p_draft_over = self.models[linha].predict_proba(X_scaled)[0][1]
                else:
                    # Interpolar entre linhas treinadas
                    lower_candidates = [l for l in trained_lines if l < linha]
                    upper_candidates = [l for l in trained_lines if l > linha]
                    
                    if not lower_candidates:
                        lower = trained_lines[0]
                    else:
                        lower = max(lower_candidates)
                    
                    if not upper_candidates:
                        upper = trained_lines[-1]
                    else:
                        upper = min(upper_candidates)
                    
                    prob_low = self.models[lower].predict_proba(X_scaled)[0][1]
                    prob_high = self.models[upper].predict_proba(X_scaled)[0][1]
                    
                    if upper == lower:
                        p_draft_over = prob_low
                    else:
                        ratio = (linha - lower) / (upper - lower)
                        p_draft_over = prob_low + (prob_high - prob_low) * ratio
                
                draft_probs[linha] = p_draft_over
                
                # Se temos probabilidades empíricas dos times, combinar com log-odds
                if radiant_probs is not None and dire_probs is not None:
                    # Calcular probabilidade combinada dos times (média simples das duas)
                    p_radiant_over = radiant_probs.get(linha, 0.5)
                    p_dire_over = dire_probs.get(linha, 0.5)
                    p_times_over = (p_radiant_over + p_dire_over) / 2
                    
                    # Combinar usando log-odds
                    # w = 0.5 (draft e times com mesmo peso)
                    w = 0.5
                    
                    # Converter para logit (evitar divisão por zero)
                    def safe_logit(p):
                        p = max(0.001, min(0.999, p))  # Clamp entre 0.001 e 0.999
                        return np.log(p / (1 - p))
                    
                    logit_draft = safe_logit(p_draft_over)
                    logit_times = safe_logit(p_times_over)
                    
                    # Combinar
                    logit_final = w * logit_draft + (1 - w) * logit_times
                    
                    # Converter de volta para probabilidade
                    p_final_over = 1 / (1 + np.exp(-logit_final))
                else:
                    # Sem fator times, usar apenas draft
                    p_final_over = p_draft_over
                    p_times_over = None
                
                prob_over = p_final_over
                prob_under = 1 - prob_over
                
                # Determinar lado favorito
                if prob_over >= 0.5:
                    lado = "OVER"
                    prob = prob_over
                else:
                    lado = "UNDER"
                    prob = prob_under
                
                # Calcular confiança
                if prob >= 0.85:
                    confianca = "Very High"
                elif prob >= 0.70:
                    confianca = "High"
                elif prob >= 0.55:
                    confianca = "Medium"
                else:
                    confianca = "Low"
                
                predictions[linha] = {
                    "line": linha,
                    "prob_over": float(prob_over),
                    "prob_under": float(prob_under),
                    "prob_draft_over": float(p_draft_over),
                    "prob_times_over": float(p_times_over) if p_times_over is not None else None,
                    "favorite": lado,
                    "confidence": confianca
                }
        
        # Estimar kills totais
        global_mean = 47.0
        draft_multiplier = 1.0
        kills_estimadas = global_mean + total_geral * draft_multiplier
        
        result = {
            "radiant_picks": radiant_picks,
            "dire_picks": dire_picks,
            "radiant_total": float(radiant_total),
            "dire_total": float(dire_total),
            "total_geral": float(total_geral),
            "radiant_impacts": radiant_impacts,
            "dire_impacts": dire_impacts,
            "kills_estimadas": float(kills_estimadas),
            "global_mean": float(global_mean),
            "draft_multiplier": float(draft_multiplier),
            "estimated_kills_formula": "global_mean + total_geral * draft_multiplier",
            "predictions": predictions
        }
        
        # Adicionar informações do fator times empírico se calculado
        if radiant_team_name and dire_team_name and radiant_probs is not None and dire_probs is not None:
            result["team_factor"] = {
                "radiant_team_name": radiant_team_name,
                "dire_team_name": dire_team_name,
                "radiant_n_games": n_games_radiant,
                "dire_n_games": n_games_dire,
                "radiant_probs": radiant_probs,
                "dire_probs": dire_probs,
                "method": "empirical_by_line",
                "weight_draft": 0.5,
                "weight_times": 0.5,
            }
        
        return result
    
    def get_available_heroes(self):
        """Retorna lista de heróis disponíveis (chaves dos impactos bayesianos)."""
        if not self.hero_impacts:
            if not self.load_models():
                return []
        return sorted(k for k in self.hero_impacts.keys() if k != "_meta")
    
    def _get_team_empirical_probs_by_line(self, team_name, lines, n_games=15):
        """
        Calcula probabilidades empíricas de OVER por linha para um time.
        Conta quantas vezes o time teve OVER em cada linha nos últimos N jogos.
        
        Args:
            team_name: Nome do time
            lines: Lista de linhas para calcular (ex: [39.5, 44.5, 45.5, ...])
            n_games: Número de jogos a considerar (mínimo 15)
        
        Returns:
            Dict com {line: p_over} para cada linha, ou None se não houver dados suficientes
            Também retorna n_available (número de jogos disponíveis)
        """
        if n_games < 15:
            n_games = 15
        
        db_path = get_dota_db_path()
        if db_path is None:
            return None, 0
        
        conn = sqlite3.connect(db_path)
        try:
            # Buscar total kills dos últimos N jogos
            kills_list = fetch_team_recent(conn, team_name, "kills", n_games)
            
            if len(kills_list) < 15:
                return None, len(kills_list)
            
            # Calcular probabilidade empírica de OVER para cada linha
            probs = {}
            for line in lines:
                over_count = sum(1 for kills in kills_list if kills > line)
                total = len(kills_list)
                # Usar suavização de Laplace (adicionar 1 over e 1 under) para evitar 0% ou 100%
                p_over = (over_count + 1) / (total + 2)
                probs[line] = p_over
            
            return probs, len(kills_list)
        except Exception as e:
            print(f"Erro ao calcular probabilidades empíricas do time {team_name}: {e}")
            return None, 0
        finally:
            conn.close()