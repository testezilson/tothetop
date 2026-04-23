"""
Script para analisar impactos dos heróis do DOTA por período de tempo.
Permite escolher quantos meses serão analisados e mostra:
- Top 20 heróis com impactos mais positivos
- Top 20 heróis com impactos mais negativos
- Lista completa de todos os heróis analisados
"""
import sqlite3
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta

# Caminho do banco de dados do DOTA
DOTA_OPENDOTA_DIR = r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\dota_draft_ml_v1"
DOTA_DB_PATH = os.path.join(DOTA_OPENDOTA_DIR, "data", "dota_matches.db")

def find_dota_db():
    """Procura o banco de dados do DOTA."""
    if os.path.exists(DOTA_DB_PATH):
        return DOTA_DB_PATH
    
    # Fallback
    data_dir = os.path.join(DOTA_OPENDOTA_DIR, "data")
    if os.path.exists(data_dir):
        possible_names = ["dota_matches.db", "dota_matches_opendota.db"]
        for db_name in possible_names:
            db_path = os.path.join(data_dir, db_name)
            if os.path.exists(db_path):
                return db_path
    
    return None

def parse_heroes(heroes_json):
    """Converte JSON string de heróis para lista."""
    try:
        heroes = json.loads(heroes_json)
        if isinstance(heroes, list):
            return [str(h).strip() for h in heroes if isinstance(h, str) and str(h).strip()]
        return []
    except Exception:
        return []

