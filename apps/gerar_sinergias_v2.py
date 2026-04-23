import itertools
import pickle
from collections import defaultdict

import numpy as np
import pandas as pd


# ==========================
# CONFIGURAÇÕES PRINCIPAIS
# ==========================

# Caminhos dos arquivos de entrada
ORACLE_PREPARED_PATH = "data/oracle_prepared.csv"      # base de jogos agregada (time x jogo)
CHAMPION_IMPACTS_PATH = "data/champion_impacts.csv"    # impactos individuais por liga + campeão

# Arquivos de saída
SYNERGY_OUTPUT_PKL = "data/champion_synergies_v2.pkl"
SYNERGY_OUTPUT_CSV = "data/champion_synergies_v2.csv"


def carregar_champion_impacts():
    """
    Carrega o champion_impacts.csv e devolve:
      - avg_kills_por_league: dict[league] -> league_avg_kills
      - champ_impacts: dict[(league, champion)] -> impact
    """
    print(f"📂 Carregando impactos individuais de {CHAMPION_IMPACTS_PATH}...")
    df_imp = pd.read_csv(CHAMPION_IMPACTS_PATH)

    # Normaliza nomes pra evitar problemas de maiúscula/minúscula
    df_imp["league"] = df_imp["league"].astype(str).str.strip()
    df_imp["champion"] = df_imp["champion"].astype(str).str.strip()

    # Dicionário: média de kills por liga (pega o primeiro valor por liga)
    avg_kills_por_league = (
        df_imp.groupby("league")["league_avg_kills"]
        .first()
        .to_dict()
    )

    # Dicionário: impacto por (liga, campeão)
    champ_impacts = {
        (row["league"], row["champion"]): float(row["impact"])
        for _, row in df_imp.iterrows()
    }

    print(f"✅ Impactos carregados para {len(champ_impacts)} pares (liga, campeão).")
    return avg_kills_por_league, champ_impacts


def carregar_oracle_prepared():
    """
    Carrega o oracle_prepared.csv.
    Estrutura esperada:
      gameid, league, teamname, teamkills,
      pick1..pick5, opponent, total_kills
    """
    print(f"📂 Carregando base de jogos de {ORACLE_PREPARED_PATH}...")
    df = pd.read_csv(ORACLE_PREPARED_PATH)

    # Normaliza liga e picks
    df["league"] = df["league"].astype(str).str.strip()

    for col in ["pick1", "pick2", "pick3", "pick4", "pick5"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    print(f"✅ {len(df)} linhas carregadas em oracle_prepared.csv.")
    return df


def calcular_residual(row, avg_kills_por_league, champ_impacts):
    """
    Calcula o residual de kills para UMA linha (um time em um jogo):

      residual = total_kills_real - (baseline_liga + soma_impactos_time)

    Obs.: usamos apenas os 5 campeões daquele time (pick1..pick5).
    """
    league = row["league"]
    total_kills = float(row["total_kills"])

    baseline = avg_kills_por_league.get(league, None)
    if baseline is None or np.isnan(baseline):
        # se por algum motivo a liga não tiver baseline, ignora este jogo
        return None

    champs = []
    for col in ["pick1", "pick2", "pick3", "pick4", "pick5"]:
        if col in row and pd.notna(row[col]):
            champ = str(row[col]).strip()
            if champ:
                champs.append(champ)

    impacto_total = 0.0
    for champ in champs:
        impacto_total += champ_impacts.get((league, champ), 0.0)

    kills_esperadas = baseline + impacto_total
    residual = total_kills - kills_esperadas

    return residual, champs


def gerar_sinergias():
    print("🔧 Iniciando geração de sinergias de draft (v2)...")

    # 1) Carregar impactos individuais (baseline de kills por liga + impacto de cada champ)
    avg_kills_por_league, champ_impacts = carregar_champion_impacts()

    # 2) Carregar base de jogos (oracle_prepared)
    df = carregar_oracle_prepared()

    # 3) Acumular residuais por (league, champ1, champ2)
    residuals_dict = defaultdict(list)

    total_rows = len(df)
    for idx, row in df.iterrows():
        if (idx + 1) % 2000 == 0 or idx == total_rows - 1:
            print(f"   ➜ Processando linha {idx+1}/{total_rows}...")

        res = calcular_residual(row, avg_kills_por_league, champ_impacts)
        if res is None:
            continue

        residual, champs = res
        league = row["league"]

        # Gera todas as duplas dentro daquele time (5 picks → 10 duplas)
        for c1, c2 in itertools.combinations(sorted(champs), 2):
            residuals_dict[(league, c1, c2)].append(residual)

    print("📊 Agregando sinergias por liga e dupla de campeões...")

    rows = []
    for (league, c1, c2), residuals in residuals_dict.items():
        n_games = len(residuals)
        mean_residual = float(np.mean(residuals))

        rows.append(
            {
                "league": league,
                "champ1": c1,
                "champ2": c2,
                "n_games": n_games,
                "mean_residual": mean_residual,
            }
        )

    synergy_df = pd.DataFrame(rows)

    print(f"✅ Sinergias calculadas para {len(synergy_df)} pares (liga, champ1, champ2).")
    print("💾 Salvando resultados em:")
    print(f"   - {SYNERGY_OUTPUT_PKL}")
    print(f"   - {SYNERGY_OUTPUT_CSV}")

    synergy_df.to_pickle(SYNERGY_OUTPUT_PKL)
    synergy_df.to_csv(SYNERGY_OUTPUT_CSV, index=False)

    print("🎉 Concluído! Agora você pode usar essas sinergias no analisar_jogos_v3.py.")


if __name__ == "__main__":
    gerar_sinergias()
