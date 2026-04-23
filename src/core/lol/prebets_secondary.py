"""
Módulo core para análise de pré-bets secundárias (kills, torres, dragons, barons, gamelength).
"""
import sqlite3
import pandas as pd
import numpy as np
import os
from core.shared.paths import get_data_dir, get_lol_db_path

# NÃO importar db_converter no nível do módulo (PyInstaller)


def _get_team_column(conn):
    """Detecta qual coluna de time existe no banco (teamname ou team)."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(oracle_matches)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'teamname' in columns:
        return 'teamname'
    elif 'team' in columns:
        return 'team'
    else:
        raise ValueError("Nenhuma coluna de time encontrada (teamname ou team)")


def _db_has_required_columns(conn, stat):
    """Para kills precisa de opponentkills; para barons/towers/dragons precisa de col+opp_col. Retorna False se faltar coluna."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(oracle_matches)")
    cols = {row[1] for row in cursor.fetchall()}
    if stat == "kills" and ("opponentkills" not in cols or "teamkills" not in cols):
        return False
    if stat == "barons" and ("barons" not in cols or "opp_barons" not in cols):
        return False
    if stat == "towers" and ("towers" not in cols or "opp_towers" not in cols):
        return False
    if stat == "dragons" and ("dragons" not in cols or "opp_dragons" not in cols):
        return False
    return True


# Estatísticas "first" (binárias: qual time pegou o objetivo)
FIRST_STATS = frozenset({"firstdragon", "firsttower", "firstherald"})

# Aliases de nomes de times: no banco podem vir "DK" ou "Dplus Kia"; buscar por qualquer um retorna os mesmos jogos.
TEAM_ALIASES = {
    "Dplus Kia": ["DK", "Dplus KIA"],
    "DK": ["Dplus Kia", "Dplus KIA"],
}


def _team_query_names(team_name):
    """Retorna lista de nomes para usar na query (time + aliases) para não pular jogos por variação de nome."""
    if not team_name or not str(team_name).strip():
        return []
    name = str(team_name).strip()
    aliases = TEAM_ALIASES.get(name, [])
    if not isinstance(aliases, (list, tuple)):
        aliases = [aliases] if aliases else []
    seen = {name.lower()}
    result = [name]
    for a in aliases:
        a_str = str(a).strip() if a else ""
        if a_str and a_str.lower() not in seen:
            seen.add(a_str.lower())
            result.append(a_str)
    return result


