"""
Script para listar todos os campeonatos/torneios e suas datas do banco de dados do DOTA.
Mostra o primeiro e último jogo de cada campeonato.
"""
import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime
from collections import defaultdict

# Adicionar src ao path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
src_dir = os.path.join(BASE_DIR, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from core.dota.prebets_secondary import get_dota_db_path, _detect_table_schema

# Caminho do banco de dados do OpenDota (usado para calcular impactos dos heróis)
DOTA_OPENDOTA_DIR = r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\dota_draft_ml_v1"
DOTA_DB_PATH = os.path.join(DOTA_OPENDOTA_DIR, "data", "dota_matches.db")


def format_date(timestamp_value, schema_type):
    """Converte timestamp para data legível."""
    if pd.isna(timestamp_value) or timestamp_value == '':
        return "N/A"
    
    try:
        if schema_type == 'cyberscore':
            # cyberscore usa timestamp Unix (segundos)
            if isinstance(timestamp_value, (int, float)):
                dt = datetime.fromtimestamp(float(timestamp_value))
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(timestamp_value, str):
                ts = float(timestamp_value)
                dt = datetime.fromtimestamp(ts)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif schema_type == 'opendota':
            # OpenDota: start_date é salvo como ISO string (YYYY-MM-DD) em import_league_opendota_to_sqlite.py
            # Mas start_time pode ser timestamp Unix
            if isinstance(timestamp_value, str):
                # Tentar parsear como ISO date primeiro
                try:
                    dt = pd.to_datetime(timestamp_value)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    # Se falhar, tentar como timestamp
                    try:
                        ts = float(timestamp_value)
                        if ts > 1e10:  # Provavelmente milissegundos
                            ts = ts / 1000
                        dt = datetime.fromtimestamp(ts)
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        return str(timestamp_value)
            elif isinstance(timestamp_value, (int, float)):
                # Timestamp Unix (segundos ou milissegundos)
                ts = float(timestamp_value)
                if ts > 1e10:  # Provavelmente milissegundos
                    ts = ts / 1000
                dt = datetime.fromtimestamp(ts)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        else:  # stratz ou outro
            if isinstance(timestamp_value, (int, float)):
                dt = datetime.fromtimestamp(float(timestamp_value))
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(timestamp_value, str):
                try:
                    ts = float(timestamp_value)
                    dt = datetime.fromtimestamp(ts)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    try:
                        dt = pd.to_datetime(timestamp_value)
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        return str(timestamp_value)
    except Exception:
        return str(timestamp_value)


def find_opendota_db():
    """Procura o banco de dados do OpenDota usado para calcular impactos dos heróis."""
    # Baseado em import_league_opendota_to_sqlite.py e merge_league_into_stratz.py,
    # o banco de dados está em data/dota_matches.db
    # e a tabela principal é dota_matches_stratz
    
    # Caminho principal: data/dota_matches.db
    if os.path.exists(DOTA_DB_PATH):
        return DOTA_DB_PATH
    
    # Fallback: procurar outros nomes possíveis
    possible_names = [
        "dota_matches.db",
        "dota_matches_opendota.db",
        "opendota_matches.db",
        "dota_opendota.db",
        "matches_opendota.db",
        "dota.db",
        "matches.db"
    ]
    
    # Procurar no subdiretório data/
    data_dir = os.path.join(DOTA_OPENDOTA_DIR, "data")
    if os.path.exists(data_dir):
        for db_name in possible_names:
            db_path = os.path.join(data_dir, db_name)
            if os.path.exists(db_path):
                return db_path
    
    # Procurar no diretório raiz do OpenDota
    if os.path.exists(DOTA_OPENDOTA_DIR):
        for db_name in possible_names:
            db_path = os.path.join(DOTA_OPENDOTA_DIR, db_name)
            if os.path.exists(db_path):
                return db_path
    
    return None


def main():
    print("=" * 80)
    print("🏆 CAMPEONATOS/TORNEIOS NO BANCO DE DADOS - DOTA 2 (OpenDota)")
    print("=" * 80)
    print()
    print("ℹ️  Procurando banco de dados do OpenDota (usado para calcular impactos dos heróis)...")
    print(f"   Diretório: {DOTA_OPENDOTA_DIR}")
    print()
    
    # Procurar banco do OpenDota
    db_path = find_opendota_db()
    if db_path is None:
        print("❌ Erro: Não foi possível encontrar o banco de dados do OpenDota.")
        print("   Verifique se o diretório existe e contém um banco de dados SQLite.")
        return
    
    print(f"✅ Banco de dados encontrado: {db_path}")
    print()
    
    conn = sqlite3.connect(db_path)
    try:
        # Verificar quais tabelas existem
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        if not tables:
            print("❌ Nenhuma tabela encontrada no banco de dados.")
            return
        
        print(f"📋 Tabelas encontradas: {', '.join(tables)}")
        print()
        
        # Baseado em merge_league_into_stratz.py, a tabela principal é dota_matches_stratz
        # Mas também pode haver tabelas individuais por liga: dota_matches_league_{LEAGUE_ID}
        # Essas tabelas individuais têm league_id e league_name
        league_tables = [t for t in tables if t.startswith('dota_matches_league_')]
        
        if league_tables:
            print(f"📊 Encontradas {len(league_tables)} tabelas de liga individuais")
            print(f"   Exemplos: {', '.join(league_tables[:5])}")
            print()
            # Vamos analisar todas as tabelas de liga para listar os campeonatos
            table_name = None  # Vamos processar múltiplas tabelas
        elif 'dota_matches_stratz' in tables:
            table_name = 'dota_matches_stratz'
            print(f"📊 Usando tabela principal: {table_name}")
            print("   (Nota: Esta tabela pode não ter colunas de liga. Verifique tabelas individuais.)")
        elif 'matches' in tables:
            table_name = 'matches'
            print(f"📊 Usando tabela: {table_name}")
        else:
            table_name = tables[0]
            print(f"📊 Usando primeira tabela disponível: {table_name}")
        print()
        
        # Verificar estrutura da tabela
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_info = cursor.fetchall()
        columns = [row[1] for row in columns_info]
        
        print(f"   Colunas disponíveis: {', '.join(columns)}")
        print()
        
        # Detectar schema baseado na estrutura da tabela
        # Se a tabela tem start_date (TEXT ISO) e não tem timestamp, é OpenDota
        # Se tem timestamp (INTEGER), pode ser cyberscore ou stratz
        schema = None
        if 'start_date' in columns and 'timestamp' not in columns:
            schema = 'opendota'
            print(f"✅ Schema detectado: {schema} (baseado em start_date)")
        else:
            try:
                schema = _detect_table_schema(conn)
                print(f"✅ Schema detectado: {schema}")
            except:
                print("⚠️  Schema não detectado automaticamente, assumindo opendota")
                schema = 'opendota'
        print()
        
        # Se temos tabelas de liga individuais, vamos processá-las separadamente
        if league_tables:
            print("=" * 80)
            print("🏆 LISTA DE CAMPEONATOS (das tabelas individuais de liga)")
            print("=" * 80)
            
            tournaments_info = []
            
            for league_table in league_tables:
                # Extrair league_id do nome da tabela
                try:
                    league_id = int(league_table.replace('dota_matches_league_', ''))
                except:
                    league_id = None
                
                # Verificar estrutura desta tabela
                cursor.execute(f"PRAGMA table_info({league_table})")
                league_columns_info = cursor.fetchall()
                league_columns = [row[1] for row in league_columns_info]
                
                # Buscar league_name se existir
                league_name = None
                if 'league_name' in league_columns:
                    cursor.execute(f"SELECT DISTINCT league_name FROM {league_table} WHERE league_name IS NOT NULL LIMIT 1")
                    result = cursor.fetchone()
                    if result:
                        league_name = result[0]
                
                # Buscar datas
                if 'start_date' in league_columns:
                    date_col = 'start_date'
                elif 'start_time' in league_columns:
                    date_col = 'start_time'
                else:
                    date_col = None
                
                if date_col:
                    cursor.execute(f"""
                        SELECT 
                            MIN({date_col}) AS first_date,
                            MAX({date_col}) AS last_date,
                            COUNT(DISTINCT match_id) AS total_matches
                        FROM {league_table}
                        WHERE {date_col} IS NOT NULL AND {date_col} != ''
                    """)
                    date_info = cursor.fetchone()
                    if date_info and date_info[0]:
                        first_date_raw = date_info[0]
                        last_date_raw = date_info[1]
                        total_matches = date_info[2]
                        
                        first_date = format_date(first_date_raw, 'opendota')
                        last_date = format_date(last_date_raw, 'opendota')
                        
                        tournaments_info.append({
                            'league_id': league_id,
                            'league_name': league_name or f"League {league_id}",
                            'first_date': first_date,
                            'last_date': last_date,
                            'total_matches': total_matches
                        })
            
            # Ordenar por primeira data
            tournaments_info.sort(key=lambda x: x['first_date'])
            
            if tournaments_info:
                print(f"\n📊 Total de campeonatos encontrados: {len(tournaments_info)}\n")
                for idx, info in enumerate(tournaments_info, 1):
                    print(f"{idx:3d}. {info['league_name']}")
                    print(f"     League ID: {info['league_id']}")
                    print(f"     Primeira partida: {info['first_date']}")
                    print(f"     Última partida:   {info['last_date']}")
                    print(f"     Total de partidas: {info['total_matches']}")
                    print()
            else:
                print("⚠️ Nenhum campeonato encontrado nas tabelas de liga.")
            
            # Não continuar com o resto do código se já processamos as tabelas de liga
            return
        
        # Se chegou aqui, vamos tentar processar uma tabela única
        # Detectar coluna de campeonato/torneio
        tournament_col = None
        possible_tournament_cols = ['league_name', 'league', 'tournament', 'tournament_name', 
                                     'event', 'event_name', 'competition', 'comp_name', 
                                     'series', 'series_name']
        
        for col_name in possible_tournament_cols:
            if col_name in columns:
                tournament_col = col_name
                break
        
        # Se não encontrou, verificar se há league_id (podemos agrupar por ele)
        league_id_col = None
        if 'league_id' in columns:
            league_id_col = 'league_id'
        
        if tournament_col is None and league_id_col is None:
            print("⚠️ Coluna de campeonato/torneio não encontrada.")
            print("   Tentando usar todas as colunas de texto para identificar campeonatos...")
            print()
            # Listar todas as colunas de texto que podem conter informações de campeonato
            text_cols = []
            for col_info in columns_info:
                col_name = col_info[1]
                col_type = col_info[2].upper()
                if 'TEXT' in col_type or 'VARCHAR' in col_type:
                    text_cols.append(col_name)
            print(f"   Colunas de texto disponíveis: {', '.join(text_cols)}")
            print()
        elif league_id_col and not tournament_col:
            # Se temos league_id mas não league_name, vamos usar league_id e tentar buscar nomes
            print(f"✅ Coluna de liga detectada: {league_id_col}")
            print("   (Usando league_id para agrupar, nomes serão mostrados como IDs)")
            tournament_col = league_id_col
        
        # Detectar coluna de ID da partida
        id_col = None
        for col_name in ['match_id', 'id', 'matchid', 'game_id', 'gameid']:
            if col_name in columns:
                id_col = col_name
                break
        
        if id_col is None:
            id_col = columns[0] if columns else 'rowid'
        
        # Definir colunas baseado no schema
        # Baseado em import_league_opendota_to_sqlite.py:
        # - match_id (PRIMARY KEY)
        # - start_date (TEXT, formato ISO)
        # - duration_seconds
        if schema == 'cyberscore':
            date_col = 'timestamp'
            id_col = 'match_id'
        elif schema == 'stratz':
            date_col = 'start_time'
            id_col = 'match_id'
        else:  # opendota ou desconhecido
            # Tentar detectar colunas comuns do OpenDota
            # Prioridade: start_date (formato ISO) > start_time (timestamp) > outros
            possible_date_cols = ['start_date', 'start_time', 'timestamp', 'match_date', 'date', 'time']
            possible_id_cols = ['match_id', 'id', 'matchid']
            
            date_col = None
            for col in possible_date_cols:
                if col in columns:
                    date_col = col
                    break
            
            id_col = None
            for col in possible_id_cols:
                if col in columns:
                    id_col = col
                    break
            
            if not date_col:
                date_col = columns[0] if columns else 'start_date'
            if not id_col:
                id_col = columns[0] if columns else 'match_id'
        
        # Verificar se a coluna de data existe
        if date_col not in columns:
            print(f"⚠️ Aviso: Coluna '{date_col}' não encontrada.")
            # Tentar encontrar qualquer coluna de data
            for col in columns:
                if 'date' in col.lower() or 'time' in col.lower():
                    date_col = col
                    use_date = True
                    break
            else:
                use_date = False
        else:
            use_date = True
        
        if id_col not in columns:
            id_col = columns[0] if columns else 'match_id'
        
        print(f"📅 Coluna de data: {date_col} (usar: {use_date})")
        print(f"🆔 Coluna de ID: {id_col}")
        print()
        
        # Se não encontrou coluna de campeonato, tentar buscar por outras colunas
        if tournament_col:
            print(f"✅ Coluna de campeonato detectada: {tournament_col}")
            print()
            
            # Query para listar campeonatos com datas
            if use_date:
                query = f"""
                    SELECT 
                        {tournament_col} AS tournament,
                        MIN({date_col}) AS first_date,
                        MAX({date_col}) AS last_date,
                        COUNT(DISTINCT {id_col}) AS total_matches
                    FROM {table_name}
                    WHERE {tournament_col} IS NOT NULL 
                      AND {tournament_col} != ''
                      AND {date_col} IS NOT NULL 
                      AND {date_col} != ''
                    GROUP BY {tournament_col}
                    ORDER BY MIN({date_col}) ASC
                """
            else:
                query = f"""
                    SELECT 
                        {tournament_col} AS tournament,
                        MIN({date_col}) AS first_date,
                        MAX({date_col}) AS last_date,
                        COUNT(DISTINCT {id_col}) AS total_matches
                    FROM {table_name}
                    WHERE {tournament_col} IS NOT NULL 
                      AND {tournament_col} != ''
                    GROUP BY {tournament_col}
                    ORDER BY {id_col} ASC
                """
            
            df_tournaments = pd.read_sql_query(query, conn)
            
            if df_tournaments.empty:
                print("⚠️ Nenhum campeonato encontrado.")
            else:
                print(f"📊 Total de campeonatos únicos: {len(df_tournaments)}")
                print()
                print("=" * 80)
                print("🏆 LISTA DE CAMPEONATOS")
                print("=" * 80)
                
                for idx, row in df_tournaments.iterrows():
                    tournament = row['tournament']
                    first_date_raw = row['first_date']
                    last_date_raw = row['last_date']
                    total_matches = row['total_matches']
                    
                    first_date = format_date(first_date_raw, schema) if use_date else str(first_date_raw)
                    last_date = format_date(last_date_raw, schema) if use_date else str(last_date_raw)
                    
                    print(f"\n{idx+1:3d}. {tournament}")
                    print(f"     Primeira partida: {first_date}")
                    print(f"     Última partida:   {last_date}")
                    print(f"     Total de partidas: {total_matches}")
        else:
            # Sem coluna de campeonato, mostrar informações gerais
            print("⚠️ Não foi possível identificar coluna de campeonato.")
            print("   Mostrando informações gerais por data...")
            print()
            
            if use_date:
                # Agrupar por mês/ano para ter uma ideia dos períodos
                query_dates = f"""
                    SELECT 
                        {date_col} AS date,
                        COUNT(DISTINCT {id_col}) AS matches
                    FROM {table_name}
                    WHERE {date_col} IS NOT NULL AND {date_col} != ''
                    GROUP BY {date_col}
                    ORDER BY {date_col} ASC
                """
                
                df_dates = pd.read_sql_query(query_dates, conn)
                
                if not df_dates.empty:
                    # Agrupar por mês/ano
                    tournaments_by_period = defaultdict(lambda: {'first': None, 'last': None, 'count': 0})
                    
                    for _, row in df_dates.iterrows():
                        date_raw = row['date']
                        matches = row['matches']
                        
                        try:
                            if schema == 'cyberscore':
                                dt = datetime.fromtimestamp(float(date_raw))
                            else:
                                dt = datetime.fromtimestamp(float(date_raw))
                            
                            period = dt.strftime("%Y-%m")
                            
                            if tournaments_by_period[period]['first'] is None:
                                tournaments_by_period[period]['first'] = date_raw
                            tournaments_by_period[period]['last'] = date_raw
                            tournaments_by_period[period]['count'] += matches
                        except:
                            pass
                    
                    print("📅 Partidas agrupadas por mês/ano:")
                    print()
                    for period in sorted(tournaments_by_period.keys()):
                        info = tournaments_by_period[period]
                        first = format_date(info['first'], schema)
                        last = format_date(info['last'], schema)
                        print(f"  {period}: {first} até {last} ({info['count']} partidas)")
        
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
