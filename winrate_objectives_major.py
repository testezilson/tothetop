"""
Win rate por objetivos e leads (ligas MAJOR apenas).
- First tower, first dragon, first herald e todas as combinações.
- First to three towers.
- Gold/XP/CS diff em 10, 15, 20, 25 min (gold >= 1k) e combinações.
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
GOLD_MIN = 1000  # gold diff mínimo (1k)
XP_CS_MIN = 0    # xp/cs diff: time na frente (>= 0)


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


def load_major_df(csv_path):
    """Uma linha por (gameid, team): MAJOR leagues, com first*, result e diffs."""
    df_raw = pd.read_csv(csv_path, low_memory=False)
    df_raw.columns = df_raw.columns.str.strip().str.lower()
    df_raw = df_raw[df_raw["league"].isin(MAJOR_LEAGUES)]
    if df_raw.empty:
        return pd.DataFrame()

    cols = [
        "gameid", "teamname", "league", "result",
        "firstdragon", "firsttower", "firstherald", "firsttothreetowers",
        "golddiffat10", "xpdiffat10", "csdiffat10",
        "golddiffat15", "xpdiffat15", "csdiffat15",
        "golddiffat20", "xpdiffat20", "csdiffat20",
        "golddiffat25", "xpdiffat25", "csdiffat25",
    ]
    missing = [c for c in cols if c not in df_raw.columns]
    if missing:
        print(f"Colunas ausentes no CSV: {missing}")
        return pd.DataFrame()

    agg = {}
    for c in cols:
        if c in ("gameid", "teamname"):
            continue
        agg[c] = "max" if c in ("firstdragon", "firsttower", "firstherald", "firsttothreetowers") else "first"
    df = df_raw[cols].groupby(["gameid", "teamname"], as_index=False).agg(agg)
    df = df.rename(columns={"teamname": "team"})

    res = df["result"].astype(str).str.lower()
    df["result"] = (res.isin(["1", "true", "win", "w"])).astype(int)

    for c in ["firstdragon", "firsttower", "firstherald", "firsttothreetowers"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in [f"golddiffat{m}" for m in [10, 15, 20, 25]] + [f"xpdiffat{m}" for m in [10, 15, 20, 25]] + [f"csdiffat{m}" for m in [10, 15, 20, 25]]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    return df


def wr(df, mask, label):
    """Imprime win rate para a máscara (times que satisfazem a condição)."""
    if mask is None or not mask.any():
        return
    sub = df.loc[mask]
    n = len(sub)
    w = sub["result"].sum()
    pct = 100.0 * w / n if n else 0
    print(f"  {label}: {n} jogos, {int(w)} vitórias, WR {pct:.1f}%")


def main():
    csv_path = _find_csv()
    if not csv_path:
        print("CSV do Oracle não encontrado em db2026 ou data/")
        return
    print(f"CSV: {csv_path}")
    print(f"Ligas: {', '.join(sorted(MAJOR_LEAGUES))}\n")
    df = load_major_df(csv_path)
    if df.empty:
        print("Nenhum dado para ligas MAJOR.")
        return
    n_teams = len(df)
    n_games = df["gameid"].nunique()
    print(f"Partidas únicas: {n_games}  |  Registros (1 por time por jogo): {n_teams}\n")
    print("=" * 60)

    # --- First objectives (single) ---
    print("\n--- FIRST OBJECTIVES (single) ---")
    wr(df, df["firsttower"] == 1, "First Tower")
    wr(df, df["firstdragon"] == 1, "First Dragon")
    wr(df, df["firstherald"] == 1, "First Herald")

    # --- First objectives (combinations) ---
    print("\n--- FIRST OBJECTIVES (combinações) ---")
    T = (df["firsttower"] == 1)
    D = (df["firstdragon"] == 1)
    H = (df["firstherald"] == 1)
    wr(df, T & D, "First Tower + First Dragon")
    wr(df, T & H, "First Tower + First Herald")
    wr(df, D & H, "First Dragon + First Herald")
    wr(df, T & D & H, "First Tower + First Dragon + First Herald")

    # --- First to three towers ---
    print("\n--- FIRST TO THREE TOWERS ---")
    wr(df, df["firsttothreetowers"] == 1, "First to 3 Towers")

    # --- Diff at 10 (gold >= 1k, xp/cs >= 0) e combinações ---
    print("\n--- LEAD AT 10 MIN (gold diff >= 1k, xp/cs diff >= 0) ---")
    g10 = df["golddiffat10"] >= GOLD_MIN
    x10 = df["xpdiffat10"] >= XP_CS_MIN
    c10 = df["csdiffat10"] >= XP_CS_MIN
    wr(df, g10, f"Gold diff @10 >= {GOLD_MIN}")
    wr(df, x10, "XP diff @10 >= 0")
    wr(df, c10, "CS diff @10 >= 0")
    wr(df, g10 & x10, f"Gold>=1k + XP>=0 @10")
    wr(df, g10 & c10, f"Gold>=1k + CS>=0 @10")
    wr(df, x10 & c10, "XP>=0 + CS>=0 @10")
    wr(df, g10 & x10 & c10, f"Gold>=1k + XP>=0 + CS>=0 @10")

    # --- Diff at 15 ---
    print("\n--- LEAD AT 15 MIN ---")
    g15 = df["golddiffat15"] >= GOLD_MIN
    x15 = df["xpdiffat15"] >= XP_CS_MIN
    c15 = df["csdiffat15"] >= XP_CS_MIN
    wr(df, g15, f"Gold diff @15 >= {GOLD_MIN}")
    wr(df, x15, "XP diff @15 >= 0")
    wr(df, c15, "CS diff @15 >= 0")
    wr(df, g15 & x15, f"Gold>=1k + XP>=0 @15")
    wr(df, g15 & c15, f"Gold>=1k + CS>=0 @15")
    wr(df, x15 & c15, "XP>=0 + CS>=0 @15")
    wr(df, g15 & x15 & c15, f"Gold>=1k + XP>=0 + CS>=0 @15")

    # --- Diff at 20 ---
    print("\n--- LEAD AT 20 MIN ---")
    g20 = df["golddiffat20"] >= GOLD_MIN
    x20 = df["xpdiffat20"] >= XP_CS_MIN
    c20 = df["csdiffat20"] >= XP_CS_MIN
    wr(df, g20, f"Gold diff @20 >= {GOLD_MIN}")
    wr(df, x20, "XP diff @20 >= 0")
    wr(df, c20, "CS diff @20 >= 0")
    wr(df, g20 & x20, f"Gold>=1k + XP>=0 @20")
    wr(df, g20 & c20, f"Gold>=1k + CS>=0 @20")
    wr(df, x20 & c20, "XP>=0 + CS>=0 @20")
    wr(df, g20 & x20 & c20, f"Gold>=1k + XP>=0 + CS>=0 @20")

    # --- Diff at 25 ---
    print("\n--- LEAD AT 25 MIN ---")
    g25 = df["golddiffat25"] >= GOLD_MIN
    x25 = df["xpdiffat25"] >= XP_CS_MIN
    c25 = df["csdiffat25"] >= XP_CS_MIN
    wr(df, g25, f"Gold diff @25 >= {GOLD_MIN}")
    wr(df, x25, "XP diff @25 >= 0")
    wr(df, c25, "CS diff @25 >= 0")
    wr(df, g25 & x25, f"Gold>=1k + XP>=0 @25")
    wr(df, g25 & c25, f"Gold>=1k + CS>=0 @25")
    wr(df, x25 & c25, "XP>=0 + CS>=0 @25")
    wr(df, g25 & x25 & c25, f"Gold>=1k + XP>=0 + CS>=0 @25")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