def calculate_hero_impacts(db_path, months_back):
    """
    Calcula impactos dos heróis para os últimos N meses a partir de hoje.
    
    Parâmetros:
    - db_path: caminho do banco de dados
    - months_back: número de meses para trás a partir de hoje
    
    Retorna:
    - global_mean: média global de kills no período
    - hero_impacts: dict {hero_name: {'impact': float, 'mean_kills': float, 'games': int}}
    - total_matches: número total de partidas analisadas
    """
    print(f"\n📊 Conectando ao banco de dados...")
    conn = sqlite3.connect(db_path)
    
    # Data final = hoje
    end_date = datetime.now()
    
    # Data inicial = hoje - N meses
    start_date = end_date - timedelta(days=months_back * 30)
    
    cutoff_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    print(f"📅 Data inicial: {cutoff_date_str} ({months_back} meses atrás)")
    print(f"📅 Data final: {end_date_str} (hoje)")
    print(f"📅 Período: últimos {months_back} meses")
    
    # Query para buscar partidas com kills válidas
    # IMPORTANTE: Não filtrar por data na query inicial (como no compute_hero_impacts_dota_v2.py)
    # O filtro de data será aplicado depois no pandas
    query = """
        SELECT match_id, radiant_kills, dire_kills, heroes, start_date
        FROM dota_matches_stratz
        WHERE radiant_kills IS NOT NULL
        AND dire_kills IS NOT NULL
        AND heroes IS NOT NULL
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("❌ Nenhum jogo encontrado no banco de dados.")
        return None, {}, 0
    
    # Aplicar filtro de data se start_date estiver disponível
    if "start_date" in df.columns and df["start_date"].notna().any():
        df["start_date"] = pd.to_datetime(df["start_date"], errors='coerce')
        
        # Filtrar por data (entre start_date e end_date)
        # Incluir partidas com data válida no período E partidas sem data
        df_with_date = df[df["start_date"].notna()].copy()
        df_in_period = df_with_date[
            (df_with_date["start_date"] >= start_date) & 
            (df_with_date["start_date"] <= end_date)
        ].copy()
        
        # Incluir partidas sem data também (como o original faz)
        df_no_date = df[df["start_date"].isna()].copy()
        
        if len(df_in_period) > 0:
            if len(df_no_date) > 0:
                print(f"   ℹ️  {len(df_no_date)} partidas sem data também incluídas")
                df_filtered = pd.concat([df_in_period, df_no_date], ignore_index=True)
            else:
                df_filtered = df_in_period.copy()
        else:
            if len(df_no_date) > 0:
                print(f"⚠️ Nenhuma partida com data no período, mas {len(df_no_date)} partidas sem data serão incluídas")
                df_filtered = df_no_date.copy()
            else:
                print(f"⚠️ Nenhuma partida encontrada no período {cutoff_date_str} até {end_date_str}.")
                if df["start_date"].notna().any():
                    min_date = df["start_date"].min()
                    max_date = df["start_date"].max()
                    print(f"   Partidas disponíveis: {min_date.strftime('%Y-%m-%d')} até {max_date.strftime('%Y-%m-%d')}")
                return None, {}, 0
    else:
        # Se não houver coluna start_date, usar todas as partidas
        print("ℹ️  Coluna start_date não disponível. Usando TODAS as partidas.")
        df_filtered = df.copy()
    
    print(f"✅ {len(df_filtered)} partidas encontradas no período")
    
    # Calcular total de kills por partida
    df_filtered["total_kills"] = df_filtered["radiant_kills"] + df_filtered["dire_kills"]
    
    # Calcular média global
    global_mean = float(df_filtered["total_kills"].mean())
    total_matches = len(df_filtered)
    
    print(f"📈 Média global de kills: {global_mean:.2f}")
    print(f"📊 Total de partidas analisadas: {total_matches}")
    print()
    
    # Converter lista de heróis
    print("🔄 Processando heróis...")
    df_filtered["heroes_list"] = df_filtered["heroes"].apply(parse_heroes)
    
    # Expandir lista de heróis em linhas (cada herói em uma linha)
    exploded = df_filtered.explode("heroes_list")
    exploded = exploded.dropna(subset=["heroes_list"])
    exploded["heroes_list"] = exploded["heroes_list"].astype(str)
    
    # Calcular estatísticas por herói
    hero_stats = (
        exploded.groupby("heroes_list")["total_kills"]
        .agg(["count", "mean"])
        .reset_index()
        .rename(columns={"heroes_list": "hero_name"})
    )
    
    # Calcular impacto = média do herói - média global
    hero_stats["impact"] = hero_stats["mean"] - global_mean
    
    # Filtrar apenas heróis com pelo menos 5 jogos
    hero_stats = hero_stats[hero_stats["count"] >= 5]
    
    # Converter para dicionário
    hero_impacts = {
        row["hero_name"]: {
            "impact": float(row["impact"]),
            "mean_kills": float(row["mean"]),
            "games": int(row["count"]),
        }
        for _, row in hero_stats.iterrows()
    }
    
    print(f"✅ {len(hero_impacts)} heróis analisados (mínimo 5 jogos)")
    print()
    
    return global_mean, hero_impacts, total_matches

def display_results(global_mean, hero_impacts, total_matches, months_back):
    """Exibe os resultados formatados."""
    if not hero_impacts:
        print("❌ Nenhum herói encontrado para exibir.")
        return
    
    # Converter para lista ordenada
    heroes_list = [
        {
            "name": name,
            "impact": data["impact"],
            "mean_kills": data["mean_kills"],
            "games": data["games"]
        }
        for name, data in hero_impacts.items()
    ]
    
    # Ordenar por impacto (maior para menor)
    heroes_sorted = sorted(heroes_list, key=lambda x: x["impact"], reverse=True)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months_back * 30)
    
    print("=" * 80)
    print(f"📊 ANÁLISE DE IMPACTOS DOS HERÓIS - ÚLTIMOS {months_back} MESES")
    print(f"📅 Período: {start_date.strftime('%Y-%m-%d')} até {end_date.strftime('%Y-%m-%d')}")
    print("=" * 80)
    print(f"Média global de kills: {global_mean:.2f}")
    print(f"Total de partidas analisadas: {total_matches}")
    print(f"Total de heróis analisados: {len(heroes_sorted)}")
    print()
    
    # Top 20 heróis com impactos mais positivos
    print("=" * 80)
    print("🟢 TOP 20 HERÓIS COM IMPACTOS MAIS POSITIVOS")
    print("=" * 80)
    top_positive = heroes_sorted[:20]
    for idx, hero in enumerate(top_positive, 1):
        impact = hero["impact"]
        mean = hero["mean_kills"]
        games = hero["games"]
        emoji = "🔥" if impact > 2.0 else "✅"
        print(f"{idx:2d}. {hero['name']:<25} | Impacto: {impact:>+6.2f} | Média: {mean:>5.2f} | Jogos: {games:>4} {emoji}")
    print()
    
    # Top 20 heróis com impactos mais negativos
    print("=" * 80)
    print("🔴 TOP 20 HERÓIS COM IMPACTOS MAIS NEGATIVOS")
    print("=" * 80)
    top_negative = heroes_sorted[-20:][::-1]  # Últimos 20, invertidos
    for idx, hero in enumerate(top_negative, 1):
        impact = hero["impact"]
        mean = hero["mean_kills"]
        games = hero["games"]
        emoji = "❄️" if impact < -2.0 else "⚠️"
        print(f"{idx:2d}. {hero['name']:<25} | Impacto: {impact:>+6.2f} | Média: {mean:>5.2f} | Jogos: {games:>4} {emoji}")
    print()
    
    # Lista completa de todos os heróis
    print("=" * 80)
    print("📋 LISTA COMPLETA DE TODOS OS HERÓIS ANALISADOS")
    print("=" * 80)
    print(f"{'Pos':<4} | {'Herói':<25} | {'Impacto':>8} | {'Média Kills':>12} | {'Jogos':>6}")
    print("-" * 80)
    for idx, hero in enumerate(heroes_sorted, 1):
        impact = hero["impact"]
        mean = hero["mean_kills"]
        games = hero["games"]
        print(f"{idx:<4} | {hero['name']:<25} | {impact:>+8.2f} | {mean:>12.2f} | {games:>6}")
    print()
    
    # Estatísticas resumidas
    print("=" * 80)
    print("📈 ESTATÍSTICAS RESUMIDAS")
    print("=" * 80)
    impacts = [h["impact"] for h in heroes_sorted]
    print(f"Impacto médio: {np.mean(impacts):+.2f}")
    print(f"Impacto mediano: {np.median(impacts):+.2f}")
    print(f"Impacto máximo: {max(impacts):+.2f} ({top_positive[0]['name']})")
    print(f"Impacto mínimo: {min(impacts):+.2f} ({top_negative[0]['name']})")
    print(f"Desvio padrão: {np.std(impacts):.2f}")
    print()

def main():
    print("=" * 80)
    print("🎯 ANÁLISE DE IMPACTOS DOS HERÓIS DO DOTA POR PERÍODO")
    print("=" * 80)
    print()
    
    # Verificar banco de dados
    db_path = find_dota_db()
    if db_path is None:
        print("❌ Erro: Não foi possível encontrar o banco de dados do DOTA.")
        print(f"   Procurando em: {DOTA_DB_PATH}")
        return
    
    print(f"✅ Banco de dados encontrado: {db_path}")
    
    # Solicitar número de meses
    print()
    print("📅 Quantos meses você deseja analisar (a partir de hoje)?")
    print("   (Exemplo: 1 = último mês, 3 = últimos 3 meses, 6 = últimos 6 meses, 12 = últimos 12 meses)")
    
    while True:
        try:
            months_input = input("   Digite o número de meses: ").strip()
            months_back = int(months_input)
            if months_back <= 0:
                print("   ⚠️ Por favor, digite um número positivo.")
                continue
            if months_back > 24:
                print("   ⚠️ Número muito alto. Usando 24 meses como máximo.")
                months_back = 24
            break
        except ValueError:
            print("   ⚠️ Por favor, digite um número válido.")
    
    # Calcular datas
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months_back * 30)
    
    print()
    print(f"🔄 Analisando últimos {months_back} meses...")
    print(f"   Período: {start_date.strftime('%Y-%m-%d')} até {end_date.strftime('%Y-%m-%d')}")
    print()
    
    # Calcular impactos
    global_mean, hero_impacts, total_matches = calculate_hero_impacts(db_path, months_back)
    
    if global_mean is None:
        return
    
    # Exibir resultados
    display_results(global_mean, hero_impacts, total_matches, months_back)
    
    print("=" * 80)
    print("✅ Análise concluída!")
    print("=" * 80)

if __name__ == "__main__":
    main()
