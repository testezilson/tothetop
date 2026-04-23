#!/usr/bin/env python3
"""
Diagnóstico: últimos 10 jogos (total, em casa, fora) por clube, alinhado ao app.

- Usa o mesmo FootballAPIClient.get_fixtures_last (com a nova ordem: ligas primeiro).
- Mostra o que /leagues e /fixtures devolvem (contagens, erros).
- Aplica a mesma lógica de «mandante/visitante» do pré-bets (prebets_football).

Uso (raiz do projecto):
  set PYTHONPATH=src
  python scripts/diagnose_football_team_last10.py --teams 728 540

Chave: FOOTBALL_API_KEY ou data/football_api_key.txt, ou --key
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import requests  # noqa: E402

from core.football.api_client import (  # noqa: E402
    API_FIXTURE_STATUS_FINISHED,
    BASE_URL,
    FootballAPIClient,
    FootballAPIError,
)
from core.football.prebets_football import (  # noqa: E402
    _label_team_name,
    _opponent_name,
    _team_venue_in_fixture,
)
from core.shared.paths import get_football_api_key  # noqa: E402


def _raw_leagues_count(key: str, team_id: int) -> None:
    for label, p in [
        ("leagues?team&current=true", {"team": team_id, "current": "true"}),
        ("leagues?team (sem current)", {"team": team_id}),
    ]:
        r = requests.get(
            f"{BASE_URL.rstrip('/')}/leagues",
            params=p,
            headers={"x-apisports-key": key},
            timeout=60,
        )
        try:
            d = r.json()
        except Exception:  # noqa: BLE001
            print(f"  {label} -> HTTP {r.status_code} (JSON inválido) {r.text[:200]}")
            continue
        n = len(d.get("response") or [])
        e = d.get("errors")
        print(
            f"  {label} -> HTTP {r.status_code}  n_ligas={n}  "
            f"errors={json.dumps(e, ensure_ascii=False) if e else e}"
        )


def _venue_split(
    raw: List[Dict[str, Any]], team_id: int, name_hint: str
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    tid = int(team_id)
    nm = _label_team_name(name_hint) or None
    home, away = [], []
    for fx in raw:
        v = _team_venue_in_fixture(fx, tid, nm)
        if v == "home":
            home.append(fx)
        elif v == "away":
            away.append(fx)
    return home, away


def _fmt_row(fx: Dict[str, Any], team_id: int, name: str) -> str:
    tid = int(team_id)
    f = fx.get("fixture") or {}
    fid = f.get("id")
    d = f.get("date", "?")
    h = _opponent_name(fx, tid)
    ven = _team_venue_in_fixture(
        fx, tid, _label_team_name(name) or None
    )
    st = (f.get("status") or {}).get("short", "")
    return f"  id={fid}  {d}  {ven or '?'}  vs {h}  ({st})"


def run_team(
    c: FootballAPIClient, key: str, team_id: int, name: str, take: int
) -> None:
    print()
    print("=" * 70)
    print(f"EQUIPA  id={team_id}  nome_query={name!r}")
    print("=" * 70)
    print("\n[Bruto] /leagues")
    _raw_leagues_count(key, team_id)

    print(f"\n[Cliente] get_fixtures_last(…, last={take}, status=FT-AET-PEN)")
    fxs: List[Dict[str, Any]] = []
    try:
        fxs = c.get_fixtures_last(team_id, last=take, status=API_FIXTURE_STATUS_FINISHED)
    except FootballAPIError as e:
        print(f"  Erro: {e}")
    else:
        print(f"  len = {len(fxs)}")
        for fx in fxs[: take]:
            if isinstance(fx, dict):
                print(_fmt_row(fx, team_id, name))

    h_list, a_list = _venue_split(fxs, team_id, name)
    print(
        f"\n[Filtro app] a partir do mesmo lote: casas={len(h_list)}  foras={len(a_list)}"
    )
    print(f"  Últimos {take} como mandante (máx):")
    for fx in h_list[:take]:
        if isinstance(fx, dict):
            print(_fmt_row(fx, team_id, name))
    print(f"  Últimos {take} como visitante (máx):")
    for fx in a_list[:take]:
        if isinstance(fx, dict):
            print(_fmt_row(fx, team_id, name))

    tinfo: Optional[Dict[str, Any]] = None
    try:
        tinfo = c.get_team_info(team_id)
    except FootballAPIError:
        pass
    if tinfo:
        print(
            f"\n[Validação] /teams?id= : nome API = {tinfo.get('name', tinfo) !r}"
        )
    if not fxs:
        print(
            "\n[Conclusão] 0 jogos. Possíveis causas: chave errada, quota, "
            "plano sem /fixtures, ou a API a devolver vazio. Compare com a secção [Bruto] acima."
        )
    else:
        print(
            f"\n[Conclusão] OK — {len(fxs)} jogos; o app deveria mostrar o mesmo. "
            "Se o UI ainda de 0, verifica se a chave na app é a mesma que no script."
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", type=int, nargs="*", default=[728, 540])
    ap.add_argument("--last", type=int, default=10)
    ap.add_argument("--key", type=str, default="")
    ap.add_argument(
        "-n", "--name", type=str, default="", help="Dica de nome (Rayo) para o venue"
    )
    args = ap.parse_args()
    key = (args.key or get_football_api_key() or os.environ.get("FOOTBALL_API_KEY", "")).strip()
    if not key:
        print("Chave em falta.")
        return 1
    c = FootballAPIClient(api_key=key)
    for tid in args.teams:
        name = args.name
        if not name:
            try:
                t = c.get_team_info(tid)
                name = (t or {}).get("name") or str(tid)
            except Exception:  # noqa: BLE001
                name = str(tid)
        run_team(c, key, tid, name, int(args.last))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
