#!/usr/bin/env python3
"""
Mostra a media de duracao de partida para TODOS os herois de Dota da DB.

DB padrao:
  data/dota_opendota_leagues.db (tabela dota_matches_stratz)

Colunas suportadas de duracao:
  - duration_seconds
  - duration

Uso:
  python scripts/show_all_heroes_avg_duration_db.py
  python scripts/show_all_heroes_avg_duration_db.py --sort asc
  python scripts/show_all_heroes_avg_duration_db.py --min-matches 20
  python scripts/show_all_heroes_avg_duration_db.py --output-csv data/hero_avg_duration.csv
"""
import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "dota_opendota_leagues.db"


def parse_heroes(raw: str) -> list[str]:
    try:
        heroes = json.loads(raw)
    except Exception:
        return []
    if not isinstance(heroes, list):
        return []
    return [str(h).strip() for h in heroes if str(h).strip()]


def discover_duration_col(conn: sqlite3.Connection, table: str) -> str | None:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if "duration_seconds" in cols:
        return "duration_seconds"
    if "duration" in cols:
        return "duration"
    return None


def load_avg_duration_by_hero(db_path: Path, min_matches: int) -> tuple[list[tuple[str, float, int]], str]:
    conn = sqlite3.connect(db_path)
    try:
        table_name = "dota_matches_stratz"
        duration_col = discover_duration_col(conn, table_name)
        if not duration_col:
            raise RuntimeError("Tabela sem coluna de duracao (duration_seconds/duration).")

        query = f"""
            SELECT heroes, {duration_col}
            FROM {table_name}
            WHERE heroes IS NOT NULL AND {duration_col} IS NOT NULL AND {duration_col} > 0
        """
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    hero_durations_sec = defaultdict(list)
    for heroes_raw, duration_sec in rows:
        heroes = parse_heroes(heroes_raw)
        if len(heroes) != 10:
            continue
        for hero in heroes:
            hero_durations_sec[hero].append(float(duration_sec))

    result = []
    for hero, durations in hero_durations_sec.items():
        n = len(durations)
        if n < min_matches:
            continue
        avg_sec = sum(durations) / n
        result.append((hero, avg_sec / 60.0, n))

    return result, duration_col


def write_csv(path: Path, rows: list[tuple[str, float, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hero", "avg_duration_min", "matches"])
        for hero, avg_min, n in rows:
            writer.writerow([hero, round(avg_min, 3), n])


def main() -> int:
    parser = argparse.ArgumentParser(description="Media de tempo de todos os herois Dota da DB")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Caminho da DB sqlite")
    parser.add_argument(
        "--sort",
        choices=["desc", "asc"],
        default="desc",
        help="Ordenacao por media de tempo (desc=maior para menor, asc=menor para maior)",
    )
    parser.add_argument("--min-matches", type=int, default=1, help="Minimo de partidas por heroi")
    parser.add_argument("--output-csv", type=Path, default=None, help="Salvar saida em CSV")
    args = parser.parse_args()

    db_path = args.db_path if args.db_path.is_absolute() else (PROJECT_ROOT / args.db_path)
    if not db_path.exists():
        print(f"ERRO: DB nao encontrada: {db_path}")
        return 1
    if args.min_matches < 1:
        print("ERRO: --min-matches precisa ser >= 1")
        return 1

    try:
        rows, duration_col = load_avg_duration_by_hero(db_path, args.min_matches)
    except Exception as exc:
        print(f"ERRO ao ler DB: {exc}")
        return 1

    rows.sort(key=lambda x: x[1], reverse=(args.sort == "desc"))

    print("=" * 72)
    print("DOTA - MEDIA DE TEMPO POR HEROI (TODOS)")
    print("=" * 72)
    print(f"DB: {db_path}")
    print(f"Coluna de duracao: {duration_col}")
    print(f"Herois retornados: {len(rows)} (min_matches={args.min_matches})")
    print()
    print(f"{'#':<4} {'Hero':<28} {'Media (min)':>12} {'Partidas':>10}")
    print("-" * 72)
    for i, (hero, avg_min, n) in enumerate(rows, 1):
        print(f"{i:<4} {hero:<28} {avg_min:>12.2f} {n:>10}")
    print("-" * 72)

    if args.output_csv:
        output_path = args.output_csv if args.output_csv.is_absolute() else (PROJECT_ROOT / args.output_csv)
        write_csv(output_path, rows)
        print(f"CSV salvo em: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