def fetch_team_recent(conn, team_name, stat, limit_games=10):
    """
    Retorna uma lista dos valores nos últimos n jogos (do time como filtro de quais partidas).
    Para kills, towers, dragons, barons: TOTAL DA PARTIDA (soma dos dois times).
    Para firstdragon/firsttower/firstherald: 0 ou 1 (time pegou ou não).
    Para gamelength: duração em minutos da partida.
    """
    stat = stat.lower()
    team_col = _get_team_column(conn)
    names = _team_query_names(team_name)
    if not names:
        return []
    ph = ", ".join("?" for _ in names)

    # Caso especial: first objectives (binário por jogo)
    if stat in FIRST_STATS:
        query = f"""
            WITH team_gameids AS (
                SELECT DISTINCT gameid, MAX(date) AS date
                FROM oracle_matches
                WHERE {team_col} COLLATE NOCASE IN ({ph})
                GROUP BY gameid
            ),
            team_first AS (
                SELECT gameid, {team_col} AS team, MAX({stat}) AS value
                FROM oracle_matches
                WHERE {stat} IS NOT NULL
                GROUP BY gameid, {team_col}
            )
            SELECT tf.value, tg.date
            FROM team_first tf
            INNER JOIN team_gameids tg ON tg.gameid = tf.gameid AND tf.team COLLATE NOCASE IN ({ph})
            WHERE tg.date IS NOT NULL AND trim(tg.date) != ''
            ORDER BY datetime(trim(tg.date)) DESC, tg.gameid DESC
            LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(*names, *names, limit_games))
        if df.empty or df["date"].isna().all():
            query_fallback = f"""
                WITH team_gameids AS (
                    SELECT DISTINCT gameid
                    FROM oracle_matches
                    WHERE {team_col} COLLATE NOCASE IN ({ph})
                    GROUP BY gameid
                ),
                team_first AS (
                    SELECT gameid, {team_col} AS team, MAX({stat}) AS value
                    FROM oracle_matches
                    WHERE {stat} IS NOT NULL
                    GROUP BY gameid, {team_col}
                )
                SELECT tf.value
                FROM team_first tf
                INNER JOIN team_gameids tg ON tg.gameid = tf.gameid AND tf.team COLLATE NOCASE IN ({ph})
                ORDER BY tg.gameid DESC
                LIMIT ?
            """
            df = pd.read_sql_query(query_fallback, conn, params=(*names, *names, limit_games))
        return df["value"].dropna().astype(int).tolist()
    
    # Caso especial: gamelength
    if stat == "gamelength":
        query = f"""
            WITH team_gameids AS (
                SELECT DISTINCT gameid, MAX(date) AS date
                FROM oracle_matches
                WHERE {team_col} COLLATE NOCASE IN ({ph})
                GROUP BY gameid
            ),
            per_game AS (
                SELECT 
                    gameid, 
                    MAX(gamelength) AS gl_sec, 
                    MAX(date) AS date
                FROM oracle_matches
                GROUP BY gameid
            )
            SELECT (g.gl_sec/60.0) AS total_min, tg.date
            FROM per_game g
            INNER JOIN team_gameids tg ON tg.gameid = g.gameid
            WHERE tg.date IS NOT NULL AND trim(tg.date) != ''
            ORDER BY datetime(trim(tg.date)) DESC, tg.gameid DESC
            LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(*names, limit_games))
        # Se não houver datas válidas, tentar ordenar por gameid
        if df.empty or df["date"].isna().all():
            query_fallback = f"""
                WITH team_gameids AS (
                    SELECT DISTINCT gameid
                    FROM oracle_matches
                    WHERE {team_col} COLLATE NOCASE IN ({ph})
                    GROUP BY gameid
                ),
                per_game AS (
                    SELECT
                        gameid,
                        MAX(gamelength) AS gl_sec
                    FROM oracle_matches
                    GROUP BY gameid
                )
                SELECT (g.gl_sec/60.0) AS total_min
                FROM per_game g
                INNER JOIN team_gameids tg ON tg.gameid = g.gameid
                ORDER BY tg.gameid DESC
                LIMIT ?
            """
            df = pd.read_sql_query(query_fallback, conn, params=(*names, limit_games))
        return df["total_min"].dropna().tolist()

    # Kills, towers, dragons, barons: TOTAL DA PARTIDA por jogo.
    # Usar (col + opp_col) por linha e GROUP BY gameid: 1 valor por jogo, sem depender de JOIN entre times.
    # Assim evitamos erros por nomes duplicados ou times faltando e batemos com o CSV (barons+opp_barons).
    if stat == "kills":
        total_expr = "MAX(COALESCE(teamkills,0) + COALESCE(opponentkills,0))"
    elif stat == "barons":
        total_expr = "MAX(COALESCE(barons,0) + COALESCE(opp_barons,0))"
    elif stat == "towers":
        total_expr = "MAX(COALESCE(towers,0) + COALESCE(opp_towers,0))"
    elif stat == "dragons":
        total_expr = "MAX(COALESCE(dragons,0) + COALESCE(opp_dragons,0))"
    else:
        total_expr = "MAX(COALESCE(teamkills,0) + COALESCE(opponentkills,0))"  # fallback kills
    # Ordenar por datetime normalizado: evita que jogos com date só "YYYY-MM-DD" (sem hora)
    # fiquem depois de "YYYY-MM-DD HH:MM:SS" na ordenação textual e sejam pulados do "últimos 10"
    query = f"""
        WITH ordered_gameids AS (
            SELECT gameid, MAX(trim(date)) AS date
            FROM oracle_matches
            WHERE {team_col} COLLATE NOCASE IN ({ph})
              AND date IS NOT NULL AND trim(date) != ''
            GROUP BY gameid
            ORDER BY datetime(trim(MAX(trim(date)))) DESC, gameid DESC
            LIMIT ?
        ),
        game_totals AS (
            SELECT gameid, {total_expr} AS total
            FROM oracle_matches
            GROUP BY gameid
        )
        SELECT gt.total, o.date
        FROM ordered_gameids o
        INNER JOIN game_totals gt ON gt.gameid = o.gameid
        ORDER BY datetime(trim(o.date)) DESC, o.gameid DESC
    """
    df = pd.read_sql_query(query, conn, params=(*names, limit_games))
    if not df.empty:
        return df["total"].dropna().tolist()
    query_fallback = f"""
        WITH ordered_gameids AS (
            SELECT gameid
            FROM oracle_matches
            WHERE {team_col} COLLATE NOCASE IN ({ph})
            GROUP BY gameid
            ORDER BY gameid DESC
            LIMIT ?
        ),
        game_totals AS (
            SELECT gameid, {total_expr} AS total
            FROM oracle_matches
            GROUP BY gameid
        )
        SELECT gt.total
        FROM ordered_gameids o
        INNER JOIN game_totals gt ON gt.gameid = o.gameid
        ORDER BY o.gameid DESC
    """
    df = pd.read_sql_query(query_fallback, conn, params=(*names, limit_games))
    return df["total"].dropna().tolist()


