"""
Script para comparar ultimos 10 jogos (barons - total da partida) entre CSV e DB.
Mostra jogo a jogo para achar por que o .exe exibe medias erradas (ex: 1.0 e 1.4 em vez de 1.1 e 1.6).
Valores esperados (referencia): DRX media 1.1, NS media 1.6, H2H 2 over / 1 under (linha 1.5).

Execute na raiz do projeto: python verificar_ultimos_10_barons.py
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

TEAM1 = "DRX"
TEAM2 = "Nongshim RedForce"
LINE = 1.5
LIMIT = 10


def csv_last_n_with_details(csv_path, team_name, n=10):
    """Retorna ultimos n jogos do time a partir do CSV: lista de (gameid, date, total_barons)."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    team_rows = df[df["position"].astype(str).str.strip().str.lower() == "team"].copy()
    if team_rows.empty:
        return [], "CSV sem linhas position=team"
    team_rows["total_barons"] = team_rows["barons"].fillna(0).astype(int) + team_rows["opp_barons"].fillna(0).astype(int)
    team_rows["date"] = pd.to_datetime(team_rows["date"], errors="coerce")
    sub = team_rows[team_rows["teamname"].astype(str).str.strip().str.lower() == team_name.strip().lower()]
    sub = sub.sort_values(["date", "gameid"], ascending=[False, False]).head(n)
    rows = list(zip(sub["gameid"].tolist(), sub["date"].tolist(), sub["total_barons"].tolist()))
    return rows, None


def csv_h2h_with_details(csv_path, team1, team2):
    """Retorna jogos H2H do CSV: lista de (gameid, date, total_barons)."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    team_rows = df[df["position"].astype(str).str.strip().str.lower() == "team"].copy()
    if team_rows.empty:
        return [], "CSV sem linhas position=team"
    team_rows["total_barons"] = team_rows["barons"].fillna(0).astype(int) + team_rows["opp_barons"].fillna(0).astype(int)
    team_rows["date"] = pd.to_datetime(team_rows["date"], errors="coerce")
    g1 = set(team_rows[team_rows["teamname"].astype(str).str.strip().str.lower() == team1.strip().lower()]["gameid"].unique())
    g2 = set(team_rows[team_rows["teamname"].astype(str).str.strip().str.lower() == team2.strip().lower()]["gameid"].unique())
    h2h_gids = g1 & g2
    sub = team_rows[team_rows["gameid"].isin(h2h_gids)].drop_duplicates(subset=["gameid"], keep="first")
    sub = sub.sort_values(["date", "gameid"], ascending=[False, False])
    return list(zip(sub["gameid"].tolist(), sub["date"].tolist(), sub["total_barons"].tolist()))


def db_last_n_with_details(conn, team_name, n=10):
    """Retorna ultimos n jogos do time a partir do DB: lista de (gameid, date, total)."""
    import sqlite3
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(oracle_matches)")
    cols = [r[1] for r in cursor.fetchall()]
    team_col = "teamname" if "teamname" in cols else "team"
    query = f"""
    WITH team_gameids AS (
        SELECT gameid, MAX(date) AS date
        FROM oracle_matches
        WHERE {team_col} COLLATE NOCASE = ?
        GROUP BY gameid
    ),
    team_stats AS (
        SELECT gameid, {team_col} AS team, MAX(COALESCE(barons, 0)) AS value
        FROM oracle_matches
        GROUP BY gameid, {team_col}
    ),
    game_totals AS (
        SELECT t1.gameid, (t1.value + t2.value) AS total
        FROM team_stats t1
        INNER JOIN team_stats t2 ON t1.gameid = t2.gameid AND t1.team != t2.team
        WHERE t1.team COLLATE NOCASE = ?
    )
    SELECT tg.gameid, tg.date, gt.total
    FROM team_gameids tg
    INNER JOIN game_totals gt ON gt.gameid = tg.gameid
    WHERE tg.date IS NOT NULL AND trim(tg.date) != ''
    ORDER BY tg.date DESC, tg.gameid DESC
    LIMIT ?
    """
    cursor.execute(query, (team_name, team_name, n))
    return cursor.fetchall()


def db_h2h_with_details(conn, team1, team2):
    """Retorna jogos H2H do DB: lista de (date, total)."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(oracle_matches)")
    cols = [r[1] for r in cursor.fetchall()]
    team_col = "teamname" if "teamname" in cols else "team"
    query = f"""
    WITH team_stats AS (
        SELECT gameid, date, {team_col} AS team, MAX(COALESCE(barons, 0)) AS value
        FROM oracle_matches
        GROUP BY gameid, {team_col}
    )
    SELECT t1.date, (t1.value + t2.value) AS total
    FROM team_stats t1
    JOIN team_stats t2 ON t1.gameid = t2.gameid AND t1.team != t2.team
    WHERE t1.team COLLATE NOCASE = ? AND t2.team COLLATE NOCASE = ?
    ORDER BY t1.date DESC, t1.gameid DESC
    """
    cursor.execute(query, (team1, team2))
    return cursor.fetchall()


