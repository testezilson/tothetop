"""
Módulo core para análise de pré-bets do LoL.
Calcula probabilidades, EV, fair odds, etc.
"""
import pandas as pd
from core.shared.paths import path_in_data


class LoLPrebetsAnalyzer:
    """Analisador de pré-bets do LoL."""
    
    def __init__(self):
        self.oracle_data = None
        self._loaded = False
    
    def load_data(self):
        """Carrega dados do Oracle."""
        if self._loaded:
            return True
        
        try:
            oracle_path = path_in_data("oracle_prepared.csv")
            self.oracle_data = pd.read_csv(oracle_path)
            self._loaded = True
            return True
        except Exception as e:
            print(f"Erro ao carregar dados: {e}")
            return False
    
    def calculate_h2h(self, team1, team2, league=None):
        """
        Calcula head-to-head entre dois times.
        
        Args:
            team1: Nome do time 1
            team2: Nome do time 2
            league: Liga específica (opcional, pode ser "MAJOR")
        
        Returns:
            Dict com estatísticas H2H
        """
        if not self.load_data():
            return None
        
        df = self.oracle_data.copy()
        
        # Filtrar por liga se especificada
        if league:
            # Se league for "MAJOR", usar lista de ligas major
            from core.shared.utils import MAJOR_LEAGUES
            if league == "MAJOR":
                df = df[df["league"].isin(MAJOR_LEAGUES)]
            else:
                df = df[df["league"] == league]
        
        # Buscar partidas entre os dois times
        mask = (
            ((df["teamname"] == team1) & (df.get("opponent", pd.Series())) == team2) |
            ((df["teamname"] == team2) & (df.get("opponent", pd.Series())) == team1)
        )
        
        # Se não tiver coluna opponent, usar gameid para agrupar
        if "opponent" not in df.columns:
            # Agrupar por gameid e verificar se ambos os times estão no mesmo jogo
            games = df[df["teamname"].isin([team1, team2])].groupby("gameid")
            gameids = []
            for gameid, group in games:
                teams_in_game = set(group["teamname"].unique())
                if team1 in teams_in_game and team2 in teams_in_game:
                    gameids.append(gameid)
            
            if not gameids:
                return {
                    "total_games": 0,
                    "team1_wins": 0,
                    "team2_wins": 0,
                    "team1_winrate": 0.5,
                    "team2_winrate": 0.5
                }
            
            df_h2h = df[df["gameid"].isin(gameids)]
        else:
            df_h2h = df[mask]
        
        # Determinar vencedor de cada jogo
        total_games = len(df_h2h["gameid"].unique())
        team1_wins = 0
        team2_wins = 0
        
        for gameid in df_h2h["gameid"].unique():
            game_rows = df_h2h[df_h2h["gameid"] == gameid]
            if len(game_rows) != 2:
                continue
            
            # Verificar qual time venceu
            if "result" in game_rows.columns:
                t1_row = game_rows[game_rows["teamname"] == team1]
                if not t1_row.empty and t1_row.iloc[0]["result"] == 1:
                    team1_wins += 1
                else:
                    team2_wins += 1
            else:
                # Usar kills como fallback
                t1_kills = game_rows[game_rows["teamname"] == team1]["teamkills"].iloc[0]
                t2_kills = game_rows[game_rows["teamname"] == team2]["teamkills"].iloc[0]
                if t1_kills > t2_kills:
                    team1_wins += 1
                else:
                    team2_wins += 1
        
        return {
            "total_games": total_games,
            "team1_wins": team1_wins,
            "team2_wins": team2_wins,
            "team1_winrate": team1_wins / total_games if total_games > 0 else 0.5,
            "team2_winrate": team2_wins / total_games if total_games > 0 else 0.5
        }
    
    def calculate_ev(self, probability, odd):
        """
        Calcula Expected Value (EV).
        
        Args:
            probability: Probabilidade real (0-1)
            odd: Odd da casa de apostas
        
        Returns:
            EV em porcentagem
        """
        if probability <= 0 or odd <= 1:
            return 0.0
        
        ev = (probability * (odd - 1)) - (1 - probability)
        return ev * 100  # Retornar em porcentagem
    
    def calculate_fair_odd(self, probability):
        """
        Calcula a odd justa baseada na probabilidade.
        
        Args:
            probability: Probabilidade real (0-1)
        
        Returns:
            Odd justa
        """
        if probability <= 0:
            return None
        return 1.0 / probability
    
    def analyze_bet(self, market_type, team1=None, team2=None, line=None, odd=None, league=None):
        """
        Analisa uma aposta específica.
        
        Args:
            market_type: Tipo de mercado ("Map Winner", "Total Kills", etc.)
            team1: Nome do time 1 (para Map Winner)
            team2: Nome do time 2 (para Map Winner)
            line: Linha da aposta (para Total Kills)
            odd: Odd da casa
            league: Liga específica
        
        Returns:
            Dict com análise completa
        """
        if market_type == "Map Winner":
            if not team1 or not team2:
                return None
            
            h2h = self.calculate_h2h(team1, team2, league)
            if h2h is None:
                return None
            
            prob_team1 = h2h["team1_winrate"]
            prob_team2 = h2h["team2_winrate"]
            
            ev_team1 = self.calculate_ev(prob_team1, odd) if odd else None
            ev_team2 = self.calculate_ev(prob_team2, odd) if odd else None
            
            fair_odd_team1 = self.calculate_fair_odd(prob_team1)
            fair_odd_team2 = self.calculate_fair_odd(prob_team2)
            
            return {
                "market_type": market_type,
                "team1": team1,
                "team2": team2,
                "probability_team1": prob_team1,
                "probability_team2": prob_team2,
                "ev_team1": ev_team1,
                "ev_team2": ev_team2,
                "fair_odd_team1": fair_odd_team1,
                "fair_odd_team2": fair_odd_team2,
                "h2h": h2h
            }
        
        # Outros tipos de mercado podem ser adicionados aqui
        return None
    
    def get_available_teams(self, league=None):
        """Retorna lista de times disponíveis."""
        if not self.load_data():
            return []
        
        df = self.oracle_data.copy()
        if league:
            # Se league for "MAJOR", usar lista de ligas major
            from core.shared.utils import MAJOR_LEAGUES
            if league == "MAJOR":
                df = df[df["league"].isin(MAJOR_LEAGUES)]
            else:
                df = df[df["league"] == league]
        
        return sorted(df["teamname"].unique().tolist())
    
    def get_available_leagues(self):
        """Retorna lista de ligas disponíveis, incluindo 'MAJOR'."""
        if not self.load_data():
            return []
        
        leagues = sorted(self.oracle_data["league"].unique().tolist())
        # Adicionar "MAJOR" no início da lista
        if "MAJOR" not in leagues:
            leagues.insert(0, "MAJOR")
        return leagues
