"""
Módulo core para comparação de composições de campeões.
"""
import os
import pandas as pd
from itertools import combinations
from core.shared.paths import path_in_data
from core.shared.utils import MAJOR_LEAGUES


class LoLCompareAnalyzer:
    """Analisador de comparação de composições."""
    
    def __init__(self):
        self.data = {
            "champ_wr": None,
            "synergy_wr": None,
            "comp_wr": None,
            "matchup_wr": None
        }
        self._loaded = False
    
    def load_data(self):
        """Carrega todos os dados necessários."""
        if self._loaded:
            return True
        
        try:
            # Caminhos dos arquivos
            champ_wr_path = path_in_data("champion_winrates.csv")
            synergy_wr_path = path_in_data("synergy_winrates.csv")
            comp_wr_path = path_in_data("composition_winrates.csv")
            matchup_wr_path = path_in_data("matchup_winrates.csv")
            
            # Carregar dados
            if os.path.exists(champ_wr_path):
                self.data["champ_wr"] = pd.read_csv(champ_wr_path)
            
            if os.path.exists(synergy_wr_path):
                self.data["synergy_wr"] = pd.read_csv(synergy_wr_path)
            
            if os.path.exists(comp_wr_path):
                self.data["comp_wr"] = pd.read_csv(comp_wr_path)
            
            if os.path.exists(matchup_wr_path):
                self.data["matchup_wr"] = pd.read_csv(matchup_wr_path)
            
            self._loaded = True
            return True
        except Exception as e:
            print(f"[ERRO] Erro ao carregar dados: {e}")
            return False
    
    def get_available_leagues(self):
        """Retorna lista de ligas disponíveis, incluindo 'MAJOR'."""
        if not self.load_data():
            return []
        
        leagues = set()
        if self.data["champ_wr"] is not None:
            leagues.update(self.data["champ_wr"]["league"].unique())
        if self.data["synergy_wr"] is not None:
            leagues.update(self.data["synergy_wr"]["league"].unique())
        if self.data["comp_wr"] is not None:
            leagues.update(self.data["comp_wr"]["league"].unique())
        if self.data["matchup_wr"] is not None:
            leagues.update(self.data["matchup_wr"]["league"].unique())
        
        leagues_list = sorted(list(leagues))
        # Adicionar "MAJOR" no início da lista
        if "MAJOR" not in leagues_list:
            leagues_list.insert(0, "MAJOR")
        return leagues_list
    
    def _get_champ_wr(self, leagues, champ):
        """Obtém win rate e número de jogos de um campeão."""
        # Se for múltiplas ligas (MAJOR), recalcular do CSV Oracle's Elixir mais recente
        # (fallback oracle_prepared.csv) para incluir todas as ligas.
        if isinstance(leagues, list) and len(leagues) > 1:
            return self._get_champ_wr_from_oracle(leagues, champ)
        
        # Liga única: usar champion_winrates.csv
        if self.data["champ_wr"] is None:
            return 50.0, 0
        
        if isinstance(leagues, str):
            leagues = [leagues]
        
        mask = self.data["champ_wr"]["league"].isin(leagues) & \
               (self.data["champ_wr"]["champion"].str.casefold() == str(champ).casefold())
        row = self.data["champ_wr"][mask]
        
        if not row.empty:
            if len(row) > 1:
                total_games = row["games_played"].sum()
                if total_games > 0:
                    weighted_wr = (row["win_rate"] * row["games_played"]).sum() / total_games
                    return float(weighted_wr), int(total_games)
            return float(row["win_rate"].iloc[0]), int(row["games_played"].iloc[0])
        return 50.0, 0
    
    def _get_champ_wr_from_oracle(self, leagues, champ):
        """Recalcula win rate a partir do CSV Oracle's Elixir mais recente (fallback: oracle_prepared.csv)."""
        from core.lol.oracle_team_games import get_draft_oracle_dataframe
        import pandas as pd

        df = get_draft_oracle_dataframe()
        if df is None or df.empty:
            return 50.0, 0
        
        # Filtrar por ligas
        df = df[df["league"].isin(leagues)]
        
        # Determinar vencedor de cada jogo
        winners = {}
        for gameid, df_game in df.groupby("gameid"):
            if len(df_game) != 2:
                continue
            t1_kills = df_game.iloc[0]["teamkills"]
            t2_kills = df_game.iloc[1]["teamkills"]
            if t1_kills > t2_kills:
                winners[gameid] = df_game.iloc[0]["teamname"]
            elif t2_kills > t1_kills:
                winners[gameid] = df_game.iloc[1]["teamname"]
        
        # Adicionar coluna de vitória
        df["won"] = df.apply(
            lambda row: 1 if winners.get(row["gameid"]) == row["teamname"] else 0,
            axis=1
        )
        
        # Buscar partidas onde o campeão jogou
        mask = (
            (df["pick1"].str.casefold() == str(champ).casefold()) |
            (df["pick2"].str.casefold() == str(champ).casefold()) |
            (df["pick3"].str.casefold() == str(champ).casefold()) |
            (df["pick4"].str.casefold() == str(champ).casefold()) |
            (df["pick5"].str.casefold() == str(champ).casefold())
        )
        
        champ_games = df[mask]
        
        if len(champ_games) == 0:
            return 50.0, 0
        
        # Contar jogos únicos (cada partida aparece 2 vezes - uma por time)
        # Mas queremos contar quantas vezes o campeão jogou, não quantas partidas únicas
        total_games = len(champ_games)
        wins = int(champ_games["won"].sum())
        win_rate = (wins / total_games) * 100 if total_games > 0 else 50.0
        
        return float(win_rate), int(total_games)
    
    def _get_synergy_wr(self, leagues, champ1, champ2):
        """Obtém win rate e impacto de uma sinergia."""
        if self.data["synergy_wr"] is None:
            return 0.0, 50.0, 0
        
        if isinstance(leagues, str):
            leagues = [leagues]
        
        c1, c2 = sorted([champ1, champ2])
        mask = self.data["synergy_wr"]["league"].isin(leagues) & \
               (self.data["synergy_wr"]["champ1"].str.casefold() == str(c1).casefold()) & \
               (self.data["synergy_wr"]["champ2"].str.casefold() == str(c2).casefold())
        row = self.data["synergy_wr"][mask]
        
        if not row.empty:
            if len(row) > 1:
                total_games = row["n_games"].sum()
                if total_games > 0:
                    weighted_wr = (row["win_rate"] * row["n_games"]).sum() / total_games
                    weighted_impact = (row["synergy_impact"] * row["n_games"]).sum() / total_games
                    return float(weighted_impact), float(weighted_wr), int(total_games)
            return (
                float(row["synergy_impact"].iloc[0]),
                float(row["win_rate"].iloc[0]),
                int(row["n_games"].iloc[0])
            )
        return 0.0, 50.0, 0
    
    def _get_comp_wr(self, leagues, composition):
        """Obtém win rate de uma composição completa."""
        if self.data["comp_wr"] is None:
            return None
        
        if isinstance(leagues, str):
            leagues = [leagues]
        
        comp_key = "|".join(sorted(composition))
        mask = self.data["comp_wr"]["league"].isin(leagues) & \
               (self.data["comp_wr"]["composition"] == comp_key)
        row = self.data["comp_wr"][mask]
        
        if not row.empty:
            if len(row) > 1:
                total_games = row["games"].sum()
                total_wins = row["wins"].sum()
                if total_games > 0:
                    avg_wr = (total_wins / total_games) * 100
                    return {
                        "win_rate": float(avg_wr),
                        "games": int(total_games),
                        "wins": int(total_wins)
                    }
            return {
                "win_rate": float(row["win_rate"].iloc[0]),
                "games": int(row["games"].iloc[0]),
                "wins": int(row["wins"].iloc[0])
            }
        return None
    
    def _get_matchup_wr(self, leagues, champ1, champ2):
        """Obtém win rate de um matchup."""
        if self.data["matchup_wr"] is None:
            return 50.0, 0
        
        if isinstance(leagues, str):
            leagues = [leagues]
        
        mask = self.data["matchup_wr"]["league"].isin(leagues) & \
               (self.data["matchup_wr"]["champ1"].str.casefold() == str(champ1).casefold()) & \
               (self.data["matchup_wr"]["champ2"].str.casefold() == str(champ2).casefold())
        row = self.data["matchup_wr"][mask]
        
        if not row.empty:
            if len(row) > 1:
                total_games = row["games"].sum()
                if total_games > 0:
                    weighted_wr = (row["win_rate"] * row["games"]).sum() / total_games
                    return float(weighted_wr), int(total_games)
            return float(row["win_rate"].iloc[0]), int(row["games"].iloc[0])
        return 50.0, 0
    
    def _calculate_team_score(self, leagues, composition):
        """Calcula um score para a composição baseado em múltiplos fatores."""
        score = 0.0
        factors = {}
        
        # 1. Win rate médio dos campeões individuais
        champ_wrs = []
        champ_details = []
        for champ in composition:
            wr, games = self._get_champ_wr(leagues, champ)
            champ_wrs.append(wr)
            champ_details.append({"champion": champ, "win_rate": wr, "games": games})
        avg_champ_wr = sum(champ_wrs) / len(champ_wrs)
        factors["avg_champ_wr"] = avg_champ_wr
        factors["champ_details"] = champ_details
        score += avg_champ_wr * 0.3  # 30% do peso
        
        # 2. Sinergias internas (todos os pares)
        synergy_impacts = []
        synergy_details = []
        for c1, c2 in combinations(composition, 2):
            impact, wr, games = self._get_synergy_wr(leagues, c1, c2)
            synergy_impacts.append(impact)
            synergy_details.append({
                "champ1": c1,
                "champ2": c2,
                "win_rate": wr,
                "impact": impact,
                "games": games
            })
        avg_synergy = sum(synergy_impacts) / len(synergy_impacts) if synergy_impacts else 0
        factors["avg_synergy_impact"] = avg_synergy
        factors["synergy_details"] = synergy_details
        score += (50 + avg_synergy) * 0.3  # 30% do peso
        
        # 3. Win rate da composição completa (se disponível)
        comp_data = self._get_comp_wr(leagues, composition)
        if comp_data:
            factors["comp_wr"] = comp_data["win_rate"]
            factors["comp_games"] = comp_data["games"]
            score += comp_data["win_rate"] * 0.4  # 40% do peso se disponível
        else:
            factors["comp_wr"] = None
            # Se não tem dados da comp completa, aumenta peso dos outros fatores
            score = score / 0.6  # Normaliza para 100%
        
        factors["total_score"] = score
        return score, factors
    
    def compare_compositions(self, league, comp1, comp2):
        """
        Compara duas composições e retorna análise detalhada.
        
        Args:
            league: Nome da liga (ex: "LCK", "LPL", "MAJOR") ou lista de ligas
            comp1: Lista de 5 campeões do time 1
            comp2: Lista de 5 campeões do time 2
        
        Returns:
            Dict com resultados completos da comparação
        """
        if not self.load_data():
            return None
        
        # Se league for "MAJOR", usar lista de ligas major
        if league == "MAJOR":
            # Verificar em todos os arquivos de dados
            all_leagues = set()
            for key in ["champ_wr", "synergy_wr", "comp_wr", "matchup_wr"]:
                if self.data[key] is not None:
                    all_leagues.update(self.data[key]["league"].unique())
            
            # Ordem específica: LCK, LPL, LCS, CBLOL, LCP, LEC
            ordem_major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]
            # Incluir todas as ligas major que existem nos dados OU que são major (incluindo LCS mesmo sem dados)
            # Se LCS não estiver nos dados, ainda assim incluí-la se for major
            league = []
            for lg in ordem_major:
                if lg in MAJOR_LEAGUES:
                    # Incluir se estiver nos dados OU se for LCS (sempre incluir LCS como major)
                    if lg in all_leagues or lg == "LCS":
                        league.append(lg)
        
        # Calcular scores
        score1, factors1 = self._calculate_team_score(league, comp1)
        score2, factors2 = self._calculate_team_score(league, comp2)
        
        # Comparação
        diff = score1 - score2
        winner = "Time 1" if diff > 0 else "Time 2" if diff < 0 else "Empate"
        
        # Matchups individuais
        matchup_details = []
        matchup_scores = []
        positions = ["Top", "Jungle", "Mid", "ADC", "Support"]
        for i, c1 in enumerate(comp1):
            for j, c2 in enumerate(comp2):
                wr, games = self._get_matchup_wr(league, c1, c2)
                matchup_details.append({
                    "champ1": c1,
                    "champ2": c2,
                    "pos1": positions[i],
                    "pos2": positions[j],
                    "win_rate": wr,
                    "games": games
                })
                if games > 0:
                    matchup_scores.append(wr)
        
        avg_matchup = sum(matchup_scores) / len(matchup_scores) if matchup_scores else 0.0

        # Prob. calibrada (draft prior) se o calibrador existir
        try:
            from core.lol.draft_prior import calibrated_draft_prob
            p_draft = calibrated_draft_prob(score1, score2)
        except Exception:
            p_draft = None

        return {
            "league": league,
            "comp1": comp1,
            "comp2": comp2,
            "winner": winner,
            "score1": score1,
            "score2": score2,
            "difference": abs(diff),
            "factors1": factors1,
            "factors2": factors2,
            "matchup_details": matchup_details,
            "avg_matchup_wr": avg_matchup,
            "matchups_with_data": len(matchup_scores),
            "p_draft_calibrated": p_draft,
        }
