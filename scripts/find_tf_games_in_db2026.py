"""
Procura no CSV db2026 os jogos de Twisted Fate da tabela da imagem:
- Por data e confronto (Time A vs Time B).
- CSV: formato OraclesElixir (1 linha por jogador); agrupamos por gameid.
"""
import os
import pandas as pd

DB_PATH = r"C:\Users\Lucas\Documents\db2026\2026_LoL_esports_match_data_from_OraclesElixir.csv"

# Jogos da imagem (DATE, GAME, TOURNAMENT)
TARGET_GAMES = [
    ("2026-02-21", "Gen.G", "BNK FearX", "LCK Cup 2026"),
    ("2026-02-19", "DN SOOPers", "DRX", "LCK Cup 2026"),
    ("2026-02-15", "Deep Cross Gaming", "Ground Zero Gaming", "LCP 2026 Split 1 Playoffs"),  # DCG vs GZ
    ("2026-02-15", "T1", "BNK FearX", "LCK Cup 2026"),
    ("2026-02-13", "Dplus KIA", "DRX", "LCK Cup 2026"),
    ("2026-02-09", "Top Esports", "Team WE", "LPL 2026 Split 1 Playoffs"),
    ("2026-02-03", "Invictus Gaming", "JD Gaming", "LPL 2026 Split 1"),  # IG vs JDG
    ("2026-01-21", "Dplus Kia", "Nongshim RedForce", "LCK Cup 2026"),  # Dplus KIA vs NS
]


def normalize_team(s):
    if pd.isna(s):
        return ""
    return str(s).strip().upper()


def team_match(team_a, team_b, names_in_game):
    """Verifica se os dois times do confronto estão em names_in_game (set de nomes normalizados)."""
    a = normalize_team(team_a)
    b = normalize_team(team_b)
    if not a or not b:
        return False
    # Pode ser "DPLUS KIA" no CSV e "Dplus KIA" na lista; "BNK FEARX" vs "BNK FearX"
    for n in names_in_game:
        if a in n or n in a:
            for m in names_in_game:
                if m == n:
                    continue
                if b in m or m in b:
                    return True
    return False


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERRO] CSV não encontrado: {DB_PATH}")
        return

    print("Carregando CSV...")
    df = pd.read_csv(DB_PATH, low_memory=False)
    df.columns = df.columns.str.strip()

    # Colunas esperadas
    need = ["gameid", "date", "teamname", "champion", "league"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        print(f"[ERRO] Colunas faltando: {missing}")
        return

    # Apenas linhas de jogador (excluir participantid 100/200 se quiser só jogadores)
    # Para identificar jogo: gameid + date + conjunto de teamname
    df["date_str"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Por jogo: data e times únicos
    def _team_set(x):
        return set(str(t).strip().upper() for t in x.dropna() if str(t).strip())

    games = df.groupby("gameid").agg(
        date_str=("date_str", "first"),
        teams=("teamname", _team_set),
        leagues=("league", "first"),
    ).reset_index()

    # Onde tem Twisted Fate
    tf_mask = df["champion"].astype(str).str.strip().str.upper() == "TWISTED FATE"
    tf_gameids = set(df.loc[tf_mask, "gameid"].unique())

    print("\n" + "=" * 80)
    print("BUSCA DOS 8 JOGOS (Twisted Fate) NO CSV db2026")
    print("=" * 80)

    found = []
    for target_date, team1, team2, tournament in TARGET_GAMES:
        # Jogos nessa data
        same_date = games[games["date_str"] == target_date]
        # Confronto team1 vs team2 (normalizar para comparação flexível)
        t1_norm = normalize_team(team1)
        t2_norm = normalize_team(team2)
        match_gameids = []
        for _, row in same_date.iterrows():
            names = row["teams"]
            if not names:
                continue
            # Ver se existe um nome que contém t1_norm e outro que contém t2_norm
            n1 = next((n for n in names if t1_norm in n or n in t1_norm or team1.upper() in n), None)
            n2 = next((n for n in names if t2_norm in n or n in t2_norm or team2.upper() in n), None)
            if n1 and n2:
                match_gameids.append(row["gameid"])

        # Entre os jogos que batem com o confronto, quais têm TF?
        has_tf = [g for g in match_gameids if g in tf_gameids]
        any_found = len(match_gameids) > 0
        tf_found = len(has_tf) > 0

        status = "OK (com TF)" if tf_found else ("OK (jogo existe, sem TF)" if any_found else "NÃO ENCONTRADO")
        print(f"\n{target_date} | {team1} vs {team2} | {tournament}")
        print(f"  -> {status}")
        if match_gameids:
            for gid in match_gameids[:3]:  # até 3 gameids
                tf_tag = " [TWISTED FATE]" if gid in tf_gameids else ""
                print(f"      gameid: {gid}{tf_tag}")
            if len(match_gameids) > 3:
                print(f"      ... e mais {len(match_gameids) - 3} jogo(s)")
        found.append((target_date, team1, team2, any_found, tf_found))

    print("\n" + "=" * 80)
    resumo_encontrados = sum(1 for _, _, _, any_f, _ in found if any_f)
    resumo_com_tf = sum(1 for _, _, _, _, tf_f in found if tf_f)
    print(f"Resumo: {resumo_encontrados}/8 jogos encontrados no CSV | {resumo_com_tf}/8 com Twisted Fate")
    print("=" * 80)

    # Listar gameids onde Twisted Fate jogou (uma linha por jogo)
    print("\nGameids com Twisted Fate (para conferência):")
    tf_rows = df[df["champion"].astype(str).str.strip().str.upper() == "TWISTED FATE"]
    for gid in sorted(tf_rows["gameid"].unique()):
        r = tf_rows[tf_rows["gameid"] == gid].iloc[0]
        print(f"  {gid} | {r.get('date_str', r.get('date', ''))} | {r.get('league', '')} | {r.get('teamname', '')}")


if __name__ == "__main__":
    main()
