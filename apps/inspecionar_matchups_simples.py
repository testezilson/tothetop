import os
import pandas as pd

# Caminhos padrão
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DATA_PATH = os.path.join(ROOT_DIR, "data")
MATCHUP_PATH = os.path.join(DATA_PATH, "matchup_synergies_simple.pkl")

# Parâmetro mínimo de jogos para exibição
MIN_GAMES = 10


def main():
    print("=== 🔍 Consulta de Matchups Simples (impacto de kills por role) ===\n")

    # 1️⃣ Carregar dataset de matchups
    try:
        df = pd.read_pickle(MATCHUP_PATH)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {MATCHUP_PATH}")
        print("   Rode gerar_sinergias_matchup_simples_oracle.py primeiro.")
        return
    except Exception as e:
        print("❌ Erro ao carregar arquivo de matchups:")
        print(e)
        return

    # Normalizar texto
    df["league"] = df["league"].astype(str).str.strip()
    df["role"] = df["role"].astype(str).str.strip()
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

    print(f"\n📊 {len(df_league)} matchups encontrados na liga {league}.")

    # 3️⃣ Mostrar top 10 mais e menos impactantes (opcional)
    opcao = input("Mostrar o top 10 mais e menos impactantes por role? (s/n): ").strip().lower()
    if opcao == "s":
        roles = df_league["role"].unique()
        for role in roles:
            df_role = df_league[
                (df_league["role"].str.lower() == role.lower())
                & (df_league["n_games"] >= MIN_GAMES)
            ]

            if df_role.empty:
                continue

            print(f"\n=== ROLE: {role.upper()} ===")

            # 🔥 Top 10 MAIS impactantes (apenas impacto > 0)
            df_pos = df_role[df_role["impacto_matchup"] > 0]
            if df_pos.empty:
                print(f"🔥 Top 10 MAIS impactantes ({league}, {role}, n≥{MIN_GAMES}):")
                print("  (nenhum matchup com impacto positivo)\n")
            else:
                top_pos = df_pos.sort_values("impacto_matchup", ascending=False).head(10)
                print(f"🔥 Top 10 MAIS impactantes ({league}, {role}, n≥{MIN_GAMES}):")
                for _, row in top_pos.iterrows():
                    print(
                        f"  {row['champ1']} vs {row['champ2']} → "
                        f"{row['impacto_matchup']:+.2f} kills (n={int(row['n_games'])})"
                    )

            # ❄️ Top 10 MENOS impactantes (apenas impacto < 0)
            df_neg = df_role[df_role["impacto_matchup"] < 0]
            if df_neg.empty:
                print(f"\n❄️ Top 10 MENOS impactantes ({league}, {role}, n≥{MIN_GAMES}):")
                print("  (nenhum matchup com impacto negativo)\n")
            else:
                top_neg = df_neg.sort_values("impacto_matchup", ascending=True).head(10)
                print(f"\n❄️ Top 10 MENOS impactantes ({league}, {role}, n≥{MIN_GAMES}):")
                for _, row in top_neg.iterrows():
                    print(
                        f"  {row['champ1']} vs {row['champ2']} → "
                        f"{row['impacto_matchup']:+.2f} kills (n={int(row['n_games'])})"
                    )

    # 4️⃣ Consulta específica
    print("\n🔎 Consultar matchup específico")
    role = input("Role (top/jung/mid/adc/sup/botlane): ").strip().lower()
    champ_a = input("Campeão 1: ").strip()
    champ_b = input("Campeão 2: ").strip()

    if not role or not champ_a or not champ_b:
        print("⚠️ Entradas inválidas. Encerrando.")
        return

    df_match = df_league[
        (df_league["role"].str.lower() == role)
        & (df_league["champ1"].str.lower() == champ_a.lower())
        & (df_league["champ2"].str.lower() == champ_b.lower())
    ]

    print("\n=== RESULTADO ===")
    if df_match.empty:
        print(f"❌ Nenhum matchup encontrado: {champ_a} vs {champ_b} ({role}) na liga {league}.")
    else:
        for _, row in df_match.iterrows():
            arrow = "🔺" if row["impacto_matchup"] > 0 else "🔻"
            print(
                f"[{league}] {arrow} {champ_a} vs {champ_b} ({role.upper()}) → "
                f"{row['impacto_matchup']:+.2f} kills "
                f"(n={int(row['n_games'])}, média matchup={row['avg_kills_matchup']:.2f}, "
                f"média liga={row['avg_kills_league']:.2f})"
            )

    print("\n🏁 Fim da consulta.")


if __name__ == "__main__":
    main()
