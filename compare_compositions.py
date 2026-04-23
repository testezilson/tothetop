"""
Script para comparar duas composições de 5 campeões e prever qual é melhor.
Usa win rates de campeões individuais, sinergias e composições completas.
"""

import pandas as pd
import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Caminhos dos arquivos de dados
CHAMP_WR_PATH = os.path.join(DATA_DIR, "champion_winrates.csv")
SYNERGY_WR_PATH = os.path.join(DATA_DIR, "synergy_winrates.csv")
COMP_WR_PATH = os.path.join(DATA_DIR, "composition_winrates.csv")
MATCHUP_WR_PATH = os.path.join(DATA_DIR, "matchup_winrates.csv")
ORACLE_PREPARED_PATH = os.path.join(DATA_DIR, "oracle_prepared.csv")

# Ligas Major
MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}

def load_data():
    """Carrega todos os dados necessários"""
    data = {}
    
    if os.path.exists(CHAMP_WR_PATH):
        data["champ_wr"] = pd.read_csv(CHAMP_WR_PATH)
        print(f"[OK] Carregados win rates de {len(data['champ_wr'])} campeoes")
    else:
        print(f"[AVISO] Arquivo nao encontrado: {CHAMP_WR_PATH}")
        data["champ_wr"] = None
    
    if os.path.exists(SYNERGY_WR_PATH):
        data["synergy_wr"] = pd.read_csv(SYNERGY_WR_PATH)
        print(f"[OK] Carregadas sinergias de {len(data['synergy_wr'])} pares")
    else:
        print(f"[AVISO] Arquivo nao encontrado: {SYNERGY_WR_PATH}")
        data["synergy_wr"] = None
    
    if os.path.exists(COMP_WR_PATH):
        data["comp_wr"] = pd.read_csv(COMP_WR_PATH)
        print(f"[OK] Carregadas {len(data['comp_wr'])} composicoes completas")
    else:
        print(f"[AVISO] Arquivo nao encontrado: {COMP_WR_PATH}")
        data["comp_wr"] = None
    
    if os.path.exists(MATCHUP_WR_PATH):
        data["matchup_wr"] = pd.read_csv(MATCHUP_WR_PATH)
        print(f"[OK] Carregados matchups de {len(data['matchup_wr'])} pares")
    else:
        print(f"[AVISO] Arquivo nao encontrado: {MATCHUP_WR_PATH}")
        data["matchup_wr"] = None
    
    return data

def get_champ_wr(data, leagues, champ):
    """Obtém win rate e número de jogos de um campeão
    leagues pode ser uma string (liga única) ou lista de ligas
    """
    # Se for múltiplas ligas (MAJOR), recalcular diretamente do oracle_prepared.csv
    # para incluir todas as ligas, mesmo que tenham poucos jogos
    if isinstance(leagues, list) and len(leagues) > 1:
        return get_champ_wr_from_oracle(leagues, champ)
    
    # Liga única: usar champion_winrates.csv
    if data["champ_wr"] is None:
        return 50.0, 0  # Default
    
    # Se leagues é string, converter para lista
    if isinstance(leagues, str):
        leagues = [leagues]
    
    # Filtrar por ligas
    mask = data["champ_wr"]["league"].isin(leagues) & \
           (data["champ_wr"]["champion"].str.casefold() == str(champ).casefold())
    row = data["champ_wr"][mask]
    
    if not row.empty:
        # Se múltiplas ligas, calcular média ponderada por jogos
        if len(row) > 1:
            total_games = row["games_played"].sum()
            if total_games > 0:
                weighted_wr = (row["win_rate"] * row["games_played"]).sum() / total_games
                return float(weighted_wr), int(total_games)
        return float(row["win_rate"].iloc[0]), int(row["games_played"].iloc[0])
    return 50.0, 0

