"""
Análise exploratória: gold diff por lane (top, jng, mid, bot, sup) @10, @15, @20 e @25 min,
cruzado com win rate final. Apenas ligas MAJOR.
"""
import os
import sys
import pandas as pd

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB2026_DIR = r"C:\Users\Lucas\Documents\db2026"

# Posições de jogador (ignorar 'team' que é linha agregada)
LANES = ["top", "jng", "mid", "bot", "sup"]


def _find_csv():
    """CSV do Oracle: prioridade db2026, depois data/ do projeto."""
    if os.path.isdir(DB2026_DIR):
        for f in os.listdir(DB2026_DIR):
            if f.endswith(".csv") and ("LoL_esports" in f or "oracle" in f.lower() or "2026" in f):
                return os.path.join(DB2026_DIR, f)
    if os.path.isdir(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith(".csv") and ("OraclesElixir" in f or ("LoL_esports" in f and "match_data" in f)):
                return os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR):
            if f.endswith(".csv") and ("LoL_esports" in f or "2026" in f):
                return os.path.join(DATA_DIR, f)
    return None


TIMES = [10, 15, 20, 25]


def load_player_level(csv_path):
    """Carrega uma linha por jogador, ligas MAJOR, com gold@10/15/20/25 por position."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    df = df[df["league"].isin(MAJOR_LEAGUES)].copy()
    df = df[df["position"].isin(LANES)].copy()
    for c in ["goldat10", "goldat15", "result"]:
        if c not in df.columns:
            raise ValueError(f"Coluna ausente: {c}")
    cols = ["gameid", "teamname", "position", "result"]
    for t in TIMES:
        c = f"goldat{t}"
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
            cols.append(c)
    return df[cols]


def build_lane_diffs(df):
    """
    Para cada (gameid, teamname) calcula gold diff por lane @10, @15, @20 e @25.
    gold_diff_lane = gold_desse_time_na_lane - gold_do_oponente_na_mesma_lane.
    Retorna DataFrame: uma linha por (gameid, teamname) com result e colunas top_diff_10, top_diff_15, ...
    """
    teams_per_game = df.groupby("gameid")["teamname"].apply(lambda x: list(x.unique())).reset_index()
    teams_per_game.columns = ["gameid", "teams"]
    df = df.merge(teams_per_game, on="gameid")
    df["opp_teamname"] = df.apply(lambda r: [t for t in r["teams"] if t != r["teamname"]][0] if len(r["teams"]) == 2 else None, axis=1)
    df = df.drop(columns=["teams"])

    gold_cols = [c for c in df.columns if c.startswith("goldat") and c.replace("goldat", "").isdigit()]
    opp_cols = [f"opp_{c}" for c in gold_cols]
    opp = df[["gameid", "teamname", "position"] + gold_cols].copy()
    opp = opp.rename(columns={"teamname": "opp_teamname", **dict(zip(gold_cols, opp_cols))})
    df = df.merge(opp, on=["gameid", "opp_teamname", "position"], how="left")

    result_col = "result"
    pivots = {}
    for c in gold_cols:
        t = c.replace("goldat", "")
        diff_col = f"lane_gold_diff_{t}"
        opp_c = f"opp_{c}"
        if opp_c not in df.columns:
            continue
        df[diff_col] = df[c] - df[opp_c]
        include_result = result_col in df.columns and t == "10"
        pivots[t] = df.pivot_table(index=["gameid", "teamname"] + ([result_col] if include_result else []), columns="position", values=diff_col, aggfunc="first").reset_index()
        pivots[t] = pivots[t].rename(columns={p: f"{p}_diff_{t}" for p in LANES if p in pivots[t].columns})

    out = None
    for t in TIMES:
        ts = str(t)
        if ts not in pivots:
            continue
        if out is None:
            out = pivots[ts].copy()
        else:
            merge_cols = ["gameid", "teamname"]
            drop = [c for c in pivots[ts].columns if c not in merge_cols and c not in out.columns]
            out = out.merge(pivots[ts][merge_cols + [c for c in pivots[ts].columns if c not in merge_cols]], on=merge_cols, how="left")
    if out is None:
        return pd.DataFrame()
    if result_col in out.columns:
        out["result"] = out["result"].astype(str).str.lower().isin(["1", "true", "win", "w"]).astype(int)
    return out


def wr_by_lane_diff(team_df, lane_col, thresholds=None):
    """Para uma coluna de gold diff (ex: mid_diff_15), calcula win rate por faixa."""
    if thresholds is None:
        thresholds = [0, 500, 1000, 1500, 2000, 3000, 5000, 100000]
    ser = team_df[lane_col].dropna()
    wins = team_df.loc[ser.index, "result"]
    out = []
    for i in range(len(thresholds) - 1):
        lo, hi = thresholds[i], thresholds[i + 1]
        mask = (ser >= lo) & (ser < hi)
        if mask.sum() == 0:
            continue
        n = mask.sum()
        w = (wins.loc[mask]).sum()
        out.append((f"[{lo}, {hi})", n, w, 100.0 * w / n if n else 0))
    return out


def main():
    csv_path = _find_csv()
    if not csv_path:
        print("CSV do Oracle não encontrado em db2026 ou data/")
        return
    print(f"CSV: {csv_path}")
    print(f"Ligas MAJOR: {', '.join(sorted(MAJOR_LEAGUES))}\n")

    df = load_player_level(csv_path)
    if df.empty:
        print("Nenhum dado para ligas MAJOR.")
        return

    team_df = build_lane_diffs(df)
    n_games = team_df["gameid"].nunique()
    n_rows = len(team_df)
    print(f"Jogos únicos: {n_games}  |  Registros (1 por time por jogo): {n_rows}")
    print(f"Win rate geral: {team_df['result'].mean()*100:.1f}%\n")
    print("=" * 70)

    thresholds = [0, 500, 1000, 1500, 2000, 3000, 5000, 100000]
    for lane in LANES:
        for t in TIMES:
            col = f"{lane}_diff_{t}"
            if col not in team_df.columns:
                continue
            print(f"\n--- {lane.upper()} — Gold diff @{t} min (perspectiva do time) ---")
            rows = wr_by_lane_diff(team_df, col, thresholds)
            for label, n, w, pct in rows:
                print(f"  {label:>12}  n={n:4}  vitórias={int(w):4}  WR={pct:.1f}%")
    print("\n" + "=" * 70)

    # Resumo: quando a lane está à frente/atrás por >= 1k gold, por timer
    for t in TIMES:
        print(f"\n--- Resumo: WR quando a lane está à frente >= 1k gold @{t} min ---")
        for lane in LANES:
            col = f"{lane}_diff_{t}"
            if col not in team_df.columns:
                continue
            mask = team_df[col] >= 1000
            if mask.sum() < 10:
                continue
            wr_lead = team_df.loc[mask, "result"].mean() * 100
            print(f"  {lane.upper():>4}  à frente >= 1k @{t:>2}:  n={mask.sum():4}  WR={wr_lead:.1f}%")
        print(f"\n--- Resumo: WR quando a lane está atrás >= 1k gold @{t} min ---")
        for lane in LANES:
            col = f"{lane}_diff_{t}"
            if col not in team_df.columns:
                continue
            mask = team_df[col] <= -1000
            if mask.sum() < 10:
                continue
            wr_behind = team_df.loc[mask, "result"].mean() * 100
            print(f"  {lane.upper():>4}  atrás >= 1k @{t:>2}:    n={mask.sum():4}  WR={wr_behind:.1f}%")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
