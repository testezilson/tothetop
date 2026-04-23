#!/usr/bin/env python3
"""
Calcula métricas de campeões LoL e extrai impactos contínuos.

Métricas (espelhando o Dota):
  1. impact_kills: mean(total_kills | champion) - global_mean  [APENAS ligas MAJOR]
  2. impact_duration: mean(duration | champion) - mean(duration | ~champion)  [todas as ligas]
  3. impact_conversion: conversão de vantagem (WR quando à frente em gold aos 15 min)  [todas as ligas]
  4. impact_kpm: ritmo de kills acima/abaixo da média global  [APENAS ligas MAJOR]

Fonte: OraclesElixir CSV em C:\\Users\\Lucas\\Documents\\db2026 (fallback: data/ no projeto).

Uso:
  python scripts/compute_champion_metrics_lol.py
  python scripts/compute_champion_metrics_lol.py -o data/champion_impacts_lol.json
"""
# Ligas MAJOR para impact_kills e impact_kpm (TESTE LOL LIVE GAME)
MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB2026_LOL_CSV = Path(r"C:\Users\Lucas\Documents\db2026\2026_LoL_esports_match_data_from_OraclesElixir.csv")
FALLBACK_LOL_CSV = PROJECT_ROOT / "data" / "2026_LoL_esports_match_data_from_OraclesElixir.csv"
CSV_PATH = DB2026_LOL_CSV if DB2026_LOL_CSV.exists() else FALLBACK_LOL_CSV

GOLD_LEAD_THRESHOLD = 3000
MIN_MATCHES_PER_CHAMPION = 5
SHRINKAGE_K = 10
SHRINKAGE_K_DURATION = 15


def _apply_shrinkage(raw: float, n: int, k: int, toward: float = 0.0) -> float:
    """Shrinkage bayesiano: (n/(n+k))*raw + (k/(n+k))*toward."""
    if n >= k * 2:
        return raw
    weight = n / (n + k)
    return weight * raw + (1 - weight) * toward


