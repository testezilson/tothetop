"""
Script para visualizar as últimas partidas na database Oracle.

Uso:
    python ver_ultimas_partidas.py [liga] [numero_de_partidas]
    
Exemplos:
    python ver_ultimas_partidas.py                    # Modo interativo
    python ver_ultimas_partidas.py LPL                # Últimas 10 partidas da LPL
    python ver_ultimas_partidas.py LPL 20             # Últimas 20 partidas da LPL
    python ver_ultimas_partidas.py 1 15              # Liga número 1, 15 partidas
"""

import pandas as pd
import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")

def determine_winner(df_game):
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

def format_composition(row):
    """Formata a composição de um time"""
    picks = [row[c] for c in ["pick1", "pick2", "pick3", "pick4", "pick5"] if pd.notna(row[c])]
    return " + ".join(picks)

def main():
    print("=== Visualizador de Ultimas Partidas - LoL Oracle ML v3 ===\n")
    
    # Carregar dados
    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo nao encontrado: {DATA_PATH}")
        return
    
    print(f"[OK] Carregando dados de {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    print(f"[OK] Total de linhas carregadas: {len(df)}")
    
    # Verificar se coluna date existe
    tem_data = "date" in df.columns
    if not tem_data:
        print(f"[AVISO] Coluna 'date' nao encontrada no arquivo. Datas nao serao exibidas.")
        print(f"        Para incluir datas, reprocesse o arquivo com prepare_oracle_dataset.py ou atualizar_database.py")
    
    # Obter ligas disponíveis
    ligas_disponiveis = sorted(df["league"].unique())
    print(f"\n[OK] Ligas disponiveis ({len(ligas_disponiveis)}):")
    for i, liga in enumerate(ligas_disponiveis, 1):
        n_partidas_liga = df[df["league"] == liga]["gameid"].nunique()
        print(f"   {i}. {liga} ({n_partidas_liga} partidas)")
    
    # Escolher liga
    if len(sys.argv) > 1:
        # Tentar usar argumento como número ou nome da liga
        try:
            liga_escolhida_num = int(sys.argv[1])
            if 1 <= liga_escolhida_num <= len(ligas_disponiveis):
                liga_escolhida = ligas_disponiveis[liga_escolhida_num - 1]
            else:
                print(f"[ERRO] Numero invalido. Use um numero entre 1 e {len(ligas_disponiveis)}")
                return
        except ValueError:
            # Se não for número, tentar como nome da liga
            liga_escolhida = sys.argv[1]
            if liga_escolhida not in ligas_disponiveis:
                print(f"[ERRO] Liga '{liga_escolhida}' nao encontrada.")
                print(f"[INFO] Ligas disponiveis: {', '.join(ligas_disponiveis)}")
                return
    else:
        try:
            escolha = input(f"\nEscolha a liga (numero 1-{len(ligas_disponiveis)} ou nome): ").strip()
            # Tentar como número primeiro
            try:
                liga_escolhida_num = int(escolha)
                if 1 <= liga_escolhida_num <= len(ligas_disponiveis):
                    liga_escolhida = ligas_disponiveis[liga_escolhida_num - 1]
                else:
                    print(f"[ERRO] Numero invalido. Usando padrao: {ligas_disponiveis[0]}")
                    liga_escolhida = ligas_disponiveis[0]
            except ValueError:
                # Se não for número, tentar como nome
                if escolha in ligas_disponiveis:
                    liga_escolhida = escolha
                else:
                    print(f"[AVISO] Liga '{escolha}' nao encontrada. Usando padrao: {ligas_disponiveis[0]}")
                    liga_escolhida = ligas_disponiveis[0]
        except (ValueError, EOFError):
            liga_escolhida = ligas_disponiveis[0]
            print(f"[INFO] Usando padrao: {liga_escolhida}")
    
    print(f"\n[OK] Liga selecionada: {liga_escolhida}")
    
    # Filtrar por liga
    df = df[df["league"] == liga_escolhida].copy()
    
    # Obter número de partidas a exibir
    if len(sys.argv) > 2:
        try:
            n_partidas = int(sys.argv[2])
        except ValueError:
            print(f"[AVISO] Numero invalido: {sys.argv[2]}. Usando padrao: 10")
            n_partidas = 10
    else:
        try:
            n_partidas = input(f"\nQuantas partidas deseja ver? (padrao: 10): ").strip()
            n_partidas = int(n_partidas) if n_partidas else 10
        except (ValueError, EOFError):
            n_partidas = 10
            print(f"[INFO] Usando padrao: {n_partidas} partidas")
    
    # Agrupar por gameid e obter partidas únicas
    unique_games = df["gameid"].unique()
    print(f"\n[OK] Total de partidas unicas na liga {liga_escolhida}: {len(unique_games)}")
    
    # Ordenar partidas por data (se disponível) ou por gameid
    if tem_data:
        # Criar DataFrame temporário com gameid e data para ordenação
        df_dates = df.groupby("gameid")["date"].first().reset_index()
        df_dates = df_dates[df_dates["date"].notna()].copy()
        
        if len(df_dates) > 0:
            # Converter datas para datetime se possível
            try:
                df_dates["date_parsed"] = pd.to_datetime(df_dates["date"], errors='coerce')
                df_dates = df_dates[df_dates["date_parsed"].notna()].copy()
                df_dates = df_dates.sort_values("date_parsed", ascending=False)
                sorted_games = df_dates["gameid"].tolist()
                # Adicionar gameids sem data no final
                games_without_date = [g for g in unique_games if g not in sorted_games]
                sorted_games.extend(games_without_date)
            except:
                # Se não conseguir converter, ordenar alfabeticamente por data
                df_dates = df_dates.sort_values("date", ascending=False)
                sorted_games = df_dates["gameid"].tolist()
                games_without_date = [g for g in unique_games if g not in sorted_games]
                sorted_games.extend(games_without_date)
        else:
            # Se não houver datas válidas, ordenar por gameid
            try:
                def extract_game_number(gameid):
                    try:
                        parts = str(gameid).split('-')
                        if len(parts) > 0:
                            return int(parts[0])
                        return 0
                    except:
                        return 0
                sorted_games = sorted(unique_games, key=extract_game_number, reverse=True)
            except:
                sorted_games = sorted(unique_games, reverse=True)
    else:
        # Ordenar gameids (assumindo que gameids mais altos são mais recentes)
        try:
            def extract_game_number(gameid):
                try:
                    parts = str(gameid).split('-')
                    if len(parts) > 0:
                        return int(parts[0])
                    return 0
                except:
                    return 0
            sorted_games = sorted(unique_games, key=extract_game_number, reverse=True)
        except:
            sorted_games = sorted(unique_games, reverse=True)
    
    # Pegar as últimas N partidas
    ultimas_partidas = sorted_games[:n_partidas]
    
    print(f"\n{'='*80}")
    print(f"ULTIMAS {len(ultimas_partidas)} PARTIDAS - LIGA: {liga_escolhida}")
    print(f"{'='*80}\n")
    
    # Processar cada partida
    for idx, gameid in enumerate(ultimas_partidas, 1):
        df_game = df[df["gameid"] == gameid]
        
        if len(df_game) != 2:
            continue
        
        t1 = df_game.iloc[0]
        t2 = df_game.iloc[1]
        league = t1["league"]
        
        winner = determine_winner(df_game)
        
        print(f"{idx}. PARTIDA: {gameid}")
        print(f"   Liga: {league}")
        
        # Mostrar data se disponível
        if tem_data and "date" in df_game.columns:
            date_val = t1.get("date")
            if pd.notna(date_val) and str(date_val).strip() != "":
                date_str = str(date_val)
                # Tentar formatar a data se for datetime
                try:
                    date_parsed = pd.to_datetime(date_val)
                    date_str = date_parsed.strftime("%Y-%m-%d")
                except:
                    pass
                print(f"   Data: {date_str}")
        elif not tem_data:
            print(f"   Data: [Nao disponivel]")
        
        print(f"   {'-'*76}")
        
        # Time 1
        t1_won = "[VENCEU]" if winner == t1["teamname"] else "[PERDEU]"
        print(f"   {t1['teamname']} {t1_won}")
        print(f"      Kills: {t1['teamkills']}")
        print(f"      Composicao: {format_composition(t1)}")
        
        # Time 2
        t2_won = "[VENCEU]" if winner == t2["teamname"] else "[PERDEU]"
        print(f"   {t2['teamname']} {t2_won}")
        print(f"      Kills: {t2['teamkills']}")
        print(f"      Composicao: {format_composition(t2)}")
        
        print(f"   Total de Kills: {t1['total_kills']}")
        print()
    
    # Estatísticas da liga selecionada
    print(f"{'='*80}")
    print(f"ESTATISTICAS - LIGA: {liga_escolhida}")
    print(f"{'='*80}")
    print(f"   Total de partidas na liga: {len(unique_games)}")
    
    # Carregar dados completos para estatísticas gerais
    df_completo = pd.read_csv(DATA_PATH)
    print(f"\n   Estatisticas gerais da database:")
    print(f"   Total de partidas na database: {df_completo['gameid'].nunique()}")
    print(f"   Total de ligas: {df_completo['league'].nunique()}")
    
    # Partidas por liga (top 10)
    print(f"\n   Top 10 ligas por numero de partidas:")
    partidas_por_liga = df_completo.groupby("league")["gameid"].nunique().sort_values(ascending=False)
    for liga, n_partidas_liga in partidas_por_liga.head(10).items():
        marcador = " <-- SELECIONADA" if liga == liga_escolhida else ""
        print(f"      {liga}: {n_partidas_liga} partidas{marcador}")

if __name__ == "__main__":
    main()
