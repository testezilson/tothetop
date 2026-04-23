#!/usr/bin/env python3
"""
Monta o dataset dota_live_snapshots para treino do modelo Live.

Uma linha por (match_id, minute) para checkpoints 10, 15, 20, 25 min.
Target: kills_remaining = total_kills_final - kills_até_t

Uso:
  python scripts/dota_live/build_snapshots.py
  python scripts/dota_live/build_snapshots.py --db data/dota_opendota_leagues.db --output data/dota_live_snapshots.csv
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dota_opendota_leagues.db"
HERO_IMPACTS_PATH = PROJECT_ROOT / "data" / "hero_impacts.json"
CHECKPOINTS = [10, 15, 20, 25]
DRAFT_WEIGHT_MAX_MIN = 40  # draft_weight = max(0, 1 - minute/40)


def _kills_at_minute_from_kills_log(players_kills_log: list, cutoff_sec: int) -> int | None:
    """
    Soma kills até cutoff_sec via kills_log por jogador.
    players_kills_log: list de 10 listas [[t1,t2,...], ...] em ordem de slot.
    Retorna total ou None se dados inválidos.
    """
    if not players_kills_log or len(players_kills_log) < 10:
        return None
    total = 0
    for times in players_kills_log[:10]:
        for t in times:
            if t is not None and t <= cutoff_sec:
                total += 1
    return total


def _kills_at_minute_teamfights(teamfights: list, cutoff_sec: int) -> int:
    """Fallback: soma deaths em teamfights. SUBCONTA (não inclui pickoffs)."""
    if not teamfights:
        return 0
    total = 0
    for tf in teamfights:
        start = tf.get("start")
        deaths = tf.get("deaths", 0)
        if start is not None and start <= cutoff_sec and deaths is not None:
            total += deaths
    return total


def _towers_alive(objectives: list, cutoff_sec: int) -> tuple[int, int]:
    """Retorna (towers_r_alive, towers_d_alive) no minuto. Inicial: 11 cada."""
    r_down = 0
    d_down = 0
    for obj in objectives or []:
        if obj.get("type") != "building_kill":
            continue
        t = obj.get("time")
        if t is None or t > cutoff_sec:
            continue
        key = str(obj.get("key", ""))
        if "tower" not in key.lower():
            continue
        if "goodguys" in key:
            r_down += 1
        elif "badguys" in key:
            d_down += 1
    return (11 - r_down, 11 - d_down)


def _roshan_kills_so_far(objectives: list, cutoff_sec: int) -> int:
    """Conta Roshan kills até cutoff_sec."""
    count = 0
    for obj in objectives or []:
        if obj.get("type") == "CHAT_MESSAGE_ROSHAN_KILL":
            t = obj.get("time")
            if t is not None and t <= cutoff_sec:
                count += 1
    return count


def _draft_impacts(heroes: list, impacts: dict) -> dict:
    """Soma impactos do draft (10 heróis). Herói sem métrica → 0."""
    out = {"kills": 0.0, "duration": 0.0, "kpm": 0.0, "conversion": 0.0}
    for h in (heroes or [])[:10]:
        name = str(h).strip() if h else ""
        data = impacts.get(name, {})
        out["kills"] += data.get("impact_kills", 0) or 0
        out["duration"] += data.get("impact_duration", 0) or 0
        out["kpm"] += data.get("impact_kpm", 0) or 0
        out["conversion"] += data.get("impact_conversion", 0) or 0
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument("--impacts", type=Path, default=HERO_IMPACTS_PATH)
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Erro: banco não encontrado: {args.db}")
        sys.exit(1)
    if not args.impacts.exists():
        print(f"Erro: hero_impacts.json não encontrado: {args.impacts}")
        sys.exit(1)

    with open(args.impacts, encoding="utf-8") as f:
        data = json.load(f)
    hero_impacts = data.get("hero_impacts", data)

    conn = sqlite3.connect(args.db)
    try:
        conn.execute("ALTER TABLE dota_matches_stratz ADD COLUMN players_kills_log TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate" not in str(e).lower():
            pass
    cur = conn.execute("""
        SELECT match_id, duration, radiant_kills, dire_kills,
               heroes, radiant_gold_adv, teamfights, objectives,
               COALESCE(players_kills_log, '') as players_kills_log
        FROM dota_matches_stratz
        WHERE duration > 600 AND heroes IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()

    records = []
    n_kills_log = 0
    n_teamfights = 0
    n_fallback = 0
    for r in rows:
        match_id, duration, r_k, d_k, heroes_json, gold_adv_json, tf_json, obj_json, pkl_json = (
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8] if len(r) > 8 else None
        )
        radiant_kills = r_k or 0
        dire_kills = d_k or 0
        total_final = radiant_kills + dire_kills
        heroes = json.loads(heroes_json) if heroes_json else []
        gold_adv = json.loads(gold_adv_json) if gold_adv_json else []
        teamfights = json.loads(tf_json) if tf_json else []
        objectives = json.loads(obj_json) if obj_json else []
        players_kills_log = json.loads(pkl_json) if pkl_json and pkl_json.strip() else None

        draft = _draft_impacts(heroes, hero_impacts)
        duration_min = duration / 60

        for minute in CHECKPOINTS:
            if duration_min < minute:
                continue
            cutoff_sec = minute * 60
            kills_now = _kills_at_minute_from_kills_log(players_kills_log, cutoff_sec)
            if kills_now is not None:
                n_kills_log += 1
            else:
                kills_now = _kills_at_minute_teamfights(teamfights, cutoff_sec)
                if kills_now > 0:
                    n_teamfights += 1
                else:
                    kpm_est = total_final / duration_min if duration_min > 0 else 0
                    kills_now = int(kpm_est * minute)
                    n_fallback += 1
            kpm_now = kills_now / minute if minute > 0 else 0
            gold_val = gold_adv[minute] if len(gold_adv) > minute and isinstance(gold_adv[minute], (int, float)) else 0
            # Gold contextual: per_min, log, stomp_intensity (regime terminal)
            gold_per_min = gold_val / max(1, minute)
            gold_log = math.copysign(math.log1p(abs(gold_val)), gold_val) if gold_val != 0 else 0.0
            gold_pressure = abs(gold_val) / max(1, minute)
            stomp_intensity = max(0.0, gold_pressure - 250)  # kink em ~250 gold/min (jogo decidido)
            towers_r, towers_d = _towers_alive(objectives, cutoff_sec)
            roshan = _roshan_kills_so_far(objectives, cutoff_sec)
            kills_remaining = total_final - kills_now

            weight = max(0.0, 1.0 - minute / DRAFT_WEIGHT_MAX_MIN)
            draft_kills_w = draft["kills"] * weight
            draft_duration_w = draft["duration"] * weight
            draft_kpm_w = draft["kpm"] * weight
            draft_conversion_w = draft["conversion"] * weight

            records.append({
                "match_id": match_id,
                "minute": minute,
                "kills_remaining": kills_remaining,
                "kills_now": kills_now,
                "kpm_now": kpm_now,
                "gold_diff_now": gold_val,
                "gold_per_min": gold_per_min,
                "gold_log": gold_log,
                "stomp_intensity": stomp_intensity,
                "towers_r_alive": towers_r,
                "towers_d_alive": towers_d,
                "towers_total_alive": towers_r + towers_d,
                "roshan_kills_so_far": roshan,
                "draft_kills_impact": draft["kills"],
                "draft_duration_impact": draft["duration"],
                "draft_kpm_impact": draft["kpm"],
                "draft_conversion_impact": draft["conversion"],
                "draft_kills_impact_weighted": draft_kills_w,
                "draft_duration_impact_weighted": draft_duration_w,
                "draft_kpm_impact_weighted": draft_kpm_w,
                "draft_conversion_impact_weighted": draft_conversion_w,
            })

    df = pd.DataFrame(records)
    out_path = args.output or (PROJECT_ROOT / "data" / "dota_live_snapshots.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Snapshots: {len(df)} linhas -> {out_path}")
    print(f"  kills_now: kills_log={n_kills_log}, teamfights={n_teamfights}, fallback_kpm={n_fallback}")
    return df


if __name__ == "__main__":
    main()