def load_matches(csv_path: Path | None = None) -> list[dict]:
    """Carrega partidas do OraclesElixir (Blue + Red por gameid)."""
    path = csv_path or CSV_PATH
    if not path.exists():
        return []
    df = pd.read_csv(path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()

    blue = df[df["participantid"] == 100].copy()
    red = df[df["participantid"] == 200].copy()
    if blue.empty:
        return []

    red_sub = red[["gameid", "pick1", "pick2", "pick3", "pick4", "pick5"]].copy()
    red_sub = red_sub.rename(columns={
        "pick1": "red_pick1", "pick2": "red_pick2", "pick3": "red_pick3",
        "pick4": "red_pick4", "pick5": "red_pick5"
    })
    merged = blue.merge(red_sub, on="gameid", how="inner")

    matches = []
    for _, row in merged.iterrows():
        gamelength = row.get("gamelength")
        if pd.isna(gamelength) or gamelength < 600:
            continue
        teamkills = int(row.get("teamkills") or 0)
        teamdeaths = int(row.get("teamdeaths") or 0)
        total_kills = teamkills + teamdeaths
        blue_won = int(row.get("result", 0)) == 1

        gold_15 = row.get("golddiffat15")
        if pd.isna(gold_15):
            gold_15 = 0
        gold_15 = float(gold_15)

        blue_champs = [row.get("pick1"), row.get("pick2"), row.get("pick3"), row.get("pick4"), row.get("pick5")]
        red_champs = [row.get("red_pick1"), row.get("red_pick2"), row.get("red_pick3"), row.get("red_pick4"), row.get("red_pick5")]
        blue_champs = [str(c).strip() for c in blue_champs if pd.notna(c) and str(c).strip()]
        red_champs = [str(c).strip() for c in red_champs if pd.notna(c) and str(c).strip()]
        if len(blue_champs) < 5 or len(red_champs) < 5:
            continue

        league = (row.get("league") or "").strip().upper()
        matches.append({
            "gameid": row["gameid"],
            "league": league,
            "duration": gamelength,
            "blue_won": blue_won,
            "total_kills": total_kills,
            "gold_diff_15": gold_15,
            "blue_champions": blue_champs,
            "red_champions": red_champs,
        })
    return matches


def metric0_kills_impact(matches: list[dict]) -> dict[str, dict]:
    """impact_kills: mean(total_kills | champion) - global_mean."""
    all_kills = [m["total_kills"] for m in matches]
    global_mean = np.mean(all_kills)
    champ_kills: dict[str, list[int]] = {}
    for m in matches:
        champs = m["blue_champions"] + m["red_champions"]
        total = m["total_kills"]
        for c in champs:
            champ_kills.setdefault(c, []).append(total)
    out = {}
    for champ, kills in champ_kills.items():
        if len(kills) < MIN_MATCHES_PER_CHAMPION:
            continue
        imp = np.mean(kills) - global_mean
        imp = _apply_shrinkage(imp, len(kills), SHRINKAGE_K_DURATION, toward=0.0)
        out[champ] = {
            "impact_kills": round(imp, 4),
            "mean_kills_with": round(np.mean(kills), 2),
            "global_mean_kills": round(global_mean, 2),
            "n_matches": len(kills),
        }
    return out


def metric1_duration_on_wins(matches: list[dict]) -> dict[str, dict]:
    """Duração média em vitórias por campeão (para referência)."""
    global_duration = np.mean([m["duration"] for m in matches])
    champ_wins: dict[str, list[float]] = {}
    for m in matches:
        blue_won = m["blue_won"]
        for i, c in enumerate(m["blue_champions"] + m["red_champions"]):
            is_blue = i < 5
            won = blue_won if is_blue else (not blue_won)
            if won:
                champ_wins.setdefault(c, []).append(m["duration"])
    out = {}
    for champ, durs in champ_wins.items():
        if len(durs) < MIN_MATCHES_PER_CHAMPION:
            continue
        mean_dur = np.mean(durs)
        diff = mean_dur - global_duration
        out[champ] = {
            "mean_duration_sec": round(mean_dur, 1),
            "mean_duration_min": round(mean_dur / 60, 2),
            "diff_min": round(diff / 60, 2),
            "n_wins": len(durs),
        }
    return out


def metric2_advantage_conversion(matches: list[dict]) -> dict[str, dict]:
    """Conversão de vantagem: WR quando time está à frente em gold aos 15 min."""
    k = SHRINKAGE_K
    champ_lead_wins: dict[str, list[bool]] = {}
    global_lead_wins: list[bool] = []
    for m in matches:
        gold_15 = m["gold_diff_15"]
        blue_won = m["blue_won"]
        for i, c in enumerate(m["blue_champions"] + m["red_champions"]):
            is_blue = i < 5
            team_ahead = (gold_15 > GOLD_LEAD_THRESHOLD and is_blue) or (gold_15 < -GOLD_LEAD_THRESHOLD and not is_blue)
            if team_ahead:
                won = blue_won if is_blue else (not blue_won)
                champ_lead_wins.setdefault(c, []).append(won)
                global_lead_wins.append(won)
    global_wr = np.mean(global_lead_wins) if global_lead_wins else 0.5
    out = {}
    for champ, wins in champ_lead_wins.items():
        n = len(wins)
        if n < MIN_MATCHES_PER_CHAMPION:
            continue
        wr_raw = np.mean(wins)
        weight = n / (n + k)
        wr_adj = weight * wr_raw + (1 - weight) * global_wr
        out[champ] = {
            "impact_conversion": round(wr_adj - global_wr, 4),
            "win_rate_leading_raw": round(wr_raw, 4),
            "n_games_leading": n,
        }
    return out


def metric3_kill_pace(matches: list[dict]) -> dict[str, dict]:
    """impact_kpm: KPM do jogo quando o campeão está presente vs média global."""
    champ_kpm: dict[str, list[float]] = {}
    for m in matches:
        duration_min = m["duration"] / 60
        kpm = m["total_kills"] / duration_min if duration_min > 0 else 0
        for c in m["blue_champions"] + m["red_champions"]:
            champ_kpm.setdefault(c, []).append(kpm)
    all_kpm = [k for v in champ_kpm.values() for k in v]
    global_kpm = np.mean(all_kpm) if all_kpm else 1.0
    out = {}
    for champ, kpms in champ_kpm.items():
        if len(kpms) < MIN_MATCHES_PER_CHAMPION:
            continue
        kpm_mean = np.mean(kpms)
        impact_kpm = (kpm_mean - global_kpm) / max(global_kpm, 0.01)
        out[champ] = {
            "impact_kpm": round(impact_kpm, 4),
            "kpm_global": round(kpm_mean, 4),
            "n_matches": len(kpms),
        }
    return out


def metric4_duration_impact(matches: list[dict]) -> dict[str, dict]:
    """impact_duration: mean(duration | champion) - mean(duration | ~champion) em minutos."""
    rows = []
    for m in matches:
        champs = set(m["blue_champions"] + m["red_champions"])
        rows.append({"duration": m["duration"], "champions": champs})
    all_durations = [r["duration"] for r in rows]
    global_mean = np.mean(all_durations)
    champ_with: dict[str, list[int]] = {}
    champ_without: dict[str, list[int]] = {}
    all_champs = set()
    for r in rows:
        all_champs |= r["champions"]
    for c in all_champs:
        for r in rows:
            if c in r["champions"]:
                champ_with.setdefault(c, []).append(r["duration"])
            else:
                champ_without.setdefault(c, []).append(r["duration"])
    out = {}
    for champ in all_champs:
        durs_with = champ_with.get(champ, [])
        if len(durs_with) < MIN_MATCHES_PER_CHAMPION:
            continue
        mean_with = np.mean(durs_with)
        durs_without = champ_without.get(champ, [])
        mean_without = np.mean(durs_without) if durs_without else global_mean
        impact_min = (mean_with - mean_without) / 60
        out[champ] = {
            "impact_duration_min": round(impact_min, 3),
            "mean_duration_with_sec": round(mean_with, 1),
            "n_matches": len(durs_with),
        }
    return out


def _build_champion_impacts(m0, m1, m2, m3, m4) -> dict[str, dict]:
    """Agrega métricas por campeão (output final)."""
    all_champs = set(m0) | set(m1) | set(m2) | set(m3) | set(m4)
    out = {}
    for champ in all_champs:
        imp_kills = m0[champ]["impact_kills"] if champ in m0 else 0.0
        imp_dur = m4[champ]["impact_duration_min"] if champ in m4 else 0.0
        imp_conv = m2[champ]["impact_conversion"] if champ in m2 else 0.0
        imp_kpm = m3[champ]["impact_kpm"] if champ in m3 else 0.0
        n = max(
            m0.get(champ, {}).get("n_matches", 0),
            m4.get(champ, {}).get("n_matches", 0),
            m2.get(champ, {}).get("n_games_leading", 0),
            m3.get(champ, {}).get("n_matches", 0),
        )
        if n < MIN_MATCHES_PER_CHAMPION:
            imp_kills = imp_dur = imp_conv = imp_kpm = 0.0
        else:
            imp_kills = _apply_shrinkage(imp_kills, n, SHRINKAGE_K_DURATION, 0.0) if champ in m0 else 0.0
            imp_dur = _apply_shrinkage(imp_dur, n, SHRINKAGE_K_DURATION, 0.0) if champ in m4 else 0.0
            imp_conv = imp_conv if champ in m2 else 0.0
            imp_kpm = _apply_shrinkage(imp_kpm, n, SHRINKAGE_K_DURATION, 0.0) if champ in m3 else 0.0

        out[champ] = {
            "impact_kills": round(imp_kills, 4),
            "impact_duration": round(imp_dur, 4),
            "impact_conversion": round(imp_conv, 4),
            "impact_kpm": round(imp_kpm, 4),
            "n_matches": n,
        }
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Calcula métricas e impactos de campeões LoL")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Salvar JSON com resultados")
    parser.add_argument("--csv", type=Path, default=CSV_PATH, help="Caminho do OraclesElixir CSV")
    args = parser.parse_args()

    matches = load_matches(args.csv)

    if not matches:
        print("Erro: nenhuma partida encontrada. Verifique o CSV OraclesElixir.")
        sys.exit(1)

    print(f"Partidas carregadas: {len(matches)}")
    matches_major = [m for m in matches if m.get("league") in MAJOR_LEAGUES]
    print(f"Partidas MAJOR (para impact_kills e impact_kpm): {len(matches_major)}")
    champs = set()
    for m in matches:
        champs |= set(m["blue_champions"] + m["red_champions"])
    print(f"Campeões únicos: {len(champs)}")
    print()

    # impact_kills e impact_kpm: apenas ligas MAJOR
    m0 = metric0_kills_impact(matches_major) if matches_major else {}
    m3 = metric3_kill_pace(matches_major) if matches_major else {}
    # duration, conversion: todas as ligas
    m1 = metric1_duration_on_wins(matches)
    m2 = metric2_advantage_conversion(matches)
    m4 = metric4_duration_impact(matches)

    champion_impacts = _build_champion_impacts(m0, m1, m2, m3, m4)

    result = {
        "n_matches": len(matches),
        "champion_impacts": champion_impacts,
        "metric0_kills_impact": m0,
        "metric1_duration_on_wins": m1,
        "metric2_advantage_conversion": m2,
        "metric3_kill_pace": m3,
        "metric4_duration_impact": m4,
    }

    print("=" * 60)
    print("IMPACTOS CONTÍNUOS DE CAMPEÕES LOL")
    print("=" * 60)
    print()
    valid_dur = [(c, v) for c, v in champion_impacts.items() if v.get("impact_duration") is not None]
    by_dur = sorted(valid_dur, key=lambda x: x[1]["impact_duration"])
    print("Top 10 que REDUZEM duração (impact_duration < 0):")
    for c, v in by_dur[:10]:
        print(f"  {c}: {v['impact_duration']} min")
    print()
    print("Top 10 que AUMENTAM duração (impact_duration > 0):")
    for c, v in reversed(by_dur[-10:]):
        print(f"  {c}: {v['impact_duration']} min")
    print()
    valid_conv = [(c, v) for c, v in champion_impacts.items() if v["impact_conversion"] is not None]
    by_conv = sorted(valid_conv, key=lambda x: x[1]["impact_conversion"], reverse=True)
    print("Top 10 conversão de vantagem (impact_conversion):")
    for c, v in by_conv[:10]:
        print(f"  {c}: {v['impact_conversion']}")
    print()
    valid_kpm = [(c, v) for c, v in champion_impacts.items() if v["impact_kpm"] is not None]
    by_kpm = sorted(valid_kpm, key=lambda x: x[1]["impact_kpm"], reverse=True)
    print("Top 10 KPM acima da média (impact_kpm):")
    for c, v in by_kpm[:10]:
        print(f"  {c}: {v['impact_kpm']}")
    print()

    if args.output:
        out_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Resultados salvos em: {out_path}")

    return result


if __name__ == "__main__":
    main()
