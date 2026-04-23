import pandas as pd
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "champion_winrates.csv")

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
    print("=== Gerando Win Rates de Campeoes - LoL Oracle ML v3 ===")

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

    # Expandir os picks (cada campeão em uma linha)
    champ_rows = []
    for _, row in df.iterrows():
        for col in ["pick1", "pick2", "pick3", "pick4", "pick5"]:
            champ = row[col]
            if pd.notna(champ) and champ.strip() != "":
                champ_rows.append({
                    "league": row["league"],
                    "champion": champ,
                    "won": row["won"]
                })

    df_champs = pd.DataFrame(champ_rows)
    print(f"[OK] Total de campeoes processados: {len(df_champs)} aparicoes em partidas")

    # Calcular win rate por campeão
    champ_stats = (
        df_champs.groupby(["league", "champion"])
        .agg({
            "won": ["sum", "count"]
        })
        .reset_index()
    )
    champ_stats.columns = ["league", "champion", "wins", "games_played"]
    champ_stats["win_rate"] = champ_stats["wins"] / champ_stats["games_played"] * 100

    # Calcular win rate médio da liga (baseline)
    league_stats = (
        df_champs.groupby("league")
        .agg({"won": "mean"})
        .reset_index()
    )
    league_stats.columns = ["league", "league_avg_wr"]
    league_stats["league_avg_wr"] = league_stats["league_avg_wr"] * 100

    # Juntar com as médias da liga
    merged = champ_stats.merge(league_stats, on="league", how="left")
    merged["wr_impact"] = merged["win_rate"] - merged["league_avg_wr"]

    # Aplicar filtro de amostragem mínima
    min_games = 5
    before = len(merged)
    merged = merged[merged["games_played"] >= min_games].copy()
    after = len(merged)
    print(f"[OK] Removidos campeoes com menos de {min_games} jogos ({before - after} removidos, {after} mantidos).")

    # Ordenar e salvar
    merged = merged.sort_values(["league", "win_rate"], ascending=[True, False])
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {OUTPUT_PATH}")
    print(f"[OK] Total de campeoes validos: {len(merged)}")
    print(f"\n[INFO] Top 5 campeoes por win rate (exemplo LPL):")
    if "LPL" in merged["league"].values:
        top5 = merged[merged["league"] == "LPL"].head(5)
        for _, row in top5.iterrows():
            print(f"   {row['champion']}: {row['win_rate']:.2f}% ({row['wins']}/{row['games_played']})")

if __name__ == "__main__":
    main()
