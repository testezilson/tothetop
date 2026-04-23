import pandas as pd
import numpy as np

ORACLE_PATH = "../data/oracle_prepared.csv"
IMPACTS_PATH = "../data/champion_impacts.csv"
OUTPUT_PATH = "../data/trainset_v3.csv"

def main():
    print("📊 Carregando base do Oracle...")
    df = pd.read_csv(ORACLE_PATH)
    df_imp = pd.read_csv(IMPACTS_PATH)

    required_cols = ["league", "gameid", "teamkills", "pick1", "pick2", "pick3", "pick4", "pick5"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"❌ Coluna obrigatória ausente: {col}")

    # Calcula kills totais por partida
    df_total = df.groupby(["league", "gameid"])["teamkills"].sum().reset_index(name="total_kills")

    # Combina times em uma única linha (T1 e T2)
    print("⚙️ Reorganizando partidas...")
    games = []
    for (league, gameid), group in df.groupby(["league", "gameid"]):
        if len(group) != 2:
            continue
        t1, t2 = group.iloc[0], group.iloc[1]
        game = {
            "league": league,
            "gameid": gameid,
            "t1": t1["teamname"],
            "t2": t2["teamname"],
            "total_kills": float(df_total.loc[
                (df_total["league"] == league) & (df_total["gameid"] == gameid), "total_kills"
            ].iloc[0])
        }
        for i in range(1, 6):
            game[f"t1_pos{i}"] = t1[f"pick{i}"]
            game[f"t2_pos{i}"] = t2[f"pick{i}"]
        games.append(game)

    df_games = pd.DataFrame(games)
    print(f"✅ {len(df_games)} partidas processadas.")

    # Função para buscar impacto por liga e campeão
    def get_impact(league, champ):
        if pd.isna(champ):
            return 0.0
        row = df_imp[
            (df_imp["league"] == league) &
            (df_imp["champion"].str.casefold() == str(champ).casefold())
        ]
        return float(row["impact"].iloc[0]) if not row.empty else 0.0

    # Calcula os impactos
    print("🎯 Calculando impactos dos campeões...")
    for i in range(1, 6):
        df_games[f"impact_t1_pos{i}"] = [
            get_impact(lg, champ) for lg, champ in zip(df_games["league"], df_games[f"t1_pos{i}"])
        ]
        df_games[f"impact_t2_pos{i}"] = [
            get_impact(lg, champ) for lg, champ in zip(df_games["league"], df_games[f"t2_pos{i}"])
        ]

    # Cria features agregadas
    df_games["total_impact_t1"] = df_games[[f"impact_t1_pos{i}" for i in range(1, 6)]].sum(axis=1)
    df_games["total_impact_t2"] = df_games[[f"impact_t2_pos{i}" for i in range(1, 6)]].sum(axis=1)
    df_games["total_impact"] = df_games["total_impact_t1"] + df_games["total_impact_t2"]
    df_games["impact_diff"] = df_games["total_impact_t1"] - df_games["total_impact_t2"]
    df_games["mean_impact_team1"] = df_games["total_impact_t1"] / 5
    df_games["mean_impact_team2"] = df_games["total_impact_t2"] / 5
    df_games["league_encoded"] = [hash(lg) % 1000 for lg in df_games["league"]]

    # Salva
    df_games.to_csv(OUTPUT_PATH, index=False)
    print(f"💾 Trainset salvo em: {OUTPUT_PATH}")
    print(f"📈 Total de linhas: {len(df_games)}")

if __name__ == "__main__":
    main()
