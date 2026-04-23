import pandas as pd
import numpy as np
import os
from collections import defaultdict

# ==========================
# CONFIGURAÇÕES
# ==========================

DATA_PATH = os.path.join("data", "oracle_prepared.csv")  # base Oracle (formato 1 linha por time)
OUTPUT_PKL = os.path.join("data", "matchup_synergies_simple.pkl")
OUTPUT_CSV = os.path.join("data", "matchup_synergies_simple.csv")

ROLES = ["top", "jung", "mid", "adc", "sup"]


def gerar_sinergias_matchup_oracle_v5():
    print("=== 🔧 Gerando sinergias simples entre matchups (Oracle v5 — inclui ANYROLE) ===\n")

    # 1️⃣ Carregar base Oracle
    df = pd.read_csv(DATA_PATH)
    df["league"] = df["league"].astype(str).str.strip()
    df["teamname"] = df["teamname"].astype(str).str.strip()

    print(f"📂 {len(df)} linhas carregadas de {DATA_PATH}")
    print("🔎 Estrutura detectada: formato Oracle (1 linha por time, sem roles explícitas)\n")

    # 2️⃣ Detectar colunas de picks
    pick_cols = [c for c in df.columns if c.startswith("pick")]
    if len(pick_cols) != 5:
        print(f"❌ Erro: foram encontradas {len(pick_cols)} colunas de picks (esperado: 5).")
        print(f"Colunas detectadas: {pick_cols}")
        return

    # 3️⃣ Calcular média de kills por liga (baseline — já é total de kills da partida)
    if "gameid" not in df.columns:
        print("❌ A base precisa conter a coluna 'gameid' para juntar os times de cada partida.")
        return

    df_game = df.groupby(["league", "gameid"])["total_kills"].first().reset_index()
    avg_kills_league = df_game.groupby("league")["total_kills"].mean().to_dict()
    print("📊 Média de kills por partida calculada por liga:")
    for lig, val in avg_kills_league.items():
        print(f"   {lig}: {val:.2f}")

    # 4️⃣ Reagrupar partidas por gameid
    grouped = df.groupby("gameid")
    matchup_data = defaultdict(list)

    for gameid, game_rows in grouped:
        if len(game_rows) != 2:
            continue

        row_t1, row_t2 = game_rows.iloc[0], game_rows.iloc[1]
        league = row_t1["league"]
        total_kills = float(row_t1["total_kills"])

        # ========================
        # ROLE vs ROLE matchups
        # ========================
        for i, role in enumerate(ROLES):
            champ_t1 = str(row_t1[pick_cols[i]]).strip()
            champ_t2 = str(row_t2[pick_cols[i]]).strip()
            if champ_t1 and champ_t2 and champ_t1 != "nan" and champ_t2 != "nan":
                champ_a, champ_b = sorted([champ_t1, champ_t2])
                matchup_data[(league, role, champ_a, champ_b)].append(total_kills)

        # ========================
        # Botlane combinada
        # ========================
        bot1 = f"{row_t1[pick_cols[3]]}+{row_t1[pick_cols[4]]}"
        bot2 = f"{row_t2[pick_cols[3]]}+{row_t2[pick_cols[4]]}"
        bot_a, bot_b = sorted([bot1, bot2])
        matchup_data[(league, "botlane", bot_a, bot_b)].append(total_kills)

        # ========================
        # ANYROLE — qualquer combinação entre os times
        # ========================
        champs_t1 = [str(row_t1[c]).strip() for c in pick_cols if pd.notna(row_t1[c])]
        champs_t2 = [str(row_t2[c]).strip() for c in pick_cols if pd.notna(row_t2[c])]
        for c1 in champs_t1:
            for c2 in champs_t2:
                if c1 and c2 and c1 != "nan" and c2 != "nan":
                    champ_a, champ_b = sorted([c1, c2])
                    matchup_data[(league, "anyrole", champ_a, champ_b)].append(total_kills)

    # 5️⃣ Agregar resultados
    registros = []
    for (league, role, champ1, champ2), kills_list in matchup_data.items():
        if not kills_list:
            continue

        avg_kills_matchup = float(np.mean(kills_list))
        avg_kills_liga = float(avg_kills_league.get(league, np.nan))
        impacto = avg_kills_matchup - avg_kills_liga

        registros.append({
            "league": league,
            "role": role,
            "champ1": champ1,
            "champ2": champ2,
            "n_games": len(kills_list),
            "avg_kills_matchup": round(avg_kills_matchup, 2),
            "avg_kills_league": round(avg_kills_liga, 2),
            "impacto_matchup": round(impacto, 2)
        })

    df_out = pd.DataFrame(registros)

    print(f"\n✅ Matchups processados: {len(df_out)}")
    print("💾 Salvando resultados em:")
    print(f"   - {OUTPUT_PKL}")
    print(f"   - {OUTPUT_CSV}")

    df_out.to_pickle(OUTPUT_PKL)
    df_out.to_csv(OUTPUT_CSV, index=False)

    print("\n🎯 Concluído!")
    print("   • Inclui role vs role e categoria 'anyrole'")
    print("   • Impacto = média de kills da matchup − média da liga")
    print("   • A vs B e B vs A unificados corretamente.\n")


if __name__ == "__main__":
    gerar_sinergias_matchup_oracle_v5()
