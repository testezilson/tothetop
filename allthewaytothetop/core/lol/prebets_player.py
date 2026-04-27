"""
Módulo core para análise de pré-bets de players (kills, deaths, assists).
"""
import sqlite3
import pandas as pd
import numpy as np
import os
from core.shared.paths import get_lol_db_path

# NÃO importar db_converter no nível do módulo (PyInstaller)


def buscar_player_recent(conn, player_name: str, stat: str, n_recent: int):
    """
    Retorna uma lista dos valores do player nos últimos n jogos, com adversário.
    Ordenado do mais recente para o menos recente.
    
    Args:
        conn: Conexão SQLite
        player_name: Nome do player
        stat: Estatística ('kills', 'deaths', 'assists')
        n_recent: Número de jogos recentes
    
    Returns:
        Lista de dicts com 'value' e 'opponent' (mais recente primeiro)
    """
    stat = stat.lower()
    
    if stat not in ['kills', 'deaths', 'assists']:
        raise ValueError(f"Estatística inválida: {stat}. Use: kills, deaths ou assists")
    
    # Time do jogador (o1.teamname) + adversário (outro time no mesmo jogo)
    query = """
        SELECT 
            o1.date,
            o1.gameid,
            o1.teamname AS team,
            o1.{stat} AS value,
            (SELECT o2.teamname FROM oracle_matches o2 
             WHERE o2.gameid = o1.gameid AND o2.teamname != o1.teamname 
             LIMIT 1) AS opponent
        FROM oracle_matches o1
        WHERE o1.playername IS NOT NULL AND trim(o1.playername) != ''
          AND o1.playername COLLATE NOCASE = ?
          AND o1.{stat} IS NOT NULL
          AND o1.date IS NOT NULL AND trim(o1.date) != ''
        ORDER BY o1.date DESC, o1.gameid DESC
        LIMIT ?
    """.format(stat=stat)
    
    df = pd.read_sql_query(query, conn, params=(player_name, n_recent))
    
    if df.empty:
        return []
    
    # Garantir que está ordenado do mais recente para o menos recente
    if 'date' in df.columns and len(df) > 0:
        try:
            df['date_parsed'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.sort_values('date_parsed', ascending=False, na_position='last')
            if df['date_parsed'].isna().any():
                df_null = df[df['date_parsed'].isna()]
                df_not_null = df[df['date_parsed'].notna()]
                df = pd.concat([df_not_null, df_null.sort_values('gameid', ascending=False)])
        except Exception:
            pass
    
    # Retornar lista de dicts com value, team e opponent (confronto completo)
    result = []
    for _, row in df.iterrows():
        val = row.get('value')
        if pd.notna(val):
            team = str(row.get('team', '')).strip() if pd.notna(row.get('team')) else "—"
            opp = row.get('opponent')
            opponent = str(opp).strip() if pd.notna(opp) else "—"
            result.append({"value": float(val), "team": team, "opponent": opponent})
    return result


def calc_ev_pinnacle(prob: float, odd: float, stake=1.0):
    """
    Calcula EV (Expected Value) no formato Pinnacle.
    
    Returns:
        (ev, ev_pct, fair_odd)
    """
    win = (odd - 1.0) * stake
    lose = stake
    ev = prob * win - (1 - prob) * lose
    fair = 1/prob if prob > 0 else np.inf
    return ev, ev/stake, fair


class LoLPlayerBetsAnalyzer:
    """Analisador de pré-bets de players (kills, deaths, assists)."""
    
    def __init__(self):
        self.db_path = None
    
    def get_db_path(self):
        """Retorna o caminho do banco de dados. Sempre resolve de novo (nao cacheia) para usar o DB atualizado apos 'Atualizar Banco'."""
        self.db_path = get_lol_db_path()
        if not self.db_path or not os.path.exists(self.db_path):
            try:
                from core.lol.db_converter import ensure_db_exists
                self.db_path = ensure_db_exists()
            except ImportError as e:
                print(f"Erro ao importar db_converter: {e}")
                self.db_path = None
            except Exception as e:
                print(f"Erro ao criar banco: {e}")
                self.db_path = None
        return self.db_path
    
    def analyze_bet(self, player_name, stat, line, odd_over, odd_under, n_recent=10):
        """
        Analisa uma aposta de player.
        
        Args:
            player_name: Nome do player
            stat: Estatística ('kills', 'deaths', 'assists')
            line: Linha da aposta (ex: 5.5)
            odd_over: Odd Over
            odd_under: Odd Under
            n_recent: Quantos jogos recentes usar
        
        Returns:
            Dict com análise completa ou None em caso de erro
        """
        db_path = self.get_db_path()
        if db_path is None:
            return {"error": "Banco de dados não encontrado."}
        
        # Criar conexão dentro desta função (para evitar problemas de threading)
        conn = sqlite3.connect(db_path)
        
        try:
            # Buscar dados do player (lista de dicts com value e opponent)
            raw = buscar_player_recent(conn, player_name, stat, n_recent)
            
            if not raw:
                return {
                    "error": f"Nenhum dado encontrado para {player_name} na estatística {stat}.",
                    "games_found": 0
                }
            
            vals = [x["value"] for x in raw]
            
            if len(vals) < n_recent:
                games_warning = f"Apenas {len(vals)} jogos encontrados (solicitados {n_recent})"
            else:
                games_warning = None
            
            # Calcular estatísticas
            arr = np.array(vals, dtype=float)
            mean = np.mean(arr)
            median = np.median(arr)
            std = np.std(arr)
            
            over_mask = arr > line
            over_count = int(over_mask.sum())
            under_count = len(arr) - over_count
            over_rate = over_count / len(arr) if len(arr) > 0 else 0
            under_rate = 1 - over_rate
            
            # Calcular probabilidades e EV
            prob_over = over_rate
            prob_under = under_rate
            
            ev_over, ev_over_pct, fair_over = calc_ev_pinnacle(prob_over, odd_over)
            ev_under, ev_under_pct, fair_under = calc_ev_pinnacle(prob_under, odd_under)
            
            return {
                "player_name": player_name,
                "stat": stat,
                "line": line,
                "odd_over": odd_over,
                "odd_under": odd_under,
                "games_found": len(vals),
                "games_requested": n_recent,
                "games_warning": games_warning,
                "mean": mean,
                "median": median,
                "std": std,
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "over_count": over_count,
                "under_count": under_count,
                "prob_over": prob_over,
                "prob_under": prob_under,
                "ev_over": ev_over,
                "ev_over_pct": ev_over_pct,
                "ev_under": ev_under,
                "ev_under_pct": ev_under_pct,
                "fair_over": fair_over,
                "fair_under": fair_under,
                "last_values": raw[:10],  # Últimos 10 (cada item tem value e opponent)
                "recommendation": self._get_recommendation(ev_over, ev_under, line)
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()
    
    def _get_recommendation(self, ev_over, ev_under, line):
        """Retorna recomendação baseada em EV."""
        if ev_over > 0 and ev_under > 0:
            if ev_over > ev_under:
                return f"OVER {line} (EV {ev_over:+.2f}u)"
            else:
                return f"UNDER {line} (EV {ev_under:+.2f}u)"
        elif ev_over > 0:
            return f"OVER {line} (EV {ev_over:+.2f}u)"
        elif ev_under > 0:
            return f"UNDER {line} (EV {ev_under:+.2f}u)"
        else:
            return "Nenhuma aposta com EV positivo"
    
    def get_available_players(self, search_term=""):
        """Busca players disponíveis no banco (busca parcial, case-insensitive)."""
        db_path = self.get_db_path()
        if db_path is None:
            return []
        
        conn = sqlite3.connect(db_path)
        try:
            if not search_term:
                query = """
                    SELECT DISTINCT playername 
                    FROM oracle_matches 
                    WHERE playername IS NOT NULL AND playername != ''
                    ORDER BY playername
                """
                df = pd.read_sql_query(query, conn)
            else:
                query = """
                    SELECT DISTINCT playername 
                    FROM oracle_matches 
                    WHERE playername COLLATE NOCASE LIKE ?
                    ORDER BY playername
                """
                df = pd.read_sql_query(query, conn, params=(f"%{search_term}%",))
            
            return df["playername"].tolist()
        except Exception as e:
            print(f"Erro ao buscar players: {e}")
            return []
        finally:
            conn.close()
    
    def get_available_stats(self):
        """Retorna lista de estatísticas disponíveis."""
        return ["kills", "deaths", "assists"]
