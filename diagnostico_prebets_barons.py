"""
Diagnóstico: compara totais da partida (barons) entre CSV e DB.
- Últimos 10 jogos por time (total barons da partida em cada jogo).
- Média e over/under.
- H2H (jogos entre os dois times, total barons da partida).
Execute: python diagnostico_prebets_barons.py
"""
import os
import sys
import pandas as pd

# garantir que src está no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

def from_csv(csv_path, team1="DRX", team2="Nongshim RedForce", limit=10):
    """Calcula a partir do CSV: total barons por jogo (barons + opp_barons da linha team)."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    # Apenas linhas position=team têm barons/opp_barons preenchidos no source
    team_rows = df[df["position"].astype(str).str.strip().str.lower() == "team"].copy()
    if team_rows.empty:
        print("[CSV] Nenhuma linha position=team encontrada.")
        return
    # Total da partida = barons + opp_barons (um time já tem o total do jogo na sua linha)
    team_rows["total_barons"] = team_rows["barons"].fillna(0).astype(int) + team_rows["opp_barons"].fillna(0).astype(int)
    team_rows["date"] = pd.to_datetime(team_rows["date"], errors="coerce")
    team_rows = team_rows.sort_values("date", ascending=False)

    def last_n(tname, n):
        sub = team_rows[team_rows["teamname"].astype(str).str.strip().str.lower() == tname.strip().lower()]
        # um jogo = duas linhas (um por time); pegar gameids únicos por data
        sub = sub.drop_duplicates(subset=["gameid"], keep="first")
        sub = sub.head(n)
        return sub["total_barons"].tolist(), sub["date"].tolist()

    t1_vals, t1_dates = last_n(team1, limit)
    t2_vals, t2_dates = last_n(team2, limit)

    print("=== DADOS DO CSV (total da partida: barons + opp_barons por jogo) ===")
    print(f"Time 1: {team1}")
    print(f"  Últimos {limit} jogos (totais): {t1_vals}")
    if t1_vals:
        print(f"  Média: {sum(t1_vals)/len(t1_vals):.2f}")
    print(f"Time 2: {team2}")
    print(f"  Últimos {limit} jogos (totais): {t2_vals}")
    if t2_vals:
        print(f"  Média: {sum(t2_vals)/len(t2_vals):.2f}")
    combined = t1_vals + t2_vals
    if combined:
        print(f"Combinado ({len(combined)} jogos): média {sum(combined)/len(combined):.2f}")

    # H2H: jogos em que os dois times jogaram
    g1 = set(team_rows[team_rows["teamname"].astype(str).str.strip().str.lower() == team1.strip().lower()]["gameid"].unique())
    g2 = set(team_rows[team_rows["teamname"].astype(str).str.strip().str.lower() == team2.strip().lower()]["gameid"].unique())
    h2h_gids = g1 & g2
    h2h_rows = team_rows[team_rows["gameid"].isin(h2h_gids)].drop_duplicates(subset=["gameid"], keep="first")
    h2h_rows = h2h_rows.sort_values("date", ascending=False)
    h2h_totals = h2h_rows["total_barons"].tolist()
    print(f"H2H ({team1} x {team2}): {len(h2h_totals)} jogos, totais por jogo: {h2h_totals}")
    if h2h_totals:
        print(f"  Média H2H: {sum(h2h_totals)/len(h2h_totals):.2f}")
    print()
    return {"t1": t1_vals, "t2": t2_vals, "h2h": h2h_totals}


def from_db(db_path, team1="DRX", team2="Nongshim RedForce", limit=10):
    """Calcula a partir do DB usando a mesma lógica do prebets_secondary (total da partida)."""
    import sqlite3
    from core.lol.prebets_secondary import fetch_team_recent, fetch_h2h_empirico, _get_team_column

    conn = sqlite3.connect(db_path)
    try:
        team_col = _get_team_column(conn)
        # Nomes exatos no banco podem variar (ex: "Nongshim RedForce" vs "NS")
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT {team_col} FROM oracle_matches WHERE {team_col} LIKE '%DRX%' OR {team_col} LIKE '%Nongshim%' OR {team_col} LIKE '%NS%'")
        names = [r[0] for r in cursor.fetchall()]
        print(f"[DB] Nomes de times no banco (DRX/NS): {names}")

        vals1 = fetch_team_recent(conn, team1, "barons", limit_games=limit)
        vals2 = fetch_team_recent(conn, team2, "barons", limit_games=limit)
        h2h_rate, nh2h, h2h_mean, over_h2h, under_h2h = fetch_h2h_empirico(conn, team1, team2, "barons", months=12, line=1.5)

        print("=== DADOS DO BANCO (total da partida) ===")
        print(f"Time 1: {team1}")
        print(f"  Últimos {limit} jogos (totais): {vals1}")
        if vals1:
            print(f"  Média: {sum(vals1)/len(vals1):.2f}")
        print(f"Time 2: {team2}")
        print(f"  Últimos {limit} jogos (totais): {vals2}")
        if vals2:
            print(f"  Média: {sum(vals2)/len(vals2):.2f}")
        combined = vals1 + vals2
        if combined:
            print(f"Combinado ({len(combined)} jogos): média {sum(combined)/len(combined):.2f}")
        print(f"H2H: {nh2h} jogos, média {h2h_mean:.2f}, over/under {over_h2h}/{under_h2h}")
        print()
        return {"t1": vals1, "t2": vals2, "h2h_n": nh2h, "h2h_mean": h2h_mean}
    finally:
        conn.close()


def main():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    csv_path = os.path.join(data_dir, "2026_LoL_esports_match_data_from_OraclesElixir.csv")
    db_path = os.path.join(data_dir, "lol_esports.db")

    if not os.path.exists(csv_path):
        print(f"CSV não encontrado: {csv_path}")
        return
    from_csv(csv_path, team1="DRX", team2="Nongshim RedForce", limit=10)

    if os.path.exists(db_path):
        from_db(db_path, team1="DRX", team2="Nongshim RedForce", limit=10)
    else:
        print(f"Banco nao encontrado: {db_path}")
        print("  Rode no app: LoL > Atualizar Banco e escolha o CSV 2026. Depois rode este script de novo.")
    print("Compare os valores acima: CSV vs DB devem bater (totais da partida).")


if __name__ == "__main__":
    main()
