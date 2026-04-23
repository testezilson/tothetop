#!/usr/bin/env python3
"""
Monta o dataset lol_live_snapshots para treino do modelo Live LoL.

Uma linha por (gameid, minute) para checkpoints 10, 15, 20, 25 min.
Target: kills_remaining. Regime lento via slow_intensity = max(0, 0.33 - kpm_now).
Sem torres/barons/dragons nas features.

Fonte: OraclesElixir CSV (team rows participantid 100/200).
Impactos: champion_impacts_lol.json (4 métricas como Dota) ou fallback champion_impacts.csv (só kills).

Uso:
  python scripts/lol_live/build_snapshots.py
  python scripts/lol_live/build_snapshots.py --csv data/2026_LoL_esports_match_data_from_OraclesElixir.csv -o data/lol_live_snapshots.csv
"""
import json
import math
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "2026_LoL_esports_match_data_from_OraclesElixir.csv"
CHAMPION_IMPACTS_JSON = PROJECT_ROOT / "data" / "champion_impacts_lol.json"
CHAMPION_IMPACTS_CSV = PROJECT_ROOT / "data" / "champion_impacts.csv"
CHECKPOINTS = [10, 15, 20, 25]
DRAFT_WEIGHT_MAX_MIN = 40


def _load_champion_impacts_full(json_path: Path | None = None, csv_path: Path | None = None) -> dict[str, dict]:
    """
    Carrega os 4 impactos por campeão (como Dota).
    Prioridade: champion_impacts_lol.json. Fallback: champion_impacts.csv (só impact_kills).
    """
    jpath = json_path or CHAMPION_IMPACTS_JSON
    if jpath.exists():
        try:
            with open(jpath, encoding="utf-8") as f:
                data = json.load(f)
            imp = data.get("champion_impacts", data)
            if isinstance(imp, dict):
                return imp
        except Exception:
            pass
    # Fallback: champion_impacts.csv (só kills)
    out = {}
    cpath = csv_path or CHAMPION_IMPACTS_CSV
    if cpath.exists():
        df = pd.read_csv(cpath)
        df.columns = df.columns.str.strip().str.lower()
        if "champion" in df.columns and "impact" in df.columns:
            agg = df.groupby("champion")["impact"].mean()
            for c, v in agg.items():
                out[str(c)] = {
                    "impact_kills": float(v),
                    "impact_duration": 0.0,
                    "impact_kpm": 0.0,
                    "impact_conversion": 0.0,
                }
    return out