def fetch_team_recent_with_opponent(conn, team_name, stat, limit_games=10):
    """
    Retorna os últimos N jogos do time com valor (total kills, gamelength em min, etc) e adversário.
    Para conferência: lista de {"value": float, "opponent": str}.
    Usa a mesma ordenação e a mesma definição de valor que fetch_team_recent (ex.: gamelength = minutos).
    """
    stat = stat.lower()
    team_col = _get_team_column(conn)
    names = _team_query_names(team_name)
    if not names:
        return []
    ph = ", ".join("?" for _ in names)

    # Gamelength: valor em minutos (gl_sec/60), mesma lógica que fetch_team_recent
    if stat == "gamelength":
        query = f"""
            WITH ordered_gameids AS (
                SELECT gameid, MAX(trim(date)) AS date
                FROM oracle_matches
                WHERE {team_col} COLLATE NOCASE IN ({ph})
                  AND date IS NOT NULL AND trim(date) != ''
                GROUP BY gameid
                ORDER BY datetime(trim(MAX(trim(date)))) DESC, gameid DESC
                LIMIT ?
            ),
            per_game AS (
                SELECT gameid, MAX(gamelength) AS gl_sec
                FROM oracle_matches
                GROUP BY gameid
            ),
            game_opponent AS (
                SELECT o.gameid, MAX(o2.{team_col}) AS opponent
                FROM oracle_matches o
                JOIN oracle_matches o2 ON o.gameid = o2.gameid AND o2.{team_col} != o.{team_col}
                WHERE o.gameid IN (SELECT gameid FROM ordered_gameids)
                  AND o.{team_col} COLLATE NOCASE IN ({ph})
                GROUP BY o.gameid
            )
            SELECT (g.gl_sec / 60.0) AS value, COALESCE(go.opponent, '—') AS opponent
            FROM ordered_gameids og
            INNER JOIN per_game g ON g.gameid = og.gameid
            LEFT JOIN game_opponent go ON go.gameid = og.gameid
            ORDER BY datetime(trim(og.date)) DESC, og.gameid DESC
        """
        try:
            df = pd.read_sql_query(query, conn, params=(*names, limit_games, *names))
            out = []
            for _, row in df.iterrows():
                v = row.get("value")
                opp = row.get("opponent")
                if pd.notna(v):
                    out.append({"value": float(v), "opponent": str(opp).strip() if pd.notna(opp) else "—"})
            return out
        except Exception:
            return []

    if stat == "kills":
        total_expr = "MAX(COALESCE(teamkills,0) + COALESCE(opponentkills,0))"
    elif stat == "barons":
        total_expr = "MAX(COALESCE(barons,0) + COALESCE(opp_barons,0))"
    elif stat == "towers":
        total_expr = "MAX(COALESCE(towers,0) + COALESCE(opp_towers,0))"
    elif stat == "dragons":
        total_expr = "MAX(COALESCE(dragons,0) + COALESCE(opp_dragons,0))"
    else:
        total_expr = "MAX(COALESCE(teamkills,0) + COALESCE(opponentkills,0))"
    # Últimos N gameids (mesma ordenação por datetime)
    query = f"""
        WITH ordered_gameids AS (
            SELECT gameid, MAX(trim(date)) AS date
            FROM oracle_matches
            WHERE {team_col} COLLATE NOCASE IN ({ph})
              AND date IS NOT NULL AND trim(date) != ''
            GROUP BY gameid
            ORDER BY datetime(trim(MAX(trim(date)))) DESC, gameid DESC
            LIMIT ?
        ),
        game_totals AS (
            SELECT gameid, {total_expr} AS total
            FROM oracle_matches
            GROUP BY gameid
        ),
        game_opponent AS (
            SELECT o.gameid, MAX(o2.{team_col}) AS opponent
            FROM oracle_matches o
            JOIN oracle_matches o2 ON o.gameid = o2.gameid AND o2.{team_col} != o.{team_col}
            WHERE o.gameid IN (SELECT gameid FROM ordered_gameids)
              AND o.{team_col} COLLATE NOCASE IN ({ph})
            GROUP BY o.gameid
        )
        SELECT gt.total AS value, COALESCE(go.opponent, '—') AS opponent
        FROM ordered_gameids og
        INNER JOIN game_totals gt ON gt.gameid = og.gameid
        LEFT JOIN game_opponent go ON go.gameid = og.gameid
        ORDER BY datetime(trim(og.date)) DESC, og.gameid DESC
    """
    try:
        df = pd.read_sql_query(query, conn, params=(*names, limit_games, *names))
        out = []
        for _, row in df.iterrows():
            v = row.get("value")
            opp = row.get("opponent")
            if pd.notna(v):
                out.append({"value": float(v), "opponent": str(opp).strip() if pd.notna(opp) else "—"})
        return out
    except Exception:
        return []


