"""
Módulo core para análise de draft do LoL.
Contém toda a lógica de cálculo, sem dependência de UI.
"""
import pickle
import pandas as pd
import sys
import os
from core.shared.paths import path_in_data, path_in_models, BASE_DIR

# Adicionar src ao path para importar load_and_predict_v3
# No .exe empacotado, o PyInstaller mantém a estrutura, então src deve estar acessível
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Adicionar src ao path se não estiver
src_dir = os.path.join(BASE_DIR, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Importar predict_game com fallbacks
try:
    # Tentar import normal (deve funcionar no .exe se PyInstaller incluir)
    from src.load_and_predict_v3 import predict_game
except ImportError:
    # Fallback: importar diretamente do arquivo (funciona em dev e .exe)
    import importlib.util
    load_predict_path = os.path.join(src_dir, 'load_and_predict_v3.py')
    if os.path.exists(load_predict_path):
        spec = importlib.util.spec_from_file_location("load_and_predict_v3", load_predict_path)
        load_predict_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load_predict_module)
        predict_game = load_predict_module.predict_game
    else:
        # Último fallback: tentar import sem src
        try:
            from load_and_predict_v3 import predict_game
        except ImportError:
            raise ImportError(f"Não foi possível importar load_and_predict_v3. BASE_DIR: {BASE_DIR}, src_dir: {src_dir}")


