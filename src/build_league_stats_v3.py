import os
import pandas as pd
import pickle

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "oracle_prepared.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "league_stats_v3.pkl")

def main():
    print("=== ⚙️ Gerando Estatísticas de Ligas - LoL Oracle ML v3 ===")

    # Carregar dataset
    if not os.path.exists(DATA_PATH):
        print(f"❌ Arquivo não encontrado: {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"📂 Dataset carregado: {len(df)} linhas")

    expected_cols = ["gameid", "league", "total_kills"]
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        print(f"⚠️ Colunas faltando no dataset: {missing}")
        return

    # Remover duplicatas (cada partida aparece duas vezes — um por time)
    df_unique = df.drop_duplicates(subset=["gameid", "league", "total_kills"]).copy()
    print(f"🧮 Partidas únicas detectadas: {len(df_unique)}")

    # Calcular média, std e contagem de partidas por liga
    league_summary = (
        df_unique.groupby("league")["total_kills"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(columns={"mean": "mean_kills", "std": "std_kills", "count": "games"})
    )

    # Converter para dicionário
    league_stats = {}
    for _, row in league_summary.iterrows():
        league_stats[row["league"]] = {
            "mean_kills": round(row["mean_kills"], 2),
            "std_kills": round(row["std_kills"], 2),
            "games": int(row["games"]),
        }

    # Mostrar resumo
    print(f"\n📈 Ligas processadas: {len(league_stats)}")
    for lg, stats in list(league_stats.items())[:10]:
        print(f"   {lg}: média={stats['mean_kills']} | std={stats['std_kills']} | jogos={stats['games']}")

    # Salvar como .pkl
    with open(OUTPUT_PATH, "wb") as f:
        pickle.dump(league_stats, f)

    print(f"\n💾 Arquivo salvo em: {OUTPUT_PATH}")
    print("✅ Estatísticas compatíveis com o formato Oracle geradas com sucesso!")

if __name__ == "__main__":
    main()
