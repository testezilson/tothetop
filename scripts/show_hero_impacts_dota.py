#!/usr/bin/env python3
"""
Lista todos os heróis Dota 2 com tempo médio e impactos.

Lê data/hero_impacts.json e exibe:
- Tempo médio (min) em vitórias (metric1_duration_on_wins)
- impact_kills, impact_duration, impact_conversion, impact_kpm
- n_matches

Uso:
  python scripts/show_hero_impacts_dota.py
  python scripts/show_hero_impacts_dota.py --output hero_list.csv
  python scripts/show_hero_impacts_dota.py --sort kills  (ou duration, conversion, kpm, tempo)
"""
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
HERO_IMPACTS_PATH = PROJECT_ROOT / "data" / "hero_impacts.json"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Lista heróis Dota com tempo médio e impactos")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Salvar CSV")
    parser.add_argument("--sort", choices=["name", "tempo", "kills", "duration", "conversion", "kpm", "n"],
                        default="name", help="Ordenar por")
    parser.add_argument("--impacts", type=Path, default=HERO_IMPACTS_PATH)
    args = parser.parse_args()

    if not args.impacts.exists():
        print(f"Erro: {args.impacts} não encontrado. Rode compute_hero_metrics_dota.py primeiro.")
        sys.exit(1)

    with open(args.impacts, encoding="utf-8") as f:
        data = json.load(f)

    hero_impacts = data.get("hero_impacts", data)
    m1 = data.get("metric1_duration_on_wins", {})

    rows = []
    for hero, hi in hero_impacts.items():
        tempo_min = m1.get(hero, {}).get("mean_duration_min")
        if tempo_min is None and hero in m1:
            tempo_min = m1[hero].get("mean_duration_sec", 0) / 60 if m1[hero].get("mean_duration_sec") else None
        rows.append({
            "hero": hero,
            "tempo_medio_min": tempo_min,
            "impact_kills": hi.get("impact_kills"),
            "impact_duration": hi.get("impact_duration"),
            "impact_conversion": hi.get("impact_conversion"),
            "impact_kpm": hi.get("impact_kpm"),
            "n_matches": hi.get("n_matches", 0),
        })

    sort_key = args.sort
    if sort_key == "name":
        rows.sort(key=lambda r: (r["hero"] or "").lower())
    elif sort_key == "tempo":
        rows.sort(key=lambda r: (r["tempo_medio_min"] is not None, r["tempo_medio_min"] or 0), reverse=True)
    elif sort_key == "kills":
        rows.sort(key=lambda r: (r["impact_kills"] or 0), reverse=True)
    elif sort_key == "duration":
        rows.sort(key=lambda r: (r["impact_duration"] or 0), reverse=True)
    elif sort_key == "conversion":
        rows.sort(key=lambda r: (r["impact_conversion"] or 0), reverse=True)
    elif sort_key == "kpm":
        rows.sort(key=lambda r: (r["impact_kpm"] or 0), reverse=True)
    elif sort_key == "n":
        rows.sort(key=lambda r: (r["n_matches"] or 0), reverse=True)

    n_matches_total = data.get("n_matches", 0)
    print("=" * 100)
    print(f"Heróis Dota 2 — tempo médio e impactos (n_matches base: {n_matches_total})")
    print("=" * 100)
    print(f"{'Herói':<25} {'Tempo min':>10} {'impact_kills':>12} {'impact_dur':>12} {'impact_conv':>12} {'impact_kpm':>12} {'n':>6}")
    print("-" * 100)

    for r in rows:
        tempo = f"{r['tempo_medio_min']:.1f}" if r["tempo_medio_min"] is not None else "-"
        ik = r["impact_kills"]
        id_ = r["impact_duration"]
        ic = r["impact_conversion"]
        ikpm = r["impact_kpm"]
        ik_s = f"{ik:.3f}" if ik is not None else "-"
        id_s = f"{id_:.3f}" if id_ is not None else "-"
        ic_s = f"{ic:.3f}" if ic is not None else "-"
        ikpm_s = f"{ikpm:.3f}" if ikpm is not None else "-"
        n = r["n_matches"] or 0
        print(f"{r['hero']:<25} {tempo:>10} {ik_s:>12} {id_s:>12} {ic_s:>12} {ikpm_s:>12} {n:>6}")

    print("-" * 100)
    print(f"Total: {len(rows)} heróis")
    print()
    print("Tempo médio = duração média (min) em vitórias com o herói")
    print("impact_* = desvio vs global (positivo = acima da média)")
    print()

    if args.output:
        out_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        import csv
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["hero", "tempo_medio_min", "impact_kills", "impact_duration",
                                              "impact_conversion", "impact_kpm", "n_matches"])
            w.writeheader()
            for r in rows:
                wr = {k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()}
                w.writerow(wr)
        print(f"Salvo em: {out_path}")


if __name__ == "__main__":
    main()
