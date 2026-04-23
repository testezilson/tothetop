"""
Diagnostico completo: CSV -> DB -> script de calculo (prebets secundarias).
Rode na raiz do projeto: python diagnostico_csv_db_calculo.py

Verifica:
1. Dados no CSV (linhas position=team): ultimos 10 jogos por time, total barons, over/under 1.5
2. Se o lookup (gameid, teamname) encontraria os valores para as linhas de jogador
3. O que o DB tem apos converter (se existir)
4. O que o script prebets_secondary retorna
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

LINE = 1.5
LIMIT = 10


def passo1_csv(csv_path, team_name, n=10):
    """Le o CSV e extrai ultimos n jogos do time a partir das linhas position=team."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    team_rows = df[df["position"].astype(str).str.strip().str.lower() == "team"].copy()
    if team_rows.empty:
        return None, "CSV sem linhas position=team"
    team_rows["total_barons"] = (
        team_rows["barons"].fillna(0).astype(int)
        + team_rows["opp_barons"].fillna(0).astype(int)
    )
    team_rows["date"] = pd.to_datetime(team_rows["date"], errors="coerce")
    # Match time: exato e case-insensitive
    mask = team_rows["teamname"].astype(str).str.strip().str.lower() == str(team_name).strip().lower()
    sub = team_rows.loc[mask].sort_values(["date", "gameid"], ascending=[False, False]).head(n)
    if sub.empty:
        return None, f"Nenhum jogo encontrado para time '{team_name}' no CSV"
    vals = sub["total_barons"].tolist()
    over = sum(1 for v in vals if v > LINE)
    under = len(vals) - over
    media = sum(vals) / len(vals)
    return {
        "vals": vals,
        "media": media,
        "over": over,
        "under": under,
        "gameids": sub["gameid"].tolist(),
        "dates": sub["date"].tolist(),
    }, None


def passo2_lookup_csv(csv_path, team_name, gameids):
    """Verifica se o lookup (gameid, teamname) do converter encontraria valores para esses gameids."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    team_rows = df[df["position"].astype(str).str.strip().str.lower() == "team"]
    # Construir lookup como o converter
    team_lookup = {}
    for _, trow in team_rows.iterrows():
        gid = trow.get("gameid")
        tname = trow.get("teamname") if pd.notna(trow.get("teamname")) else trow.get("team", None)
        if gid is None or pd.isna(gid) or tname is None:
            continue
        key = (str(gid).strip(), str(tname).strip())
        team_lookup[key] = {
            "barons": int(trow["barons"]) if pd.notna(trow.get("barons")) else None,
            "opp_barons": int(trow["opp_barons"]) if pd.notna(trow.get("opp_barons")) else None,
        }
    # Para cada gameid, qual key existe no lookup? E se usarmos o team_name do usuario?
    team_clean = str(team_name).strip()
    team_lower = team_clean.lower()
    found = 0
    missing = []
    for gid in gameids:
        key_exact = (str(gid).strip(), team_clean)
        if key_exact in team_lookup:
            found += 1
            continue
        # Fallback case-insensitive
        ok = False
        for (k_gid, k_team), v in team_lookup.items():
            if k_gid == str(gid).strip() and (k_team or "").strip().lower() == team_lower:
                ok = True
                break
        if ok:
            found += 1
        else:
            missing.append((gid, [k for (gk, kt) in team_lookup if gk == str(gid).strip()]))
    return found, len(gameids), missing


def passo3_db(db_path, team_name, n=10):
    """Consulta o DB como o prebets_secondary: ordered_gameids + game_totals (barons+opp_barons)."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(oracle_matches)")
        cols = [r[1] for r in cur.fetchall()]
        team_col = "teamname" if "teamname" in cols else "team"
        query = f"""
        WITH ordered_gameids AS (
            SELECT gameid, MAX(date) AS date
            FROM oracle_matches
            WHERE {team_col} COLLATE NOCASE = ?
              AND date IS NOT NULL AND trim(date) != ''
            GROUP BY gameid
            ORDER BY date DESC, gameid DESC
            LIMIT ?
        ),
        game_totals AS (
            SELECT gameid, MAX(COALESCE(barons,0) + COALESCE(opp_barons,0)) AS total
            FROM oracle_matches
            GROUP BY gameid
        )
        SELECT gt.total, o.date, o.gameid
        FROM ordered_gameids o
        INNER JOIN game_totals gt ON gt.gameid = o.gameid
        ORDER BY o.date DESC, o.gameid DESC
        """
        cur.execute(query, (team_name, n))
        rows = cur.fetchall()
        if not rows:
            return None, "Nenhum jogo retornado do DB (verifique nome do time)"
        vals = [r[0] for r in rows]
        over = sum(1 for v in vals if v > LINE)
        under = len(vals) - over
        media = sum(vals) / len(vals)
        return {
            "vals": vals,
            "media": media,
            "over": over,
            "under": under,
        }, None
    finally:
        conn.close()


