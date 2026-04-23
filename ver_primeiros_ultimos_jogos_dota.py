"""
Script para verificar os primeiros e últimos 10 jogos (com data) da base de dados do DOTA.
Útil para entender o range de datas dos dados usados para calcular impactos dos heróis.
"""
import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime

# Adicionar src ao path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
src_dir = os.path.join(BASE_DIR, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from core.dota.prebets_secondary import get_dota_db_path, _detect_table_schema


def main():
    print("=" * 80)
    print("📊 PRIMEIROS E ÚLTIMOS 10 JOGOS DA BASE DE DADOS - DOTA 2")
    print("=" * 80)
    print()
    
    # Conectar ao banco
    db_path = get_dota_db_path()
    if db_path is None:
        print("❌ Erro: Não foi possível encontrar o banco de dados do DOTA.")
        print("   Verifique se o banco existe em um dos locais esperados:")
        print("   - cyberscore.db")
        print("   - dota_matches_stratz.db")
        return
    
    print(f"📂 Banco de dados: {db_path}")
    print()
    
    conn = sqlite3.connect(db_path)
    try:
        # Detectar schema da tabela
        schema = _detect_table_schema(conn)
        print(f"✅ Schema detectado: {schema}")
        print()
        
        # Verificar estrutura da tabela
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(matches)")
        columns_info = cursor.fetchall()
        columns = [row[1] for row in columns_info]
        
        print(f"   Colunas disponíveis: {', '.join(columns[:10])}...")
        print()
        
        # Detectar coluna de ID da partida
        id_col = None
        for col_name in ['match_id', 'id', 'matchid', 'game_id', 'gameid']:
            if col_name in columns:
                id_col = col_name
                break
        
        if id_col is None:
            # Tentar usar rowid ou primeira coluna
            id_col = columns[0] if columns else 'rowid'
            print(f"⚠️ Coluna de ID não encontrada, usando: {id_col}")
        else:
            print(f"✅ Coluna de ID detectada: {id_col}")
        print()
        
        # Definir colunas baseado no schema
        if schema == 'cyberscore':
            date_col = 'timestamp'
            team_col_radiant = 'radiant_team'
            team_col_dire = 'dire_team'
        else:  # stratz
            date_col = 'start_time'
            team_col_radiant = 'radiant_name'
            team_col_dire = 'dire_name'
        
        # Verificar se a coluna de data existe
        if date_col not in columns:
            print(f"⚠️ Aviso: Coluna '{date_col}' não encontrada na tabela.")
            print()
            use_date = False
        else:
            use_date = True
        
        # Query para primeiros 10 jogos
        if use_date:
            query_first = f"""
                SELECT DISTINCT 
                    {id_col} AS match_id,
                    MAX({date_col}) AS date,
                    MAX({team_col_radiant}) AS radiant_team,
                    MAX({team_col_dire}) AS dire_team
                FROM matches
                WHERE {date_col} IS NOT NULL AND {date_col} != ''
                GROUP BY {id_col}
                ORDER BY {date_col} ASC
                LIMIT 10
            """
            
            query_last = f"""
                SELECT DISTINCT 
                    {id_col} AS match_id,
                    MAX({date_col}) AS date,
                    MAX({team_col_radiant}) AS radiant_team,
                    MAX({team_col_dire}) AS dire_team
                FROM matches
                WHERE {date_col} IS NOT NULL AND {date_col} != ''
                GROUP BY {id_col}
                ORDER BY {date_col} DESC
                LIMIT 10
            """
        else:
            # Fallback: usar ID
            query_first = f"""
                SELECT DISTINCT 
                    {id_col} AS match_id,
                    MAX({date_col}) AS date,
                    MAX({team_col_radiant}) AS radiant_team,
                    MAX({team_col_dire}) AS dire_team
                FROM matches
                GROUP BY {id_col}
                ORDER BY {id_col} ASC
                LIMIT 10
            """
            
            query_last = f"""
                SELECT DISTINCT 
                    {id_col} AS match_id,
                    MAX({date_col}) AS date,
                    MAX({team_col_radiant}) AS radiant_team,
                    MAX({team_col_dire}) AS dire_team
                FROM matches
                GROUP BY {id_col}
                ORDER BY {id_col} DESC
                LIMIT 10
            """
        
        # Função para converter timestamp para data legível
        def format_date(timestamp_value, schema_type):
            if pd.isna(timestamp_value) or timestamp_value == '':
                return "N/A"
            
            try:
                if schema_type == 'cyberscore':
                    # cyberscore usa timestamp Unix (segundos)
                    if isinstance(timestamp_value, (int, float)):
                        dt = datetime.fromtimestamp(float(timestamp_value))
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    elif isinstance(timestamp_value, str):
                        # Tentar converter string para int/float
                        ts = float(timestamp_value)
                        dt = datetime.fromtimestamp(ts)
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                else:  # stratz
                    # stratz pode usar timestamp Unix ou formato ISO
                    if isinstance(timestamp_value, (int, float)):
                        dt = datetime.fromtimestamp(float(timestamp_value))
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    elif isinstance(timestamp_value, str):
                        # Tentar parsear como ISO ou Unix timestamp
                        try:
                            ts = float(timestamp_value)
                            dt = datetime.fromtimestamp(ts)
                            return dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            # Tentar parsear como ISO
                            try:
                                dt = pd.to_datetime(timestamp_value)
                                return dt.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                return str(timestamp_value)
            except Exception as e:
                return str(timestamp_value)
        
        # Buscar primeiros 10 jogos
        print("=" * 80)
        print("📅 PRIMEIROS 10 JOGOS (MAIS ANTIGOS)")
        print("=" * 80)
        df_first = pd.read_sql_query(query_first, conn)
        
        if df_first.empty:
            print("⚠️ Nenhum jogo encontrado.")
        else:
            for idx, row in df_first.iterrows():
                match_id = row['match_id']
                date_raw = row['date'] if pd.notna(row['date']) else None
                date_formatted = format_date(date_raw, schema) if date_raw else "N/A"
                radiant = row['radiant_team'] if pd.notna(row['radiant_team']) else "N/A"
                dire = row['dire_team'] if pd.notna(row['dire_team']) else "N/A"
                
                # Limitar tamanho das strings
                if isinstance(radiant, str) and len(radiant) > 25:
                    radiant = radiant[:22] + "..."
                if isinstance(dire, str) and len(dire) > 25:
                    dire = dire[:22] + "..."
                
                print(f"  {idx+1:2d}. MatchID: {match_id:<15} | Data: {date_formatted:<20} | 🟩 {radiant:<25} vs 🟥 {dire}")
        
        print()
        
        # Buscar últimos 10 jogos
        print("=" * 80)
        print("📅 ÚLTIMOS 10 JOGOS (MAIS RECENTES)")
        print("=" * 80)
        df_last = pd.read_sql_query(query_last, conn)
        
        if df_last.empty:
            print("⚠️ Nenhum jogo encontrado.")
        else:
            for idx, row in df_last.iterrows():
                match_id = row['match_id']
                date_raw = row['date'] if pd.notna(row['date']) else None
                date_formatted = format_date(date_raw, schema) if date_raw else "N/A"
                radiant = row['radiant_team'] if pd.notna(row['radiant_team']) else "N/A"
                dire = row['dire_team'] if pd.notna(row['dire_team']) else "N/A"
                
                # Limitar tamanho das strings
                if isinstance(radiant, str) and len(radiant) > 25:
                    radiant = radiant[:22] + "..."
                if isinstance(dire, str) and len(dire) > 25:
                    dire = dire[:22] + "..."
                
                print(f"  {idx+1:2d}. MatchID: {match_id:<15} | Data: {date_formatted:<20} | 🟩 {radiant:<25} vs 🟥 {dire}")
        
        print()
        
        # Estatísticas gerais
        print("=" * 80)
        print("📊 ESTATÍSTICAS GERAIS")
        print("=" * 80)
        
        # Total de jogos únicos
        query_count = f"SELECT COUNT(DISTINCT {id_col}) AS total FROM matches"
        df_count = pd.read_sql_query(query_count, conn)
        total_games = df_count['total'].iloc[0] if not df_count.empty else 0
        print(f"Total de jogos únicos: {total_games}")
        
        # Range de datas
        if use_date:
            query_dates = f"""
                SELECT 
                    MIN({date_col}) AS min_date,
                    MAX({date_col}) AS max_date
                FROM matches
                WHERE {date_col} IS NOT NULL AND {date_col} != ''
            """
            df_dates = pd.read_sql_query(query_dates, conn)
            if not df_dates.empty:
                min_date_raw = df_dates['min_date'].iloc[0]
                max_date_raw = df_dates['max_date'].iloc[0]
                if pd.notna(min_date_raw) and pd.notna(max_date_raw):
                    min_date_formatted = format_date(min_date_raw, schema)
                    max_date_formatted = format_date(max_date_raw, schema)
                    print(f"Range de datas: {min_date_formatted} até {max_date_formatted}")
        
        # Times únicos (amostra)
        if schema == 'cyberscore':
            query_teams = f"""
                SELECT DISTINCT {team_col_radiant} AS team FROM matches 
                WHERE {team_col_radiant} IS NOT NULL
                UNION
                SELECT DISTINCT {team_col_dire} AS team FROM matches 
                WHERE {team_col_dire} IS NOT NULL
                LIMIT 20
            """
        else:
            query_teams = f"""
                SELECT DISTINCT {team_col_radiant} AS team FROM matches 
                WHERE {team_col_radiant} IS NOT NULL
                UNION
                SELECT DISTINCT {team_col_dire} AS team FROM matches 
                WHERE {team_col_dire} IS NOT NULL
                LIMIT 20
            """
        
        df_teams = pd.read_sql_query(query_teams, conn)
        teams = sorted(df_teams['team'].dropna().tolist())
        if teams:
            print(f"Times únicos (amostra de 20): {', '.join(teams[:10])}...")
            print(f"Total de times únicos: {len(teams)}")
        
    except Exception as e:
        print(f"❌ Erro ao consultar banco de dados: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
