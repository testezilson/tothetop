"""
Script para validar as previsões do compare_compositions.

Analisa partidas das ligas especificadas dos últimos 4 meses e compara
as previsões com os resultados reais.
"""

import pandas as pd
import os
from datetime import datetime, timedelta
from compare_compositions import load_data, calculate_team_score

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")

# Ligas a analisar
LIGAS_ANALISAR = ["LPL", "LCK", "CBLOL", "LTA S", "LTA N", "LEC"]

def determine_winner_from_data(df_game):
    """Determina o vencedor de um jogo baseado em teamkills"""
    if len(df_game) != 2:
        return None
    
    t1_kills = df_game.iloc[0]["teamkills"]
    t2_kills = df_game.iloc[1]["teamkills"]
    
    if t1_kills > t2_kills:
        return df_game.iloc[0]["teamname"]
    elif t2_kills > t1_kills:
        return df_game.iloc[1]["teamname"]
    else:
        return None  # Empate

def get_composition(row):
    """Extrai a composição de um time"""
    comp = []
    for i in range(1, 6):
        pick = row.get(f"pick{i}")
        if pd.notna(pick) and str(pick).strip() != "":
            comp.append(str(pick).strip())
    return comp

def main():
    print("=== Validador de Previsoes - LoL Oracle ML v3 ===\n")
    
    # Carregar dados
    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo nao encontrado: {DATA_PATH}")
        return
    
    print(f"[OK] Carregando dados de {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    print(f"[OK] Total de linhas carregadas: {len(df)}")
    
    # Filtrar ligas
    print(f"\n[OK] Filtrando ligas: {', '.join(LIGAS_ANALISAR)}")
    df_filtered = df[df["league"].isin(LIGAS_ANALISAR)].copy()
    print(f"[OK] Partidas nas ligas selecionadas: {df_filtered['gameid'].nunique()}")
    
    # Filtrar por ano 2025
    if "date" not in df_filtered.columns:
        print(f"[ERRO] Coluna 'date' nao encontrada. Nao e possivel filtrar por data.")
        print(f"[INFO] Analisando todas as partidas das ligas selecionadas...")
        df_by_date = df_filtered
    else:
        print(f"\n[OK] Filtrando partidas de 2025...")
        # Converter datas
        df_filtered["date_parsed"] = pd.to_datetime(df_filtered["date"], errors='coerce')
        df_by_date = df_filtered[df_filtered["date_parsed"].notna()].copy()
        
        if len(df_by_date) == 0:
            print(f"[ERRO] Nenhuma data valida encontrada.")
            return
        
        # Filtrar por ano 2025
        df_by_date = df_by_date[df_by_date["date_parsed"].dt.year == 2025].copy()
        
        print(f"[OK] Partidas de 2025: {df_by_date['gameid'].nunique()}")
        
        if len(df_by_date) == 0:
            print(f"[AVISO] Nenhuma partida encontrada em 2025.")
            print(f"[INFO] Analisando todas as partidas das ligas selecionadas...")
            df_by_date = df_filtered
    
    # Carregar dados de win rates
    print(f"\n[OK] Carregando dados de win rates e sinergias...")
    data = load_data()
    
    # Processar cada partida
    print(f"\n[OK] Processando partidas...")
    resultados = []
    partidas_processadas = 0
    
    unique_games = df_by_date["gameid"].unique()
    total_games = len(unique_games)
    
    for gameid in unique_games:
        df_game = df_by_date[df_by_date["gameid"] == gameid]
        
        if len(df_game) != 2:
            continue
        
        t1 = df_game.iloc[0]
        t2 = df_game.iloc[1]
        league = t1["league"]
        
        # Obter composições
        comp1 = get_composition(t1)
        comp2 = get_composition(t2)
        
        # Verificar se ambas têm 5 campeões
        if len(comp1) != 5 or len(comp2) != 5:
            continue
        
        # Calcular scores
        try:
            score1, _ = calculate_team_score(data, league, comp1)
            score2, _ = calculate_team_score(data, league, comp2)
        except Exception as e:
            print(f"[AVISO] Erro ao calcular scores para {gameid}: {e}")
            continue
        
        # Calcular diferença
        diff = abs(score1 - score2)
        
        # Apenas considerar partidas com diferença >= 1%
        if diff < 1.0:
            continue
        
        # Determinar vencedor previsto
        if score1 > score2:
            vencedor_previsto = t1["teamname"]
            vantagem = score1 - score2
        else:
            vencedor_previsto = t2["teamname"]
            vantagem = score2 - score1
        
        # Determinar vencedor real
        vencedor_real = determine_winner_from_data(df_game)
        
        if vencedor_real is None:
            continue  # Empate, pular
        
        # Verificar se a previsão estava correta
        acertou = (vencedor_previsto == vencedor_real)
        
        resultados.append({
            "gameid": gameid,
            "league": league,
            "date": t1.get("date", "N/A"),
            "team1": t1["teamname"],
            "team2": t2["teamname"],
            "score1": score1,
            "score2": score2,
            "diferenca": diff,
            "vencedor_previsto": vencedor_previsto,
            "vencedor_real": vencedor_real,
            "acertou": acertou
        })
        
        partidas_processadas += 1
        if partidas_processadas % 50 == 0:
            print(f"   Processadas {partidas_processadas}/{total_games} partidas...")
    
    # Análise dos resultados
    print(f"\n{'='*80}")
    print(f"RESULTADOS DA VALIDACAO")
    print(f"{'='*80}\n")
    
    if len(resultados) == 0:
        print(f"[AVISO] Nenhuma partida com diferenca >= 1% encontrada.")
        return
    
    df_resultados = pd.DataFrame(resultados)
    
    total_analises = len(df_resultados)
    acertos = df_resultados["acertou"].sum()
    erros = total_analises - acertos
    taxa_acerto = (acertos / total_analises * 100) if total_analises > 0 else 0
    
    print(f"Total de partidas analisadas (diferenca >= 1%): {total_analises}")
    print(f"   Acertos: {acertos} ({taxa_acerto:.2f}%)")
    print(f"   Erros: {erros} ({100 - taxa_acerto:.2f}%)")
    
    # Análise por liga
    print(f"\n{'='*80}")
    print(f"ANALISE POR LIGA")
    print(f"{'='*80}\n")
    
    for liga in LIGAS_ANALISAR:
        df_liga = df_resultados[df_resultados["league"] == liga]
        if len(df_liga) > 0:
            total_liga = len(df_liga)
            acertos_liga = df_liga["acertou"].sum()
            taxa_liga = (acertos_liga / total_liga * 100) if total_liga > 0 else 0
            print(f"{liga}:")
            print(f"   Total: {total_liga} partidas")
            print(f"   Acertos: {acertos_liga} ({taxa_liga:.2f}%)")
            print(f"   Erros: {total_liga - acertos_liga} ({100 - taxa_liga:.2f}%)")
        else:
            print(f"{liga}: Nenhuma partida com diferenca >= 1%")
    
    # Análise por faixa de diferença
    print(f"\n{'='*80}")
    print(f"ANALISE POR FAIXA DE DIFERENCA")
    print(f"{'='*80}\n")
    
    df_resultados["faixa"] = pd.cut(
        df_resultados["diferenca"],
        bins=[0, 2, 5, 10, 100],
        labels=["1-2%", "2-5%", "5-10%", "10%+"]
    )
    
    for faixa in ["1-2%", "2-5%", "5-10%", "10%+"]:
        df_faixa = df_resultados[df_resultados["faixa"] == faixa]
        if len(df_faixa) > 0:
            total_faixa = len(df_faixa)
            acertos_faixa = df_faixa["acertou"].sum()
            taxa_faixa = (acertos_faixa / total_faixa * 100) if total_faixa > 0 else 0
            print(f"{faixa}:")
            print(f"   Total: {total_faixa} partidas")
            print(f"   Acertos: {acertos_faixa} ({taxa_faixa:.2f}%)")
            print(f"   Erros: {total_faixa - acertos_faixa} ({100 - taxa_faixa:.2f}%)")
    
    # Salvar resultados detalhados
    output_path = os.path.join(BASE_DIR, "data", "validacao_previsoes.csv")
    df_resultados.to_csv(output_path, index=False)
    print(f"\n{'='*80}")
    print(f"[OK] Resultados detalhados salvos em: {output_path}")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
