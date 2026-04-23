import pandas as pd
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "matchup_winrates.csv")

def determine_winner(df_game):
    """Determina o vencedor de um jogo baseado em teamkills"""
    if len(df_game) != 2:
        return None
    
    t1_kills = df_game.iloc[0]["teamkills"]
    t2_kills = df_game.iloc[1]["teamkills"]
    
    if t1_kills > t2_kills:
        return 0  # Time 1 venceu
    elif t2_kills > t1_kills:
        return 1  # Time 2 venceu
    else:
        return None  # Empate

def main():
    print("=== Gerando Win Rates de Matchups (Campeao X vs Campeao Y) - LoL Oracle ML v3 ===")

    # Carregar dataset
    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo nao encontrado: {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"[OK] Dataset carregado: {len(df)} linhas")

    # Processar matchups
    print("[OK] Processando matchups...")
    matchup_data = []

    for gameid, df_game in df.groupby("gameid"):
        if len(df_game) != 2:
            continue

        winner = determine_winner(df_game)
        if winner is None:
            continue

        t1 = df_game.iloc[0]
        t2 = df_game.iloc[1]
        league = t1["league"]

        # Obter todos os campeões de cada time
        t1_champs = [t1[c] for c in ["pick1", "pick2", "pick3", "pick4", "pick5"] if pd.notna(t1[c])]
        t2_champs = [t2[c] for c in ["pick1", "pick2", "pick3", "pick4", "pick5"] if pd.notna(t2[c])]

        # Criar matchups: cada campeão do time 1 vs cada campeão do time 2
        for c1 in t1_champs:
            for c2 in t2_champs:
                # Matchup do ponto de vista de c1 (quando c1 enfrenta c2)
                matchup_data.append({
                    "league": league,
                    "champ1": c1,
                    "champ2": c2,
                    "champ1_won": 1 if winner == 0 else 0
                })

    df_matchups = pd.DataFrame(matchup_data)
    print(f"[OK] Total de matchups processados: {len(df_matchups)}")

    # Calcular win rate por matchup
    matchup_stats = (
        df_matchups.groupby(["league", "champ1", "champ2"])
        .agg({
            "champ1_won": ["sum", "count"]
        })
        .reset_index()
    )
    matchup_stats.columns = ["league", "champ1", "champ2", "wins", "games"]
    matchup_stats["win_rate"] = matchup_stats["wins"] / matchup_stats["games"] * 100

    # Calcular win rate médio da liga (baseline)
    league_stats = (
        df_matchups.groupby("league")["champ1_won"].mean()
        .reset_index()
    )
    league_stats.columns = ["league", "league_avg_wr"]
    league_stats["league_avg_wr"] = league_stats["league_avg_wr"] * 100

    # Juntar com as médias da liga
    merged = matchup_stats.merge(league_stats, on="league", how="left")
    merged["matchup_impact"] = merged["win_rate"] - merged["league_avg_wr"]

    # Aplicar filtro de amostragem mínima
    min_games = 5
    before = len(merged)
    merged = merged[merged["games"] >= min_games].copy()
    after = len(merged)
    print(f"[OK] Removidos matchups com menos de {min_games} jogos ({before - after} removidos, {after} mantidos).")

    # Ordenar e salvar
    merged = merged.sort_values(["league", "win_rate"], ascending=[True, False])
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {OUTPUT_PATH}")
    print(f"[OK] Total de matchups validos: {len(merged)}")
    print(f"\n[INFO] Top 5 matchups favoraveis (exemplo LPL):")
    if "LPL" in merged["league"].values:
        top5 = merged[merged["league"] == "LPL"].head(5)
        for _, row in top5.iterrows():
            print(f"   {row['champ1']} vs {row['champ2']}: {row['win_rate']:.2f}% ({row['wins']}/{row['games']})")

if __name__ == "__main__":
    main()
