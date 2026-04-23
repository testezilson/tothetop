"""Script temporário para checar últimas partidas das ligas major no CSV."""
import pandas as pd

MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}
csv_path = r"c:\Users\Lucas\Documents\db2026\2026_LoL_esports_match_data_from_OraclesElixir.csv"

df = pd.read_csv(csv_path, low_memory=False)
df_major = df[df["league"].isin(MAJOR_LEAGUES)].copy()

# Agrupar por gameid + league - pegar date e times (usar linhas com position para evitar duplicatas)
df_players = df_major[df_major["position"].notna() & (df_major["position"] != "team")]
games = (
    df_players.groupby(["gameid", "league"])
    .agg({"date": "first", "teamname": lambda x: " | ".join(x.dropna().unique()[:2])})
    .reset_index()
)

games = games[games["date"].notna() & (games["date"] != "")]
games["date_parsed"] = pd.to_datetime(games["date"], errors="coerce")
games = games[games["date_parsed"].notna()]
games = games.sort_values("date_parsed", ascending=False)

print("=" * 90)
print("ULTIMAS PARTIDAS DAS LIGAS MAJOR (LPL, LCK, LEC, CBLOL, LCS, LCP) - com data")
print("=" * 90)

for league in sorted(MAJOR_LEAGUES):
    lg_games = games[games["league"] == league].head(15)
    if lg_games.empty:
        print(f"\n{league}: Nenhuma partida com data")
        continue
    print(f"\n--- {league} (últimas {len(lg_games)} partidas) ---")
    for _, r in lg_games.iterrows():
        date_str = r["date_parsed"].strftime("%Y-%m-%d %H:%M") if pd.notna(r["date_parsed"]) else str(r["date"])[:16]
        teams = str(r["teamname"])[:70] + "..." if len(str(r["teamname"])) > 70 else str(r["teamname"])
        print(f"  {date_str} | {r['gameid']} | {teams}")

print("\n" + "=" * 90)
print("RESUMO: Total de partidas por liga (com data válida)")
for league in sorted(MAJOR_LEAGUES):
    n = len(games[games["league"] == league])
    last = games[games["league"] == league].iloc[0] if n > 0 else None
    last_str = last["date_parsed"].strftime("%Y-%m-%d") if last is not None and pd.notna(last["date_parsed"]) else "N/A"
    print(f"  {league}: {n} partidas | última: {last_str}")
