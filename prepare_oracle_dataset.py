import pandas as pd

INPUT_PATH = "data/2025_LoL_esports_match_data_from_OraclesElixir.csv"
OUTPUT_PATH = "data/oracle_prepared.csv"

print("📊 Carregando dataset bruto da Oracle’s Elixir...")
df = pd.read_csv(INPUT_PATH, low_memory=False)

# 🔍 Garante que as colunas essenciais existem
required_cols = ["league", "gameid", "teamname", "champion", "teamkills"]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    raise ValueError(f"❌ Colunas faltando no CSV original: {missing}")

# 🔹 Mantém apenas colunas relevantes
keep_cols = [
    "league", "date", "split", "playoffs", "gameid",
    "teamname", "result", "teamkills", "totalgold", "champion"
]
df = df[[c for c in keep_cols if c in df.columns]].copy()

# 🔹 Remove linhas sem campeão
df = df[df["champion"].notna()]

# 🔄 Reconstrói picks por time (1 linha por time, com pick1–pick5)
def build_team_picks(group):
    picks = list(group["champion"].values)[:5]
    while len(picks) < 5:
        picks.append(None)
    return pd.Series({
        "gameid": group["gameid"].iloc[0],
        "league": group["league"].iloc[0],
        "date": group["date"].iloc[0] if "date" in group else None,
        "split": group["split"].iloc[0] if "split" in group else None,
        "playoffs": group["playoffs"].iloc[0] if "playoffs" in group else None,
        "teamname": group["teamname"].iloc[0],
        "teamkills": group["teamkills"].iloc[0],
        "pick1": picks[0],
        "pick2": picks[1],
        "pick3": picks[2],
        "pick4": picks[3],
        "pick5": picks[4]
    })

print("⚙️ Reconstruindo drafts por time...")
df_team = (
    df.groupby(["gameid", "teamname"])
    .apply(build_team_picks)
    .reset_index(drop=True)
)

# 🔁 Atribui o adversário com base no mesmo gameid
print("🔄 Atribuindo adversários...")
df_team["opponent"] = None
for gid, group in df_team.groupby("gameid"):
    if len(group) == 2:
        t1, t2 = group["teamname"].iloc[0], group["teamname"].iloc[1]
        df_team.loc[group.index[0], "opponent"] = t2
        df_team.loc[group.index[1], "opponent"] = t1

print(f"✅ {len(df_team)} times processados ({len(df_team)//2} partidas).")

# 💾 Salva dataset final
df_team.to_csv(OUTPUT_PATH, index=False)
print(f"✅ Dataset final salvo em {OUTPUT_PATH}")
print("📘 Colunas finais:", ", ".join(df_team.columns))
