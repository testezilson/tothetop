# -*- coding: utf-8 -*-
"""
Teste: últimos 10 jogos FT retornados por get_fixtures_by_referee (mesma lógica da app).

Uso (na raiz do projeto):
  python scripts/test_referee_last10.py
  python scripts/test_referee_last10.py "S. Frappart"
  python scripts/test_referee_last10.py "S. Frappart" --t1 106 --t2 116

Chave: FOOTBALL_API_KEY ou data/football_api_key.txt (core.shared.paths).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# `core` vive em src/; mesmo padrão que scripts/champion_gamelength_by_region.py, etc.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core.football.api_client import FootballAPIClient, FootballAPIError  # noqa: E402


def _fmt_ts(fx: Dict[str, Any]) -> str:
    f = fx.get("fixture") or {}
    d = f.get("date")
    if d:
        return str(d)[:19].replace("T", " ")
    ts = f.get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except (TypeError, ValueError, OSError):
            pass
    return "—"


def _names(fx: Dict[str, Any]) -> tuple[str, str]:
    t = fx.get("teams") or {}
    h = (t.get("home") or {}).get("name") or "?"
    a = (t.get("away") or {}).get("name") or "?"
    return str(h), str(a)


def _score(fx: Dict[str, Any]) -> str:
    g = fx.get("goals") or {}
    th, ta = g.get("home"), g.get("away")
    if th is not None and ta is not None:
        return f"{th}-{ta}"
    return "—"


def _league(fx: Dict[str, Any]) -> str:
    lg = fx.get("league") or {}
    return str(lg.get("name") or "?") + (f" ({lg.get('country', '')})" if lg.get("country") else "")


def _ref(fx: Dict[str, Any]) -> str:
    r = (fx.get("fixture") or {}).get("referee")
    return str(r).strip() if r else "—"


def main() -> None:
    p = argparse.ArgumentParser(description="Lista os últimos N jogos FT do árbitro (API-Sports).")
    p.add_argument("referee", nargs="?", default="S. Frappart", help='Nome como na API, ex. "S. Frappart"')
    p.add_argument("-n", "--need", type=int, default=10, help="Quantos jogos (máx. 100)")
    p.add_argument("--t1", type=int, default=None, help="ID time 1 (âncora opcional)")
    p.add_argument("--t2", type=int, default=None, help="ID time 2 (âncora opcional)")
    args = p.parse_args()

    need = max(1, min(int(args.need), 100))
    anchor: Optional[tuple] = None
    if args.t1 is not None and args.t2 is not None and args.t1 != args.t2:
        anchor = (int(args.t1), int(args.t2))

    client = FootballAPIClient()
    if not client.has_key():
        print(
            "Erro: defina FOOTBALL_API_KEY ou crie data/football_api_key.txt com a chave.",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"Arbitro pedido: {args.referee!r}")
    print(f"N = {need}" + (f"  |  ancora clubes: {anchor}" if anchor else ""))
    print("=" * 100)

    try:
        fxs: List[Dict[str, Any]] = client.get_fixtures_by_referee(
            args.referee, need, anchor_team_ids=anchor
        )
    except FootballAPIError as e:
        print("Erro API:", e, file=sys.stderr)
        sys.exit(1)

    if not fxs:
        print("0 jogos na amostra (get_fixtures_by_referee).")
        sys.exit(0)

    print(f"Encontrados: {len(fxs)} jogo(s)\n")
    for i, fx in enumerate(fxs, 1):
        fid = (fx.get("fixture") or {}).get("id")
        h, a = _names(fx)
        print(f"{i:2}. id={fid}  {_fmt_ts(fx)}  |  {h}  {_score(fx)}  {a}")
        print(f"     Juiz no JSON: {_ref(fx)}")
        print(f"     Liga: {_league(fx)}")
        print()


if __name__ == "__main__":
    main()
