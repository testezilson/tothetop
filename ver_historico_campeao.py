"""
Script para visualizar o histórico de um campeão específico
Mostra todas as partidas onde o campeão jogou e calcula estatísticas
"""

import pandas as pd
import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")

# Ligas Major
MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}

def determinar_vencedor(df_game):
    """Determina qual time venceu a partida"""
    if len(df_game) != 2:
        return None
    
    # Tentar usar coluna "result" se disponível
    if "result" in df_game.columns:
        t1_result = df_game.iloc[0]["result"]
        t2_result = df_game.iloc[1]["result"]
        
        # result geralmente é 1 para vitória, 0 para derrota
        if pd.notna(t1_result) and pd.notna(t2_result):
            if t1_result == 1 or str(t1_result).lower() in ['1', 'true', 'win', 'w']:
                return df_game.iloc[0]["teamname"]
            elif t2_result == 1 or str(t2_result).lower() in ['1', 'true', 'win', 'w']:
                return df_game.iloc[1]["teamname"]
    
    # Fallback: usar kills
    t1_kills = df_game.iloc[0]["teamkills"]
    t2_kills = df_game.iloc[1]["teamkills"]
    
    if t1_kills > t2_kills:
        return df_game.iloc[0]["teamname"]
    elif t2_kills > t1_kills:
        return df_game.iloc[1]["teamname"]
    else:
        return None  # Empate

def obter_campeoes_disponiveis(df):
    """Obtém lista de todos os campeões disponíveis"""
    campeoes = set()
    for col in ["pick1", "pick2", "pick3", "pick4", "pick5"]:
        if col in df.columns:
            campeoes.update(df[col].dropna().unique())
    return sorted([c for c in campeoes if c and str(c).strip() != ""])

def buscar_partidas_campeao(df, campeao, liga=None, apenas_major=False, apenas_nao_major=False):
    """Busca todas as partidas onde o campeão apareceu"""
    # Filtrar por campeão em qualquer pick
    mask = (
        (df["pick1"].str.casefold() == campeao.casefold()) |
        (df["pick2"].str.casefold() == campeao.casefold()) |
        (df["pick3"].str.casefold() == campeao.casefold()) |
        (df["pick4"].str.casefold() == campeao.casefold()) |
        (df["pick5"].str.casefold() == campeao.casefold())
    )
    
    if liga:
        mask = mask & (df["league"].str.casefold() == liga.casefold())
    elif apenas_major:
        mask = mask & df["league"].isin(MAJOR_LEAGUES)
    elif apenas_nao_major:
        mask = mask & ~df["league"].isin(MAJOR_LEAGUES)
    
    partidas_campeao = df[mask].copy()
    
    # Adicionar informação de vitória
    partidas_campeao["venceu"] = False
    for gameid in partidas_campeao["gameid"].unique():
        df_game = df[df["gameid"] == gameid]
        vencedor = determinar_vencedor(df_game)
        if vencedor:
            partidas_campeao.loc[partidas_campeao["gameid"] == gameid, "venceu"] = \
                partidas_campeao.loc[partidas_campeao["gameid"] == gameid, "teamname"] == vencedor
    
    return partidas_campeao

def calcular_estatisticas(partidas):
    """Calcula estatísticas das partidas do campeão"""
    if len(partidas) == 0:
        return None
    
    stats = {
        "total_jogos": len(partidas),
        "vitorias": int(partidas["venceu"].sum()),
        "derrotas": int((~partidas["venceu"]).sum()),
        "win_rate": (partidas["venceu"].sum() / len(partidas)) * 100,
        "media_total_kills": partidas["total_kills"].mean(),
        "mediana_total_kills": partidas["total_kills"].median(),
        "min_total_kills": partidas["total_kills"].min(),
        "max_total_kills": partidas["total_kills"].max(),
        "desvio_total_kills": partidas["total_kills"].std(),
    }
    
    # Estatísticas por liga
    stats["por_liga"] = {}
    for liga in partidas["league"].unique():
        partidas_liga = partidas[partidas["league"] == liga]
        stats["por_liga"][liga] = {
            "jogos": len(partidas_liga),
            "vitorias": int(partidas_liga["venceu"].sum()),
            "win_rate": (partidas_liga["venceu"].sum() / len(partidas_liga)) * 100 if len(partidas_liga) > 0 else 0,
            "media_total_kills": partidas_liga["total_kills"].mean(),
        }
    
    return stats