def passo4_script(db_path, team_name, n=10):
    """Chama fetch_team_recent (prebets_secondary) e calcula over/under."""
    import sqlite3
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from core.lol.prebets_secondary import fetch_team_recent

    conn = sqlite3.connect(db_path)
    try:
        vals = fetch_team_recent(conn, team_name, "barons", limit_games=n)
        if not vals:
            return None, "fetch_team_recent retornou vazio"
        over = sum(1 for v in vals if v > LINE)
        under = len(vals) - over
        media = sum(vals) / len(vals)
        return {"vals": vals, "media": media, "over": over, "under": under}, None
    finally:
        conn.close()


def main():
    base = os.path.dirname(__file__)
    csv_path = os.path.join(base, "data", "2026_LoL_esports_match_data_from_OraclesElixir.csv")
    db_path = os.path.join(base, "data", "lol_esports.db")

    if not os.path.exists(csv_path):
        print(f"CSV nao encontrado: {csv_path}")
        return

    teams_check = [
        ("Team Vitality", "Team Vitality"),
        ("DRX", "DRX"),
        ("Nongshim RedForce", "Nongshim RedForce"),
        ("Los Ratones", "Los Ratones"),
    ]

    for display_name, csv_team_name in teams_check:
        print("=" * 70)
        print(f"TIME: {display_name}")
        print("=" * 70)

        # 1) CSV
        res, err = passo1_csv(csv_path, csv_team_name, LIMIT)
        if err:
            print(f"  [CSV] {err}")
            continue
        print(f"  [1-CSV] Ultimos {LIMIT} jogos (linhas position=team):")
        print(f"    Valores (total barons/partida): {res['vals']}")
        print(f"    Media: {res['media']:.2f}  |  OVER {LINE}: {res['over']}  UNDER: {res['under']}")

        # 2) Lookup
        found, total, missing = passo2_lookup_csv(csv_path, csv_team_name, res["gameids"])
        print(f"  [2-LOOKUP] Converter encontraria barons para {found}/{total} jogos.")
        if missing:
            print(f"    Jogos sem match: {missing[:3]}{'...' if len(missing) > 3 else ''}")

        # 3 e 4) DB e script
        res_db = res_script = None
        if os.path.exists(db_path):
            try:
                res_db, err_db = passo3_db(db_path, display_name, LIMIT)
                if err_db:
                    print(f"  [3-DB] {err_db}")
                else:
                    print(f"  [3-DB] Valores: {res_db['vals']}  Media: {res_db['media']:.2f}  OVER: {res_db['over']}  UNDER: {res_db['under']}")
            except Exception as e:
                print(f"  [3-DB] Erro: {e}")
                if "opp_barons" in str(e) or "no such column" in str(e).lower():
                    print("  >>> Rode 'Atualizar Banco' no app para recriar o DB com as colunas corretas.")
            try:
                res_script, err_script = passo4_script(db_path, display_name, LIMIT)
                if err_script:
                    print(f"  [4-SCRIPT] {err_script}")
                else:
                    print(f"  [4-SCRIPT] Valores: {res_script['vals']}  Media: {res_script['media']:.2f}  OVER: {res_script['over']}  UNDER: {res_script['under']}")
            except Exception as e:
                print(f"  [4-SCRIPT] Erro: {e}")
            if res and res_script and res["vals"] != res_script["vals"]:
                print("  >>> DISCREPANCIA: CSV e script retornam valores diferentes!")
        else:
            print("  [3-DB] Banco nao encontrado. Rode 'Atualizar Banco' e execute este script de novo.")
        print()

    print("=" * 70)
    print("Se [1-CSV] estiver correto e [3-DB] ou [4-SCRIPT] diferentes:")
    print("  - Atualize o banco (Atualizar Banco) e rode de novo.")
    print("  - Se continuar diferente, o nome do time no dropdown pode nao bater com o CSV/DB.")
    print("=" * 70)


if __name__ == "__main__":
    main()
