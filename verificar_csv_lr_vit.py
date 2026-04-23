"""
Verifica no CSV Oracle (2026) os últimos 10 jogos de Los Ratones e Team Vitality.
Mostra totais da partida: kills (team+opp), towers, dragons, barons.
Use para comparar com o que o app exibe (RECENT FORM / Pré-bets Secundárias).
"""
import pandas as pd
import os
from pathlib import Path

def main():
    data_dir = Path(__file__).resolve().parent / "data"
    csv_path = data_dir / "2026_LoL_esports_match_data_from_OraclesElixir.csv"
    if not csv_path.exists():
        print(f"CSV não encontrado: {csv_path}")
        return
    print(f"Carregando: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()

    # Apenas linhas position=team (uma por time por jogo; objetivos e teamkills vêm aqui)
    team_rows = df[df["position"].astype(str).str.strip().str.lower() == "team"].copy()
    if team_rows.empty:
        print("Nenhuma linha position=team no CSV.")
        return

    # Garantir date para ordenação
    team_rows["date"] = pd.to_datetime(team_rows["date"], errors="coerce")
    team_rows = team_rows.dropna(subset=["date"])

    def last_n_games(team_name, n=10):
        """Últimos n jogos do time (por date desc). Retorna lista de (date, gameid, opponent, total_kills, total_towers, total_dragons, total_barons)."""
        subset = team_rows[team_rows["teamname"].astype(str).str.strip().str.lower() == team_name.strip().lower()]
        subset = subset.sort_values("date", ascending=False)
        gameids = subset["gameid"].unique()[:n]
        result = []
        for gid in gameids:
            rows = team_rows[team_rows["gameid"] == gid]
            if len(rows) != 2:
                continue
            r = rows[rows["teamname"].astype(str).str.strip().str.lower() == team_name.strip().lower()].iloc[0]
            opp_row = rows[rows["teamname"] != r["teamname"]].iloc[0]
            opponent = opp_row["teamname"]
            # Total da partida: para kills = teamkills do time + teamkills do oponente
            total_kills = int(r.get("teamkills", 0) or 0) + int(opp_row.get("teamkills", 0) or 0)
            # towers + opp_towers já é total da partida (um time's towers = other's opp_towers)
            total_towers = int(r.get("towers", 0) or 0) + int(r.get("opp_towers", 0) or 0)
            total_dragons = int(r.get("dragons", 0) or 0) + int(r.get("opp_dragons", 0) or 0)
            total_barons = int(r.get("barons", 0) or 0) + int(r.get("opp_barons", 0) or 0)
            result.append((r["date"], gid, opponent, total_kills, total_towers, total_dragons, total_barons))
        return result

    for label, team_name in [("LR (Los Ratones)", "Los Ratones"), ("VIT (Team Vitality)", "Team Vitality")]:
        print("\n" + "=" * 60)
        print(f"  {label} — Últimos 10 jogos (TOTAIS DA PARTIDA)")
        print("=" * 60)
        games = last_n_games(team_name, 10)
        if not games:
            print(f"Nenhum jogo encontrado para '{team_name}'.")
            continue
        kills_list = []
        towers_list = []
        dragons_list = []
        barons_list = []
        for date, gid, opp, tk, tw, dr, br in games:
            kills_list.append(tk)
            towers_list.append(tw)
            dragons_list.append(dr)
            barons_list.append(br)
            opp_short = opp[:12] if len(str(opp)) > 12 else opp
            print(f"  {opp_short:12} | Kills: {tk:3}  Towers: {tw:2}  Dragons: {dr}  Barons: {br}  | {date}")
        avg_k = sum(kills_list) / len(kills_list)
        avg_t = sum(towers_list) / len(towers_list)
        avg_d = sum(dragons_list) / len(dragons_list)
        avg_b = sum(barons_list) / len(barons_list)
        print(f"  Média (last 10): Kills {avg_k:.1f}  Towers {avg_t:.1f}  Dragons {avg_d:.1f}  Barons {avg_b:.1f}")
        avg5_k = sum(kills_list[:5]) / 5 if len(kills_list) >= 5 else avg_k
        avg5_t = sum(towers_list[:5]) / 5 if len(towers_list) >= 5 else avg_t
        avg5_d = sum(dragons_list[:5]) / 5 if len(dragons_list) >= 5 else avg_d
        avg5_b = sum(barons_list[:5]) / 5 if len(barons_list) >= 5 else avg_b
        print(f"  Média (last 5):  Kills {avg5_k:.1f}  Towers {avg5_t:.1f}  Dragons {avg5_d:.1f}  Barons {avg5_b:.1f}")

    print("\n[Concluído] Compare estes totais com o app (RECENT FORM / Pré-bets Secundárias).")
    print("Kills devem ser TOTAIS da partida (time + adversário). Se o app mostrar só kills do time, está errado.")

if __name__ == "__main__":
    main()
