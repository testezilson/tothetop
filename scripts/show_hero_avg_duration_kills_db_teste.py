#!/usr/bin/env python3
"""
Consulta a DB usada pela aba TESTE (testezudo) e mostra:
- 20 herois com MAIOR media de tempo de jogo (duracao)
- 20 herois com MENOR media de tempo de jogo
- 20 herois com MAIOR media de kills totais por partida
- 20 herois com MENOR media de kills totais por partida

Usa a mesma DB que o testezudo (get_dota_db_path). Tabela: dota_matches_stratz.
Coluna duration_seconds: se nao existir, so exibe os rankings de kills.

Uso (na raiz do projeto):
  python scripts/show_hero_avg_duration_kills_db_teste.py
"""
import json
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

# Descobrir DB do testezudo (mesma da aba TESTE)
ROOT = Path(__file__).resolve().parents[1]
TESTEZUDO_DIR = ROOT.parent / "testezudo"  # irmao do lol_oracle_ml_v3
if not TESTEZUDO_DIR.exists():
    TESTEZUDO_DIR = Path(r"C:\Users\Lucas\Documents\testezudo")

def get_db_path():
    """Usa a mesma logica do testezudo para achar a DB."""
    if TESTEZUDO_DIR.exists():
        sys.path.insert(0, str(TESTEZUDO_DIR))
        try:
            from dota_db_path import get_dota_db_path
            return get_dota_db_path()
        except Exception:
            pass
    # Fallback: paths comuns
    for rel in [
        TESTEZUDO_DIR / "data" / "dota_matches.db",
        TESTEZUDO_DIR / "data" / "dota_matches_stratz.db",
        Path(r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\dota_draft_ml_v1\data\dota_matches.db"),
    ]:
        if rel.exists():
            return str(rel)
    return None


def parse_heroes(raw):
    try:
        heroes = json.loads(raw)
        if isinstance(heroes, list):
            return [str(h).strip() for h in heroes]
        return []
    except Exception:
        return []


def main():
    db_path = get_db_path()
    if not db_path:
        print("ERRO: Nenhuma DB Dota encontrada (testezudo ou fallback).")
        return 1

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(dota_matches_stratz)")
    columns = [row[1] for row in cur.fetchall()]
    has_duration = "duration_seconds" in columns

    if has_duration:
        query = """
            SELECT radiant_kills, dire_kills, heroes, duration_seconds
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

    # Por heroi: listas de (total_kills, duration_seconds ou None)
    hero_kills = defaultdict(list)
    hero_duration = defaultdict(list)

    for row in rows:
        rk, dk, heroes_raw = row[0], row[1], row[2]
        total_kills = (rk or 0) + (dk or 0)
        duration_sec = row[3] if has_duration and len(row) > 3 else None
        heroes = parse_heroes(heroes_raw)
        if len(heroes) != 10:
            continue
        for h in heroes:
            if not h:
                continue
            hero_kills[h].append(total_kills)
            if duration_sec is not None:
                hero_duration[h].append(duration_sec)

    # Medias por heroi (apenas com pelo menos 1 jogo)
    avg_kills = {h: (sum(v) / len(v), len(v)) for h, v in hero_kills.items() if v}
    avg_duration = {h: (sum(v) / len(v), len(v)) for h, v in hero_duration.items() if v}

    print()
    print("=" * 70)
    print("DB USADA PELA ABA TESTE (dota_matches_stratz)")
    print("=" * 70)
    print(f"DB: {db_path}")
    print(f"Partidas com 10 herois: {len(rows)}")
    print(f"Coluna duration_seconds: {'sim' if has_duration else 'nao'}")
    print()

    # Top 20 maior media de tempo
    if avg_duration:
        by_dur_desc = sorted(avg_duration.items(), key=lambda x: x[1][0], reverse=True)
        print("=" * 70)
        print("TOP 20 MAIOR MEDIA DE TEMPO (duracao em segundos)")
        print("=" * 70)
        print(f"{'#':<4} {'Hero':<22} {'Media (s)':>12} {'Min':>8} {'Jogos':>8}")
        print("-" * 70)
        for i, (hero, (avg_sec, games)) in enumerate(by_dur_desc[:20], 1):
            avg_min = avg_sec / 60.0
            print(f"{i:<4} {hero:<22} {avg_sec:>12.0f} {avg_min:>8.1f} {games:>8}")
        print("-" * 70)
        print()

        print("=" * 70)
        print("TOP 20 MENOR MEDIA DE TEMPO (duracao em segundos)")
        print("=" * 70)
        print(f"{'#':<4} {'Hero':<22} {'Media (s)':>12} {'Min':>8} {'Jogos':>8}")
        print("-" * 70)
        for i, (hero, (avg_sec, games)) in enumerate(by_dur_desc[-20:][::-1], 1):
            avg_min = avg_sec / 60.0
            print(f"{i:<4} {hero:<22} {avg_sec:>12.0f} {avg_min:>8.1f} {games:>8}")
        print("-" * 70)
        print()
    else:
        print("(Sem coluna duration_seconds na tabela - pulando rankings de tempo)")
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
