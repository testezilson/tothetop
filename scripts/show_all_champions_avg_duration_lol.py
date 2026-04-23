#!/usr/bin/env python3
"""
Média de tempo de jogo por campeão LoL (todos), em ordem alfabética.

Fonte padrão: C:\\Users\\Lucas\\Documents\\db2026\\2026_LoL_esports_match_data_from_OraclesElixir.csv
(se não existir, usa data/2026_LoL_esports_match_data_from_OraclesElixir.csv no projeto — igual ao compute_champion_metrics_lol).

(o oracle_prepared.csv do histórico não contém gamelength)

Duração: coluna gamelength em segundos; exibição em minutos.
Cada partida conta uma vez por campeão presente (blue + red).

Uso:
  python scripts/show_all_champions_avg_duration_lol.py
  python scripts/show_all_champions_avg_duration_lol.py --min-matches 10
  python scripts/show_all_champions_avg_duration_lol.py --db-dir "C:\\Users\\Lucas\\Documents\\db2026"
  python scripts/show_all_champions_avg_duration_lol.py --csv data/outro.csv
  python scripts/show_all_champions_avg_duration_lol.py --output-csv data/champion_avg_duration_lol.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

ORACLE_CSV_NAME = "2026_LoL_esports_match_data_from_OraclesElixir.csv"

from compute_champion_metrics_lol import CSV_PATH, load_matches


def compute_avg_duration_by_champion(matches: list[dict]) -> list[tuple[str, float, int]]:
    champ_dur: dict[str, list[float]] = defaultdict(list)
    for m in matches:
        dur = float(m["duration"])
        for c in m["blue_champions"] + m["red_champions"]:
            champ_dur[c].append(dur)
    rows = []
    for champ, durs in champ_dur.items():
        n = len(durs)
        avg_sec = sum(durs) / n
        rows.append((champ, avg_sec / 60.0, n))
    rows.sort(key=lambda x: x[0].casefold())
    return rows


def write_csv(path: Path, rows: list[tuple[str, float, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["champion", "avg_duration_min", "matches"])
        for champ, avg_min, n in rows:
            w.writerow([champ, round(avg_min, 3), n])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Média de tempo por campeão LoL (ordem alfabética)"
    )
    parser.add_argument(
        "--db-dir",
        type=Path,
        default=None,
        help=f"Pasta com o CSV OraclesElixir (usa {ORACLE_CSV_NAME} dentro dela)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Caminho completo do CSV OraclesElixir (sobrepõe --db-dir)",
    )
    parser.add_argument("--min-matches", type=int, default=1, help="Mínimo de partidas por campeão")
    parser.add_argument("--output-csv", type=Path, default=None, help="Salvar resultado em CSV")
    args = parser.parse_args()

    if args.csv is not None:
        csv_path = args.csv if args.csv.is_absolute() else (PROJECT_ROOT / args.csv)
    elif args.db_dir is not None:
        base = args.db_dir if args.db_dir.is_absolute() else (PROJECT_ROOT / args.db_dir)
        csv_path = base / ORACLE_CSV_NAME
    else:
        csv_path = CSV_PATH
        if not csv_path.is_absolute():
            csv_path = PROJECT_ROOT / csv_path
    if not csv_path.exists():
        print(f"ERRO: arquivo não encontrado: {csv_path}")
        return 1
    if args.min_matches < 1:
        print("ERRO: --min-matches precisa ser >= 1")
        return 1

    matches = load_matches(csv_path)
    if not matches:
        print("ERRO: nenhuma partida válida (verifique o CSV e picks completos).")
        return 1

    rows = compute_avg_duration_by_champion(matches)
    rows = [r for r in rows if r[2] >= args.min_matches]

    print("=" * 72)
    print("LoL — MÉDIA DE TEMPO POR CAMPEÃO (ordem alfabética)")
    print("=" * 72)
    print(f"Fonte: {csv_path}")
    print(f"Partidas carregadas: {len(matches)}")
    print(f"Campeões listados: {len(rows)} (min_matches={args.min_matches})")
    print()
    print(f"{'#':<5} {'Campeão':<28} {'Média (min)':>12} {'Partidas':>10}")
    print("-" * 72)
    for i, (champ, avg_min, n) in enumerate(rows, 1):
        print(f"{i:<5} {champ:<28} {avg_min:>12.2f} {n:>10}")
    print("-" * 72)

    if args.output_csv:
        out = args.output_csv if args.output_csv.is_absolute() else (PROJECT_ROOT / args.output_csv)
        write_csv(out, rows)
        print(f"CSV salvo em: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
