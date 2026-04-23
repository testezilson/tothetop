"""
Script para verificar os primeiros e últimos 10 jogos (com data) da base de dados.
Útil para entender o range de datas dos dados usados para calcular impactos dos campeões.
"""
import sqlite3
import pandas as pd
import os
import sys

# Adicionar src ao path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
src_dir = os.path.join(BASE_DIR, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from core.lol.prebets_secondary import get_db_path, _get_team_column


def main():
    print("=" * 80)
    print("📊 PRIMEIROS E ÚLTIMOS 10 JOGOS DA BASE DE DADOS")
    print("=" * 80)
    print()
    
    # Conectar ao banco
    db_path = get_db_path()
    if db_path is None:
        print("❌ Erro: Não foi possível encontrar o banco de dados.")
        print("   Verifique se o banco existe em um dos locais esperados.")
        return
    
    print(f"📂 Banco de dados: {db_path}")
    print()
    
    conn = sqlite3.connect(db_path)
    try:
        # Detectar coluna de time
        team_col = _get_team_column(conn)
        print(f"✅ Coluna de time detectada: {team_col}")
        print()
        
        # Verificar estrutura da tabela
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(oracle_matches)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "date" not in columns:
            print("⚠️ Aviso: Coluna 'date' não encontrada na tabela.")
            print(f"   Colunas disponíveis: {', '.join(columns)}")
            print()
            # Tentar usar gameid para ordenar
            use_date = False
        else:
            use_date = True
        
        # Query para primeiros 10 jogos
        if use_date:
            query_first = f"""
                SELECT DISTINCT 
                    gameid,
                    MAX(date) AS date,
                    MAX(league) AS league,
                    GROUP_CONCAT(DISTINCT {team_col}) AS teams
                FROM oracle_matches
                WHERE date IS NOT NULL AND date != ''
                GROUP BY gameid
                ORDER BY datetime(date) ASC
                LIMIT 10
            """
            
            query_last = f"""
                SELECT DISTINCT 
                    gameid,
                    MAX(date) AS date,
                    MAX(league) AS league,
                    GROUP_CONCAT(DISTINCT {team_col}) AS teams
                FROM oracle_matches
                WHERE date IS NOT NULL AND date != ''
                GROUP BY gameid
                ORDER BY datetime(date) DESC
                LIMIT 10
            """
        else:
            # Fallback: usar gameid
            query_first = f"""
                SELECT DISTINCT 
                    gameid,
                    MAX(date) AS date,
                    MAX(league) AS league,
                    GROUP_CONCAT(DISTINCT {team_col}) AS teams
                FROM oracle_matches
                GROUP BY gameid
                ORDER BY gameid ASC
                LIMIT 10
            """
            
            query_last = f"""
                SELECT DISTINCT 
                    gameid,
                    MAX(date) AS date,
                    MAX(league) AS league,
                    GROUP_CONCAT(DISTINCT {team_col}) AS teams
                FROM oracle_matches
                GROUP BY gameid
                ORDER BY gameid DESC
                LIMIT 10
            """
        
        # Buscar primeiros 10 jogos
        print("=" * 80)
        print("📅 PRIMEIROS 10 JOGOS (MAIS ANTIGOS)")
        print("=" * 80)
        df_first = pd.read_sql_query(query_first, conn)
        
        if df_first.empty:
            print("⚠️ Nenhum jogo encontrado.")
        else:
            for idx, row in df_first.iterrows():
                gameid = row['gameid']
                date = row['date'] if pd.notna(row['date']) else "N/A"
                league = row['league'] if pd.notna(row['league']) else "N/A"
                teams = row['teams'] if pd.notna(row['teams']) else "N/A"
                
                # Limitar tamanho da string de times
                if isinstance(teams, str) and len(teams) > 50:
                    teams = teams[:47] + "..."
                
                print(f"  {idx+1:2d}. GameID: {gameid:<15} | Data: {date:<12} | Liga: {league:<8} | Times: {teams}")
        
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
                gameid = row['gameid']
                date = row['date'] if pd.notna(row['date']) else "N/A"
                league = row['league'] if pd.notna(row['league']) else "N/A"
                teams = row['teams'] if pd.notna(row['teams']) else "N/A"
                
                # Limitar tamanho da string de times
                if isinstance(teams, str) and len(teams) > 50:
                    teams = teams[:47] + "..."
                
                print(f"  {idx+1:2d}. GameID: {gameid:<15} | Data: {date:<12} | Liga: {league:<8} | Times: {teams}")
        
        print()
        
        # Estatísticas gerais
        print("=" * 80)
        print("📊 ESTATÍSTICAS GERAIS")
        print("=" * 80)
        
        # Total de jogos únicos
        query_count = "SELECT COUNT(DISTINCT gameid) AS total FROM oracle_matches"
        df_count = pd.read_sql_query(query_count, conn)
        total_games = df_count['total'].iloc[0] if not df_count.empty else 0
        print(f"Total de jogos únicos: {total_games}")
        
        # Range de datas
        if use_date:
            query_dates = """
                SELECT 
                    MIN(date) AS min_date,
                    MAX(date) AS max_date
                FROM oracle_matches
                WHERE date IS NOT NULL AND date != ''
            """
            df_dates = pd.read_sql_query(query_dates, conn)
            if not df_dates.empty:
                min_date = df_dates['min_date'].iloc[0]
                max_date = df_dates['max_date'].iloc[0]
                if pd.notna(min_date) and pd.notna(max_date):
                    print(f"Range de datas: {min_date} até {max_date}")
        
        # Ligas disponíveis
        query_leagues = "SELECT DISTINCT league FROM oracle_matches WHERE league IS NOT NULL"
        df_leagues = pd.read_sql_query(query_leagues, conn)
        leagues = sorted(df_leagues['league'].dropna().tolist())
        print(f"Ligas disponíveis: {', '.join(leagues)}")
        
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