class LoLDraftAnalyzer:
    """Analisador de draft do LoL."""
    
    def __init__(self):
        self.models = None
        self.scaler = None
        self.feature_cols = None
        self.league_stats = None
        self.champion_impacts = None
        self.synergy_df = None
        self.matchup_df = None
        self._loaded = False
    
    def load_models(self):
        """Carrega todos os modelos e dados necessários."""
        if self._loaded:
            return True
        
        try:
            # Debug: sempre imprimir caminhos para diagnóstico
            base_dir = BASE_DIR
            data_dir = path_in_data("")
            models_dir = path_in_models("")
            print(f"[DRAFT DEBUG] BASE_DIR: {base_dir}")
            print(f"[DRAFT DEBUG] DATA_DIR: {data_dir}")
            print(f"[DRAFT DEBUG] MODELS_DIR: {models_dir}")
            print(f"[DRAFT DEBUG] DATA_DIR existe: {os.path.exists(data_dir)}")
            print(f"[DRAFT DEBUG] MODELS_DIR existe: {os.path.exists(models_dir)}")
            
            # Debug: mostrar informações do ambiente
            is_frozen = getattr(sys, 'frozen', False)
            exe_path = sys.executable if is_frozen else "N/A (dev mode)"
            
            print(f"[DEBUG] Modo frozen: {is_frozen}")
            print(f"[DEBUG] sys.executable: {exe_path}")
            if hasattr(sys, '_MEIPASS'):
                print(f"[DEBUG] sys._MEIPASS: {sys._MEIPASS}")
            
            # Carregar modelos ML
            models_path = path_in_models("trained_models_v3.pkl")
            models_dir = path_in_models("")
            
            print(f"[DEBUG] BASE_DIR: {BASE_DIR}")
            print(f"[DEBUG] models_dir: {models_dir}")
            print(f"[DEBUG] models_path: {models_path}")
            print(f"[DEBUG] models_path existe: {os.path.exists(models_path)}")
            
            if not os.path.exists(models_path):
                print(f"[ERRO] Arquivo não encontrado: {models_path}")
                # Listar arquivos no diretório para debug
                if os.path.exists(models_dir):
                    files = os.listdir(models_dir)
                    print(f"[DEBUG] Arquivos em {models_dir}: {files}")
                else:
                    print(f"[ERRO] Diretório não existe: {models_dir}")
                    # Tentar encontrar o diretório
                    exe_dir = os.path.dirname(sys.executable) if is_frozen else BASE_DIR
                    print(f"[DEBUG] Procurando em: {exe_dir}")
                    if os.path.exists(os.path.join(exe_dir, "model_artifacts")):
                        print(f"[DEBUG] Encontrado model_artifacts em: {os.path.join(exe_dir, 'model_artifacts')}")
                return False
            
            # Carregar modelos ML (pode usar scipy via sklearn)
            # Importar sklearn aqui para garantir que scipy seja carregado primeiro
            try:
                # Importar scipy e seus submódulos necessários ANTES de carregar modelos
                import scipy
                import scipy.sparse
                import scipy._lib
                # Tentar importar o módulo problemático de forma segura
                try:
                    import scipy._lib.array_api_compat.numpy.fft
                except ImportError:
                    # Se não existir, não é problema - pode ser versão diferente do scipy
                    pass
                import sklearn
            except ImportError as e:
                print(f"[ERRO] Erro ao importar scipy/sklearn: {e}")
                import traceback
                traceback.print_exc()
                # Continuar mesmo assim - pode funcionar
            
            print(f"[DEBUG] Carregando modelos de: {models_path}")
            try:
                with open(models_path, "rb") as f:
                    self.models = pickle.load(f)
                print(f"[DEBUG] Modelos carregados com sucesso")
            except Exception as e:
                print(f"[ERRO] Falha ao carregar modelos: {e}")
                import traceback
                traceback.print_exc()
                return False
            
            try:
                with open(path_in_models("scaler_v3.pkl"), "rb") as f:
                    self.scaler = pickle.load(f)
                print(f"[DEBUG] Scaler carregado com sucesso")
            except Exception as e:
                print(f"[ERRO] Falha ao carregar scaler: {e}")
                import traceback
                traceback.print_exc()
                return False
            
            try:
                with open(path_in_models("feature_columns_v3.pkl"), "rb") as f:
                    self.feature_cols = pickle.load(f)
                print(f"[DEBUG] Feature columns carregadas com sucesso")
            except Exception as e:
                print(f"[ERRO] Falha ao carregar feature columns: {e}")
                import traceback
                traceback.print_exc()
                return False
            
            # Carregar estatísticas de ligas
            with open(path_in_data("league_stats_v3.pkl"), "rb") as f:
                self.league_stats = pickle.load(f)
            
            # Carregar impactos de campeões
            impacts_path = path_in_data("champion_impacts.csv")
            if not os.path.exists(impacts_path):
                print(f"Arquivo não encontrado: {impacts_path}")
                return False
            
            self.champion_impacts = pd.read_csv(impacts_path)
            self.champion_impacts.columns = self.champion_impacts.columns.str.strip().str.lower()
            
            # Carregar sinergias e matchups (opcional)
            try:
                synergy_path = path_in_data("champion_synergies_simples.pkl")
                if os.path.exists(synergy_path):
                    self.synergy_df = pd.read_pickle(synergy_path)
                    self.synergy_df.columns = self.synergy_df.columns.str.strip()
                else:
                    self.synergy_df = None
            except Exception as e:
                print(f"Aviso: Não foi possível carregar sinergias: {e}")
                self.synergy_df = None
            
            try:
                matchup_path = path_in_data("matchup_synergies_simple.pkl")
                if os.path.exists(matchup_path):
                    self.matchup_df = pd.read_pickle(matchup_path)
                    self.matchup_df.columns = self.matchup_df.columns.str.strip()
                else:
                    self.matchup_df = None
            except Exception as e:
                print(f"Aviso: Não foi possível carregar matchups: {e}")
                self.matchup_df = None
            
            self._loaded = True
            return True
            
        except Exception as e:
            print(f"Erro ao carregar modelos: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _calcular_league_stats_agregado(self, leagues):
        """Calcula estatísticas agregadas para múltiplas ligas."""
        if isinstance(leagues, str):
            return self.league_stats.get(leagues, {"mean_kills": 28.0, "std_kills": 8.0, "games": 0})
        
        # Agregar estatísticas de múltiplas ligas
        stats_list = [self.league_stats.get(lg) for lg in leagues if lg in self.league_stats]
        if not stats_list:
            # Fallback para primeira liga disponível
            return self.league_stats.get(list(self.league_stats.keys())[0], {"mean_kills": 28.0, "std_kills": 8.0, "games": 0})
        
        # Calcular média ponderada
        total_games = sum(s["games"] for s in stats_list if s)
        if total_games == 0:
            return stats_list[0] if stats_list[0] else {"mean_kills": 28.0, "std_kills": 8.0, "games": 0}
        
        mean_kills = sum(s["mean_kills"] * s["games"] for s in stats_list if s) / total_games
        # Para std, usar a maior (mais conservador)
        std_kills = max(s["std_kills"] for s in stats_list if s)
        
        return {
            "mean_kills": round(mean_kills, 2),
            "std_kills": round(std_kills, 2),
            "games": total_games
        }
    
    def _recalcular_impactos_agregados(self, leagues_list, campeao):
        """Recalcula o impacto de um campeão usando média agregada de múltiplas ligas.
        Retorna None se o campeão tiver menos de 5 jogos para garantir confiabilidade estatística."""
        import pandas as pd

        MIN_GAMES = 5  # Mínimo de jogos para considerar o impacto

        from core.lol.oracle_team_games import get_draft_oracle_dataframe

        df = get_draft_oracle_dataframe()
        if df is None or df.empty:
            return None, 0
        
        # Filtrar apenas as ligas selecionadas
        df = df[df["league"].isin(leagues_list)]
        
        if len(df) == 0:
            return None, 0
        
        # Calcular média agregada de total_kills para todas as ligas selecionadas
        # Remover duplicatas por gameid (cada partida aparece 2 vezes - um por time)
        df_unique = df.drop_duplicates(subset=["gameid", "total_kills"])
        media_agregada = df_unique["total_kills"].mean()
        
        # Buscar todas as partidas onde o campeão jogou
        mask = (
            (df["pick1"].str.casefold() == campeao.casefold()) |
            (df["pick2"].str.casefold() == campeao.casefold()) |
            (df["pick3"].str.casefold() == campeao.casefold()) |
            (df["pick4"].str.casefold() == campeao.casefold()) |
            (df["pick5"].str.casefold() == campeao.casefold())
        )
        
        partidas_campeao = df[mask]
        
        if len(partidas_campeao) == 0:
            return None, 0
        
        # Remover duplicatas por gameid para calcular média correta
        partidas_campeao_unique = partidas_campeao.drop_duplicates(subset=["gameid", "total_kills"])
        
        # Número de jogos
        n_jogos = len(partidas_campeao_unique)
        
        # Apenas calcular impacto se tiver 5 ou mais jogos
        if n_jogos < MIN_GAMES:
            return None, int(n_jogos)
        
        # Calcular média de total_kills quando o campeão joga
        media_com_campeao = partidas_campeao_unique["total_kills"].mean()
        
        # Calcular impacto: média com campeão - média agregada
        impacto = media_com_campeao - media_agregada
        
        return float(impacto), int(n_jogos)
    
    def analyze_draft(self, league, team1, team2, threshold=0.55):
        """
        Analisa um draft completo.
        
        Args:
            league: Nome da liga (ex: "LCK", "LPL", "MAJOR") ou lista de ligas
            team1: Lista de 5 campeões do time 1
            team2: Lista de 5 campeões do time 2
            threshold: Threshold para decisão (padrão 0.55)
        
        Returns:
            Dict com resultados completos da análise
        """
        if not self.load_models():
            return None
        
        # Se league for "MAJOR", usar lista de ligas major que existem nos dados
        from core.shared.utils import MAJOR_LEAGUES
        import pandas as pd

        if league == "MAJOR":
            # Ligas major presentes no CSV Oracle's Elixir mais recente (ou fallback oracle_prepared)
            from core.lol.oracle_team_games import get_draft_oracle_dataframe

            try:
                oracle_df = get_draft_oracle_dataframe()
                if oracle_df is not None and not oracle_df.empty and "league" in oracle_df.columns:
                    oracle_leagues = set(oracle_df["league"].dropna().astype(str).str.strip().unique())
                    # Incluir todas as ligas major que existem nos dados
                    # Ordem específica: LCK, LPL, LCS, CBLOL, LCP, LEC
                    ordem_major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]
                    major_final = [lg for lg in ordem_major if lg in MAJOR_LEAGUES and lg in oracle_leagues]
                    if major_final:
                        league = major_final
                    else:
                        # Fallback: usar apenas as que estão em champion_impacts.csv
                        available_leagues = sorted(self.champion_impacts["league"].unique().tolist())
                        major_disponiveis = sorted([lg for lg in available_leagues if lg in MAJOR_LEAGUES])
                        league = major_disponiveis if major_disponiveis else sorted(list(MAJOR_LEAGUES))
                else:
                    # Fallback: usar apenas as que estão em champion_impacts.csv
                    available_leagues = sorted(self.champion_impacts["league"].unique().tolist())
                    major_disponiveis = sorted([lg for lg in available_leagues if lg in MAJOR_LEAGUES])
                    league = major_disponiveis if major_disponiveis else sorted(list(MAJOR_LEAGUES))
            except Exception:
                # Fallback: usar apenas as que estão em champion_impacts.csv
                available_leagues = sorted(self.champion_impacts["league"].unique().tolist())
                major_disponiveis = sorted([lg for lg in available_leagues if lg in MAJOR_LEAGUES])
                league = major_disponiveis if major_disponiveis else sorted(list(MAJOR_LEAGUES))
        
        # Verificar se é lista de ligas (agregado)
        is_aggregated = isinstance(league, list) and len(league) > 1
        
        # Inicializar dict de impactos calculados (para usar depois se agregado)
        impactos_calculados = {}
        
        if is_aggregated:
            # Calcular estatísticas agregadas
            stats_agregado = self._calcular_league_stats_agregado(league)
            
            # Criar DataFrame temporário com impactos recalculados (igual ao script do PowerShell)
            league_for_pred = league[0]  # Usar primeira liga para predição
            impacts_para_pred = self.champion_impacts.copy()
            todos_campeoes = set(team1 + team2)
            
            # Recalcular impactos usando média agregada (igual ao script do PowerShell)
            # Armazenar em dict para usar depois
            for champ in todos_campeoes:
                imp, n_jogos = self._recalcular_impactos_agregados(league, champ)
                impactos_calculados[champ] = (imp, n_jogos)
                
                if imp is not None:
                    # Buscar ou criar entrada para este campeão na primeira liga
                    mask = (impacts_para_pred["league"] == league_for_pred) & \
                           (impacts_para_pred["champion"].str.lower() == champ.lower())
                    
                    if mask.any():
                        # Atualizar impacto existente (igual ao script do PowerShell - não atualiza colunas relacionadas)
                        impacts_para_pred.loc[mask, "impact"] = imp
                        if "games_played" in impacts_para_pred.columns:
                            impacts_para_pred.loc[mask, "games_played"] = n_jogos
                    else:
                        # Criar nova linha se não existir (usar valores padrão)
                        new_row = {
                            "league": league_for_pred,
                            "champion": champ,
                            "impact": float(imp),
                            "games_played": int(n_jogos) if "games_played" in impacts_para_pred.columns else 0,
                        }
                        # Preencher outras colunas com valores padrão se necessário
                        for col in impacts_para_pred.columns:
                            if col not in new_row:
                                if col == "league_avg_kills":
                                    new_row[col] = float(stats_agregado["mean_kills"])
                                elif col == "avg_kills_with_champ":
                                    new_row[col] = float(imp + stats_agregado["mean_kills"])
                                elif col == "league_std_kills":
                                    new_row[col] = float(stats_agregado.get("std_kills", 0.0))
                                else:
                                    # Valor padrão baseado no tipo
                                    if impacts_para_pred[col].dtype in ['float64', 'float32']:
                                        new_row[col] = 0.0
                                    elif impacts_para_pred[col].dtype in ['int64', 'int32']:
                                        new_row[col] = 0
                                    else:
                                        new_row[col] = ""
                        
                        # Adicionar nova linha (garantir ordem das colunas)
                        new_df = pd.DataFrame([new_row])
                        # Reordenar colunas para corresponder ao DataFrame original
                        new_df = new_df.reindex(columns=impacts_para_pred.columns)
                        # Preencher valores faltantes com base no tipo da coluna
                        for col in new_df.columns:
                            if new_df[col].isna().any():
                                dtype = impacts_para_pred[col].dtype
                                if pd.api.types.is_float_dtype(dtype):
                                    new_df[col] = new_df[col].fillna(0.0)
                                elif pd.api.types.is_integer_dtype(dtype):
                                    new_df[col] = new_df[col].fillna(0)
                                else:
                                    new_df[col] = new_df[col].fillna("")
                        # Usar pd.concat com sort=False para evitar warnings
                        impacts_para_pred = pd.concat([impacts_para_pred, new_df], ignore_index=True, sort=False)
            
            # Criar league_stats temporário com stats agregadas
            league_stats_para_pred = {league_for_pred: stats_agregado}
            
            game_data = {
                "league": league_for_pred,
                "team1": team1,
                "team2": team2
            }
        else:
            # Liga única - usar código normal
            league_for_pred = league if isinstance(league, str) else league[0]
            impacts_para_pred = self.champion_impacts
            league_stats_para_pred = self.league_stats
            leagues_one = [league_for_pred]
            game_data = {
                "league": league_for_pred,
                "team1": team1,
                "team2": team2,
                # Mesmos impactos que a UI (Oracle bruto); senão predict_game usaria só champion_impacts.csv
                "impacts_override": {
                    "team1": [self._impact_value_for_prediction(leagues_one, c) for c in team1],
                    "team2": [self._impact_value_for_prediction(leagues_one, c) for c in team2],
                },
            }
        
        # Calcular predições usando DataFrame temporário (igual ao script do PowerShell)
        result = predict_game(
            game_data,
            self.models,
            self.scaler,
            impacts_para_pred,  # Usar DataFrame com impactos recalculados
            league_stats_para_pred,  # Usar stats agregadas
            self.feature_cols,
            threshold
        )
        
        # Adicionar informações extras
        result["league"] = league
        result["team1"] = team1
        result["team2"] = team2
        
        # Calcular sinergias e matchups
        result["sinergias"] = self._get_synergies(league, team1, team2)
        result["matchups"] = self._get_matchups(league, team1, team2)
        
        # Calcular impactos individuais para exibição (usar impactos já calculados se agregado)
        if is_aggregated:
            # Usar impactos já calculados
            impactos_individuais = {"team1": [], "team2": []}
            for champ in team1:
                imp, n_games = impactos_calculados.get(champ, (None, 0))
                # Se imp é None, significa que tem menos de 5 jogos - usar impacto 0 mas preservar n_games
                if imp is None:
                    imp = 0.0
                impactos_individuais["team1"].append({
                    "champion": champ,
                    "impact": float(imp),
                    "n_games": int(n_games)
                })
            for champ in team2:
                imp, n_games = impactos_calculados.get(champ, (None, 0))
                # Se imp é None, significa que tem menos de 5 jogos - usar impacto 0 mas preservar n_games
                if imp is None:
                    imp = 0.0
                impactos_individuais["team2"].append({
                    "champion": champ,
                    "impact": float(imp),
                    "n_games": int(n_games)
                })
            result["impactos_individuais"] = impactos_individuais
        else:
            result["impactos_individuais"] = self._get_impactos_individuais(league, team1, team2, False)
        
        return result

    def _impact_value_for_prediction(self, leagues_list: list, champ: str) -> float:
        """Impacto de kills (mesma regra dos impactos individuais na UI) para predict_game."""
        from core.lol.oracle_team_games import (
            compute_kills_impact_from_team_games,
            get_draft_oracle_dataframe,
        )

        MIN_GAMES = 5
        n_games = self._count_games_in_oracle(leagues_list, champ)
        if n_games < MIN_GAMES:
            return 0.0
        df_games = get_draft_oracle_dataframe()
        if df_games is not None and not df_games.empty:
            computed, _ = compute_kills_impact_from_team_games(
                df_games, leagues_list, champ, MIN_GAMES
            )
            if computed is not None:
                return float(computed)
        mask = self.champion_impacts["league"].isin(leagues_list) & (
            self.champion_impacts["champion"].str.casefold() == champ.casefold()
        )
        row = self.champion_impacts[mask]
        if not row.empty:
            return float(row["impact"].iloc[0])
        return 0.0

    def _get_impactos_individuais(self, league, team1, team2, is_aggregated=False):
        """Calcula impactos individuais (liga única): n e impacto vêm do mesmo CSV (Oracle bruto / fallback).

        Com n >= 5, o impacto é recalculado como em generate_champion_impacts.py (kills totais).
        champion_impacts.csv só entra como fallback se não houver DataFrame de jogos."""
        impactos = {"team1": [], "team2": []}
        leagues_list = league if isinstance(league, list) else [league]

        for label, team in [("team1", team1), ("team2", team2)]:
            for champ in team:
                n_games = self._count_games_in_oracle(leagues_list, champ)
                imp = self._impact_value_for_prediction(leagues_list, champ)
                impactos[label].append({
                    "champion": champ,
                    "impact": imp,
                    "n_games": int(n_games),
                })

        return impactos
    
    def _count_games_in_oracle(self, leagues_list, champ):
        """Conta jogos do campeão no CSV Oracle's Elixir mais recente (fallback: oracle_prepared.csv)."""
        from core.lol.oracle_team_games import get_draft_oracle_dataframe
        import pandas as pd

        try:
            df = get_draft_oracle_dataframe()
            if df is None or df.empty:
                return 0
            # Filtrar ligas
            df = df[df["league"].isin(leagues_list)]
            
            # Buscar campeão em qualquer pick
            mask = (
                (df["pick1"].astype(str).str.casefold() == champ.casefold()) |
                (df["pick2"].astype(str).str.casefold() == champ.casefold()) |
                (df["pick3"].astype(str).str.casefold() == champ.casefold()) |
                (df["pick4"].astype(str).str.casefold() == champ.casefold()) |
                (df["pick5"].astype(str).str.casefold() == champ.casefold())
            )
            
            partidas = df[mask]
            if len(partidas) == 0:
                return 0
            
            # Remover duplicatas por gameid (cada partida aparece 2 vezes - um por time)
            if "gameid" in partidas.columns and "total_kills" in partidas.columns:
                partidas_unique = partidas.drop_duplicates(subset=["gameid", "total_kills"])
                return len(partidas_unique)
            else:
                # Fallback: contar linhas únicas
                return len(partidas.drop_duplicates())
        except Exception as e:
            # Em caso de erro, retornar 0
            return 0
    
    def _get_synergies(self, league, team1, team2):
        """Calcula sinergias dentro de cada time."""
        if self.synergy_df is None:
            return {"team1": [], "team2": []}
        
        import itertools
        
        leagues_list = league if isinstance(league, list) else [league]
        df_league = self.synergy_df[
            (self.synergy_df["league"].isin(leagues_list)) &
            (self.synergy_df["n_games"] >= 5)
        ]
        
        sin_t1, sin_t2 = [], []
        
        # Time 1 - ordenar pares antes de buscar (igual ao script do PowerShell)
        pairs_t1 = [tuple(sorted(p)) for p in itertools.combinations(team1, 2)]
        for c1, c2 in pairs_t1:
            # Buscar em ambas as ordens (champ1, champ2) e (champ2, champ1)
            mask = (
                (df_league["champ1"].str.lower() == c1.lower()) &
                (df_league["champ2"].str.lower() == c2.lower())
            )
            if not mask.any():
                # Tentar ordem inversa
                mask = (
                    (df_league["champ1"].str.lower() == c2.lower()) &
                    (df_league["champ2"].str.lower() == c1.lower())
                )
            if mask.any():
                row = df_league[mask].iloc[0]
                sin_t1.append({
                    "champ1": c1,
                    "champ2": c2,
                    "sinergia": float(row.get("sinergia_bruta", 0)),
                    "n_games": int(row.get("n_games", 0))
                })
        
        # Time 2 - ordenar pares antes de buscar (igual ao script do PowerShell)
        pairs_t2 = [tuple(sorted(p)) for p in itertools.combinations(team2, 2)]
        for c1, c2 in pairs_t2:
            # Buscar em ambas as ordens (champ1, champ2) e (champ2, champ1)
            mask = (
                (df_league["champ1"].str.lower() == c1.lower()) &
                (df_league["champ2"].str.lower() == c2.lower())
            )
            if not mask.any():
                # Tentar ordem inversa
                mask = (
                    (df_league["champ1"].str.lower() == c2.lower()) &
                    (df_league["champ2"].str.lower() == c1.lower())
                )
            if mask.any():
                row = df_league[mask].iloc[0]
                sin_t2.append({
                    "champ1": c1,
                    "champ2": c2,
                    "sinergia": float(row.get("sinergia_bruta", 0)),
                    "n_games": int(row.get("n_games", 0))
                })
        
        return {"team1": sin_t1, "team2": sin_t2}
    
    def _get_matchups(self, league, team1, team2):
        """Calcula matchups entre os times, incluindo anyrole."""
        if self.matchup_df is None:
            return {"diretos": [], "anyrole": []}
        
        leagues_list = league if isinstance(league, list) else [league]
        df_league = self.matchup_df[
            (self.matchup_df["league"].isin(leagues_list)) &
            (self.matchup_df["n_games"] >= 5)
        ]
        
        roles = ["top", "jung", "mid", "adc", "sup"]
        matchups_diretos = []
        matchups_diretos_set = set()  # Para evitar duplicatas no anyrole
        
        # Matchups diretos (por role)
        for i, role in enumerate(roles):
            if i >= len(team1) or i >= len(team2):
                continue
            
            c1 = team1[i]
            c2 = team2[i]
            
            # Buscar matchup direto
            mask = (
                (df_league["role"].str.lower() == role) &
                (df_league["champ1"].str.lower() == c1.lower()) &
                (df_league["champ2"].str.lower() == c2.lower())
            )
            if not mask.any():
                mask = (
                    (df_league["role"].str.lower() == role) &
                    (df_league["champ1"].str.lower() == c2.lower()) &
                    (df_league["champ2"].str.lower() == c1.lower())
                )
            
            if mask.any():
                row = df_league[mask].iloc[0]
                matchups_diretos.append({
                    "role": role,
                    "champ1": c1,
                    "champ2": c2,
                    "impacto": float(row.get("impacto_matchup", 0)),
                    "n_games": int(row.get("n_games", 0))
                })
                # Adicionar ao set para evitar duplicatas no anyrole
                matchups_diretos_set.add(tuple(sorted([c1.lower(), c2.lower()])))
        
        # Anyrole matchups (fora das lanes diretas)
        df_any = df_league[df_league["role"].str.lower() == "anyrole"]
        anyrole_matchups = []
        
        for c1 in team1:
            for c2 in team2:
                key = tuple(sorted([c1.lower(), c2.lower()]))
                # Pular se já está nos matchups diretos
                if key in matchups_diretos_set:
                    continue
                
                # Buscar anyrole matchup
                mask = (
                    (df_any["champ1"].str.lower() == c1.lower()) &
                    (df_any["champ2"].str.lower() == c2.lower())
                )
                if not mask.any():
                    mask = (
                        (df_any["champ1"].str.lower() == c2.lower()) &
                        (df_any["champ2"].str.lower() == c1.lower())
                    )
                
                if mask.any():
                    row = df_any[mask].iloc[0]
                    anyrole_matchups.append({
                        "champ1": c1,
                        "champ2": c2,
                        "impacto": float(row.get("impacto_matchup", 0)),
                        "n_games": int(row.get("n_games", 0))
                    })
        
        # Limitar a 5 anyrole matchups (igual ao script do PowerShell)
        anyrole_matchups = anyrole_matchups[:5]
        
        return {
            "diretos": matchups_diretos,
            "anyrole": anyrole_matchups
        }
    
    def get_available_leagues(self):
        """Retorna lista de ligas disponíveis, incluindo 'MAJOR'."""
        if not self.load_models():
            return []
        
        if self.champion_impacts is None or self.champion_impacts.empty:
            return []
        
        leagues = sorted(self.champion_impacts["league"].unique().tolist())
        # Adicionar "MAJOR" no início da lista
        if "MAJOR" not in leagues:
            leagues.insert(0, "MAJOR")
        return leagues
