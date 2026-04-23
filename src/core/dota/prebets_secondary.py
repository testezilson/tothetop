"""
Módulo core para análise de pré-bets secundárias de Dota 2 (kills, torres, barracks, roshans, tempo,
first blood / first 10 kills / first tower / first roshan — estes últimos via CyberScore no cyberscore.db).
"""
import re
import sqlite3
import pandas as pd
import numpy as np
import os
from core.shared.paths import get_data_dir

# Colunas no cyberscore.db preenchidas pelo scraper (1 = Radiant fez, 0 = Dire fez)
CYBERSCORE_OBJECTIVE_COLUMNS = {
    "first_blood": "first_blood_radiant",
    "first_10_kills": "first_10_radiant",
    "first_tower": "first_tower_radiant",
    "first_roshan": "first_roshan_radiant",
}

# Mercados binários CyberScore: odd "over" = Time 1, odd "under" = Time 2 (igual first tower no LoL)
DOTA_FIRST_STYLE_STATS = frozenset(CYBERSCORE_OBJECTIVE_COLUMNS.keys())


def _matches_column_names(conn) -> set:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(matches)")
    return {row[1] for row in cur.fetchall()}


def _norm_team_upper(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s).upper().strip())


def _objective_value_for_team(team_upper: str, radiant: str | None, dire: str | None, rad_flag) -> float | None:
    """Valor 0/1: o time `team_upper` conseguiu o objetivo nesta partida."""
    if rad_flag is None:
        return None
    try:
        rf = float(rad_flag)
    except (TypeError, ValueError):
        return None
    tu = _norm_team_upper(team_upper)
    r = _norm_team_upper(radiant)
    d = _norm_team_upper(dire)
    if r == tu:
        return rf
    if d == tu:
        return 1.0 - rf
    return None


def _objective_value_for_team_fuzzy(team_upper: str, radiant: str | None, dire: str | None, rad_flag) -> float | None:
    v = _objective_value_for_team(team_upper, radiant, dire, rad_flag)
    if v is not None:
        return v
    try:
        rf = float(rad_flag)
    except (TypeError, ValueError):
        return None
    tu = _norm_team_upper(team_upper)
    r = _norm_team_upper(radiant)
    d = _norm_team_upper(dire)
    if tu in r or r in tu:
        return rf
    if tu in d or d in tu:
        return 1.0 - rf
    return None


def _register_cyberscore_sql_helpers(conn: sqlite3.Connection) -> None:
    """
    Permite WHERE por nome de time alinhado ao Python (espaços colapsados, trim).
    Sem isso, 'XTREME  GAMING' no DB não casava com 'XTREME GAMING' no combo.
    """

    def _cyber_norm_team_sql(s) -> str:
        if s is None:
            return ""
        return _norm_team_upper(str(s))

    conn.create_function("cyber_norm_team", 1, _cyber_norm_team_sql)


def _cyberscore_order_by_recent_sql(conn) -> str:
    """Ordena por data real da partida: match_timestamp costuma estar preenchido quando timestamp é NULL."""
    cols = _matches_column_names(conn)
    if "match_timestamp" in cols:
        co = "COALESCE(NULLIF(match_timestamp, 0), NULLIF(timestamp, 0), 0)"
    else:
        co = "COALESCE(NULLIF(timestamp, 0), 0)"
    # Jogos sem data ficam por último (evita misturar ordem com match_id só)
    return f"({co} = 0) ASC, {co} DESC, match_id DESC"