def get_champ_wr_from_oracle(leagues, champ):
    """Recalcula win rate diretamente do oracle_prepared.csv para incluir todas as ligas."""
    if not os.path.exists(ORACLE_PREPARED_PATH):
        return 50.0, 0
    
    df = pd.read_csv(ORACLE_PREPARED_PATH)
    
    # Filtrar por ligas
    df = df[df["league"].isin(leagues)]
    
    # Determinar vencedor de cada jogo
    winners = {}
    for gameid, df_game in df.groupby("gameid"):
        if len(df_game) != 2:
            continue
        t1_kills = df_game.iloc[0]["teamkills"]
        t2_kills = df_game.iloc[1]["teamkills"]
        if t1_kills > t2_kills:
            winners[gameid] = df_game.iloc[0]["teamname"]
        elif t2_kills > t1_kills:
            winners[gameid] = df_game.iloc[1]["teamname"]
    
    # Adicionar coluna de vitória
    df["won"] = df.apply(
        lambda row: 1 if winners.get(row["gameid"]) == row["teamname"] else 0,
        axis=1
    )
    
    # Buscar partidas onde o campeão jogou
    mask = (
        (df["pick1"].str.casefold() == str(champ).casefold()) |
        (df["pick2"].str.casefold() == str(champ).casefold()) |
        (df["pick3"].str.casefold() == str(champ).casefold()) |
        (df["pick4"].str.casefold() == str(champ).casefold()) |
        (df["pick5"].str.casefold() == str(champ).casefold())
    )
    
    champ_games = df[mask]
    
    if len(champ_games) == 0:
        return 50.0, 0
    
    # Contar jogos (cada partida aparece 2 vezes - uma por time)
    # Mas queremos contar quantas vezes o campeão jogou, não quantas partidas únicas
    total_games = len(champ_games)
    wins = int(champ_games["won"].sum())
    win_rate = (wins / total_games) * 100 if total_games > 0 else 50.0
    
    return float(win_rate), int(total_games)

def get_synergy_wr(data, leagues, champ1, champ2):
    """Obtém win rate e impacto de uma sinergia
    leagues pode ser uma string (liga única) ou lista de ligas
    """
    if data["synergy_wr"] is None:
        return 0.0, 50.0, 0  # Default (sem impacto, 50% WR, 0 jogos)
    
    # Se leagues é string, converter para lista
    if isinstance(leagues, str):
        leagues = [leagues]
    
    # Ordenar para garantir consistência
    c1, c2 = sorted([champ1, champ2])
    mask = data["synergy_wr"]["league"].isin(leagues) & \
           (data["synergy_wr"]["champ1"].str.casefold() == str(c1).casefold()) & \
           (data["synergy_wr"]["champ2"].str.casefold() == str(c2).casefold())
    row = data["synergy_wr"][mask]
    
    if not row.empty:
        # Se múltiplas ligas, calcular média ponderada
        if len(row) > 1:
            total_games = row["n_games"].sum()
            if total_games > 0:
                weighted_wr = (row["win_rate"] * row["n_games"]).sum() / total_games
                weighted_impact = (row["synergy_impact"] * row["n_games"]).sum() / total_games
                return float(weighted_impact), float(weighted_wr), int(total_games)
        return (
            float(row["synergy_impact"].iloc[0]),
            float(row["win_rate"].iloc[0]),
            int(row["n_games"].iloc[0])
        )
    return 0.0, 50.0, 0

def get_comp_wr(data, leagues, composition):
    """Obtém win rate de uma composição completa
    leagues pode ser uma string (liga única) ou lista de ligas
    """
    if data["comp_wr"] is None:
        return None
    
    # Se leagues é string, converter para lista
    if isinstance(leagues, str):
        leagues = [leagues]
    
    comp_key = "|".join(sorted(composition))
    mask = data["comp_wr"]["league"].isin(leagues) & \
           (data["comp_wr"]["composition"] == comp_key)
    row = data["comp_wr"][mask]
    
    if not row.empty:
        # Se múltiplas ligas, agregar dados
        if len(row) > 1:
            total_games = row["games"].sum()
            total_wins = row["wins"].sum()
            if total_games > 0:
                avg_wr = (total_wins / total_games) * 100
                return {
                    "win_rate": float(avg_wr),
                    "games": int(total_games),
                    "wins": int(total_wins)
                }
        return {
            "win_rate": float(row["win_rate"].iloc[0]),
            "games": int(row["games"].iloc[0]),
            "wins": int(row["wins"].iloc[0])
        }
    return None

