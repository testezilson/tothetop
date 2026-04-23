#!/usr/bin/env python3
"""
Diagnóstico do endpoint /fixtures (API-FOOTball / API-Sports v3).
Mostra, para um ou mais team ids, o que a API devolve com vários parâmetros
(sem o cliente «levantar» FootballAPIError — imprime o JSON de erro).

Uso a partir da raiz do projecto:
  set PYTHONPATH=src
  python scripts/debug_football_fixtures.py --teams 536 539

Chave: variável de ambiente FOOTBALL_API_KEY ou ficheiro data/football_api_key.txt
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Repositório: src/ na path
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import requests  # noqa: E402

from core.football.api_client import (  # noqa: E402
    API_FIXTURE_STATUS_FINISHED,
    FootballAPIClient,
    FootballAPIError,
    BASE_URL,
)
from core.shared.paths import get_football_api_key  # noqa: E402


def _y0() -> int:
    d = datetime.now(timezone.utc)
    return int(d.year) if d.month >= 7 else int(d.year) - 1


def raw_fixtures(
    key: str, params: Dict[str, Any], label: str
) -> None:
    url = f"{BASE_URL.rstrip('/')}/fixtures"
    r = requests.get(
        url, params=params, headers={"x-apisports-key": key}, timeout=60
    )
    try:
        data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"\n--- {label} --- HTTP {r.status_code!r} (JSON inválido: {e})")
        print(r.text[:800])
        return
    n = 0
    if isinstance(data.get("response"), list):
        n = len(data["response"])
    err = data.get("errors")
    print(f"\n--- {label} --- HTTP {r.status_code}  response_len={n}")
    if err:
        print("errors:", json.dumps(err, ensure_ascii=False) if isinstance(err, (dict, list)) else err)
    if n and isinstance(data["response"], list) and data["response"]:
        f0 = data["response"][0]
        if isinstance(f0, dict):
            fi = f0.get("fixture") or {}
            print(
                "primeiro jogo: fixture_id=",
                fi.get("id"),
                "status=",
                (fi.get("status") or {}).get("short") if isinstance(fi.get("status"), dict) else fi.get("status"),
            )


def run_client_smoke(
    key: str, team_id: int, last: int
) -> None:
    c = FootballAPIClient(api_key=key)
    for label, st in [
        ("FT (antigo, pode falhar)", "FT"),
        (f"recomendado ({API_FIXTURE_STATUS_FINISHED})", API_FIXTURE_STATUS_FINISHED),
    ]:
        try:
            fxs = c.get_fixtures_last(team_id, last=last, status=st)
        except FootballAPIError as e:
            print(f"\n  [cliente] {label} -> FootballAPIError: {e}")
        else:
            print(f"\n  [cliente] {label} -> len = {len(fxs)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", type=int, nargs="*", default=[536, 539])
    ap.add_argument("--last", type=int, default=10)
    ap.add_argument("--key", type=str, default="")
    args = ap.parse_args()
    key = (args.key or get_football_api_key() or os.environ.get("FOOTBALL_API_KEY", "") or "").strip()
    if not key:
        print("Chave em falta: FOOTBALL_API_KEY ou data/football_api_key.txt")
        return 1
    y0 = _y0()
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=400)

    for team_id in args.teams:
        print("\n" + "=" * 60)
        print(f"TEAM {team_id}  (época padrão ~{y0})")
        print("=" * 60)
        # Pedidos em bruto (sempre imprimir erros no corpo)
        raw_fixtures(key, {"team": team_id, "last": args.last, "status": "FT"}, "A) team+last+status=FT")
        raw_fixtures(
            key,
            {"team": team_id, "last": args.last, "status": API_FIXTURE_STATUS_FINISHED},
            f"B) team+last+status={API_FIXTURE_STATUS_FINISHED!r}",
        )
        raw_fixtures(
            key,
            {
                "team": team_id,
                "season": y0,
                "last": args.last,
                "status": API_FIXTURE_STATUS_FINISHED,
            },
            f"C) team+season+last+status={API_FIXTURE_STATUS_FINISHED!r}",
        )
        raw_fixtures(
            key,
            {"team": team_id, "from": str(start), "to": str(end)},
            f"D) team+from+to ({start} .. {end})",
        )
        r = requests.get(
            f"{BASE_URL.rstrip('/')}/leagues",
            params={"team": team_id, "current": "true"},
            headers={"x-apisports-key": key},
            timeout=60,
        )
        try:
            ld = r.json()
        except Exception:  # noqa: BLE001
            ld = {}
        lresp = ld.get("response")
        nlg = len(lresp) if isinstance(lresp, list) else 0
        print(f"\n--- E) leagues?team&current=true --- n_leagues={nlg} errors={ld.get('errors')}")
        if nlg and isinstance(lresp, list):
            row0 = lresp[0]
            if isinstance(row0, dict):
                lid = (row0.get("league") or {}).get("id")
                seasons: List[Dict[str, Any]] = row0.get("seasons") or []
                y = None
                for s in seasons:
                    if s.get("year") is not None:
                        y = int(s["year"])
                        break
                if lid is not None and y is not None:
                    raw_fixtures(
                        key,
                        {
                            "team": team_id,
                            "league": int(lid),
                            "season": y,
                            "last": args.last,
                            "status": API_FIXTURE_STATUS_FINISHED,
                        },
                        f"F) team+league+season+last (L={lid} S={y})",
                    )
        print("\n[Cliente] comparação FootballAPIClient.get_fixtures_last:")
        run_client_smoke(key, team_id, args.last)

    print("\nFim. Se B) ou C) tiver len>0 mas o app mostrar 0, o bug estava no parâmetro status ou na cadeia de fallbacks; corrigir para FT-AET-PEN (já feito).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
