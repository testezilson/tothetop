#!/usr/bin/env python3
"""
Calcula métricas de heróis Dota 2 e extrai impactos contínuos.

Métricas (corrigidas estatisticamente):
  1. impact_duration: duração média em vitórias (vs global)
  2. impact_conversion: conversão de vantagem com shrinkage bayesiano
  3. impact_kpm: ritmo de kills via teamfights (early vs late) quando disponível
  4. impact_duration_adj: mean(duration | hero) - mean(duration | ~hero) — sem regressão

Output: 4 números contínuos por herói (impact_kills, impact_duration, impact_conversion, impact_kpm).
impact_kills = mean(total_kills | hero) - global_mean — para draft_kills_impact no Live.
Sem classificação discreta.

Uso:
  python scripts/compute_hero_metrics_dota.py
  python scripts/compute_hero_metrics_dota.py --output data/hero_impacts.json
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "dota_opendota_leagues.db"
OPENDOTA_HEROES_URL = "https://api.opendota.com/api/heroes"

# Limiar de gold para "vantagem" em 15 min
GOLD_LEAD_THRESHOLD = 3000
MIN_MATCHES_PER_HERO = 5
SHRINKAGE_K = 10  # Prior strength para métrica 2 (conversion)
SHRINKAGE_K_DURATION = 15  # Shrinkage para duration/kpm quando n < 15
MIN_N_FOR_DRAFT = 1  # n=0 → desconhecido, impactos = 0

# Whitelist de heróis válidos (OpenDota). Fallback estático se API falhar.
_VALID_HEROES_FALLBACK = frozenset()  # Vazio = aceitar todos se API falhar


def fetch_valid_hero_names() -> frozenset[str]:
    """Carrega whitelist de nomes de heróis válidos do OpenDota. Garante mapping limpo."""
    try:
        r = requests.get(OPENDOTA_HEROES_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
        names = set()
        for h in data or []:
            ln = h.get("localized_name") or h.get("name")
            if ln:
                names.add(str(ln).strip())
        return frozenset(names)
    except Exception:
        return _VALID_HEROES_FALLBACK


def load_matches(conn: sqlite3.Connection) -> list[dict]:
    """Carrega todas as partidas do banco."""
    cur = conn.execute("""
        SELECT match_id, radiant_win, duration, radiant_kills, dire_kills,
               heroes, radiant_gold_adv, radiant_xp_adv, teamfights
        FROM dota_matches_stratz
        WHERE duration > 600 AND heroes IS NOT NULL
    """)
    rows = cur.fetchall()
    return [
        {
            "match_id": r[0],
            "radiant_win": bool(r[1]),
            "duration": r[2],
            "radiant_kills": r[3] or 0,
            "dire_kills": r[4] or 0,
            "heroes": json.loads(r[5]) if r[5] else [],
            "radiant_gold_adv": json.loads(r[6]) if r[6] else [],
            "radiant_xp_adv": json.loads(r[7]) if r[7] else [],
            "teamfights": json.loads(r[8]) if r[8] else [],
        }
        for r in rows
    ]


def _apply_shrinkage(raw: float, n: int, k: int, toward: float = 0.0) -> float:
    """Shrinkage bayesiano: (n/(n+k))*raw + (k/(n+k))*toward."""
    if n >= k * 2:
        return raw
    weight = n / (n + k)
    return weight * raw + (1 - weight) * toward


def metric0_kills_impact(matches: list[dict]) -> dict[str, dict]:
    """
    Impacto no total de kills: mean(total_kills | hero) - global_mean.
    Usado para draft_kills_impact no Live.
    """
    all_kills = [m["radiant_kills"] + m["dire_kills"] for m in matches]
    global_mean = np.mean(all_kills)
    hero_kills: dict[str, list[int]] = {}
    for m in matches:
        heroes = m.get("heroes") or []
        if len(heroes) < 10:
            continue
        total = m["radiant_kills"] + m["dire_kills"]
        for h in heroes:
            name = str(h).strip() if h else None
            if not name:
                continue
            hero_kills.setdefault(name, []).append(total)
    out = {}
    for hero, kills in hero_kills.items():
        if len(kills) < MIN_MATCHES_PER_HERO:
            continue
        imp = np.mean(kills) - global_mean
        imp = _apply_shrinkage(imp, len(kills), SHRINKAGE_K_DURATION, toward=0.0)
        out[hero] = {
            "impact_kills": round(imp, 4),
            "mean_kills_with": round(np.mean(kills), 2),
            "global_mean_kills": round(global_mean, 2),
            "n_matches": len(kills),
        }
    return out


def metric1_duration_on_wins(matches: list[dict]) -> dict[str, dict]:
    """
    Métrica 1: Duração média em vitórias por herói.
    Heróis com duração menor tendem a fechar jogos mais rápido.
    """
    global_duration_sec = np.mean([m["duration"] for m in matches])
    hero_wins: dict[str, list[int]] = {}
    for m in matches:
        heroes = m.get("heroes") or []
        if len(heroes) < 10:
            continue
        radiant_won = m["radiant_win"]
        for i, h in enumerate(heroes):
            name = str(h).strip() if h else None
            if not name:
                continue
            is_radiant = i < 5
            won = radiant_won if is_radiant else (not radiant_won)
            if won:
                hero_wins.setdefault(name, []).append(m["duration"])
    out = {}
    for hero, durs in hero_wins.items():
        if len(durs) < MIN_MATCHES_PER_HERO:
            continue
        mean_dur = np.mean(durs)
        diff = mean_dur - global_duration_sec
        out[hero] = {
            "mean_duration_sec": round(mean_dur, 1),
            "mean_duration_min": round(mean_dur / 60, 2),
            "global_mean_sec": round(global_duration_sec, 1),
            "diff_sec": round(diff, 1),
            "diff_min": round(diff / 60, 2),
            "n_wins": len(durs),
        }
    return out


def metric2_advantage_conversion(matches: list[dict]) -> dict[str, dict]:
    """
    Métrica 2: Conversão de vantagem com shrinkage bayesiano.
    adjusted = (n/(n+k)) * hero_wr + (k/(n+k)) * global_wr
    Evita heróis com 3 jogos virarem extremos.
    """
    gold_adv = GOLD_LEAD_THRESHOLD
    k = SHRINKAGE_K
    hero_lead_wins: dict[str, list[bool]] = {}
    global_lead_wins: list[bool] = []
    for m in matches:
        adv = m.get("radiant_gold_adv") or []
        if len(adv) <= 15:
            continue
        val_15 = adv[15] if isinstance(adv[15], (int, float)) else 0
        heroes = m.get("heroes") or []
        if len(heroes) < 10:
            continue
        radiant_won = m["radiant_win"]
        for i, h in enumerate(heroes):
            name = str(h).strip() if h else None
            if not name:
                continue
            is_radiant = i < 5
            team_ahead = (val_15 > gold_adv and is_radiant) or (val_15 < -gold_adv and not is_radiant)
            if team_ahead:
                hero_lead_wins.setdefault(name, []).append(radiant_won if is_radiant else (not radiant_won))
                global_lead_wins.append(radiant_won if is_radiant else (not radiant_won))
    global_wr = np.mean(global_lead_wins) if global_lead_wins else 0.5
    out = {}
    for hero, wins in hero_lead_wins.items():
        n = len(wins)
        wr_raw = np.mean(wins)
        weight = n / (n + k)
        wr_adj = weight * wr_raw + (1 - weight) * global_wr
        out[hero] = {
            "impact_conversion": round(wr_adj - global_wr, 4),
            "win_rate_leading_raw": round(wr_raw, 4),
            "win_rate_leading_shrunk": round(wr_adj, 4),
            "global_win_rate_leading": round(global_wr, 4),
            "n_games_leading": n,
        }
    return out


def _deaths_by_window(teamfights: list, cutoff_sec: int, duration_sec: int) -> tuple[int, int] | None:
    """
    Extrai deaths (kills) por janela a partir de teamfights.
    teamfight.start < cutoff → early; teamfight.start >= cutoff → late.
    Retorna (deaths_early, deaths_late) ou None se vazio.
    """
    if not teamfights:
        return None
    early = 0
    late = 0
    for tf in teamfights:
        start = tf.get("start")
        deaths = tf.get("deaths", 0)
        if start is None or deaths is None:
            continue
        if start < cutoff_sec:
            early += deaths
        else:
            late += deaths
    if early == 0 and late == 0:
        return None
    return (early, late)


def metric3_kill_pace(matches: list[dict]) -> dict[str, dict]:
    """
    Métrica 3: Ritmo de kills via teamfights (0-20 min vs 20-fim).
    Usa deaths em teamfights como proxy para ação. Quando sem teamfights, usa KPM global.
    """
    hero_kpm_early: dict[str, list[float]] = {}
    hero_kpm_late: dict[str, list[float]] = {}
    hero_kpm_global: dict[str, list[float]] = {}
    hero_has_teamfights: dict[str, int] = {}
    cutoff_sec = 20 * 60
    for m in matches:
        heroes = m.get("heroes") or []
        if len(heroes) < 10:
            continue
        duration_sec = m["duration"]
        total_kills = m["radiant_kills"] + m["dire_kills"]
        kpm_global = total_kills / (duration_sec / 60) if duration_sec > 0 else 0
        dw = _deaths_by_window(m.get("teamfights") or [], cutoff_sec, duration_sec)
        if dw is not None and (dw[0] > 0 or dw[1] > 0):
            early_d, late_d = dw
            mins_early = 20
            mins_late = max(0.1, (duration_sec / 60) - 20)
            kpm_early = early_d / mins_early
            kpm_late = late_d / mins_late if mins_late > 0 else 0
        else:
            kpm_early = kpm_global
            kpm_late = kpm_global
        for h in heroes:
            name = str(h).strip() if h else None
            if not name:
                continue
            hero_kpm_early.setdefault(name, []).append(kpm_early)
            hero_kpm_late.setdefault(name, []).append(kpm_late)
            hero_kpm_global.setdefault(name, []).append(kpm_global)
            if dw is not None and (dw[0] > 0 or dw[1] > 0):
                hero_has_teamfights[name] = hero_has_teamfights.get(name, 0) + 1
    out = {}
    global_kpm = np.mean([np.mean(v) for v in hero_kpm_global.values()]) if hero_kpm_global else 1.0
    for hero in set(hero_kpm_early) & set(hero_kpm_late):
        if len(hero_kpm_early[hero]) < MIN_MATCHES_PER_HERO:
            continue
        kpm_e = np.mean(hero_kpm_early[hero])
        kpm_l = np.mean(hero_kpm_late[hero])
        kpm_g = np.mean(hero_kpm_global[hero])
        ratio = kpm_e / max(1e-6, kpm_l) if kpm_l > 0 else 1.0
        # impact_kpm: quanto acima/abaixo da média global; ratio > 1 = mais early
        impact_kpm = (kpm_g - global_kpm) / max(global_kpm, 0.01)
        out[hero] = {
            "impact_kpm": round(impact_kpm, 4),
            "kpm_0_20": round(kpm_e, 4),
            "kpm_20_end": round(kpm_l, 4),
            "kpm_global": round(kpm_g, 4),
            "ratio_early_late": round(ratio, 4),
            "n_matches": len(hero_kpm_early[hero]),
            "n_with_teamfights": hero_has_teamfights.get(hero, 0),
        }
    return out


def metric4_duration_impact(matches: list[dict]) -> dict[str, dict]:
    """
    Métrica 4: Impacto na duração via mean_with - mean_without.
    impact = mean(duration | hero in match) - mean(duration | hero NOT in match)
    Sem regressão, sem colinearidade estrutural.
    """
    rows = []
    for m in matches:
        heroes = m.get("heroes") or []
        if len(heroes) < 10:
            continue
        rows.append({"duration": m["duration"], "heroes": set(str(h).strip() for h in heroes if h)})
    all_durations = [r["duration"] for r in rows]
    global_mean = np.mean(all_durations)
    hero_with: dict[str, list[int]] = {}
    hero_without: dict[str, list[int]] = {}
    all_heroes = set()
    for r in rows:
        for h in r["heroes"]:
            all_heroes.add(h)
    for h in all_heroes:
        for r in rows:
            if h in r["heroes"]:
                hero_with.setdefault(h, []).append(r["duration"])
            else:
                hero_without.setdefault(h, []).append(r["duration"])
    out = {}
    for hero in all_heroes:
        durs_with = hero_with.get(hero, [])
        if len(durs_with) < MIN_MATCHES_PER_HERO:
            continue
        mean_with = np.mean(durs_with)
        durs_without = hero_without.get(hero, [])
        mean_without = np.mean(durs_without) if durs_without else global_mean
        impact_min = (mean_with - mean_without) / 60
        out[hero] = {
            "impact_duration_min": round(impact_min, 3),
            "mean_duration_with_sec": round(mean_with, 1),
            "mean_duration_without_sec": round(mean_without, 1),
            "n_matches": len(durs_with),
        }
    return out


def _build_hero_impacts(
    m0: dict[str, dict],
    m1: dict[str, dict],
    m2: dict[str, dict],
    m3: dict[str, dict],
    m4: dict[str, dict],
    valid_heroes: frozenset[str],
) -> dict[str, dict]:
    """
    Agrega as 5 métricas contínuas por herói (output final).
    - impact_kills: m0 (total kills) — para draft Live
    - impact_duration: m4 com shrinkage quando n<15
    - impact_conversion: m2 com shrinkage
    - impact_kpm: m3 com shrinkage quando n<15
    - n=0 ou null → 0 (neutro) para draft seguro
    - Filtra heróis fora da whitelist OpenDota
    """
    k_dur = SHRINKAGE_K_DURATION
    all_heroes = set(m0) | set(m1) | set(m2) | set(m3) | set(m4)
    if valid_heroes:
        all_heroes = all_heroes & valid_heroes  # Só heróis na whitelist OpenDota
    # Se valid_heroes vazio (API falhou), mantém todos
    out = {}
    for hero in all_heroes:
        imp_kills = m0[hero]["impact_kills"] if hero in m0 else None
        imp_dur = m4[hero]["impact_duration_min"] if hero in m4 else None
        imp_conv = m2[hero]["impact_conversion"] if hero in m2 else None
        imp_kpm = m3[hero]["impact_kpm"] if hero in m3 else None
        n = 0
        if hero in m0:
            n = max(n, m0[hero]["n_matches"])
        if hero in m4:
            n = max(n, m4[hero]["n_matches"])
        if hero in m1:
            n = max(n, m1[hero].get("n_wins", 0))
        if hero in m3:
            n = max(n, m3[hero].get("n_matches", 0))
        if hero in m2:
            n = max(n, m2[hero].get("n_games_leading", 0))

        if n < MIN_N_FOR_DRAFT:
            imp_kills = imp_dur = imp_conv = imp_kpm = 0.0
        else:
            if imp_kills is not None:
                imp_kills = _apply_shrinkage(imp_kills, n, k_dur, toward=0.0)
            else:
                imp_kills = 0.0
            if imp_dur is not None:
                imp_dur = _apply_shrinkage(imp_dur, n, k_dur, toward=0.0)
            else:
                imp_dur = 0.0
            if imp_conv is not None:
                pass
            else:
                imp_conv = 0.0
            if imp_kpm is not None:
                imp_kpm = _apply_shrinkage(imp_kpm, n, k_dur, toward=0.0)
            else:
                imp_kpm = 0.0

        out[hero] = {
            "impact_kills": round(imp_kills, 4),
            "impact_duration": round(imp_dur, 4),
            "impact_conversion": round(imp_conv, 4),
            "impact_kpm": round(imp_kpm, 4),
            "n_matches": n,
        }
    # Inclui heróis válidos sem dados (draft lookup seguro)
    if valid_heroes:
        for h in valid_heroes:
            if h not in out:
                out[h] = {
                    "impact_kills": 0.0,
                    "impact_duration": 0.0,
                    "impact_conversion": 0.0,
                    "impact_kpm": 0.0,
                    "n_matches": 0,
                }
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Calcula métricas e classifica heróis Dota 2")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Salvar JSON com resultados")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Caminho do banco")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Erro: banco não encontrado: {args.db}")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    matches = load_matches(conn)
    conn.close()

    if not matches:
        print("Nenhuma partida encontrada no banco.")
        sys.exit(1)

    print(f"Partidas carregadas: {len(matches)}")
    print()

    valid_heroes = fetch_valid_hero_names()
    if valid_heroes:
        print(f"Whitelist OpenDota: {len(valid_heroes)} heróis")
    else:
        print("Whitelist OpenDota: indisponível, aceitando todos os nomes")
    print()

    m0 = metric0_kills_impact(matches)
    m1 = metric1_duration_on_wins(matches)
    m2 = metric2_advantage_conversion(matches)
    m3 = metric3_kill_pace(matches)
    m4 = metric4_duration_impact(matches)

    hero_impacts = _build_hero_impacts(m0, m1, m2, m3, m4, valid_heroes)

    result = {
        "n_matches": len(matches),
        "hero_impacts": hero_impacts,
        "metric0_kills_impact": m0,
        "metric1_duration_on_wins": m1,
        "metric2_advantage_conversion": m2,
        "metric3_kill_pace": m3,
        "metric4_duration_impact": m4,
    }

    print("=" * 60)
    print("IMPACTOS CONTÍNUOS DE HERÓIS DOTA 2")
    print("=" * 60)
    print()
    valid = [(h, v) for h, v in hero_impacts.items() if v.get("impact_duration") is not None]
    by_dur = sorted(valid, key=lambda x: x[1]["impact_duration"])
    print("Top 10 que REDUZEM duração (impact_duration < 0):")
    for h, v in by_dur[:10]:
        print(f"  {h}: {v['impact_duration']} min")
    print()
    print("Top 10 que AUMENTAM duração (impact_duration > 0):")
    for h, v in reversed(by_dur[-10:]):
        print(f"  {h}: {v['impact_duration']} min")
    print()
    valid_conv = [(h, v) for h, v in hero_impacts.items() if v["impact_conversion"] is not None]
    by_conv = sorted(valid_conv, key=lambda x: x[1]["impact_conversion"], reverse=True)
    print("Top 10 conversão de vantagem (impact_conversion):")
    for h, v in by_conv[:10]:
        print(f"  {h}: {v['impact_conversion']}")
    print()
    valid_kpm = [(h, v) for h, v in hero_impacts.items() if v["impact_kpm"] is not None]
    by_kpm = sorted(valid_kpm, key=lambda x: x[1]["impact_kpm"], reverse=True)
    print("Top 10 KPM acima da média (impact_kpm):")
    for h, v in by_kpm[:10]:
        print(f"  {h}: {v['impact_kpm']}")
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
