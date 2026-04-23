import os
import pandas as pd

# Diretórios base
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DATA_PATH = os.path.join(ROOT_DIR, "data")

# Arquivo de sinergias gerado pelo gerar_sinergias_v2.py
SYNERGY_PATH = os.path.join(DATA_PATH, "champion_synergies_v2.pkl")

# Corte mínimo de jogos para considerar na listagem de top sinergias
MIN_GAMES = 10


def main():
    print("=== 🔍 Inspeção de Sinergias de Draft (v2) ===\n")

    # Carregar sinergias
    try:
        synergy_df = pd.read_pickle(SYNERGY_PATH)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {SYNERGY_PATH}")
        print("   Certifique-se de ter rodado gerar_sinergias_v2.py antes.")
        return
    except Exception as e:
        print("❌ Erro ao carregar arquivo de sinergias:")
        print(e)
        return

    # Normalizar texto
    synergy_df["league"] = synergy_df["league"].astype(str).str.strip()
    synergy_df["champ1"] = synergy_df["champ1"].astype(str).str.strip()
    synergy_df["champ2"] = synergy_df["champ2"].astype(str).str.strip()

    total_sinergias = len(synergy_df)
    total_ligas = synergy_df["league"].nunique()

    print(f"📊 Sinergias totais: {total_sinergias}")
    print(f"🌍 Ligas diferentes: {total_ligas}")

    # Sinergias com base mínima de jogos
    df_filtrado = synergy_df[synergy_df["n_games"] >= MIN_GAMES].copy()
    total_filtrado = len(df_filtrado)

    print(f"✅ Sinergias com n_games ≥ {MIN_GAMES}: {total_filtrado}\n")

    if df_filtrado.empty:
        print("⚠️ Nenhuma sinergia com base mínima suficiente. "
              "Talvez seja preciso reduzir MIN_GAMES ou aumentar a base.")
        return

    # Top 20 sinergias mais positivas (mais kills acima do esperado)
    top_positivas = df_filtrado.sort_values("mean_residual", ascending=False).head(20)

    # Top 20 sinergias mais negativas (menos kills que o esperado)
    top_negativas = df_filtrado.sort_values("mean_residual", ascending=True).head(20)

    # Exibir
    print("🔥 Top 20 sinergias MAIS impactantes (positivas):")
    print("(league | champ1 + champ2 | mean_residual | n_games)\n")
    for _, row in top_positivas.iterrows():
        print(
            f"  [{row['league']}] "
            f"{row['champ1']} + {row['champ2']} → "
            f"{row['mean_residual']:+.2f} kills  (n={int(row['n_games'])})"
        )

    print("\n❄️ Top 20 sinergias MENOS impactantes (negativas):")
    print("(league | champ1 + champ2 | mean_residual | n_games)\n")
    for _, row in top_negativas.iterrows():
        print(
            f"  [{row['league']}] "
            f"{row['champ1']} + {row['champ2']} → "
            f"{row['mean_residual']:+.2f} kills  (n={int(row['n_games'])})"
        )

    print("\n✅ Fim da inspeção de sinergias.")


if __name__ == "__main__":
    main()