def _draft_impacts_weighted(blue_picks: list, red_picks: list, impacts: dict[str, dict], minute: int) -> dict:
    """Soma os 4 impactos do draft (10 campeões) com peso. weight = max(0, 1 - minute/40)."""
    weight = max(0.0, 1.0 - minute / DRAFT_WEIGHT_MAX_MIN)
    out = {"kills": 0.0, "duration": 0.0, "kpm": 0.0, "conversion": 0.0}
    for name in (blue_picks or [])[:5] + (red_picks or [])[:5]:
        n = str(name).strip() if name else ""
        if not n or (isinstance(n, float) and math.isnan(n)):
            continue
        data = impacts.get(n) or impacts.get(n.replace(" ", "")) or impacts.get(n.replace(".", ""))
        if isinstance(data, dict):
            out["kills"] += (data.get("impact_kills") or 0) * weight
            out["duration"] += (data.get("impact_duration") or 0) * weight
            out["kpm"] += (data.get("impact_kpm") or 0) * weight
            out["conversion"] += (data.get("impact_conversion") or 0) * weight
        elif isinstance(data, (int, float)):
            out["kills"] += float(data) * weight
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument("--impacts", type=Path, default=None, help="champion_impacts_lol.json (prioridade)")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Erro: CSV não encontrado: {args.csv}")
        sys.exit(1)

    imp_path = args.impacts if args.impacts else None
    impacts = _load_champion_impacts_full(json_path=imp_path)
    if not impacts:
        print("Aviso: champion_impacts_lol.json/champion_impacts.csv não encontrado. Draft impacts = 0.")

    df = pd.read_csv(args.csv)
    df.columns = df.columns.str.strip().str.lower()

    # Filtrar linhas de time (participantid 100 = Blue, 200 = Red)
    blue = df[df["participantid"] == 100].copy()
    red = df[df["participantid"] == 200].copy()

    if blue.empty:
        print("Erro: nenhuma linha Blue (participantid 100) encontrada.")
        sys.exit(1)

    # Join Blue + Red por gameid
    red_sub = red[["gameid", "pick1", "pick2", "pick3", "pick4", "pick5"]].copy()
    red_sub = red_sub.rename(columns={c: f"red_{c}" for c in ["pick1", "pick2", "pick3", "pick4", "pick5"]})
    merged = blue.merge(red_sub, on="gameid", how="left")

    records = []
    for _, row in merged.iterrows():
        gameid = row["gameid"]
        gamelength_sec = row.get("gamelength", 0)
        if pd.isna(gamelength_sec):
            continue
        duration_min = gamelength_sec / 60
        teamkills = row.get("teamkills", 0) or 0
        teamdeaths = row.get("teamdeaths", 0) or 0
        total_final = int(teamkills) + int(teamdeaths)

        blue_picks = [
            row.get("pick1"), row.get("pick2"), row.get("pick3"), row.get("pick4"), row.get("pick5")
        ]
        red_picks = [
            row.get("red_pick1"), row.get("red_pick2"), row.get("red_pick3"), row.get("red_pick4"), row.get("red_pick5")
        ]
        blue_picks = [p for p in blue_picks if pd.notna(p) and str(p).strip()]
        red_picks = [p for p in red_picks if pd.notna(p) and str(p).strip()]

        # Colunas por checkpoint
        col_map = {
            10: ("killsat10", "opp_killsat10", "golddiffat10"),
            15: ("killsat15", "opp_killsat15", "golddiffat15"),
            20: ("killsat20", "opp_killsat20", "golddiffat20"),
            25: ("killsat25", "opp_killsat25", "golddiffat25"),
        }

        for minute in CHECKPOINTS:
            if duration_min < minute:
                continue
            k_col, ok_col, g_col = col_map[minute]
            kills_blue = row.get(k_col, 0)
            kills_red = row.get(ok_col, 0)
            if pd.isna(kills_blue):
                kills_blue = 0
            if pd.isna(kills_red):
                kills_red = 0
            kills_now = int(kills_blue) + int(kills_red)
            gold_val = float(row.get(g_col, 0) or 0)

            kpm_now = kills_now / minute if minute > 0 else 0
            gold_per_min = gold_val / max(1, minute)
            gold_log = math.copysign(math.log1p(abs(gold_val)), gold_val) if gold_val != 0 else 0.0
            gold_pressure = abs(gold_val) / max(1, minute)
            stomp_intensity = max(0.0, gold_pressure - 250)
            slow_intensity = max(0.0, 0.33 - kpm_now)

            draft = _draft_impacts_weighted(blue_picks, red_picks, impacts, minute)
            kills_remaining = total_final - kills_now

            league = (row.get("league") or "").strip().upper()
            records.append({
                "gameid": gameid,
                "league": league,
                "minute": minute,
                "kills_remaining": kills_remaining,
                "kills_now": kills_now,
                "kpm_now": kpm_now,
                "gold_diff_now": gold_val,
                "gold_per_min": gold_per_min,
                "gold_log": gold_log,
                "stomp_intensity": stomp_intensity,
                "slow_intensity": slow_intensity,
                "draft_kills_impact_weighted": draft["kills"],
                "draft_duration_impact_weighted": draft["duration"],
                "draft_kpm_impact_weighted": draft["kpm"],
                "draft_conversion_impact_weighted": draft["conversion"],
            })

    out_df = pd.DataFrame(records)
    out_path = args.output or (PROJECT_ROOT / "data" / "lol_live_snapshots.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"Snapshots LoL: {len(out_df)} linhas -> {out_path}")
    return out_df


if __name__ == "__main__":
    main()