def _fetch_team_recent_objectives_cyberscore(
    conn, team_name: str, col_sql: str, limit_games: int
) -> tuple[list[float], int, int]:
    """
    Últimos `limit_games` jogos do time (por data da partida), **sem** filtrar NULL no objetivo.
    Valor 0/1 por jogo: sem dado no banco ou não mapeado → 0 (entra no denominador).
    Retorna (valores por jogo, nº com coluna NULL, nº com coluna preenchida mas time não mapeado).
    """
    _register_cyberscore_sql_helpers(conn)
    tu = _norm_team_upper(team_name)
    seen_mids: set[str] = set()
    vals: list[float] = []
    n_col_null = 0
    n_unmapped = 0
    order_sql = _cyberscore_order_by_recent_sql(conn)

    def consume_row(row, fuzzy: bool) -> None:
        nonlocal n_col_null, n_unmapped
        mid = str(row.get("match_id", ""))
        if not mid or mid in seen_mids:
            return
        seen_mids.add(mid)
        rf = row["rf"]
        if rf is None or pd.isna(rf):
            vals.append(0.0)
            n_col_null += 1
            return
        if fuzzy:
            v = _objective_value_for_team_fuzzy(tu, row["radiant_team"], row["dire_team"], rf)
        else:
            v = _objective_value_for_team(tu, row["radiant_team"], row["dire_team"], rf)
        if v is None:
            vals.append(0.0)
            n_unmapped += 1
        else:
            vals.append(float(v))

    query_exact = f"""
        SELECT match_id, radiant_team, dire_team, {col_sql} AS rf, timestamp
        FROM matches
        WHERE (cyber_norm_team(radiant_team) = ? OR cyber_norm_team(dire_team) = ?)
        ORDER BY {order_sql}
        LIMIT ?
    """
    df = pd.read_sql_query(query_exact, conn, params=(tu, tu, limit_games))
    for _, row in df.iterrows():
        consume_row(row, fuzzy=False)

    if len(vals) < limit_games:
        cap = max((limit_games - len(vals)) * 6, limit_games * 3, 40)
        query_like = f"""
            SELECT match_id, radiant_team, dire_team, {col_sql} AS rf, timestamp
            FROM matches
            WHERE (
                (cyber_norm_team(radiant_team) LIKE '%' || ? || '%' AND cyber_norm_team(radiant_team) != ?) OR
                (cyber_norm_team(dire_team) LIKE '%' || ? || '%' AND cyber_norm_team(dire_team) != ?)
            )
            ORDER BY {order_sql}
            LIMIT ?
        """
        df_like = pd.read_sql_query(
            query_like, conn, params=(tu, tu, tu, tu, cap)
        )
        for _, row in df_like.iterrows():
            if len(vals) >= limit_games:
                break
            consume_row(row, fuzzy=True)

    return vals[:limit_games], n_col_null, n_unmapped


def fetch_h2h_objective_cyberscore(conn, team1, team2, col_sql: str, months: int, line: float):
    """
    H2H para mercados 0/1: valor = 1 se team1 fez o objetivo na partida, 0 caso contrário.
    """
    from datetime import datetime, timedelta

    cutoff_date = datetime.now() - timedelta(days=months * 30)
    cutoff_timestamp = int(cutoff_date.timestamp())
    p1, p2 = f"%{team1}%", f"%{team2}%"
    query = f"""
        SELECT
            CASE
                WHEN UPPER(radiant_team) LIKE ? AND UPPER(dire_team) LIKE ? THEN CAST({col_sql} AS REAL)
                WHEN UPPER(radiant_team) LIKE ? AND UPPER(dire_team) LIKE ? THEN CAST(1 - {col_sql} AS REAL)
            END AS total
        FROM matches
        WHERE (
            (UPPER(radiant_team) LIKE ? AND UPPER(dire_team) LIKE ?) OR
            (UPPER(radiant_team) LIKE ? AND UPPER(dire_team) LIKE ?)
        )
        AND {col_sql} IS NOT NULL
        AND timestamp >= ?
    """
    params = (p1, p2, p2, p1, p1, p2, p2, p1, cutoff_timestamp)
    df = pd.read_sql_query(query, conn, params=params)
    df = df.dropna(subset=["total"])
    if df.empty:
        return (None, 0, 0.0, 0, 0)

    over = int((df["total"] > line).sum())
    total = len(df)
    under = total - over
    over_rate = over / total if total > 0 else 0.0
    mean_h2h = float(df["total"].mean()) if total > 0 else 0.0
    return over_rate, total, mean_h2h, over, under


