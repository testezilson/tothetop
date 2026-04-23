import os
import pandas as pd

# Caminho do arquivo de sinergias simples
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DATA_PATH = os.path.join(ROOT_DIR, "data")
SYNERGY_PATH = os.path.join(DATA_PATH, "champion_synergies_simples.pkl")

# Filtro mínimo de jogos
MIN_GAMES = 10


def main():
    print("=== 🔍 Consulta de Sinergia Simples por Liga ===\n")

    # 1️⃣ Carregar sinergias
    try:
        df = pd.read_pickle(SYNERGY_PATH)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {SYNERGY_PATH}")
        print("   Rode gerar_sinergias_simples.py primeiro.")
        return
    except Exception as e:
        print("❌ Erro ao carregar arquivo de sinergias:")
        print(e)
        return

    # Normalizar
    df["league"] = df["league"].astype(str).str.strip()
    df["champ1"] = df["champ1"].astype(str).str.strip()
    df["champ2"] = df["champ2"].astype(str).str.strip()

    # 2️⃣ Entrada da liga
    league = input("Liga desejada (ex: LCK, LPL, LEC, CBLOL): ").strip()
    if not league:
        print("⚠️ Liga inválida. Encerrando.")
        return

    df_league = df[df["league"].str.lower() == league.lower()]
    if df_league.empty:
        print(f"❌ Nenhum registro encontrado para a liga {league}.")
        return

    print(f"\n📊 {len(df_league)} combinações encontradas para a liga {league}.")

    # 3️⃣ Perguntar se deseja mostrar top 10
    opcao = input("Mostrar o top 10 mais e menos impactantes? (s/n): ").strip().lower()
    if opcao == "s":
        df_filt = df_league[df_league["n_games"] >= MIN_GAMES]

        if df_filt.empty:
            print(f"⚠️ Nenhuma sinergia com n ≥ {MIN_GAMES} na liga {league}.")
        else:
            top_pos = df_filt.sort_values("sinergia_bruta", ascending=False).head(10)
            top_neg = df_filt.sort_values("sinergia_bruta", ascending=True).head(10)

            print(f"\n🔥 Top 10 MAIS impactantes ({league}, n≥{MIN_GAMES}):")
            for _, row in top_pos.iterrows():
                print(
                    f"  {row['champ1']} + {row['champ2']} → {row['sinergia_bruta']:+.2f} kills (n={int(row['n_games'])})"
                )

            print(f"\n❄️ Top 10 MENOS impactantes ({league}, n≥{MIN_GAMES}):")
            for _, row in top_neg.iterrows():
                print(
                    f"  {row['champ1']} + {row['champ2']} → {row['sinergia_bruta']:+.2f} kills (n={int(row['n_games'])})"
                )

    # 4️⃣ Consulta específica
    print("\n🔎 Consultar sinergia específica")
    champ_a = input("Campeão 1: ").strip()
    champ_b = input("Campeão 2: ").strip()

    if not champ_a or not champ_b:
        print("⚠️ Entradas inválidas. Encerrando.")
        return

    c1, c2 = sorted([champ_a, champ_b])
    df_pair = df_league[
        (df_league["champ1"].str.lower() == c1.lower())
        & (df_league["champ2"].str.lower() == c2.lower())
    ]

    print("\n=== RESULTADO ===")
    if df_pair.empty:
        print(f"❌ Nenhuma sinergia encontrada para {c1} + {c2} na liga {league}.")
    else:
        for _, row in df_pair.iterrows():
            arrow = "🔺" if row["sinergia_bruta"] > 0 else "🔻"
            print(
                f"[{league}] {arrow} {c1} + {c2} → {row['sinergia_bruta']:+.2f} kills "
                f"(n={int(row['n_games'])}, média dupla={row['avg_kills_pair']:.2f}, média liga={row['avg_kills_league']:.2f})"
            )

    print("\n🏁 Fim da consulta.")


if __name__ == "__main__":
    main()
