import pandas as pd
import itertools
from collections import defaultdict
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "synergy_winrates.csv")

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

def main():
    print("=== Gerando Win Rates de Sinergias (Pares de Campeoes) - LoL Oracle ML v3 ===")

    # Carregar dataset
    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo nao encontrado: {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"[OK] Dataset carregado: {len(df)} linhas")

    # Determinar vencedor de cada jogo
    print("[OK] Determinando vencedores dos jogos...")
    winners = {}
    for gameid, df_game in df.groupby("gameid"):
        winner = determine_winner(df_game)
        if winner:
            winners[gameid] = winner

    # Adicionar coluna de vitória
    df["won"] = df.apply(
        lambda row: 1 if winners.get(row["gameid"]) == row["teamname"] else 0,
        axis=1
    )

    # Calcular win rate médio por liga (baseline)
    league_stats = df.groupby("league")["won"].mean().to_dict()

    # Criar dicionário para acumular vitórias por par
    synergy_dict = defaultdict(lambda: {"wins": 0, "games": 0})

    # Iterar sobre todas as linhas (cada time)
    print("[OK] Processando sinergias...")
    for idx, row in df.iterrows():
        league = row["league"]
        won = row["won"]
        champs = [row[c] for c in ["pick1", "pick2", "pick3", "pick4", "pick5"] if pd.notna(row[c])]

        # Gerar todas as combinações de 2 campeões
        for c1, c2 in itertools.combinations(sorted(champs), 2):
            key = (league, c1, c2)
            synergy_dict[key]["games"] += 1
            if won == 1:
                synergy_dict[key]["wins"] += 1

        if (idx + 1) % 2000 == 0:
            print(f"   [OK] Processadas {idx+1}/{len(df)} linhas...")

    # Agregar win rates e calcular impacto de sinergia
    registros = []
    for (league, c1, c2), stats in synergy_dict.items():
        n_games = stats["games"]
        n_wins = stats["wins"]
        win_rate = (n_wins / n_games * 100) if n_games > 0 else 0
        league_avg_wr = league_stats.get(league, 0.5) * 100
        synergy_impact = win_rate - league_avg_wr

        registros.append({
            "league": league,
            "champ1": c1,
            "champ2": c2,
            "n_games": n_games,
            "n_wins": n_wins,
            "win_rate": win_rate,
            "league_avg_wr": league_avg_wr,
            "synergy_impact": synergy_impact
        })

    df_syn = pd.DataFrame(registros)

    # Filtrar sinergias com amostragem mínima
    min_games = 5
    before = len(df_syn)
    df_syn = df_syn[df_syn["n_games"] >= min_games].copy()
    after = len(df_syn)
    print(f"[OK] Removidas sinergias com menos de {min_games} jogos ({before - after} removidas, {after} mantidas).")

    # Ordenar e salvar
    df_syn = df_syn.sort_values(["league", "win_rate"], ascending=[True, False])
    df_syn.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {OUTPUT_PATH}")
    print(f"[OK] Total de sinergias validas: {len(df_syn)}")
    print(f"\n[INFO] Top 5 sinergias por win rate (exemplo LPL):")
    if "LPL" in df_syn["league"].values:
        top5 = df_syn[df_syn["league"] == "LPL"].head(5)
        for _, row in top5.iterrows():
            print(f"   {row['champ1']} + {row['champ2']}: {row['win_rate']:.2f}% ({row['n_wins']}/{row['n_games']})")

if __name__ == "__main__":
    main()
