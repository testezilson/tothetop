#!/usr/bin/env python3
"""
Consulta a DB usada pelo TESTE DOTA LIVE GAME (build_snapshots / compute_hero_metrics)
e mostra:
- 20 herois com MAIOR media de tempo de jogo (duracao em MINUTOS)
- 20 herois com MENOR media de tempo de jogo
- 20 herois com MAIOR media de kills totais por partida
- 20 herois com MENOR media de kills totais por partida

DB: data/dota_opendota_leagues.db (tabela dota_matches_stratz).
Coluna de duracao: "duration" (segundos) ou "duration_seconds"; exibicao em minutos.

Uso (na raiz do projeto):
  python scripts/show_hero_avg_duration_kills_db_live_game.py
"""
import json
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "dota_opendota_leagues.db"


def parse_heroes(raw):
    try:
        heroes = json.loads(raw)
        if isinstance(heroes, list):
            return [str(h).strip() for h in heroes]
        return []
    except Exception:
        return []


def main():
    if not DB_PATH.exists():
        print(f"ERRO: DB nao encontrada: {DB_PATH}")
        print("Esta e a DB do TESTE DOTA LIVE GAME (dota_opendota_leagues.db).")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(dota_matches_stratz)")
    columns = [row[1] for row in cur.fetchall()]
    duration_col = "duration_seconds" if "duration_seconds" in columns else ("duration" if "duration" in columns else None)

    if duration_col:
        query = f"""
            SELECT radiant_kills, dire_kills, heroes, {duration_col}
            FROM dota_matches_stratz
            WHERE radiant_kills IS NOT NULL AND dire_kills IS NOT NULL AND heroes IS NOT NULL
        """
    else:
        query = """
            SELECT radiant_kills, dire_kills, heroes
            FROM dota_matches_stratz
            WHERE radiant_kills IS NOT NULL AND dire_kills IS NOT NULL AND heroes IS NOT NULL
        """

    rows = cur.execute(query).fetchall()
    conn.close()

    hero_kills = defaultdict(list)
    hero_duration = defaultdict(list)

    for row in rows:
        rk, dk, heroes_raw = row[0], row[1], row[2]
        total_kills = (rk or 0) + (dk or 0)
        duration_sec = row[3] if duration_col and len(row) > 3 else None
        heroes = parse_heroes(heroes_raw)
        if len(heroes) != 10:
            continue
        for h in heroes:
            if not h:
                continue
            hero_kills[h].append(total_kills)
            if duration_sec is not None:
                hero_duration[h].append(duration_sec)

    avg_kills = {h: (sum(v) / len(v), len(v)) for h, v in hero_kills.items() if v}
    avg_duration = {h: (sum(v) / len(v), len(v)) for h, v in hero_duration.items() if v}

    print()
    print("=" * 70)
    print("DB USADA PELO TESTE DOTA LIVE GAME (dota_opendota_leagues.db)")
    print("=" * 70)
    print(f"DB: {DB_PATH}")
    print(f"Partidas com 10 herois: {len(rows)}")
    print(f"Coluna duracao: {duration_col or 'nao'}")
    print()

    # Top 20 maior / menor media de tempo — em MINUTOS
    if avg_duration:
        by_dur_desc = sorted(avg_duration.items(), key=lambda x: x[1][0], reverse=True)
        print("=" * 70)
        print("TOP 20 MAIOR MEDIA DE TEMPO (duracao em minutos)")
        print("=" * 70)
        print(f"{'#':<4} {'Hero':<22} {'Media (min)':>12} {'Jogos':>8}")
        print("-" * 70)
        for i, (hero, (avg_sec, games)) in enumerate(by_dur_desc[:20], 1):
            avg_min = avg_sec / 60.0
            print(f"{i:<4} {hero:<22} {avg_min:>12.1f} {games:>8}")
        print("-" * 70)
        print()

        print("=" * 70)
        print("TOP 20 MENOR MEDIA DE TEMPO (duracao em minutos)")
        print("=" * 70)
        print(f"{'#':<4} {'Hero':<22} {'Media (min)':>12} {'Jogos':>8}")
        print("-" * 70)
        for i, (hero, (avg_sec, games)) in enumerate(by_dur_desc[-20:][::-1], 1):
            avg_min = avg_sec / 60.0
            print(f"{i:<4} {hero:<22} {avg_min:>12.1f} {games:>8}")
        print("-" * 70)
        print()
    else:
        print("(Sem coluna de duracao na tabela - pulando rankings de tempo)")
        print()

    # Top 20 maior e menor media de kills
    by_kills_desc = sorted(avg_kills.items(), key=lambda x: x[1][0], reverse=True)

    print("=" * 70)
    print("TOP 20 MAIOR MEDIA DE KILLS (total da partida)")
    print("=" * 70)
    print(f"{'#':<4} {'Hero':<22} {'Media':>10} {'Jogos':>8}")
    print("-" * 70)
    for i, (hero, (avg, games)) in enumerate(by_kills_desc[:20], 1):
        print(f"{i:<4} {hero:<22} {avg:>10.2f} {games:>8}")
    print("-" * 70)
    print()

    print("=" * 70)
    print("TOP 20 MENOR MEDIA DE KILLS (total da partida)")
    print("=" * 70)
    print(f"{'#':<4} {'Hero':<22} {'Media':>10} {'Jogos':>8}")
    print("-" * 70)
    for i, (hero, (avg, games)) in enumerate(by_kills_desc[-20:][::-1], 1):
        print(f"{i:<4} {hero:<22} {avg:>10.2f} {games:>8}")
    print("-" * 70)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