def exibir_historico(partidas, campeao, stats):
    """Exibe o histórico formatado"""
    print("\n" + "="*80)
    print(f"HISTORICO DO CAMPEAO: {campeao.upper()}")
    print("="*80)
    
    # Estatísticas gerais
    print(f"\nESTATISTICAS GERAIS:")
    print(f"  Total de jogos: {stats['total_jogos']}")
    print(f"  Vitorias: {stats['vitorias']} | Derrotas: {stats['derrotas']}")
    print(f"  Win Rate: {stats['win_rate']:.2f}%")
    print(f"\n  Total de Kills (por partida):")
    print(f"    Media: {stats['media_total_kills']:.2f}")
    print(f"    Mediana: {stats['mediana_total_kills']:.2f}")
    print(f"    Minimo: {stats['min_total_kills']:.0f}")
    print(f"    Maximo: {stats['max_total_kills']:.0f}")
    print(f"    Desvio Padrao: {stats['desvio_total_kills']:.2f}")
    
    # Estatísticas por liga
    if stats["por_liga"]:
        print(f"\n  ESTATISTICAS POR LIGA:")
        for liga, liga_stats in sorted(stats["por_liga"].items()):
            print(f"    {liga}:")
            print(f"      Jogos: {liga_stats['jogos']} | Win Rate: {liga_stats['win_rate']:.2f}%")
            print(f"      Media Total Kills: {liga_stats['media_total_kills']:.2f}")
    
    # Histórico detalhado
    print(f"\n" + "="*80)
    print(f"HISTORICO DETALHADO ({len(partidas)} partidas)")
    print("="*80)
    
    # Ordenar por data (mais recente primeiro)
    if "date" in partidas.columns:
        partidas["date"] = pd.to_datetime(partidas["date"], errors='coerce')
        partidas = partidas.sort_values("date", ascending=False)
    
    # Exibir partidas
    for idx, row in partidas.iterrows():
        data = row.get("date", "N/A")
        if pd.notna(data):
            data_str = data.strftime("%Y-%m-%d") if hasattr(data, 'strftime') else str(data)
        else:
            data_str = "N/A"
        
        liga = row["league"]
        time = row["teamname"]
        adversario = row.get("opponent", "N/A")
        resultado = "VITORIA" if row["venceu"] else "DERROTA"
        total_kills = row["total_kills"]
        teamkills = row["teamkills"]
        
        # Determinar posição do campeão
        posicoes = []
        for i in range(1, 6):
            if str(row[f"pick{i}"]).casefold() == campeao.casefold():
                posicoes.append(f"Pos{i}")
        
        posicao_str = ", ".join(posicoes) if posicoes else "?"
        
        print(f"\n  {data_str} | {liga} | {time} vs {adversario}")
        print(f"    Resultado: {resultado} | Total Kills: {total_kills:.0f} | Kills do Time: {teamkills:.0f}")
        print(f"    Posicao: {posicao_str}")

