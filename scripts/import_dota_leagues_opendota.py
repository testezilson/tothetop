#!/usr/bin/env python3
"""
Importa campeonatos Dota 2 do OpenDota para uma nova base SQLite.

Uso:
  python scripts/import_dota_leagues_opendota.py --league 18988
  python scripts/import_dota_leagues_opendota.py --league 18988 18629 19148
  python scripts/import_dota_leagues_opendota.py --league 18988 --fresh

  --league  IDs das ligas (obrigatório). Vários IDs separados por espaço.
  --fresh   Limpa o banco antes de importar.

Banco: data/dota_opendota_leagues.db
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Configuração
OPENDOTA_BASE = "https://api.opendota.com/api"
# API key: use env OPENDOTA_API_KEY para sobrescrever (recomendado em produção)
API_KEY = os.environ.get("OPENDOTA_API_KEY", "37e714d1-52c9-49c5-97bc-5088952738e4")
DELAY_SECONDS = 1.2  # Respeitar rate limit
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "dota_opendota_leagues.db"

def _session(api_key: str):
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "User-Agent": "LoLOracleML-Dota-Import/1.0"})
    s.params = {"api_key": api_key} if api_key else {}
    return s


def fetch_league_name(session: requests.Session, league_id: int) -> str:
    """Busca o nome da liga. Retorna 'League {id}' se falhar."""
    url = f"{OPENDOTA_BASE}/leagues/{league_id}"
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        return (data.get("name") or "").strip() or f"League {league_id}"
    except requests.RequestException:
        return f"League {league_id}"


def fetch_match_ids(session: requests.Session, league_id: int) -> list[int]:
    """Busca IDs de partidas de uma liga."""
    url = f"{OPENDOTA_BASE}/leagues/{league_id}/matchIds"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def fetch_match(session: requests.Session, match_id: int) -> dict | None:
    """Busca detalhes completos de uma partida."""
    url = f"{OPENDOTA_BASE}/matches/{match_id}"
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def _extract_players_kills_log(players: list) -> str:
    """
    Extrai kill_times por jogador para kills_at_time.
    Retorna JSON: list de 10 listas [t1, t2, ...] em ordem player_slot (0-4 Radiant, 128-132 Dire).
    """
    sorted_players = sorted(
        (p for p in (players or []) if p.get("player_slot") is not None),
        key=lambda p: p.get("player_slot", 0),
    )
    kill_times_per_player = []
    for p in sorted_players[:10]:
        times = []
        for k in p.get("kills_log") or []:
            t = k.get("time")
            if t is not None:
                times.append(int(t))
        kill_times_per_player.append(times)
    while len(kill_times_per_player) < 10:
        kill_times_per_player.append([])
    return json.dumps(kill_times_per_player[:10])


def _heroes_from_players(players: list) -> list[str]:
    """Extrai lista de heróis (nomes) dos players. Requer hero_id -> name mapping externo."""
    heroes = []
    for p in players or []:
        hid = p.get("hero_id")
        if hid is not None:
            heroes.append(str(hid))  # Guardamos ID; depois pode mapear para nome
    return heroes


def _extract_match_row(m: dict, league_id: int, league_name: str, heroes_map: dict) -> tuple:
    """Extrai linha para inserção na tabela dota_matches_stratz."""
    match_id = m.get("match_id")
    radiant_win = 1 if m.get("radiant_win") else 0
    duration = m.get("duration") or 0
    radiant_score = m.get("radiant_score") or 0
    dire_score = m.get("dire_score") or 0
    start_time = m.get("start_time")
    if start_time:
        start_date = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    else:
        start_date = None

    players = m.get("players") or []
    hero_ids = [p.get("hero_id") for p in players if p.get("hero_id") is not None]
    hero_names = [heroes_map.get(hid, str(hid)) for hid in hero_ids]
    heroes_json = json.dumps(hero_names)

    radiant_team = m.get("radiant_team") or {}
    dire_team = m.get("dire_team") or {}
    radiant_name = radiant_team.get("name") or radiant_team.get("tag") or ""
    dire_name = dire_team.get("name") or dire_team.get("tag") or ""

    # Timeline (opcional): radiant_gold_adv, radiant_xp_adv
    radiant_gold_adv = json.dumps(m.get("radiant_gold_adv") or [])
    radiant_xp_adv = json.dumps(m.get("radiant_xp_adv") or [])
    objectives = json.dumps(m.get("objectives") or [])
    teamfights = json.dumps(m.get("teamfights") or [])

    # kills_log por jogador (para kills_at_time no Live). Ordem: slots 0-4 Radiant, 128-132 Dire.
    players_kills_log = _extract_players_kills_log(players)

    return (
        match_id,
        league_id,
        league_name,
        radiant_win,
        duration,
        radiant_score,
        dire_score,
        radiant_name,
        dire_name,
        start_date,
        heroes_json,
        radiant_gold_adv,
        radiant_xp_adv,
        objectives,
        teamfights,
        players_kills_log,
    )


def fetch_heroes(session: requests.Session) -> dict[int, str]:
    """Mapeia hero_id -> localized_name."""
    url = f"{OPENDOTA_BASE}/heroes"
    r = session.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    out = {}
    for h in data or []:
        hid = h.get("id")
        name = h.get("localized_name") or h.get("name") or str(hid)
        if hid is not None:
            out[int(hid)] = name
    return out


def create_schema(conn: sqlite3.Connection) -> None:
    """Cria tabelas na nova DB."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dota_matches_stratz (
            match_id INTEGER PRIMARY KEY,
            league_id INTEGER,
            league_name TEXT,
            radiant_win INTEGER,
            duration INTEGER,
            radiant_kills INTEGER,
            dire_kills INTEGER,
            radiant_name TEXT,
            dire_name TEXT,
            start_date TEXT,
            heroes TEXT,
            radiant_gold_adv TEXT,
            radiant_xp_adv TEXT,
            objectives TEXT,
            teamfights TEXT,
            raw_json TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_league ON dota_matches_stratz(league_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_start_date ON dota_matches_stratz(start_date)
    """)
    try:
        conn.execute("ALTER TABLE dota_matches_stratz ADD COLUMN players_kills_log TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate" not in str(e).lower():
            raise
    conn.commit()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Importa campeonatos Dota 2 do OpenDota")
    parser.add_argument("--league", "-l", type=int, nargs="+", required=True, help="League ID(s) do OpenDota (ex: 18988)")
    parser.add_argument("--fresh", action="store_true", help="Limpa a tabela antes de importar (importa do zero)")
    args = parser.parse_args()

    league_ids = list(dict.fromkeys(args.league))

    print("=" * 60)
    print("Importação de Campeonatos Dota 2 - OpenDota")
    print("=" * 60)
    print()
    print(f"Banco: {DB_PATH.resolve()}")
    print(f"Ligas: {league_ids}")
    print()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    session = _session(API_KEY)

    # 1. Buscar nomes das ligas
    found = []
    for lid in league_ids:
        name = fetch_league_name(session, lid)
        found.append((lid, name))
        print(f"   {lid}: {name}")

    print("\nBuscando mapa de heróis...")
    heroes_map = fetch_heroes(session)

    # 4. Se --fresh: apagar arquivos do banco ANTES de conectar (evita lock)
    if args.fresh:
        for f in [DB_PATH, Path(str(DB_PATH) + "-wal"), Path(str(DB_PATH) + "-shm")]:
            if f.exists():
                try:
                    f.unlink()
                    print(f"Removido: {f.name}")
                except OSError as e:
                    print(f"\nErro ao remover {f}: {e}")
                    print("Feche outros programas (DB Browser, LoLOracleML) e tente novamente.")
                    sys.exit(1)
        print("Banco removido. Importando do zero.\n")

    # 5. Criar DB e schema
    try:
        conn = sqlite3.connect(DB_PATH, timeout=60)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            print(f"\nErro: banco de dados bloqueado. Feche outros programas que possam estar usando:")
            print(f"   {DB_PATH}")
            print("   (DB Browser, LoLOracleML, etc.)")
        raise
    create_schema(conn)

    conn.execute("PRAGMA busy_timeout = 60000")

    total_matches = 0
    total_imported = 0
    total_skipped = 0
    total_errors = 0

    COMMIT_EVERY = 10

    for league_id, league_name in found:
        print(f"\n--- {league_name} (ID {league_id}) ---")
        match_ids = fetch_match_ids(session, league_id)
        total_matches += len(match_ids)
        print(f"   Partidas na liga: {len(match_ids)}")

        imported = 0
        skipped = 0
        errors = 0

        for i, mid in enumerate(match_ids):
            # Verificar se já existe
            cur = conn.execute("SELECT 1 FROM dota_matches_stratz WHERE match_id = ?", (mid,))
            if cur.fetchone():
                skipped += 1
                if (i + 1) % 20 == 0:
                    print(f"   Progresso: {i+1}/{len(match_ids)} (importados: {imported}, pulados: {skipped})")
                time.sleep(0.05)
                continue

            m = fetch_match(session, mid)
            time.sleep(DELAY_SECONDS)

            if m is None:
                errors += 1
                continue

            try:
                row = _extract_match_row(m, league_id, league_name, heroes_map)
                raw_json = json.dumps(m, default=str)[:50000]
                conn.execute("""
                    INSERT OR REPLACE INTO dota_matches_stratz (
                        match_id, league_id, league_name, radiant_win, duration,
                        radiant_kills, dire_kills, radiant_name, dire_name,
                        start_date, heroes, radiant_gold_adv, radiant_xp_adv,
                        objectives, teamfights, raw_json, players_kills_log
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (*row[:-1], raw_json, row[-1]))
                imported += 1
                if imported % COMMIT_EVERY == 0:
                    conn.commit()
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"   Erro match {mid}: {e}")

            if (i + 1) % 20 == 0:
                print(f"   Progresso: {i+1}/{len(match_ids)} (importados: {imported}, pulados: {skipped})")

        conn.commit()
        total_imported += imported
        total_skipped += skipped
        total_errors += errors
        print(f"   Fim: importados={imported}, pulados={skipped}, erros={errors}")

    conn.close()

    print()
    print("=" * 60)
    print("Resumo")
    print("=" * 60)
    print(f"   Banco: {DB_PATH}")
    print(f"   Total de partidas nas ligas: {total_matches}")
    print(f"   Importadas: {total_imported}")
    print(f"   Já existiam (puladas): {total_skipped}")
    print(f"   Erros: {total_errors}")
    print()
    print("Concluído.")


if __name__ == "__main__":
    main()