def get_matchup_wr(data, leagues, champ1, champ2):
    """Obtém win rate de um matchup (champ1 vs champ2) e número de jogos
    leagues pode ser uma string (liga única) ou lista de ligas
    
    Retorna o win rate do champ1 quando enfrenta champ2.
    Se não houver dados suficientes (menos de 5 jogos), retorna 50% (default).
    """
    if data["matchup_wr"] is None:
        return 50.0, 0  # Default
    
    # Se leagues é string, converter para lista
    if isinstance(leagues, str):
        leagues = [leagues]
    
    mask = data["matchup_wr"]["league"].isin(leagues) & \
           (data["matchup_wr"]["champ1"].str.casefold() == str(champ1).casefold()) & \
           (data["matchup_wr"]["champ2"].str.casefold() == str(champ2).casefold())
    row = data["matchup_wr"][mask]
    
    if not row.empty:
        # Se múltiplas ligas, calcular média ponderada
        if len(row) > 1:
            total_games = row["games"].sum()
            if total_games > 0:
                weighted_wr = (row["win_rate"] * row["games"]).sum() / total_games
                return float(weighted_wr), int(total_games)
        return float(row["win_rate"].iloc[0]), int(row["games"].iloc[0])
    return 50.0, 0

def calculate_team_score(data, leagues, composition):
    """Calcula um score para a composição baseado em múltiplos fatores"""
    score = 0.0
    factors = {}
    
    # 1. Win rate médio dos campeões individuais
    champ_wrs = []
    champ_details = []
    for champ in composition:
        wr, games = get_champ_wr(data, leagues, champ)
        champ_wrs.append(wr)
        champ_details.append({"champion": champ, "win_rate": wr, "games": games})
    avg_champ_wr = sum(champ_wrs) / len(champ_wrs)
    factors["avg_champ_wr"] = avg_champ_wr
    factors["champ_details"] = champ_details
    score += avg_champ_wr * 0.3  # 30% do peso
    
    # 2. Sinergias internas (todos os pares)
    synergy_impacts = []
    synergy_details = []
    from itertools import combinations
    for c1, c2 in combinations(composition, 2):
        impact, wr, games = get_synergy_wr(data, leagues, c1, c2)
        synergy_impacts.append(impact)
        synergy_details.append({
            "champ1": c1,
            "champ2": c2,
            "win_rate": wr,
            "impact": impact,
            "games": games
        })
    avg_synergy = sum(synergy_impacts) / len(synergy_impacts) if synergy_impacts else 0
    factors["avg_synergy_impact"] = avg_synergy
    factors["synergy_details"] = synergy_details
    score += (50 + avg_synergy) * 0.3  # 30% do peso (converte impacto para win rate)
    
    # 3. Win rate da composição completa (se disponível)
    comp_data = get_comp_wr(data, leagues, composition)
    if comp_data:
        factors["comp_wr"] = comp_data["win_rate"]
        factors["comp_games"] = comp_data["games"]
        score += comp_data["win_rate"] * 0.4  # 40% do peso se disponível
    else:
        factors["comp_wr"] = None
        # Se não tem dados da comp completa, aumenta peso dos outros fatores
        score = score / 0.6  # Normaliza para 100%
    
    factors["total_score"] = score
    return score, factors