def fetch_h2h_empirico(conn, team1, team2, stat, months, line):
    """
    Retorna estatísticas H2H recentes:
      - taxa de over
      - número de jogos
      - média
      - contagem de overs e unders
    
    Para first* stats: over = team1 pegou o objetivo (value=1), under = team2 pegou (value=0).
    """
    stat = stat.lower()
    team_col = _get_team_column(conn)
    names1 = _team_query_names(team1)
    names2 = _team_query_names(team2)
    if not names1 or not names2:
        return None, 0, 0.0, 0, 0
    ph1 = ", ".join("?" for _ in names1)
    ph2 = ", ".join("?" for _ in names2)

    if stat in FIRST_STATS:
        query = f"""
            WITH per_team AS (
                SELECT gameid, date, {team_col} AS team, MAX({stat}) AS value
                FROM oracle_matches
                WHERE {stat} IS NOT NULL
                GROUP BY gameid, {team_col}
            )
            SELECT t1.date, t1.value AS total
            FROM per_team t1
            JOIN per_team t2 ON t2.gameid = t1.gameid AND t2.team != t1.team
            WHERE t1.team COLLATE NOCASE IN ({ph1}) AND t2.team COLLATE NOCASE IN ({ph2})
        """
        df = pd.read_sql_query(query, conn, params=(*names1, *names2))
        if df.empty:
            return None, 0, 0.0, 0, 0
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        cutoff = pd.Timestamp.today() - pd.DateOffset(months=months)
        df = df[df["date"] >= cutoff]
        if df.empty:
            return None, 0, 0.0, 0, 0
        over_mask = df["total"] > line
        over = int(over_mask.sum())
        total = len(df)
        under = total - over
        over_rate = over / total
        mean_h2h = float(df["total"].mean())
        return over_rate, total, mean_h2h, over, under
    
    if stat == "gamelength":
        query = f"""
            WITH per_team AS (
                SELECT gameid, date, {team_col} AS team
                FROM oracle_matches
                GROUP BY gameid, {team_col}
            ),
            per_game AS (
                SELECT gameid, MAX(gamelength) AS gl_sec, MAX(date) AS date
                FROM oracle_matches
                GROUP BY gameid
            )
            SELECT
                g.date,
                (g.gl_sec/60.0) AS total_min
            FROM per_game g
            JOIN per_team t1 ON t1.gameid = g.gameid
            JOIN per_team t2 ON t2.gameid = g.gameid AND t2.team != t1.team
            WHERE t1.team COLLATE NOCASE IN ({ph1}) AND t2.team COLLATE NOCASE IN ({ph2})
        """
        df = pd.read_sql_query(query, conn, params=(*names1, *names2))
        if df.empty:
            return None, 0, 0.0, 0, 0
        
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        cutoff = pd.Timestamp.today() - pd.DateOffset(months=months)
        df = df[df["date"] >= cutoff]
        
        if df.empty:
            return None, 0, 0.0, 0, 0
        
        over_mask = df["total_min"] > line
        over = int(over_mask.sum())
        total = len(df)
        under = total - over
        over_rate = over / total
        mean_h2h = float(df["total_min"].mean())
        return over_rate, total, mean_h2h, over, under
    
    # Kills, towers, dragons, barons: total da partida por jogo H2H usando (col+opp_col), 1 linha por jogo.
    if stat == "kills":
        h2h_total_expr = "MAX(COALESCE(teamkills,0) + COALESCE(opponentkills,0))"
    elif stat == "barons":
        h2h_total_expr = "MAX(COALESCE(barons,0) + COALESCE(opp_barons,0))"
    elif stat == "towers":
        h2h_total_expr = "MAX(COALESCE(towers,0) + COALESCE(opp_towers,0))"
    elif stat == "dragons":
        h2h_total_expr = "MAX(COALESCE(dragons,0) + COALESCE(opp_dragons,0))"
    else:
        h2h_total_expr = "MAX(COALESCE(teamkills,0) + COALESCE(opponentkills,0))"
    query = f"""
        WITH h2h_games AS (
            SELECT o1.gameid, MAX(o1.date) AS date
            FROM oracle_matches o1
            JOIN oracle_matches o2 ON o1.gameid = o2.gameid AND o1.{team_col} != o2.{team_col}
            WHERE o1.{team_col} COLLATE NOCASE IN ({ph1}) AND o2.{team_col} COLLATE NOCASE IN ({ph2})
            GROUP BY o1.gameid
        ),
        game_totals AS (
            SELECT gameid, {h2h_total_expr} AS total
            FROM oracle_matches
            GROUP BY gameid
        )
        SELECT h.gameid, h.date, g.total
        FROM h2h_games h
        JOIN game_totals g ON g.gameid = h.gameid
    """
    df = pd.read_sql_query(query, conn, params=(*names1, *names2))
    if df.empty:
        return None, 0, 0.0, 0, 0
    # 1 linha por jogo (h2h_games já tem GROUP BY gameid)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    cutoff = pd.Timestamp.today() - pd.DateOffset(months=months)
    df = df[df["date"] >= cutoff]
    
    if df.empty:
        return None, 0, 0.0, 0, 0
    
    # Over = total da partida > linha; Under = total <= linha
    over_mask = df["total"] > line
    over = int(over_mask.sum())
    total = len(df)
    under = total - over
    over_rate = over / total if total > 0 else 0.0
    mean_h2h = float(df["total"].mean())
    return over_rate, total, mean_h2h, over, under