def main():
    print("="*80)
    print("HISTORICO DE CAMPEAO - LoL Oracle ML v3")
    print("="*80)
    
    # Carregar dados
    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo nao encontrado: {DATA_PATH}")
        return
    
    print(f"\n[OK] Carregando dados de {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    print(f"[OK] {len(df)} linhas carregadas")
    
    # Obter campeões disponíveis
    campeoes = obter_campeoes_disponiveis(df)
    print(f"[OK] {len(campeoes)} campeoes encontrados no banco de dados")
    
    # Selecionar campeão
    print(f"\n" + "="*80)
    print("SELECAO DE CAMPEAO")
    print("="*80)
    
    # Busca interativa
    busca = input("\nDigite o nome do campeao (ou parte do nome): ").strip()
    if not busca:
        print("[ERRO] Nome do campeao nao pode estar vazio!")
        return
    
    # Buscar campeões que correspondem
    matches = [c for c in campeoes if busca.casefold() in str(c).casefold()]
    
    if not matches:
        print(f"[ERRO] Nenhum campeao encontrado com '{busca}'")
        print(f"\nCampeoes disponiveis (primeiros 20):")
        for i, c in enumerate(campeoes[:20], 1):
            print(f"  {i}. {c}")
        return
    
    if len(matches) == 1:
        campeao = matches[0]
        print(f"[OK] Campeao selecionado: {campeao}")
    else:
        print(f"\n[OK] {len(matches)} campeoes encontrados:")
        for i, c in enumerate(matches, 1):
            print(f"  {i}. {c}")
        try:
            escolha = int(input(f"\nEscolha o numero (1-{len(matches)}): ").strip()) - 1
            if 0 <= escolha < len(matches):
                campeao = matches[escolha]
                print(f"[OK] Campeao selecionado: {campeao}")
            else:
                print("[ERRO] Numero invalido!")
                return
        except (ValueError, EOFError):
            print("[ERRO] Entrada invalida!")
            return
    
    # Filtrar por liga (opcional)
    ligas_disponiveis = sorted(df["league"].unique().tolist())
    major_disponiveis = [lg for lg in ligas_disponiveis if lg in MAJOR_LEAGUES]
    nao_major_disponiveis = [lg for lg in ligas_disponiveis if lg not in MAJOR_LEAGUES]
    
    print(f"\n" + "="*80)
    print("FILTRO POR LIGA (opcional)")
    print("="*80)
    print("Opcoes:")
    print("  1. MAJOR (todas as ligas major: LPL, LCK, LEC, CBLOL, LCS, LCP)")
    if nao_major_disponiveis:
        print("  2. NAO-MAJOR (todas as ligas que nao sao major)")
    print("  3. Liga especifica")
    print("  4. Todas as ligas (sem filtro)")
    print("="*80)
    
    escolha = input("\nEscolha uma opcao (1/2/3/4): ").strip()
    
    liga_filtro = None
    apenas_major = False
    apenas_nao_major = False
    
    if escolha == "1":
        if major_disponiveis:
            apenas_major = True
            print(f"\n[OK] Filtrando apenas ligas MAJOR: {', '.join(major_disponiveis)}")
        else:
            print("[AVISO] Nenhuma liga major disponivel. Usando todas as ligas.")
    
    elif escolha == "2" and nao_major_disponiveis:
        apenas_nao_major = True
        print(f"\n[OK] Filtrando ligas NAO-MAJOR: {', '.join(nao_major_disponiveis)}")
    
    elif escolha == "3":
        print(f"\nLigas disponiveis:")
        for i, lg in enumerate(ligas_disponiveis, 1):
            tipo = "MAJOR" if lg in MAJOR_LEAGUES else "nao-MAJOR"
            print(f"  {i}. {lg} ({tipo})")
        
        try:
            idx = int(input("\nEscolha o numero da liga: ").strip()) - 1
            if 0 <= idx < len(ligas_disponiveis):
                liga_filtro = ligas_disponiveis[idx]
                print(f"[OK] Liga selecionada: {liga_filtro}")
            else:
                print(f"[ERRO] Numero invalido. Usando todas as ligas.")
        except (ValueError, EOFError):
            print(f"[ERRO] Entrada invalida. Usando todas as ligas.")
    
    elif escolha == "4" or escolha == "":
        print(f"\n[OK] Sem filtro de liga - usando todas as ligas")
    
    else:
        print(f"[AVISO] Opcao invalida. Usando todas as ligas.")
    
    # Buscar partidas
    print(f"\n[OK] Buscando partidas do campeao {campeao}...")
    partidas = buscar_partidas_campeao(df, campeao, liga_filtro, apenas_major, apenas_nao_major)
    
    if len(partidas) == 0:
        print(f"[ERRO] Nenhuma partida encontrada para o campeao {campeao}")
        if liga_filtro:
            print(f"       (com filtro de liga: {liga_filtro})")
        elif apenas_major:
            print(f"       (apenas ligas MAJOR)")
        elif apenas_nao_major:
            print(f"       (apenas ligas NAO-MAJOR)")
        return
    
    print(f"[OK] {len(partidas)} partidas encontradas")
    
    # Calcular estatísticas
    stats = calcular_estatisticas(partidas)
    
    # Exibir histórico
    exibir_historico(partidas, campeao, stats)
    
    # Opção para salvar
    print(f"\n" + "="*80)
    salvar = input("Deseja salvar o historico em CSV? (s/n): ").strip().lower()
    if salvar in ['s', 'sim', 'y', 'yes']:
        output_path = os.path.join(BASE_DIR, "data", f"historico_{campeao.replace(' ', '_').replace("'", '')}.csv")
        partidas.to_csv(output_path, index=False)
        print(f"[OK] Historico salvo em: {output_path}")
    
    print("\n" + "="*80)
    print("[OK] Analise concluida!")
    print("="*80)

if __name__ == "__main__":
    main()