def compare_compositions(data, leagues, comp1, comp2):
    """Compara duas composições e retorna análise detalhada"""
    print(f"\n{'='*60}")
    print(f"COMPARACAO DE COMPOSICOES")
    print(f"{'='*60}\n")
    
    # Formatar nome das ligas para exibição
    if isinstance(leagues, list):
        # Verificar se são todas as 6 ligas major (incluindo LCS)
        ordem_major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]
        if len(leagues) == 6 and set(leagues) == set(ordem_major):
            league_display = "MAJOR (todas)"
        else:
            league_display = ", ".join(leagues)
    else:
        league_display = leagues
    
    print(f"Liga(s): {league_display}")
    print(f"\nTime 1: {' + '.join(comp1)}")
    print(f"Time 2: {' + '.join(comp2)}\n")
    
    # Calcular scores
    score1, factors1 = calculate_team_score(data, leagues, comp1)
    score2, factors2 = calculate_team_score(data, leagues, comp2)
    
    # Exibir análise do Time 1
    print(f"{'-'*60}")
    print(f"ANALISE TIME 1:")
    print(f"{'-'*60}")
    
    # Win rates individuais
    print(f"   Win Rates Individuais dos Campeoes:")
    for champ_detail in factors1['champ_details']:
        games = champ_detail.get('games', 0)
        if games > 0:
            print(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% ({games} jogos)")
        else:
            print(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% (sem dados)")
    print(f"   Win Rate medio dos campeoes: {factors1['avg_champ_wr']:.2f}%")
    print(f"      [Media simples dos win rates individuais acima]")
    
    # Sinergias
    print(f"\n   Sinergias (Pares de Campeoes):")
    sinergias_com_dados = [s for s in factors1['synergy_details'] if s['games'] > 0]
    if sinergias_com_dados:
        for syn_detail in sinergias_com_dados:
            print(f"      {syn_detail['champ1']} + {syn_detail['champ2']}: {syn_detail['win_rate']:.2f}% WR ({syn_detail['games']} jogos) | Impacto: {syn_detail['impact']:+.2f}%")
        print(f"   Impacto medio de sinergias: {factors1['avg_synergy_impact']:+.2f}%")
        print(f"      [Media dos impactos acima | Positivo = jogam bem juntos | Negativo = nao combinam bem]")
    else:
        print(f"      [AVISO] Nenhuma sinergia com dados suficientes (minimo 5 jogos)")
        print(f"   Impacto medio de sinergias: {factors1['avg_synergy_impact']:+.2f}%")
    
    if factors1['comp_wr']:
        print(f"\n   Win Rate da composicao completa: {factors1['comp_wr']:.2f}% ({factors1['comp_games']} jogos)")
    else:
        print(f"\n   Win Rate da composicao completa: N/A (composicao nao encontrada no historico)")
    print(f"\n   Score Total: {score1:.2f}%")
    
    # Exibir análise do Time 2
    print(f"\n{'-'*60}")
    print(f"ANALISE TIME 2:")
    print(f"{'-'*60}")
    
    # Win rates individuais
    print(f"   Win Rates Individuais dos Campeoes:")
    for champ_detail in factors2['champ_details']:
        games = champ_detail.get('games', 0)
        if games > 0:
            print(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% ({games} jogos)")
        else:
            print(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% (sem dados)")
    print(f"   Win Rate medio dos campeoes: {factors2['avg_champ_wr']:.2f}%")
    print(f"      [Media simples dos win rates individuais acima]")
    
    # Sinergias
    print(f"\n   Sinergias (Pares de Campeoes):")
    sinergias_com_dados = [s for s in factors2['synergy_details'] if s['games'] > 0]
    if sinergias_com_dados:
        for syn_detail in sinergias_com_dados:
            print(f"      {syn_detail['champ1']} + {syn_detail['champ2']}: {syn_detail['win_rate']:.2f}% WR ({syn_detail['games']} jogos) | Impacto: {syn_detail['impact']:+.2f}%")
        print(f"   Impacto medio de sinergias: {factors2['avg_synergy_impact']:+.2f}%")
        print(f"      [Media dos impactos acima | Positivo = jogam bem juntos | Negativo = nao combinam bem]")
    else:
        print(f"      [AVISO] Nenhuma sinergia com dados suficientes (minimo 5 jogos)")
        print(f"   Impacto medio de sinergias: {factors2['avg_synergy_impact']:+.2f}%")
    
    if factors2['comp_wr']:
        print(f"\n   Win Rate da composicao completa: {factors2['comp_wr']:.2f}% ({factors2['comp_games']} jogos)")
    else:
        print(f"\n   Win Rate da composicao completa: N/A (composicao nao encontrada no historico)")
    print(f"\n   Score Total: {score2:.2f}%")
    
    # Comparação
    diff = score1 - score2
    winner = "Time 1" if diff > 0 else "Time 2" if diff < 0 else "Empate"
    
    print(f"\n{'='*60}")
    print(f"RESULTADO:")
    print(f"{'='*60}")
    print(f"   Vencedor Previsto: {winner}")
    print(f"   Diferenca: {abs(diff):.2f}% pontos")
    if abs(diff) < 2:
        print(f"   [AVISO] Partida muito equilibrada!")
    elif abs(diff) < 5:
        print(f"   [INFO] Partida equilibrada, mas com leve vantagem")
    else:
        print(f"   [OK] Vantagem significativa")
    
    # Matchups individuais
    print(f"\n{'-'*60}")
    print(f"MATCHUPS INDIVIDUAIS (Time 1 vs Time 2):")
    print(f"[INFO] Win Rate = porcentagem de vitorias do campeao do Time 1 quando enfrenta o campeao do Time 2")
    print(f"[INFO] Apenas matchups com 5 ou mais jogos sao exibidos")
    print(f"{'-'*60}")
    matchup_scores = []
    matchup_games = []
    matchups_exibidos = 0
    for i, c1 in enumerate(comp1):
        for j, c2 in enumerate(comp2):
            wr, games = get_matchup_wr(data, leagues, c1, c2)
            pos1 = ["Top", "Jungle", "Mid", "ADC", "Support"][i]
            pos2 = ["Top", "Jungle", "Mid", "ADC", "Support"][j]
            if games > 0:
                print(f"   {c1} ({pos1}) vs {c2} ({pos2}): {wr:.2f}% WR de {c1} ({games} jogos)")
                matchup_scores.append(wr)
                matchup_games.append(games)
                matchups_exibidos += 1
    
    if matchup_scores:
        avg_matchup = sum(matchup_scores) / len(matchup_scores)
        print(f"\n   Win Rate medio nos matchups (do Time 1): {avg_matchup:.2f}%")
        print(f"   Matchups exibidos: {matchups_exibidos}/25 ({matchups_exibidos*100//25}%)")
    else:
        print(f"\n   [AVISO] Nenhum matchup com dados suficientes (minimo 5 jogos)")
    
    return {
        "winner": winner,
        "score1": score1,
        "score2": score2,
        "difference": abs(diff),
        "factors1": factors1,
        "factors2": factors2
    }

def get_available_leagues(data):
    """Obtém lista de ligas disponíveis nos dados"""
    leagues = set()
    if data["champ_wr"] is not None:
        leagues.update(data["champ_wr"]["league"].unique())
    if data["synergy_wr"] is not None:
        leagues.update(data["synergy_wr"]["league"].unique())
    if data["comp_wr"] is not None:
        leagues.update(data["comp_wr"]["league"].unique())
    if data["matchup_wr"] is not None:
        leagues.update(data["matchup_wr"]["league"].unique())
    return sorted(list(leagues))

def selecionar_liga(available_leagues):
    """Permite ao usuário selecionar liga: major, não-major, ou específica"""
    major_disponiveis = [lg for lg in available_leagues if lg in MAJOR_LEAGUES]
    nao_major_disponiveis = [lg for lg in available_leagues if lg not in MAJOR_LEAGUES]
    
    print("\n" + "="*60)
    print("SELECAO DE LIGA")
    print("="*60)
    print("Opcoes:")
    print("  1. MAJOR (todas as ligas major: LCK, LPL, LCS, CBLOL, LCP, LEC)")
    if nao_major_disponiveis:
        print("  2. NAO-MAJOR (todas as ligas que nao sao major)")
    print("  3. Liga especifica")
    print("="*60)
    
    escolha = input("Escolha uma opcao (1/2/3): ").strip()
    
    if escolha == "1":
        # Verificar quais ligas major existem nos dados (verificar em todos os arquivos)
        try:
            all_leagues = set()
            if os.path.exists(CHAMP_WR_PATH):
                df = pd.read_csv(CHAMP_WR_PATH)
                all_leagues.update(df["league"].unique())
            if os.path.exists(SYNERGY_WR_PATH):
                df = pd.read_csv(SYNERGY_WR_PATH)
                all_leagues.update(df["league"].unique())
            if os.path.exists(COMP_WR_PATH):
                df = pd.read_csv(COMP_WR_PATH)
                all_leagues.update(df["league"].unique())
            if os.path.exists(MATCHUP_WR_PATH):
                df = pd.read_csv(MATCHUP_WR_PATH)
                all_leagues.update(df["league"].unique())
            
            # Ordem específica: LCK, LPL, LCS, CBLOL, LCP, LEC
            ordem_major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]
            # Incluir todas as ligas major que existem nos dados OU que são major (incluindo LCS mesmo sem dados)
            major_final = []
            for lg in ordem_major:
                if lg in MAJOR_LEAGUES:
                    # Incluir se estiver nos dados OU se for LCS (sempre incluir LCS como major)
                    if lg in all_leagues or lg == "LCS":
                        major_final.append(lg)
            
            if major_final:
                print(f"\n[OK] Usando todas as ligas MAJOR: {', '.join(major_final)}")
                return major_final
        except:
            pass
        
        # Fallback: usar apenas as que estão em available_leagues
        if major_disponiveis:
            print(f"\n[OK] Usando ligas MAJOR disponíveis: {', '.join(major_disponiveis)}")
            return major_disponiveis
        else:
            print("[AVISO] Nenhuma liga major disponivel. Usando primeira liga disponivel.")
            return [available_leagues[0]]
    
    elif escolha == "2" and nao_major_disponiveis:
        print(f"\n[OK] Usando ligas NAO-MAJOR: {', '.join(nao_major_disponiveis)}")
        return nao_major_disponiveis
    
    elif escolha == "3":
        print(f"\nLigas disponiveis:")
        for i, lg in enumerate(available_leagues, 1):
            tipo = "MAJOR" if lg in MAJOR_LEAGUES else "nao-MAJOR"
            print(f"  {i}. {lg} ({tipo})")
        
        try:
            idx = int(input("\nEscolha o numero da liga: ").strip()) - 1
            if 0 <= idx < len(available_leagues):
                liga_escolhida = available_leagues[idx]
                print(f"[OK] Liga selecionada: {liga_escolhida}")
                return liga_escolhida
            else:
                print(f"[ERRO] Numero invalido. Usando primeira liga disponivel.")
                return available_leagues[0]
        except (ValueError, EOFError):
            print(f"[ERRO] Entrada invalida. Usando primeira liga disponivel.")
            return available_leagues[0]
    
    else:
        print(f"[AVISO] Opcao invalida. Usando primeira liga disponivel.")
        return available_leagues[0]

def main():
    print("=== Comparador de Composicoes - LoL Oracle ML v3 ===\n")
    
    # Carregar dados
    data = load_data()
    
    # Verificar se há argumentos de linha de comando
    if len(sys.argv) > 1:
        # Modo via argumentos (para compatibilidade)
        if len(sys.argv) < 8:
            print("[ERRO] Uso: python compare_compositions.py <league> <champ1_1> <champ1_2> ... <champ1_5> <champ2_1> <champ2_2> ... <champ2_5>")
            print("   Exemplo: python compare_compositions.py LPL Gnar Nocturne Orianna Varus Neeko K'Sante Viego Aurora Ashe Braum")
            return
        
        league = sys.argv[1]
        comp1 = sys.argv[2:7]
        comp2 = sys.argv[7:12]
    else:
        # Modo interativo
        print("[INFO] Modo interativo - Digite as informacoes solicitadas\n")
        
        # Obter ligas disponíveis
        available_leagues = get_available_leagues(data)
        if not available_leagues:
            print("[ERRO] Nenhuma liga encontrada nos dados!")
            return
        
        # Selecionar liga usando o novo sistema
        league = selecionar_liga(available_leagues)
        
        print("\n" + "="*60)
        print("TIME 1 - Digite os 5 campeoes (Top, Jungle, Mid, ADC, Support)")
        print("="*60)
        positions = ["Top", "Jungle", "Mid", "ADC", "Support"]
        comp1 = []
        for pos in positions:
            champ = input(f"{pos}: ").strip()
            if not champ:
                print(f"[ERRO] Campeao nao pode estar vazio!")
                return
            comp1.append(champ)
        
        print("\n" + "="*60)
        print("TIME 2 - Digite os 5 campeoes (Top, Jungle, Mid, ADC, Support)")
        print("="*60)
        comp2 = []
        for pos in positions:
            champ = input(f"{pos}: ").strip()
            if not champ:
                print(f"[ERRO] Campeao nao pode estar vazio!")
                return
            comp2.append(champ)
        
        print("\n")
    
    if len(comp1) != 5 or len(comp2) != 5:
        print("[ERRO] Cada composicao deve ter exatamente 5 campeoes!")
        return
    
    result = compare_compositions(data, league, comp1, comp2)
    
    print(f"\n{'='*60}")
    print("[OK] Analise concluida!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