class LoLSecondaryBetsAnalyzer:
    """Analisador de pré-bets secundárias (kills, torres, dragons, barons, gamelength)."""
    
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
    
    def analyze_bet(self, team1, team2, stat, line, odd_over, odd_under, limit_games=10, h2h_months=3, use_h2h=False):
        """
        Analisa uma aposta secundária.
        
        Args:
            team1: Nome do time 1
            team2: Nome do time 2
            stat: Estatística ('kills', 'towers', 'dragons', 'barons', 'gamelength')
            line: Linha da aposta (ex: 25.5)
            odd_over: Odd Over
            odd_under: Odd Under
            limit_games: Quantos jogos recentes usar
            h2h_months: Quantos meses de histórico H2H
            use_h2h: Se deve incluir peso H2H
        
        Returns:
            Dict com análise completa ou None em caso de erro
        """
        db_path = self.get_db_path()
        if db_path is None:
            return {"error": "Banco de dados não encontrado."}
        
        # Debug: verificar qual banco está sendo usado
        print(f"[DEBUG] Usando banco: {db_path}")
        
        conn = sqlite3.connect(db_path)
        try:
            if not _db_has_required_columns(conn, stat):
                missing = "opponentkills (kills)" if stat == "kills" else "opp_barons/opp_towers/opp_dragons"
                return {
                    "error": f"Banco desatualizado: faltam colunas ({missing}). "
                    "Clique em 'Atualizar Bancos' e atualize o banco LoL com o CSV do Oracle's Elixir para recriar o banco."
                }
            # Buscar dados dos dois times (e últimos com adversário para conferência)
            last_with_opp1, last_with_opp2 = [], []
            try:
                vals1 = fetch_team_recent(conn, team1, stat, limit_games)
                vals2 = fetch_team_recent(conn, team2, stat, limit_games)
                last_with_opp1 = fetch_team_recent_with_opponent(conn, team1, stat, limit_games)
                last_with_opp2 = fetch_team_recent_with_opponent(conn, team2, stat, limit_games)
            except sqlite3.OperationalError as e:
                if "opponentkills" in str(e) or "opp_barons" in str(e) or "opp_towers" in str(e) or "opp_dragons" in str(e):
                    return {
                        "error": "Banco desatualizado (faltam colunas). Clique em 'Atualizar Bancos' e atualize o banco LoL com o CSV do Oracle's Elixir."
                    }
                raise
            
            if not vals1 or not vals2:
                return {
                    "error": f"Dados insuficientes para {team1} ou {team2}.",
                    "team1_games": len(vals1),
                    "team2_games": len(vals2),
                    "last_values_team1": last_with_opp1 if vals1 else [],
                    "last_values_team2": last_with_opp2 if vals2 else [],
                }
            
            # Calcular estatísticas empíricas
            arr1 = np.array(vals1, dtype=float)
            arr2 = np.array(vals2, dtype=float)
            is_first_stat = stat in FIRST_STATS
            
            if is_first_stat:
                # First objectives: prob_team1 vs prob_team2 (normalizar para somar 1)
                mean1 = float(np.mean(arr1))  # % jogos onde time1 pegou
                mean2 = float(np.mean(arr2))  # % jogos onde time2 pegou
                total_rate = mean1 + mean2
                if total_rate > 0:
                    prob_team1 = mean1 / total_rate
                    prob_team2 = mean2 / total_rate
                else:
                    prob_team1 = prob_team2 = 0.5
                mean_combined = 0.5
                prob_form = prob_team1
                line = 0.5  # Fixar linha para first stats
            else:
                arr_all = np.concatenate([arr1, arr2])
                mean1 = float(np.mean(arr1))
                mean2 = float(np.mean(arr2))
                mean_combined = float(np.mean(arr_all))
                prob_form = float((arr_all > line).mean())
            
            # H2H
            if use_h2h:
                h2h_rate, nh2h, h2h_mean, over_h2h, under_h2h = fetch_h2h_empirico(conn, team1, team2, stat, h2h_months, line)
            else:
                h2h_rate, nh2h, h2h_mean, over_h2h, under_h2h = (None, 0, 0.0, 0, 0)
            
            # Combinar probabilidades (H2H + empírico)
            if use_h2h and h2h_rate is not None and nh2h >= 3:
                w_h2h = min(0.8, nh2h / (nh2h + 10))
                w_form = 1 - w_h2h
                prob_over = w_h2h * h2h_rate + w_form * prob_form
            else:
                w_h2h = 0
                w_form = 1
                prob_over = prob_form
            
            prob_under = 1 - prob_over
            
            # Calcular EV (formato Pinnacle)
            def calc_ev_pinnacle(prob, odd, stake=1.0):
                win = (odd - 1.0) * stake
                lose = stake
                ev = prob * win - (1 - prob) * lose
                fair = 1/prob if prob > 0 else float("inf")
                return ev, ev/stake, fair
            
            ev_over, ev_over_pct, fair_over = calc_ev_pinnacle(prob_over, odd_over)
            ev_under, ev_under_pct, fair_under = calc_ev_pinnacle(prob_under, odd_under)
            
            # Estatísticas por time
            line_used = 0.5 if is_first_stat else line
            over1 = int((arr1 > line_used).sum())
            under1 = len(arr1) - over1
            over2 = int((arr2 > line_used).sum())
            under2 = len(arr2) - over2
            if is_first_stat:
                over_all = over1 + over2
                under_all = under1 + under2
            else:
                arr_all = np.concatenate([arr1, arr2])
                over_all = int((arr_all > line).sum())
                under_all = len(arr_all) - over_all
            
            return {
                "team1": team1,
                "team2": team2,
                "stat": stat,
                "line": line,
                "odd_over": odd_over,
                "odd_under": odd_under,
                "team1_games": len(arr1),
                "team2_games": len(arr2),
                "last_values_team1": last_with_opp1,
                "last_values_team2": last_with_opp2,
                "mean_team1": mean1,
                "mean_team2": mean2,
                "mean_combined": mean_combined,
                "prob_over": prob_over,
                "prob_under": prob_under,
                "prob_form": prob_form,
                "fair_over": fair_over,
                "fair_under": fair_under,
                "ev_over": ev_over,
                "ev_over_pct": ev_over_pct,
                "ev_under": ev_under,
                "ev_under_pct": ev_under_pct,
                "use_h2h": use_h2h,
                "h2h_rate": h2h_rate,
                "h2h_games": nh2h,
                "h2h_mean": h2h_mean,
                "h2h_over": over_h2h,
                "h2h_under": under_h2h,
                "w_h2h": w_h2h,
                "w_form": w_form,
                "team1_over": over1,
                "team1_under": under1,
                "team2_over": over2,
                "team2_under": under2,
                "over_all": over_all,
                "under_all": under_all,
                "recommendation": self._get_recommendation(ev_over, ev_under, line, stat),
                "is_first_stat": is_first_stat,
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()
    
    def _get_recommendation(self, ev_over, ev_under, line, stat=""):
        """Retorna recomendação baseada em EV."""
        is_first = stat in FIRST_STATS
        if ev_over > 0 and ev_over > ev_under:
            return f"Time 1 (EV {ev_over:+.2f}%)" if is_first else f"OVER {line} (EV {ev_over:+.2f}%)"
        elif ev_under > 0 and ev_under > ev_over:
            return f"Time 2 (EV {ev_under:+.2f}%)" if is_first else f"UNDER {line} (EV {ev_under:+.2f}%)"
        else:
            return "Nenhuma aposta com EV positivo"
    
    def get_available_teams(self):
        """Retorna lista de times disponíveis no banco."""
        db_path = self.get_db_path()
        if db_path is None:
            return []
        
        conn = sqlite3.connect(db_path)
        try:
            team_col = _get_team_column(conn)
            query = f"SELECT DISTINCT {team_col} FROM oracle_matches WHERE {team_col} IS NOT NULL ORDER BY {team_col}"
            df = pd.read_sql_query(query, conn)
            return df[team_col].tolist()
        except Exception as e:
            print(f"Erro ao buscar times: {e}")
            return []
        finally:
            conn.close()
    
    def get_available_stats(self):
        """Retorna lista de estatísticas disponíveis."""
        return [
            "kills", "towers", "dragons", "barons", "gamelength",
            "firstdragon", "firsttower", "firstherald"
        ]
