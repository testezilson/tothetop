#!/usr/bin/env python3
r"""
Dota: top/bottom 20 heróis por média de duração, média de kills e impacto de kills.

Usa a MESMA fonte que a aba TESTE do programa (.exe): arquivos .pkl do projeto testezudo.
Assim os números batem com o que você vê no TESTE (impacto e jogos).

Opção --db: usar data/dota_opendota_leagues.db do projeto (números diferentes do TESTE).

Uso:
  python scripts/show_hero_duration_kills_dota.py
  python scripts/show_hero_duration_kills_dota.py --testezudo-dir "C:\Users\Lucas\Documents\testezudo"
  python scripts/show_hero_duration_kills_dota.py --db   (calcular do DB do projeto, não do testezudo)
"""
import json
import pickle
import sqlite3
import sys
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
# Mesma pasta que a aba TESTE do programa usa (draft_testezudo.TESTEZUDO_DIR)
TESTEZUDO_DIR_DEFAULT = Path(r"C:\Users\Lucas\Documents\testezudo")
DB_PATH = PROJECT_ROOT / "data" / "dota_opendota_leagues.db"
MIN_MATCHES_DEFAULT = 10
SHRINKAGE_K = 15


def _load_from_testezudo(testezudo_dir: Path):
    """
    Carrega impacto e jogos do testezudo (hero_impacts_bayesian_v2_5.pkl).
    Retorna list de (hero, impact, games) ou None se não encontrar.
    """
    bayesian_path = testezudo_dir / "hero_impacts_bayesian_v2_5.pkl"
    if not bayesian_path.exists():
        return None
    with open(bayesian_path, "rb") as f:
        data = pickle.load(f)
    if not isinstance(data, dict):
        return None
    if "_meta" in data:
        data = {k: v for k, v in data.items() if k != "_meta"}
    out = []
    for hero, v in data.items():
        if not isinstance(v, dict):
            continue
        rad = v.get("radiant", {})
        dire = v.get("dire", {})
        g_r = rad.get("games", 0) or 0
        g_d = dire.get("games", 0) or 0
        imp_r = rad.get("impact", 0) or 0
        imp_d = dire.get("impact", 0) or 0
        impact = (imp_r + imp_d) / 2.0
        games = max(g_r, g_d)
        out.append((hero, impact, games))
    return out if out else None


