"""
Script para verificar se os dados antigos foram mantidos após a atualização
"""

import pandas as pd
import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ORACLE_PATH = os.path.join(DATA_DIR, "oracle_prepared.csv")
BACKUP_PATH = os.path.join(DATA_DIR, "oracle_prepared_backup.csv")

def verificar_dados():
    print("="*70)
    print("VERIFICAÇÃO DE DADOS - LoL Oracle ML v3")
    print("="*70)
    
    # Verificar arquivo principal
    if not os.path.exists(ORACLE_PATH):
        print(f"\n❌ Arquivo principal não encontrado: {ORACLE_PATH}")
        return
    
    print(f"\n📂 Carregando arquivo principal: {ORACLE_PATH}")
    df = pd.read_csv(ORACLE_PATH)
    
    print(f"\n📊 ESTATÍSTICAS DO ARQUIVO PRINCIPAL:")
    print(f"   Total de linhas: {len(df)}")
    print(f"   Total de partidas únicas: {df['gameid'].nunique()}")
    
    # Verificar por liga
    if 'league' in df.columns:
        print(f"\n📈 PARTIDAS POR LIGA:")
        league_stats = df.groupby('league')['gameid'].nunique().sort_values(ascending=False)
        for league, n_games in league_stats.items():
            print(f"   {league}: {n_games} partidas")
    
    # Verificar por data (se existir)
    if 'date' in df.columns:
        print(f"\n📅 ANÁLISE POR DATA:")
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df_with_date = df[df['date'].notna()]
        if len(df_with_date) > 0:
            min_date = df_with_date['date'].min()
            max_date = df_with_date['date'].max()
            print(f"   Data mais antiga: {min_date.strftime('%Y-%m-%d')}")
            print(f"   Data mais recente: {max_date.strftime('%Y-%m-%d')}")
            
            # Contar por ano
            df_with_date['year'] = df_with_date['date'].dt.year
            year_stats = df_with_date.groupby('year')['gameid'].nunique().sort_index()
            print(f"\n   Partidas por ano:")
            for year, n_games in year_stats.items():
                print(f"      {int(year)}: {n_games} partidas")
    
    # Verificar backup
    print(f"\n" + "="*70)
    print("VERIFICAÇÃO DO BACKUP")
    print("="*70)
    
    if os.path.exists(BACKUP_PATH):
        print(f"\n✅ Backup encontrado: {BACKUP_PATH}")
        df_backup = pd.read_csv(BACKUP_PATH)
        print(f"   Total de linhas no backup: {len(df_backup)}")
        print(f"   Total de partidas no backup: {df_backup['gameid'].nunique()}")
        
        # Comparar
        games_backup = set(df_backup['gameid'].unique())
        games_current = set(df['gameid'].unique())
        
        games_only_backup = games_backup - games_current
        games_only_current = games_current - games_backup
        games_in_both = games_backup & games_current
        
        print(f"\n📊 COMPARAÇÃO BACKUP vs ATUAL:")
        print(f"   Partidas apenas no backup: {len(games_only_backup)}")
        print(f"   Partidas apenas no atual: {len(games_only_current)}")
        print(f"   Partidas em ambos: {len(games_in_both)}")
        
        if len(games_only_backup) > 0:
            print(f"\n⚠️ ATENÇÃO: {len(games_only_backup)} partidas do backup não estão no arquivo atual!")
            print(f"   Isso pode indicar que os dados antigos foram perdidos.")
            print(f"   Primeiras 10 partidas faltando:")
            for i, gameid in enumerate(list(games_only_backup)[:10], 1):
                sample = df_backup[df_backup['gameid'] == gameid].iloc[0]
                league = sample.get('league', '?')
                date = sample.get('date', '?')
                print(f"      {i}. {gameid} - {league} - {date}")
        else:
            print(f"\n✅ Todas as partidas do backup estão no arquivo atual!")
        
        if len(games_only_current) > 0:
            print(f"\n✅ {len(games_only_current)} novas partidas foram adicionadas!")
    else:
        print(f"\n⚠️ Backup não encontrado: {BACKUP_PATH}")
        print(f"   Isso pode significar que:")
        print(f"   1. O arquivo original não existia (primeira vez)")
        print(f"   2. O backup não foi criado")
    
    # Verificar se há dados muito antigos (antes de 2024)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df_with_date = df[df['date'].notna()]
        if len(df_with_date) > 0:
            df_old = df_with_date[df_with_date['date'].dt.year < 2024]
            if len(df_old) > 0:
                print(f"\n✅ DADOS ANTIGOS ENCONTRADOS:")
                print(f"   {df_old['gameid'].nunique()} partidas anteriores a 2024")
                print(f"   Isso confirma que os dados antigos foram mantidos!")
            else:
                print(f"\n⚠️ Nenhuma partida anterior a 2024 encontrada.")
                print(f"   Isso pode indicar que apenas dados recentes estão no arquivo.")
    
    print(f"\n" + "="*70)
    print("VERIFICAÇÃO CONCLUÍDA")
    print("="*70)

if __name__ == "__main__":
    verificar_dados()
