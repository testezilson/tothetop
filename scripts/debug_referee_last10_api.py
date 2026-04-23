#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug simples: últimos N jogos de um árbitro direto na API-Football (API-Sports).

Uso:
  python scripts/debug_referee_last10_api.py "D. England" -n 10
  python scripts/debug_referee_last10_api.py "Darren England" -n 10

Chave:
  - FOOTBALL_API_KEY (ou APISPORTS_KEY / X_APISPORTS_KEY), ou
  - data/football_api_key.txt (primeira linha).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://v3.football.api-sports.io"


def _read_key() -> str:
    for env_name in ("FOOTBALL_API_KEY", "APISPORTS_KEY", "X_APISPORTS_KEY"):
        v = os.environ.get(env_name, "").strip()
        if v:
            return v
    root = Path(__file__).resolve().parent.parent
    p = root / "data" / "football_api_key.txt"
    if p.is_file():
        txt = p.read_text(encoding="utf-8", errors="replace").strip()
        if txt:
            return txt.splitlines()[0].strip()
    return ""


def _request(session: requests.Session, key: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = session.get(
        f"{BASE_URL}/{path.lstrip('/')}",
        params=params,
        headers={"x-apisports-key": key},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    errs = data.get("errors")
    if errs and not data.get("response"):
        raise RuntimeError(f"Erro API: {errs}")
    return data


def _api_referee_param_not_supported(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("referee" in msg and "do not exist" in msg) or ("the referee field do not exist" in msg)


def _fmt_date(fx: Dict[str, Any]) -> str:
    f = fx.get("fixture") or {}
    ts = f.get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            pass
    d = f.get("date")
    if d:
        return str(d)[:10]
    return "?"


def _score(fx: Dict[str, Any]) -> str:
    g = fx.get("goals") or {}
    h, a = g.get("home"), g.get("away")
    if h is None or a is None:
        return "-:-"
    return f"{h}:{a}"


def _teams(fx: Dict[str, Any]) -> str:
    t = fx.get("teams") or {}
    h = (t.get("home") or {}).get("name") or "?"
    a = (t.get("away") or {}).get("name") or "?"
    return f"{h} vs {a}"


def _league(fx: Dict[str, Any]) -> str:
    lg = fx.get("league") or {}
    name = lg.get("name") or "?"
    country = lg.get("country") or ""
    if country:
        return f"{name} ({country})"
    return str(name)


def _ref_name(fx: Dict[str, Any]) -> str:
    return str((fx.get("fixture") or {}).get("referee") or "—")


def _done_status(fx: Dict[str, Any]) -> bool:
    s = ((fx.get("fixture") or {}).get("status") or {}).get("short")
    return str(s or "").upper() in {"FT", "AET", "PEN"}


def _fetch_by_referee_query(
    session: requests.Session,
    key: str,
    referee_query: str,
    need: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    now_year = int(datetime.now(timezone.utc).year)
    years = [now_year - k for k in range(0, 10)]
    for season in years:
        if len(out) >= need:
            break
        page = 1
        max_pages = 1
        while page <= max_pages and len(out) < need:
            try:
                d = _request(
                    session,
                    key,
                    "fixtures",
                    {
                        "referee": str(referee_query),
                        "season": int(season),
                        "status": "FT-AET-PEN",
                        "page": int(page),
                    },
                )
            except Exception as e:
                if _api_referee_param_not_supported(e):
                    # Conta/plano sem suporte ao parâmetro `referee` em /fixtures.
                    return []
                raise
            arr = list(d.get("response") or [])
            if not arr:
                break
            for fx in arr:
                if not _done_status(fx):
                    continue
                fid = (fx.get("fixture") or {}).get("id")
                try:
                    iid = int(fid)
                except (TypeError, ValueError):
                    continue
                if iid in seen:
                    continue
                seen.add(iid)
                out.append(fx)
            paging = d.get("paging") if isinstance(d, dict) else None
            if isinstance(paging, dict):
                try:
                    total_pages = int(paging.get("total") or 1)
                except (TypeError, ValueError):
                    total_pages = 1
                max_pages = max(1, min(total_pages, 25))
            page += 1
    out.sort(key=lambda x: int(((x.get("fixture") or {}).get("timestamp") or 0)), reverse=True)
    return out[:need]


def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace(".", " ").replace(",", " ").split())


def _name_matches(query: str, got: str) -> bool:
    qn = _norm(query)
    gn = _norm(got)
    if not qn or not gn:
        return False
    if qn == gn or qn in gn or gn in qn:
        return True
    qtok = qn.split()
    gtok = gn.split()
    if not qtok or not gtok:
        return False
    qlast = qtok[-1]
    if qlast not in gtok:
        return False
    if len(qtok) >= 2 and len(qtok[0]) == 1:
        ini = qtok[0]
        return any(t.startswith(ini) for t in gtok if t != qlast)
    return True


def _fetch_global_league_scan(
    session: requests.Session,
    key: str,
    referee_query: str,
    need: int,
) -> List[Dict[str, Any]]:
    """
    Fallback para contas sem /referees e quando /fixtures?referee=... falha:
    escaneia ligas/épocas e filtra localmente por nome do árbitro.
    """
    leagues = (39, 45, 48, 140, 135, 78, 61, 71, 72, 94, 88, 128, 2, 3, 40, 620)
    now_year = int(datetime.now(timezone.utc).year)
    years = [now_year - k for k in range(0, 6)]
    out: List[Dict[str, Any]] = []
    seen = set()
    for season in years:
        if len(out) >= need:
            break
        for lid in leagues:
            if len(out) >= need:
                break
            page = 1
            max_pages = 1
            while page <= max_pages and len(out) < need:
                d = _request(
                    session,
                    key,
                    "fixtures",
                    {"league": int(lid), "season": int(season), "status": "FT-AET-PEN", "page": int(page)},
                )
                arr = list(d.get("response") or [])
                if not arr:
                    break
                for fx in arr:
                    if not _done_status(fx):
                        continue
                    rn = _ref_name(fx)
                    if not _name_matches(referee_query, rn):
                        continue
                    fid = (fx.get("fixture") or {}).get("id")
                    try:
                        iid = int(fid)
                    except (TypeError, ValueError):
                        continue
                    if iid in seen:
                        continue
                    seen.add(iid)
                    out.append(fx)
                    if len(out) >= need:
                        break
                paging = d.get("paging") if isinstance(d, dict) else None
                if isinstance(paging, dict):
                    try:
                        total_pages = int(paging.get("total") or 1)
                    except (TypeError, ValueError):
                        total_pages = 1
                    max_pages = max(1, min(total_pages, 20))
                page += 1
    out.sort(key=lambda x: int(((x.get("fixture") or {}).get("timestamp") or 0)), reverse=True)
    return out[:need]


def main() -> None:
    ap = argparse.ArgumentParser(description="Debug: últimos jogos de árbitro direto na API.")
    ap.add_argument("referee", help='Nome do árbitro, ex: "D. England"')
    ap.add_argument("-n", "--need", type=int, default=10, help="Quantidade desejada (1..50)")
    args = ap.parse_args()

    need = max(1, min(int(args.need), 50))
    key = _read_key()
    if not key:
        print("Erro: defina FOOTBALL_API_KEY ou crie data/football_api_key.txt", file=sys.stderr)
        sys.exit(2)

    s = requests.Session()
    q = args.referee.strip()

    print(f"Consulta por árbitro: {q!r}")
    diag: Dict[str, int] = {
        "referee_query_full": 0,
        "referee_query_lastname": 0,
        "league_scan": 0,
        "duplicates_ignored": 0,
    }
    games = _fetch_by_referee_query(s, key, q, need)
    diag["referee_query_full"] = len(games)
    if len(games) < need:
        last_name = q.split()[-1] if q.split() else q
        if last_name and last_name.lower() != q.lower():
            more = _fetch_by_referee_query(s, key, last_name, need)
            diag["referee_query_lastname"] = len(more)
            seen = {int((fx.get("fixture") or {}).get("id") or 0) for fx in games}
            for fx in more:
                try:
                    iid = int((fx.get("fixture") or {}).get("id"))
                except (TypeError, ValueError):
                    continue
                if iid in seen:
                    diag["duplicates_ignored"] += 1
                    continue
                seen.add(iid)
                games.append(fx)
            games.sort(key=lambda x: int(((x.get("fixture") or {}).get("timestamp") or 0)), reverse=True)
            games = games[:need]
    if len(games) < need:
        print("Aviso: parâmetro referee indisponível/limitado; tentando varredura por ligas...")
        more = _fetch_global_league_scan(s, key, q, need)
        diag["league_scan"] = len(more)
        seen = {int((fx.get("fixture") or {}).get("id") or 0) for fx in games}
        for fx in more:
            try:
                iid = int((fx.get("fixture") or {}).get("id"))
            except (TypeError, ValueError):
                continue
            if iid in seen:
                diag["duplicates_ignored"] += 1
                continue
            seen.add(iid)
            games.append(fx)
        games.sort(key=lambda x: int(((x.get("fixture") or {}).get("timestamp") or 0)), reverse=True)
        games = games[:need]
    print("Diagnóstico de fontes:")
    print(f"  - referee=texto (nome completo): {diag['referee_query_full']}")
    print(f"  - referee=texto (sobrenome): {diag['referee_query_lastname']}")
    print(f"  - varredura por ligas: {diag['league_scan']}")
    print(f"  - duplicados ignorados no merge: {diag['duplicates_ignored']}")
    print(f"Jogos encontrados: {len(games)}")
    print("-" * 120)
    for i, fx in enumerate(games, 1):
        print(
            f"{i:2}. {_fmt_date(fx)} | {_league(fx)} | {_teams(fx)} | {_score(fx)} | referee='{_ref_name(fx)}'"
        )


if __name__ == "__main__":
    main()
