import pandas as pd
import itertools
from collections import defaultdict
import numpy as np
import os

# ==========================
# CONFIGURAÇÕES
# ==========================

# Caminhos de entrada
DATA_PATH = os.path.join("data", "oracle_prepared.csv")  # base principal

# Caminhos de saída
OUTPUT_PKL = os.path.join("data", "champion_synergies_simples.pkl")
OUTPUT_CSV = os.path.join("data", "champion_synergies_simples.csv")

# Colunas esperadas
CHAMP_COLS = ["pick1", "pick2", "pick3", "pick4", "pick5"]
KILLS_COL = "total_kills"
LEAGUE_COL = "league"


# ==========================
# FUNÇÕES
# ==========================

def gerar_sinergias_simples():
    print("=== 🔧 Gerando sinergias simples (sem impactos individuais) ===")

    # 1️⃣ Carregar base
    df = pd.read_csv(DATA_PATH)
    df[LEAGUE_COL] = df[LEAGUE_COL].astype(str).str.strip()

    print(f"📂 {len(df)} linhas carregadas da base.")

    # 2️⃣ Calcular média de kills por liga (baseline global)
    media_kills_liga = df.groupby(LEAGUE_COL)[KILLS_COL].mean().to_dict()

    # 3️⃣ Criar dicionário para acumular kills por par
    sinergias_dict = defaultdict(list)

    # 4️⃣ Iterar sobre todas as linhas (cada time)
    for idx, row in df.iterrows():
        league = row[LEAGUE_COL]
        total_kills = float(row[KILLS_COL])
        champs = [row[c] for c in CHAMP_COLS if pd.notna(row[c])]

        # gerar todas as combinações de 2 campeões
        for c1, c2 in itertools.combinations(sorted(champs), 2):
            sinergias_dict[(league, c1, c2)].append(total_kills)

        if (idx + 1) % 2000 == 0:
            print(f"   ➜ Processadas {idx+1}/{len(df)} linhas...")

    # 5️⃣ Agregar médias e calcular impacto de sinergia
    registros = []
    for (league, c1, c2), kills_list in sinergias_dict.items():
        avg_kills_pair = np.mean(kills_list)
        avg_kills_league = media_kills_liga.get(league, np.nan)
        impacto_sinergia = avg_kills_pair - avg_kills_league

        registros.append({
            "league": league,
            "champ1": c1,
            "champ2": c2,
            "n_games": len(kills_list),
            "avg_kills_pair": avg_kills_pair,
            "avg_kills_league": avg_kills_league,
            "sinergia_bruta": impacto_sinergia
        })

    df_sin = pd.DataFrame(registros)

    print(f"\n✅ Sinergias calculadas para {len(df_sin)} pares (todas as ligas).")
    print("💾 Salvando em:")
    print(f"   - {OUTPUT_PKL}")
    print(f"   - {OUTPUT_CSV}")

    df_sin.to_pickle(OUTPUT_PKL)
    df_sin.to_csv(OUTPUT_CSV, index=False)

    print("\n🎉 Concluído! Use champion_synergies_simples.pkl no analisar_jogos para exibir sinergias brutas.")


if __name__ == "__main__":
    gerar_sinergias_simples()