def main():
    base = os.path.dirname(__file__)
    csv_path = os.path.join(base, "data", "2026_LoL_esports_match_data_from_OraclesElixir.csv")
    db_path = os.path.join(base, "data", "lol_esports.db")

    print("=" * 70)
    print("REFERENCIA (dados reais esperados)")
    print("  DRX ultimos 10: media 1.1  |  NS ultimos 10: media 1.6")
    print("  H2H (linha 1.5): 2 over, 1 under")
    print("=" * 70)

    if not os.path.exists(csv_path):
        print(f"CSV nao encontrado: {csv_path}")
        return

    # --- CSV ---
    print("\n--- CSV: ultimos 10 jogos (total barons da partida) ---")
    for team_name, label in [(TEAM1, "DRX"), (TEAM2, "NS")]:
        rows, err = csv_last_n_with_details(csv_path, team_name, LIMIT)
        if err:
            print(f"  {label}: {err}")
            continue
        vals = [r[2] for r in rows]
        media = sum(vals) / len(vals) if vals else 0
        over = sum(1 for v in vals if v > LINE)
        under = len(vals) - over
        print(f"  {label}: valores = {vals}  -> media = {media:.2f}  |  OVER {LINE}: {over}  UNDER: {under}")
        for i, (gid, date, total) in enumerate(rows[:5], 1):
            print(f"      jogo {i}: {gid}  date={date}  total={total}")
        if len(rows) > 5:
            print(f"      ... e mais {len(rows)-5} jogos")

    print("\n--- CSV: H2H ---")
    h2h_csv = csv_h2h_with_details(csv_path, TEAM1, TEAM2)
    if h2h_csv:
        totals = [r[2] for r in h2h_csv]
        over = sum(1 for t in totals if t > LINE)
        under = len(totals) - over
        media_h2h = sum(totals) / len(totals)
        print(f"  Jogos: {len(totals)}, totais = {totals}, media = {media_h2h:.2f}")
        print(f"  OVER {LINE}: {over}  |  UNDER: {under}")
    else:
        print("  Nenhum jogo H2H no CSV.")

    # --- DB ---
    if not os.path.exists(db_path):
        print(f"\nBanco nao encontrado: {db_path}")
        print("  Rode no app: LoL > Atualizar Banco (escolha o CSV 2026) e execute este script de novo.")
        return

    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        print("\n--- DB: ultimos 10 jogos (total barons da partida) ---")
        for team_name, label in [(TEAM1, "DRX"), (TEAM2, "NS")]:
            rows = db_last_n_with_details(conn, team_name, LIMIT)
            if not rows:
                print(f"  {label}: nenhum jogo retornado (verifique nome do time no banco)")
                continue
            vals = [r[2] for r in rows]
            media = sum(vals) / len(vals)
            over = sum(1 for v in vals if v > LINE)
            under = len(vals) - over
            print(f"  {label}: valores = {vals}  -> media = {media:.2f}  |  OVER {LINE}: {over}  UNDER: {under}")
            for i, (gid, date, total) in enumerate(rows[:5], 1):
                print(f"      jogo {i}: {gid}  date={date}  total={total}")
            if len(rows) > 5:
                print(f"      ... e mais {len(rows)-5} jogos")

        print("\n--- DB: H2H ---")
        h2h_db = db_h2h_with_details(conn, TEAM1, TEAM2)
        if h2h_db:
            totals = [r[1] for r in h2h_db]
            over = sum(1 for t in totals if t > LINE)
            under = len(totals) - over
            media_h2h = sum(totals) / len(totals)
            print(f"  Jogos: {len(totals)}, totais = {totals}, media = {media_h2h:.2f}")
            print(f"  OVER {LINE}: {over}  |  UNDER: {under}")
        else:
            print("  Nenhum jogo H2H no DB.")

        # Chamar o modulo real para ver o que o app usaria
        print("\n--- O que o modulo prebets_secondary retorna (o que o app usa) ---")
        from core.lol.prebets_secondary import fetch_team_recent, fetch_h2h_empirico
        v1 = fetch_team_recent(conn, TEAM1, "barons", LIMIT)
        v2 = fetch_team_recent(conn, TEAM2, "barons", LIMIT)
        h2h_rate, nh2h, h2h_mean, over_h2h, under_h2h = fetch_h2h_empirico(conn, TEAM1, TEAM2, "barons", months=12, line=LINE)
        print(f"  DRX: lista = {v1}, media = {sum(v1)/len(v1) if v1 else 0:.2f}")
        print(f"  NS:  lista = {v2}, media = {sum(v2)/len(v2) if v2 else 0:.2f}")
        print(f"  H2H: n={nh2h}, media={h2h_mean:.2f}, over={over_h2h}, under={under_h2h}")
    finally:
        conn.close()

    print("\n" + "=" * 70)
    print("Se as medias nao baterem com a referencia (1.1 e 1.6) ou H2H 2/1:")
    print("  - .exe desatualizado: recompile o app (codigo atual usa TOTAL da partida).")
    print("  - CSV/DB diferente: outro arquivo ou data pode mudar os 'ultimos 10'.")
    print("  - Ordenacao: o codigo usa ORDER BY date DESC, gameid DESC (deterministico).")
    print("=" * 70)


if __name__ == "__main__":
    main()
