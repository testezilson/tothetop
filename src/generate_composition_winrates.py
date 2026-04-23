import pandas as pd
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "composition_winrates.csv")

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

def get_composition_key(champs):
    """Cria uma chave única para a composição (ordena os campeões)"""
    return tuple(sorted([c for c in champs if pd.notna(c) and c.strip() != ""]))

def main():
    print("=== Gerando Win Rates de Composicoes Completas (5 Campeoes) - LoL Oracle ML v3 ===")

    # Carregar dataset
    if not os.path.exists(DATA_PATH):
        print(f"[ERRO] Arquivo nao encontrado: {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"[OK] Dataset carregado: {len(df)} linhas")

    # Processar composições
    print("[OK] Processando composicoes...")
    comp_data = []

    for gameid, df_game in df.groupby("gameid"):
        if len(df_game) != 2:
            continue

        winner = determine_winner(df_game)
        if winner is None:
            continue

        for idx, row in df_game.iterrows():
            league = row["league"]
            champs = [row[c] for c in ["pick1", "pick2", "pick3", "pick4", "pick5"]]
            
            # Verificar se tem 5 campeões válidos
            valid_champs = [c for c in champs if pd.notna(c) and c.strip() != ""]
            if len(valid_champs) != 5:
                continue

            comp_key = get_composition_key(valid_champs)
            won = 1 if (idx == 0 and winner == 0) or (idx == 1 and winner == 1) else 0

            comp_data.append({
                "league": league,
                "composition": "|".join(comp_key),
                "won": won
            })

    df_comps = pd.DataFrame(comp_data)
    print(f"[OK] Total de composicoes processadas: {len(df_comps)}")

    # Calcular win rate por composição
    comp_stats = (
        df_comps.groupby(["league", "composition"])
        .agg({
            "won": ["sum", "count"]
        })
        .reset_index()
    )
    comp_stats.columns = ["league", "composition", "wins", "games"]
    comp_stats["win_rate"] = comp_stats["wins"] / comp_stats["games"] * 100

    # Calcular win rate médio da liga (baseline)
    league_stats = (
        df_comps.groupby("league")["won"].mean()
        .reset_index()
    )
    league_stats.columns = ["league", "league_avg_wr"]
    league_stats["league_avg_wr"] = league_stats["league_avg_wr"] * 100

    # Juntar com as médias da liga
    merged = comp_stats.merge(league_stats, on="league", how="left")
    merged["comp_impact"] = merged["win_rate"] - merged["league_avg_wr"]

    # Aplicar filtro de amostragem mínima
    min_games = 3  # Composições completas são mais raras, então menor threshold
    before = len(merged)
    merged = merged[merged["games"] >= min_games].copy()
    after = len(merged)
    print(f"[OK] Removidas composicoes com menos de {min_games} jogos ({before - after} removidas, {after} mantidas).")

    # Ordenar e salvar
    merged = merged.sort_values(["league", "win_rate"], ascending=[True, False])
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Arquivo salvo em: {OUTPUT_PATH}")
    print(f"[OK] Total de composicoes validas: {len(merged)}")
    print(f"\n[INFO] Top 5 composicoes por win rate (exemplo LPL):")
    if "LPL" in merged["league"].values:
        top5 = merged[merged["league"] == "LPL"].head(5)
        for _, row in top5.iterrows():
            champs = row["composition"].split("|")
            print(f"   {' + '.join(champs)}: {row['win_rate']:.2f}% ({row['wins']}/{row['games']})")

if __name__ == "__main__":
    main()
