import os
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "champion_impacts.csv")

# Ligas MAJOR para impact_kills (TESTE LOL LIVE GAME usa apenas estas no fallback CSV)
MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}

def main():
    print("=== ⚙️ Gerando Impactos de Campeões - LoL Oracle ML v3 (Formato Oracle) ===")

    # Carregar dataset
    if not os.path.exists(DATA_PATH):
        print(f"❌ Arquivo não encontrado: {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"📂 Dataset carregado: {len(df)} linhas")

    # Usar apenas ligas MAJOR para o impacto de kills (consistente com TESTE LOL LIVE GAME)
    df["league_upper"] = df["league"].astype(str).str.strip().str.upper()
    df = df[df["league_upper"].isin(MAJOR_LEAGUES)].copy()
    df = df.drop(columns=["league_upper"], errors="ignore")
    print(f"📂 Filtrado para ligas MAJOR: {len(df)} linhas")

    expected_cols = ["league", "teamname", "teamkills", "pick1", "pick2", "pick3", "pick4", "pick5", "total_kills"]
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        print(f"⚠️ Colunas faltando: {missing}")
        return

    # Expandir os picks (cada campeão em uma linha)
    champ_rows = []
    for _, row in df.iterrows():
        for col in ["pick1", "pick2", "pick3", "pick4", "pick5"]:
            champ = row[col]
            if pd.notna(champ) and champ.strip() != "":
                champ_rows.append({
                    "league": row["league"],
                    "champion": champ,
                    "total_kills": row["total_kills"]
                })

    df_champs = pd.DataFrame(champ_rows)
    print(f"📊 Total de campeões processados: {len(df_champs)} aparições em partidas")

    # Calcular média e desvio padrão da liga
    league_stats = df_champs.groupby("league")["total_kills"].agg(["mean", "std"]).reset_index()
    league_stats.columns = ["league", "league_avg_kills", "league_std_kills"]

    # Calcular média de kills por campeão
    champ_stats = (
        df_champs.groupby(["league", "champion"])["total_kills"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "avg_kills_with_champ", "count": "games_played"})
    )

    # Juntar com as médias da liga
    merged = champ_stats.merge(league_stats, on="league", how="left")
    merged["impact"] = merged["avg_kills_with_champ"] - merged["league_avg_kills"]

    # Aplicar filtro de amostragem mínima
    min_games = 5
    before = len(merged)
    merged = merged[merged["games_played"] >= min_games].copy()
    after = len(merged)
    print(f"✅ Removidos campeões com menos de {min_games} jogos ({before - after} removidos, {after} mantidos).")

    # Ordenar e salvar
    merged = merged.sort_values(["league", "impact"], ascending=[True, False])
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"💾 Arquivo salvo em: {OUTPUT_PATH}")
    print(f"📈 Total de campeões válidos: {len(merged)}")

if __name__ == "__main__":
    main()