def get_dota_db_path():
    """
    Retorna o caminho do banco de dados Dota.
    PRIORIDADE: cyberscore.db (mesmo que o PowerShell usa)
    """
    # PRIORIDADE 1: cyberscore.db (mesmo que o PowerShell)
    possible_paths = [
        r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\cyberscore.db",
        # Fallback: outros bancos
        r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\data\dota_matches_stratz.db",
    ]
    
    # Adicionar caminhos do projeto atual
    data_dir = get_data_dir()
    possible_paths.extend([
        os.path.join(data_dir, "cyberscore.db"),
        os.path.join(data_dir, "dota_matches_stratz.db"),
    ])
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None


def _get_stat_column(stat):
    """Mapeia estatística para coluna do banco."""
    stat = stat.lower()
    mapping = {
        "kills": "total_kills",
        "torres": "towers_destroyed",
        "barracks": "barracks_destroyed",
        "roshans": "roshans_killed",
        "tempo": "duration_seconds"
    }
    return mapping.get(stat, stat)


def _detect_table_schema(conn):
    """Detecta qual schema a tabela matches usa (cyberscore ou stratz)."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(matches)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # cyberscore.db usa: radiant_team, dire_team, timestamp, duration (texto)
    # stratz.db usa: radiant_name, dire_name, start_time, duration_seconds
    if 'radiant_team' in columns and 'timestamp' in columns:
        return 'cyberscore'
    elif 'radiant_name' in columns and 'start_time' in columns:
        return 'stratz'
    else:
        # Tentar detectar pelo nome do arquivo ou assumir cyberscore
        return 'cyberscore'


def _convert_duration_to_minutes(duration_str):
    """Converte duração de formato 'MM:SS' ou 'HH:MM:SS' para minutos."""
    if not isinstance(duration_str, str):
        return None
    duration_str = duration_str.strip()
    if not duration_str:
        return None
    
    partes = duration_str.split(":")
    try:
        if len(partes) == 2:
            m, s = partes
            h = 0
        elif len(partes) == 3:
            h, m, s = partes
        else:
            return None
        h = int(h)
        m = int(m)
        s = int(s)
        return h * 60 + m + s / 60.0
    except (ValueError, TypeError):
        return None


def fetch_team_recent(conn, team_name, stat, limit_games=10):
    """
    Retorna uma lista dos valores do time nos últimos n jogos.
    Compatível com cyberscore.db e stratz.db.
    Usa correspondência case-insensitive e tenta múltiplas variações do nome.
    """
    schema = _detect_table_schema(conn)
    stat_l = (stat or "").lower()
    if stat_l in CYBERSCORE_OBJECTIVE_COLUMNS:
        col_obj = CYBERSCORE_OBJECTIVE_COLUMNS[stat_l]
        if schema != "cyberscore" or col_obj not in _matches_column_names(conn):
            return []
        vals, _, _ = _fetch_team_recent_objectives_cyberscore(conn, team_name, col_obj, limit_games)
        return vals

    coluna = _get_stat_column(stat)
    
    # Normalizar nome do time para busca (case-insensitive)
    team_name_upper = team_name.upper().strip()
    team_name_lower = team_name.lower().strip()
    team_name_title = team_name.title().strip()
    
    if schema == 'cyberscore':
        # cyberscore.db: usar radiant_team/dire_team, timestamp, duration (texto)
        # Tentar correspondência exata primeiro (case-insensitive), depois LIKE como fallback
        if stat == "tempo":
            # Para tempo, precisa converter duration (texto) para minutos
            # Primeiro tentar correspondência exata (case-insensitive)
            query_exact = """
                SELECT duration, timestamp
                FROM matches
                WHERE (UPPER(radiant_team) = ? OR UPPER(dire_team) = ?)
                AND duration IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT ?
            """
            df = pd.read_sql_query(
                query_exact, 
                conn, 
                params=(team_name_upper, team_name_upper, limit_games)
            )
            
            # Se não encontrou jogos suficientes, usar LIKE como fallback
            if len(df) < limit_games:
                query_like = """
                    SELECT duration, timestamp
                    FROM matches
                    WHERE (
                        (UPPER(radiant_team) LIKE ? AND UPPER(radiant_team) != ?) OR
                        (UPPER(dire_team) LIKE ? AND UPPER(dire_team) != ?)
                    )
                    AND duration IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                df_like = pd.read_sql_query(
                    query_like, 
                    conn, 
                    params=(f"%{team_name_upper}%", team_name_upper, f"%{team_name_upper}%", team_name_upper, limit_games - len(df))
                )
                # Combinar e remover duplicatas
                df = pd.concat([df, df_like], ignore_index=True)
                df = df.drop_duplicates(subset=['timestamp'], keep='first')
                df = df.sort_values('timestamp', ascending=False).head(limit_games)
            
            # Converter duration para minutos
            durations = df["duration"].apply(_convert_duration_to_minutes).dropna().tolist()
            return durations
        else:
            # Para kills, usar total_kills
            # Primeiro tentar correspondência exata (case-insensitive)
            query_exact = f"""
                SELECT {coluna} AS total, timestamp
                FROM matches
                WHERE (UPPER(radiant_team) = ? OR UPPER(dire_team) = ?)
                AND {coluna} IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT ?
            """
            df = pd.read_sql_query(
                query_exact, 
                conn, 
                params=(team_name_upper, team_name_upper, limit_games)
            )
            
            # Se não encontrou jogos suficientes, usar LIKE como fallback
            if len(df) < limit_games:
                query_like = f"""
                    SELECT {coluna} AS total, timestamp
                    FROM matches
                    WHERE (
                        (UPPER(radiant_team) LIKE ? AND UPPER(radiant_team) != ?) OR
                        (UPPER(dire_team) LIKE ? AND UPPER(dire_team) != ?)
                    )
                    AND {coluna} IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                df_like = pd.read_sql_query(
                    query_like, 
                    conn, 
                    params=(f"%{team_name_upper}%", team_name_upper, f"%{team_name_upper}%", team_name_upper, limit_games - len(df))
                )
                # Combinar e remover duplicatas
                df = pd.concat([df, df_like], ignore_index=True)
                df = df.drop_duplicates(subset=['timestamp'], keep='first')
                df = df.sort_values('timestamp', ascending=False).head(limit_games)
            
            return df["total"].dropna().astype(float).tolist()
    else:
        # stratz.db: usar radiant_name/dire_name, start_time, duration_seconds
        if stat == "tempo":
            query = """
                SELECT duration_seconds / 60.0 AS total_min, start_time
                FROM matches
                WHERE (
                    UPPER(radiant_name) = ? OR UPPER(dire_name) = ? OR
                    UPPER(radiant_name) LIKE ? OR UPPER(dire_name) LIKE ?
                )
                AND duration_seconds IS NOT NULL
                ORDER BY start_time DESC
                LIMIT ?
            """
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(team_name_upper, team_name_upper, f"%{team_name_upper}%", f"%{team_name_upper}%", limit_games)
            )
            df = df.drop_duplicates(subset=['start_time'], keep='first')
            return df["total_min"].dropna().tolist()[:limit_games]
        else:
            query = f"""
                SELECT {coluna} AS total, start_time
                FROM matches
                WHERE (
                    UPPER(radiant_name) = ? OR UPPER(dire_name) = ? OR
                    UPPER(radiant_name) LIKE ? OR UPPER(dire_name) LIKE ?
                )
                AND {coluna} IS NOT NULL
                ORDER BY start_time DESC
                LIMIT ?
            """
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(team_name_upper, team_name_upper, f"%{team_name_upper}%", f"%{team_name_upper}%", limit_games)
            )
            df = df.drop_duplicates(subset=['start_time'], keep='first')
            return df["total"].dropna().tolist()[:limit_games]


def fetch_h2h_empirico(conn, team1, team2, stat, months=3, line=0.0):
    """
    Busca histórico H2H entre dois times.
    Retorna: (over_rate, total_games, mean, over_count, under_count)
    Compatível com cyberscore.db e stratz.db.
    """
    schema = _detect_table_schema(conn)
    stat_l = (stat or "").lower()
    if stat_l in CYBERSCORE_OBJECTIVE_COLUMNS:
        col_obj = CYBERSCORE_OBJECTIVE_COLUMNS[stat_l]
        if schema != "cyberscore" or col_obj not in _matches_column_names(conn):
            return (None, 0, 0.0, 0, 0)
        return fetch_h2h_objective_cyberscore(conn, team1, team2, col_obj, months, line)

    coluna = _get_stat_column(stat)
    
    # Calcular timestamp limite (meses atrás)
    from datetime import datetime, timedelta
    cutoff_date = datetime.now() - timedelta(days=months * 30)
    
    if schema == 'cyberscore':
        # cyberscore.db usa timestamp (inteiro Unix timestamp)
        cutoff_timestamp = int(cutoff_date.timestamp())
        
        if stat == "tempo":
            query = """
                SELECT duration
                FROM matches
                WHERE (
                    (radiant_team LIKE ? AND dire_team LIKE ?) OR
                    (radiant_team LIKE ? AND dire_team LIKE ?)
                )
                AND duration IS NOT NULL
                AND timestamp >= ?
                ORDER BY timestamp DESC
            """
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(f"%{team1}%", f"%{team2}%", f"%{team2}%", f"%{team1}%", cutoff_timestamp)
            )
            # Converter duration para minutos
            df["total"] = df["duration"].apply(_convert_duration_to_minutes)
            df = df[df["total"].notna()]
        else:
            query = f"""
                SELECT {coluna} AS total
                FROM matches
                WHERE (
                    (radiant_team LIKE ? AND dire_team LIKE ?) OR
                    (radiant_team LIKE ? AND dire_team LIKE ?)
                )
                AND {coluna} IS NOT NULL
                AND timestamp >= ?
                ORDER BY timestamp DESC
            """
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(f"%{team1}%", f"%{team2}%", f"%{team2}%", f"%{team1}%", cutoff_timestamp)
            )
            df["total"] = df["total"].astype(float)
    else:
        # stratz.db usa start_time (inteiro Unix timestamp)
        cutoff_timestamp = int(cutoff_date.timestamp())
        
        if stat == "tempo":
            query = """
                SELECT duration_seconds / 60.0 AS total
                FROM matches
                WHERE (
                    (radiant_name LIKE ? AND dire_name LIKE ?) OR
                    (radiant_name LIKE ? AND dire_name LIKE ?)
                )
                AND duration_seconds IS NOT NULL
                AND start_time >= ?
                ORDER BY start_time DESC
            """
        else:
            query = f"""
                SELECT {coluna} AS total
                FROM matches
                WHERE (
                    (radiant_name LIKE ? AND dire_name LIKE ?) OR
                    (radiant_name LIKE ? AND dire_name LIKE ?)
                )
                AND {coluna} IS NOT NULL
                AND start_time >= ?
                ORDER BY start_time DESC
            """
        
        df = pd.read_sql_query(
            query, 
            conn, 
            params=(f"%{team1}%", f"%{team2}%", f"%{team2}%", f"%{team1}%", cutoff_timestamp)
        )
    
    if df.empty:
        return (None, 0, 0.0, 0, 0)
    
    over = int((df["total"] > line).sum())
    total = len(df)
    under = total - over
    over_rate = over / total if total > 0 else 0.0
    mean_h2h = float(df["total"].mean()) if total > 0 else 0.0
    return over_rate, total, mean_h2h, over, under


class DotaSecondaryBetsAnalyzer:
    """Analisador de pré-bets secundárias de Dota 2 (kills, torres, barracks, roshans, tempo, objetivos CyberScore)."""
    
    def __init__(self):
        self.db_path = None
    
    def get_db_path(self):
        """Retorna o caminho do banco de dados."""
        if self.db_path is None:
            self.db_path = get_dota_db_path()
        
        return self.db_path
    
    def analyze_bet(self, team1, team2, stat, line, odd_over, odd_under, limit_games=10, h2h_months=3, use_h2h=False):
        """
        Analisa uma aposta secundária.
        
        Args:
            team1: Nome do time 1
            team2: Nome do time 2
            stat: Estatística ('kills', 'torres', ... ou 'first_blood', 'first_10_kills', 'first_tower', 'first_roshan' no cyberscore.db)
            line: Linha da aposta (ex: 45.5)
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
        print(f"[DEBUG] Usando banco Dota: {db_path}")
        
        # Criar conexão dentro desta função (para evitar problemas de threading)
        conn = sqlite3.connect(db_path)
        
        try:
            schema = _detect_table_schema(conn)
            stat_key = (stat or "").lower()

            if stat_key in DOTA_FIRST_STYLE_STATS:
                col_obj = CYBERSCORE_OBJECTIVE_COLUMNS[stat_key]
                if schema != "cyberscore" or col_obj not in _matches_column_names(conn):
                    return {
                        "error": f"A estatística '{stat}' usa dados CyberScore (objetivos). "
                        "Use o cyberscore.db atualizado com import das colunas FB/F10/FT/R.",
                    }
                vals1, miss1_col, miss1_map = _fetch_team_recent_objectives_cyberscore(
                    conn, team1, col_obj, limit_games
                )
                vals2, miss2_col, miss2_map = _fetch_team_recent_objectives_cyberscore(
                    conn, team2, col_obj, limit_games
                )
                miss1 = miss1_col + miss1_map
                miss2 = miss2_col + miss2_map
            else:
                vals1 = fetch_team_recent(conn, team1, stat, limit_games)
                vals2 = fetch_team_recent(conn, team2, stat, limit_games)
                miss1 = miss2 = 0

            if not vals1 or not vals2:
                return {
                    "error": f"Dados insuficientes para {team1} ou {team2}.",
                    "team1_games": len(vals1),
                    "team2_games": len(vals2)
                }

            arr1 = np.array(vals1, dtype=float)
            arr2 = np.array(vals2, dtype=float)
            is_first_stat = stat_key in DOTA_FIRST_STYLE_STATS

            def calc_ev_pinnacle(prob, odd, stake=1.0):
                win = (odd - 1.0) * stake
                lose = stake
                ev = prob * win - (1 - prob) * lose
                fair = 1.0 / prob if prob > 0 else float("inf")
                return ev, ev / stake, fair

            line_used = float(line)
            if is_first_stat:
                # Mesma ideia do LoL (first tower etc.): P(Time1) vs P(Time2) no confronto
                mean1 = float(np.mean(arr1))
                mean2 = float(np.mean(arr2))
                total_rate = mean1 + mean2
                if total_rate > 0:
                    prob_team1 = mean1 / total_rate
                else:
                    prob_team1 = 0.5
                prob_form = prob_team1
                mean_combined = 0.5
                line_used = 0.5
                h2h_line = 0.5
            else:
                arr_all = np.concatenate([arr1, arr2])
                mean1 = float(np.mean(arr1))
                mean2 = float(np.mean(arr2))
                mean_combined = float(np.mean(arr_all))
                over_count = int((arr_all > line_used).sum())
                total_count = len(arr_all)
                prob_form = over_count / total_count if total_count > 0 else 0.0
                h2h_line = line_used

            # H2H
            if use_h2h:
                h2h_rate, nh2h, h2h_mean, over_h2h, under_h2h = fetch_h2h_empirico(
                    conn, team1, team2, stat, h2h_months, h2h_line
                )
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

            ev_over, ev_over_pct, fair_over = calc_ev_pinnacle(prob_over, odd_over)
            ev_under, ev_under_pct, fair_under = calc_ev_pinnacle(prob_under, odd_under)

            # Contagens por time (over = acima da linha usada)
            over1 = int((arr1 > line_used).sum())
            under1 = len(arr1) - over1
            over2 = int((arr2 > line_used).sum())
            under2 = len(arr2) - over2
            if is_first_stat:
                over_all = over1 + over2
                under_all = under1 + under2
            else:
                arr_all = np.concatenate([arr1, arr2])
                over_all = int((arr_all > line_used).sum())
                under_all = len(arr_all) - over_all

            return {
                "team1": team1,
                "team2": team2,
                "stat": stat,
                "line": line_used,
                "odd_over": odd_over,
                "odd_under": odd_under,
                "team1_games": len(arr1),
                "team2_games": len(arr2),
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
                "recommendation": self._get_recommendation(ev_over, ev_under, line_used, stat),
                "is_first_stat": is_first_stat,
                "team1_objective_imputed_games": miss1,
                "team2_objective_imputed_games": miss2,
                "team1_objective_missing_column": miss1_col if is_first_stat else 0,
                "team2_objective_missing_column": miss2_col if is_first_stat else 0,
                "team1_objective_unmapped_team": miss1_map if is_first_stat else 0,
                "team2_objective_unmapped_team": miss2_map if is_first_stat else 0,
                # Jogos com coluna preenchida e time mapeado (para taxa só sobre dados reais)
                "team1_objective_known_games": (len(vals1) - miss1) if is_first_stat else len(vals1),
                "team2_objective_known_games": (len(vals2) - miss2) if is_first_stat else len(vals2),
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()
    
    def _get_recommendation(self, ev_over, ev_under, line, stat=""):
        """Retorna recomendação baseada em EV (Over/Under na linha ou Time 1 / Time 2 para objetivos CyberScore)."""
        sk = (stat or "").lower()
        is_first = sk in DOTA_FIRST_STYLE_STATS
        if ev_over > 0 and ev_over > ev_under:
            return f"Time 1 (EV {ev_over:+.2f}%)" if is_first else f"OVER {line} (EV {ev_over:+.2f}%)"
        if ev_under > 0 and ev_under > ev_over:
            return f"Time 2 (EV {ev_under:+.2f}%)" if is_first else f"UNDER {line} (EV {ev_under:+.2f}%)"
        return "Nenhuma aposta com EV positivo"
    
    def get_available_teams(self):
        """Retorna lista de times disponíveis no banco."""
        db_path = self.get_db_path()
        if db_path is None:
            return []
        
        conn = sqlite3.connect(db_path)
        try:
            schema = _detect_table_schema(conn)
            if schema == 'cyberscore':
                # cyberscore.db usa radiant_team e dire_team
                query = """
                    SELECT DISTINCT radiant_team AS team FROM matches WHERE radiant_team IS NOT NULL
                    UNION
                    SELECT DISTINCT dire_team AS team FROM matches WHERE dire_team IS NOT NULL
                    ORDER BY team
                """
            else:
                # stratz.db usa radiant_name e dire_name
                query = """
                    SELECT DISTINCT radiant_name AS team FROM matches WHERE radiant_name IS NOT NULL
                    UNION
                    SELECT DISTINCT dire_name AS team FROM matches WHERE dire_name IS NOT NULL
                    ORDER BY team
                """
            df = pd.read_sql_query(query, conn)
            return df["team"].tolist()
        except Exception as e:
            print(f"Erro ao buscar times: {e}")
            return []
        finally:
            conn.close()
    
    def get_available_stats(self):
        """Retorna lista de estatísticas disponíveis."""
        return [
            "kills",
            "torres",
            "barracks",
            "roshans",
            "tempo",
            "first_blood",
            "first_10_kills",
            "first_tower",
            "first_roshan",
        ]