def _get_testezudo_db_path(testezudo_dir: Path) -> Optional[Path]:
    """
    Retorna o caminho de um DB no testezudo que tenha tabela dota_matches_stratz
    com duration, radiant_kills, dire_kills, heroes. Testa data/dota_matches_stratz.db
    e data/dota_matches.db.
    """
    candidates = [
        testezudo_dir / "data" / "dota_matches_stratz.db",
        testezudo_dir / "data" / "dota_matches.db",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            conn = sqlite3.connect(path)
            cur = conn.execute("""
                SELECT duration, radiant_kills, dire_kills, heroes
                FROM dota_matches_stratz
                WHERE duration > 600 AND heroes IS NOT NULL
                LIMIT 1
            """)
            cur.fetchone()
            conn.close()
            return path
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            continue
    return None


def _shrinkage(raw: float, n: int, k: int, toward: float = 0.0) -> float:
    if n >= k * 2:
        return raw
    w = n / (n + k)
    return w * raw + (1 - w) * toward


def load_matches(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute("""
        SELECT duration, radiant_kills, dire_kills, heroes
        FROM dota_matches_stratz
        WHERE duration > 600 AND heroes IS NOT NULL
    """)
    rows = cur.fetchall()
    return [
        {
            "duration_min": r[0] / 60.0,
            "total_kills": (r[1] or 0) + (r[2] or 0),
            "heroes": json.loads(r[3]) if r[3] else [],
        }
        for r in rows
    ]


def _compute_from_db(db_path: Path, min_n: int):
    """Calcula duração, kills e impacto a partir do DB do projeto (não testezudo)."""
    conn = sqlite3.connect(db_path)
    matches = load_matches(conn)
    conn.close()
    if not matches:
        return None, None, None

    hero_durations = {}
    hero_kills = {}
    for m in matches:
        heroes = m.get("heroes") or []
        if len(heroes) < 10:
            continue
        for h in heroes:
            name = str(h).strip() if h else None
            if not name:
                continue
            hero_durations.setdefault(name, []).append(m["duration_min"])
            hero_kills.setdefault(name, []).append(m["total_kills"])

    def mean(lst):
        return sum(lst) / len(lst) if lst else 0.0

    all_kills = [m["total_kills"] for m in matches if (m.get("heroes") or []) and len(m["heroes"]) >= 10]
    global_mean = mean(all_kills) if all_kills else 0.0

    duration_stats = [
        (h, mean(d), len(d)) for h, d in hero_durations.items() if len(d) >= min_n
    ]
    kills_stats = [
        (h, mean(k), len(k)) for h, k in hero_kills.items() if len(k) >= min_n
    ]
    impact_stats = []
    for h, kills in hero_kills.items():
        if len(kills) < min_n:
            continue
        raw = mean(kills) - global_mean
        imp = _shrinkage(raw, len(kills), SHRINKAGE_K, 0.0)
        impact_stats.append((h, imp, len(kills)))

    duration_stats.sort(key=lambda x: x[1], reverse=True)
    kills_stats.sort(key=lambda x: x[1], reverse=True)
    impact_stats.sort(key=lambda x: x[1], reverse=True)
    return duration_stats, kills_stats, impact_stats


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Top/bottom 20 heróis por duração, kills e impacto (por padrão usa testezudo = mesma fonte do TESTE)."
    )
    parser.add_argument(
        "--testezudo-dir",
        type=Path,
        default=TESTEZUDO_DIR_DEFAULT,
        help="Pasta do projeto testezudo (onde estão os .pkl). Mesma que a aba TESTE usa.",
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="Usar data/dota_opendota_leagues.db em vez do testezudo (números diferentes do TESTE).",
    )
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--min-matches", type=int, default=MIN_MATCHES_DEFAULT)
    args = parser.parse_args()

    if args.db:
        # Modo DB do projeto (não testezudo)
        if not args.db_path.exists():
            print(f"Erro: {args.db_path} não encontrado.")
            sys.exit(1)
        duration_stats, kills_stats, impact_stats = _compute_from_db(args.db_path, args.min_matches)
        if not impact_stats:
            print("Nenhum dado do DB.")
            sys.exit(0)
        source = "DB do projeto (dota_opendota_leagues.db)"
        source_duration_kills = source
    else:
        # Modo testezudo = mesma fonte que a aba TESTE para impacto
        rows = _load_from_testezudo(args.testezudo_dir)
        if not rows:
            print(f"Erro: nenhum .pkl encontrado em {args.testezudo_dir}")
            print("  Esperado: hero_impacts_bayesian_v2_5.pkl (testezudo)")
            sys.exit(1)
        impact_stats = rows
        impact_stats.sort(key=lambda x: x[1], reverse=True)
        source = f"testezudo ({args.testezudo_dir}) — mesma fonte que a aba TESTE do programa"
        # Duração e kills: do DB do testezudo (data/*.db) para tudo vir da mesma fonte
        testezudo_db = _get_testezudo_db_path(args.testezudo_dir)
        if testezudo_db is not None:
            duration_stats, kills_stats, _ = _compute_from_db(testezudo_db, args.min_matches)
            source_duration_kills = str(testezudo_db)
        elif args.db_path.exists():
            duration_stats, kills_stats, _ = _compute_from_db(args.db_path, args.min_matches)
            source_duration_kills = str(args.db_path) + " (fallback: DB do projeto)"
        else:
            duration_stats, kills_stats = None, None
            source_duration_kills = None

    print("=" * 70)
    print("DOTA — Top/Bottom 20: duração, kills e impacto de kills")
    print("=" * 70)
    print(f"Impacto: {source}")
    if source_duration_kills:
        print(f"Duração e kills: {source_duration_kills}")
    elif not args.db:
        print("Duração e kills: (nenhum DB encontrado no testezudo/data/ nem no projeto)")
    print()

    # --- Duração ---
    if duration_stats:
        print("-" * 70)
        print("DURAÇÃO (média do tempo de jogo em min quando o herói joga)")
        print("-" * 70)
        print()
        print("Top 20 — MAIOR média de duração (jogos mais longos):")
        print(f"  {'Herói':<28} {'Média (min)':>12} {'Partidas':>10}")
        for hero, avg, n in duration_stats[:20]:
            print(f"  {hero:<28} {avg:>12.2f} {n:>10}")
        print()
        print("Top 20 — MENOR média de duração (jogos mais curtos):")
        print(f"  {'Herói':<28} {'Média (min)':>12} {'Partidas':>10}")
        for hero, avg, n in duration_stats[-20:][::-1]:
            print(f"  {hero:<28} {avg:>12.2f} {n:>10}")
        print()

    # --- Kills ---
    if kills_stats:
        print("-" * 70)
        print("KILLS (média do total de kills da partida quando o herói joga)")
        print("-" * 70)
        print()
        print("Top 20 — MAIOR média de kills (jogos mais sangrentos):")
        print(f"  {'Herói':<28} {'Média kills':>12} {'Partidas':>10}")
        for hero, avg, n in kills_stats[:20]:
            print(f"  {hero:<28} {avg:>12.2f} {n:>10}")
        print()
        print("Top 20 — MENOR média de kills (jogos mais parados):")
        print(f"  {'Herói':<28} {'Média kills':>12} {'Partidas':>10}")
        for hero, avg, n in kills_stats[-20:][::-1]:
            print(f"  {hero:<28} {avg:>12.2f} {n:>10}")
        print()

    # --- Impacto de kills (sempre) ---
    print("-" * 70)
    print("IMPACTO DE KILLS (positivo = jogos com mais kills; negativo = menos kills)")
    print("-" * 70)
    print()
    print("Top 20 — MAIOR impacto de kills:")
    print(f"  {'Herói':<28} {'Impacto':>12} {'Partidas':>10}")
    for hero, impact, n in impact_stats[:20]:
        print(f"  {hero:<28} {impact:>+12.2f} {n:>10}")
    print()
    print("Top 20 — MENOR impacto de kills:")
    print(f"  {'Herói':<28} {'Impacto':>12} {'Partidas':>10}")
    for hero, impact, n in impact_stats[-20:][::-1]:
        print(f"  {hero:<28} {impact:>+12.2f} {n:>10}")
    print()

    print("Fim.")


if __name__ == "__main__":
    main()
