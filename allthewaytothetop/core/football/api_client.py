"""
Cliente HTTP para v3.football.api-sports.io (API-Sports).
"""
from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from core.shared.paths import get_football_api_key

BASE_URL = "https://v3.football.api-sports.io"

# Parâmetro `status` em /fixtures para jogos terminados. `FT` sozinho omite
# prolongamento/pénáltis e, em muitas contas, devolve lista vazia indevidamente.
# Ref.: documentação / posts API-Football (FT-AET-PEN).
API_FIXTURE_STATUS_FINISHED = "FT-AET-PEN"

# Máximo `last` em **cada** pedido GET /fixtures. Com last≈100 alguns planos/rotas
# devolvem 0 itens, enquanto last≤32 responde (amostra: o diagnóstico a 10 funcionava; a
# análise a 100 falhava). A lógica agrega jogos de vários pedidos em `pool` até
# atingir a janela desejada.
API_FIXTURES_LAST_PER_REQUEST = 32


def _fixtures_last_request_param(n: int) -> int:
    n = int(n)
    if n < 1:
        return 1
    return min(API_FIXTURES_LAST_PER_REQUEST, min(100, n))


def _league_ids_for_team_country_name(country: str) -> List[int]:
    """
    Ids de liga sénior na API v3 (API-Football) quando /leagues?team= devolve vazio
    mas o clube joga nesse país. Valores aproximados: La Liga=140, PL=39, etc.
    """
    c0 = (country or "").strip().lower()
    c = "".join(
        ch
        for ch in unicodedata.normalize("NFD", c0)
        if unicodedata.category(ch) != "Mn"
    )
    if "spain" in c or c in ("es",) or "espa" in c:
        return [140, 141]
    if "portugal" in c or c in ("pt",):
        return [94, 95]
    if "england" in c or c in ("gb-eng",):
        return [39, 40]
    if "germany" in c or c in ("de",):
        return [78, 79]
    if "france" in c or c in ("fr",):
        return [61, 62]
    if "italy" in c or c in ("it",):
        return [135, 136]
    if "netherlands" in c or c in ("nl",):
        return [88, 89]
    if "brazil" in c or c in ("br",) or "brasil" in c:
        return [71, 72]
    return []


def _to_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "-"):
        return None
    s = s.rstrip("%").strip()
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


class FootballAPIError(Exception):
    pass


class FootballAPIClient:
    def __init__(self, api_key: Optional[str] = None, timeout: int = 45):
        self._key = (api_key or get_football_api_key() or "").strip()
        self.timeout = timeout
        self._session = requests.Session()
        self._last_request_at = 0.0
        self._min_interval = 0.05
        # requests.Session não é thread-safe: UI + QThread (árbitro, cálculo) usam o mesmo cliente.
        self._http_lock = threading.Lock()

    def set_key(self, key: str) -> None:
        self._key = (key or "").strip()

    def has_key(self) -> bool:
        return bool(self._key)

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._key:
            raise FootballAPIError(
                "Chave API em falta. Defina FOOTBALL_API_KEY ou crie data/football_api_key.txt com a chave."
            )
        with self._http_lock:
            elapsed = time.time() - self._last_request_at
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            url = f"{BASE_URL}/{path.lstrip('/')}"
            r = self._session.get(
                url,
                params=params or {},
                headers={"x-apisports-key": self._key},
                timeout=self.timeout,
            )
            self._last_request_at = time.time()
            if r.status_code == 429:
                raise FootballAPIError(
                    "API devolveu HTTP 429 (limite de pedidos por minuto). "
                    "Aguarda ~60 s e tenta de novo; o plano diario nao e o mesmo que req/min."
                )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                return {"response": []}
            # A API v3 devolve "response" (array). Raramente, proxies/versões
            # antigas alinham noutro campo — normalizamos.
            if "response" not in data:
                for alt in ("data", "results"):
                    v = data.get(alt)
                    if isinstance(v, list):
                        data = {**data, "response": v}
                        break
            return data

    @staticmethod
    def _api_errors(data: Dict[str, Any]) -> str:
        err = data.get("errors")
        if not err:
            return ""
        if isinstance(err, dict):
            return "; ".join(f"{k}: {v}" for k, v in err.items())
        return str(err)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = self._request(path, params)
        e = self._api_errors(data)
        if e and not data.get("response"):
            raise FootballAPIError(e)
        return data

    def search_teams(self, name: str) -> List[Dict[str, Any]]:
        # O endpoint /teams?search= não aceita o parâmetro "limit" (API v3 retorna erro).
        q = (name or "").strip()
        if not q:
            return []
        d = self._get("teams", params={"search": q})
        return [x.get("team") for x in (d.get("response") or []) if x.get("team")]

    def get_team_info(self, team_id: int) -> Optional[Dict[str, Any]]:
        d = self._get("teams", params={"id": team_id})
        arr = d.get("response") or []
        if not arr:
            return None
        t = arr[0]
        return t.get("team") if isinstance(t, dict) else None

    @staticmethod
    def _default_season_guess() -> int:
        """Ano de início de época típico (Jan–Jun = ano−1; Jul–Dez = ano), sem import circular."""
        dt = datetime.now(timezone.utc)
        return int(dt.year) if int(dt.month) >= 7 else int(dt.year) - 1

    @staticmethod
    def fixture_id_from_item(fx: Any) -> Optional[int]:
        """Id do jogo: `fixture.id` (normal) ou formatosachatados (alguns proxies)."""
        if not isinstance(fx, dict):
            return None
        f = fx.get("fixture")
        if isinstance(f, dict) and f.get("id") is not None:
            try:
                return int(f["id"])
            except (TypeError, ValueError):
                pass
        for k in ("id", "fixture_id"):
            v = fx.get(k)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return None

    @staticmethod
    def _fixture_ts(fx: Dict[str, Any]) -> int:
        f = fx.get("fixture") or {}
        ts = f.get("timestamp")
        if ts is not None:
            try:
                return int(ts)
            except (TypeError, ValueError):
                pass
        return 0

    def _get_fixtures_last_by_leagues(
        self, team_id: int, last: int, status: str
    ) -> List[Dict[str, Any]]:
        """
        Estratégia principal para muitas contas: descobre ligas atuais do clube
        e chama /fixtures?team&league&season&… — mais fiável do que
        /fixtures?team&last&status sem liga.
        """
        last = max(1, min(int(last), 100))
        tid = int(team_id)
        y0 = self._default_season_guess()
        now_y = int(datetime.now(timezone.utc).year)
        done_status: Set[str] = {
            "FT",
            "AET",
            "PEN",
            "PST",
            "CANC",
            "ABD",
            "AWD",
            "WO",
        }
        st_order = list(
            dict.fromkeys(
                s
                for s in (
                    status,
                    API_FIXTURE_STATUS_FINISHED,
                    "FT",
                )
                if s
            )
        )
        seen: Set[int] = set()
        pool: List[Dict[str, Any]] = []
        for league_params in (
            {"team": tid, "current": "true"},
            {"team": tid, "current": "1"},
            {"team": tid},
        ):
            if len(pool) >= last:
                break
            try:
                d_l = self._get("leagues", params=league_params)
            except FootballAPIError:
                continue
            rows = d_l.get("response") or []
            if not isinstance(rows, list) or not rows:
                continue
            for row in rows[:15]:
                if not isinstance(row, dict):
                    continue
                lid = (row.get("league") or {}).get("id")
                if lid is None:
                    continue
                years: Set[int] = set()
                for s in (row.get("seasons") or []):
                    if not isinstance(s, dict):
                        continue
                    yv = s.get("year")
                    if yv is not None:
                        try:
                            years.add(int(yv))
                        except (TypeError, ValueError):
                            pass
                for fallback_y in (y0, y0 - 1, now_y, now_y - 1, y0 + 1):
                    years.add(fallback_y)
                year_list = sorted(years, reverse=True)[:5]
                for sy in year_list:
                    if len(pool) >= last:
                        break
                    for st in st_order:
                        if len(pool) >= last:
                            break
                        try:
                            d2 = self._get(
                                "fixtures",
                                params={
                                    "team": tid,
                                    "league": int(lid),
                                    "season": int(sy),
                                    "last": _fixtures_last_request_param(last + 20),
                                    "status": st,
                                },
                            )
                        except FootballAPIError:
                            continue
                        for fx in d2.get("response") or []:
                            if not isinstance(fx, dict):
                                continue
                            iid = self.fixture_id_from_item(fx)
                            if iid is not None and iid not in seen:
                                seen.add(iid)
                                pool.append(fx)
                        if len(pool) >= last:
                            break
                    if len(pool) < last:
                        try:
                            d3 = self._get(
                                "fixtures",
                                params={
                                    "team": tid,
                                    "league": int(lid),
                                    "season": int(sy),
                                    "last": _fixtures_last_request_param(last + 20),
                                },
                            )
                        except FootballAPIError:
                            pass
                        else:
                            for fx in d3.get("response") or []:
                                if not isinstance(fx, dict):
                                    continue
                                sh = str(
                                    (
                                        (fx.get("fixture") or {}).get("status")
                                        or {}
                                    ).get("short")
                                    or ""
                                ).upper()
                                if sh not in done_status:
                                    continue
                                iid = self.fixture_id_from_item(fx)
                                if iid is not None and iid not in seen:
                                    seen.add(iid)
                                    pool.append(fx)
            if len(pool) >= last:
                break
        if not pool:
            return []
        pool.sort(key=self._fixture_ts, reverse=True)
        return pool[:last]

    def _get_fixtures_last_national_ladders(
        self, team_id: int, last: int, status: str
    ) -> List[Dict[str, Any]]:
        """
        Quando /leagues?team= devolve vazio mas GET /teams?id= tem «country»,
        tenta ligas típicas (ex. Espanha → La Liga 140, Segunda 141).
        """
        last = max(1, min(int(last), 100))
        tid = int(team_id)
        try:
            team = self.get_team_info(tid)
        except FootballAPIError:
            return []
        if not isinstance(team, dict):
            return []
        country = (team.get("country") or "").strip()
        lids = _league_ids_for_team_country_name(country)
        if not lids:
            return []
        y0 = self._default_season_guess()
        now_y = int(datetime.now(timezone.utc).year)
        years: Set[int] = {y0, y0 - 1, y0 + 1, now_y, now_y - 1, now_y - 2}
        done_status: Set[str] = {
            "FT",
            "AET",
            "PEN",
            "PST",
            "CANC",
            "ABD",
            "AWD",
            "WO",
        }
        st_order = list(
            dict.fromkeys(
                s for s in (status, API_FIXTURE_STATUS_FINISHED, "FT") if s
            )
        )
        seen: Set[int] = set()
        pool: List[Dict[str, Any]] = []
        for lid in lids:
            if len(pool) >= last:
                break
            for sy in sorted(years, reverse=True):
                if len(pool) >= last:
                    break
                for st in st_order:
                    if len(pool) >= last:
                        break
                    try:
                        d2 = self._get(
                            "fixtures",
                            params={
                                "team": tid,
                                "league": int(lid),
                                "season": int(sy),
                                "last": _fixtures_last_request_param(last + 20),
                                "status": st,
                            },
                        )
                    except FootballAPIError:
                        continue
                    for fx in d2.get("response") or []:
                        if not isinstance(fx, dict):
                            continue
                        iid = self.fixture_id_from_item(fx)
                        if iid is not None and iid not in seen:
                            seen.add(iid)
                            pool.append(fx)
                if len(pool) < last:
                    try:
                        d3 = self._get(
                            "fixtures",
                            params={
                                "team": tid,
                                "league": int(lid),
                                "season": int(sy),
                                "last": _fixtures_last_request_param(last + 20),
                            },
                        )
                    except FootballAPIError:
                        pass
                    else:
                        for fx in d3.get("response") or []:
                            if not isinstance(fx, dict):
                                continue
                            sh = str(
                                (
                                    (fx.get("fixture") or {}).get("status")
                                    or {}
                                ).get("short")
                                or ""
                            ).upper()
                            if sh not in done_status:
                                continue
                            iid = self.fixture_id_from_item(fx)
                            if iid is not None and iid not in seen:
                                seen.add(iid)
                                pool.append(fx)
        if not pool:
            return []
        pool.sort(key=self._fixture_ts, reverse=True)
        return pool[:last]

    def get_fixtures_last(
        self,
        team_id: int,
        last: int = 10,
        *,
        status: str = API_FIXTURE_STATUS_FINISHED,
        season: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Últimos N jogos do clube (jogos terminados: por defeito FT-AET-PEN).
        - Com `season`: só essa época.
        - Sem `season`: 1) /leagues?team + /fixtures?team&league&season (mais fiável);
          2) cadeia team+last / team+season / page / from–to;
          3) ligas por país (GET /teams?id=) se tudo o resto falhar.
        """
        last = max(1, min(int(last), 100))
        if season is not None:
            return self._get_fixtures_last_one_season(
                int(team_id), last, status, int(season)
            )
        # 1) Liga+época (muitas contas não devolvem nada com team+last global)
        by_l = self._get_fixtures_last_by_leagues(int(team_id), last, status)
        if by_l:
            return by_l
        # 2) Cadeia team+last / team+season / page / from-to
        out = self._get_fixtures_last_cross_season(int(team_id), last, status)
        if out:
            return out
        # Contas / planos em que a cadeia multi-parâmetros devolve 0: tenta épocas explícitas.
        y0 = self._default_season_guess()
        ny = int(datetime.now(timezone.utc).year)
        for sy in (y0, y0 - 1, y0 + 1, ny, ny - 1):
            try:
                extra = self._get_fixtures_last_one_season(int(team_id), last, status, int(sy))
            except FootballAPIError:
                continue
            if extra:
                ex = list(extra)
                ex.sort(key=self._fixture_ts, reverse=True)
                return ex[:last]
        # Sem `status` (rejeições a `status=FT` com last+season).
        for sy in (y0, y0 - 1, y0 + 1):
            try:
                d = self._get(
                    "fixtures",
                    params={
                        "team": int(team_id),
                        "season": int(sy),
                        "last": _fixtures_last_request_param(last),
                    },
                )
            except FootballAPIError:
                continue
            arr = list(d.get("response") or [])
            if not arr:
                continue
            done_status: Set[str] = {
                "FT",
                "AET",
                "PEN",
                "PST",
                "CANC",
                "ABD",
                "AWD",
                "WO",
            }
            good = [
                fx
                for fx in arr
                if str(((fx.get("fixture") or {}).get("status") or {}).get("short") or "")
                .upper()
                in done_status
            ]
            if good:
                g = list(good)
                g.sort(key=self._fixture_ts, reverse=True)
                return g[:last]
        nat = self._get_fixtures_last_national_ladders(int(team_id), last, status)
        if nat:
            return nat
        dbg = (os.environ.get("FOOTBALL_DEBUG_FIXTURES") or "").strip().lower()
        if dbg in ("1", "true", "yes", "y", "on"):
            print(
                f"[FOOTBALL_DEBUG] get_fixtures_last empty: team_id={team_id} last={last} "
                f"status={status!r} by_l={len(by_l)} cross_season={len(out)} nat=0"
            )
        # Última tentativa: a mesma rota muitas vezes responde com last=10 e falha com last alto.
        if int(last) > 10:
            small = self.get_fixtures_last(team_id, last=10, status=status)
            if small:
                return small
        return []

    def _get_fixtures_last_one_season(
        self, team_id: int, last: int, status: str, season: int
    ) -> List[Dict[str, Any]]:
        d = self._get(
            "fixtures",
            params={
                "team": team_id,
                "season": season,
                "last": _fixtures_last_request_param(last),
                "status": status,
            },
        )
        return list(d.get("response") or [])

    def _get_fixtures_last_raw(
        self,
        team_id: int,
        last: int,
        status: str,
        season: Optional[int],
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "team": int(team_id),
            "last": _fixtures_last_request_param(int(last)),
            "status": status,
        }
        if season is not None:
            params["season"] = int(season)
        d = self._get("fixtures", params=params)
        return list(d.get("response") or [])

    def _get_fixtures_last_cross_season(
        self, team_id: int, last: int, status: str
    ) -> List[Dict[str, Any]]:
        seen: Set[int] = set()
        pool: List[Dict[str, Any]] = []

        def _add_batch(batch: List[Dict[str, Any]]) -> None:
            for fx in batch:
                iid = self.fixture_id_from_item(fx)
                if iid is None or iid in seen:
                    continue
                seen.add(iid)
                pool.append(fx)

        try:
            _add_batch(
                self._get_fixtures_last_raw(
                    team_id, _fixtures_last_request_param(last + 20), status, None
                )
            )
        except FootballAPIError:
            pass
        y0 = self._default_season_guess()
        now_year = int(datetime.now(timezone.utc).year)
        # Inclui explicitamente o ano civil atual (ligas calendário, ex. Brasil)
        # e o ano de época típico (ligas europeias), sem duplicar.
        season_candidates: List[int] = []
        for y in (now_year, y0):
            if y not in season_candidates:
                season_candidates.append(y)
        for offset in range(1, 20):
            y = y0 - offset
            if y not in season_candidates:
                season_candidates.append(y)
        for season_year in season_candidates:
            if len(pool) >= last:
                break
            try:
                batch = self._get_fixtures_last_raw(
                    team_id, _fixtures_last_request_param(100), status, season_year
                )
            except FootballAPIError:
                continue
            _add_batch(batch)
        # Fallback robusto: alguns times/planos não respondem bem a team+last+status.
        # Nestes casos, varremos por team+season+page e filtramos localmente jogos concluídos.
        if len(pool) < last:
            done_status: Set[str] = {
                "FT",
                "AET",
                "PEN",
                "PST",
                "CANC",
                "ABD",
                "AWD",
                "WO",
            }
            season_fallback: List[int] = []
            for y in (now_year, y0, y0 - 1, y0 - 2, y0 - 3, y0 - 4, y0 - 5):
                if y not in season_fallback:
                    season_fallback.append(y)
            for season in season_fallback:
                if len(pool) >= last:
                    break
                page = 1
                max_pages = 1
                while page <= max_pages and len(pool) < last:
                    try:
                        d = self._get(
                            "fixtures",
                            params={"team": int(team_id), "season": int(season), "page": int(page)},
                        )
                    except FootballAPIError:
                        break
                    arr = list(d.get("response") or [])
                    if not arr:
                        break
                    for fx in arr:
                        st = ((fx.get("fixture") or {}).get("status") or {}).get("short")
                        short = str(st or "").upper()
                        if short not in done_status:
                            continue
                        _add_batch([fx])
                    paging = d.get("paging") if isinstance(d, dict) else None
                    if isinstance(paging, dict):
                        try:
                            total_pages = int(paging.get("total") or 1)
                        except (TypeError, ValueError):
                            total_pages = 1
                        max_pages = max(1, min(total_pages, 25))
                    page += 1
        # Último fallback: alguns planos devolvem vazio com `status=FT` mesmo havendo jogos.
        # Tenta `team+last` sem status e filtra localmente os concluídos.
        if len(pool) < last:
            try:
                d = self._get(
                    "fixtures",
                    params={"team": int(team_id), "last": _fixtures_last_request_param(100)},
                )
                arr = list(d.get("response") or [])
            except FootballAPIError:
                arr = []
            if arr:
                done_status: Set[str] = {
                    "FT",
                    "AET",
                    "PEN",
                    "PST",
                    "CANC",
                    "ABD",
                    "AWD",
                    "WO",
                }
                filt = []
                for fx in arr:
                    st = ((fx.get("fixture") or {}).get("status") or {}).get("short")
                    short = str(st or "").upper()
                    if short in done_status:
                        filt.append(fx)
                _add_batch(filt)
        # Alguns planos respondem a `from`+`to`+`team` quando `last`/`status` falham.
        if len(pool) < last:
            end = datetime.now(timezone.utc).date()
            for days in (400, 800):
                if len(pool) >= last:
                    break
                start = end - timedelta(days=days)
                try:
                    d = self._get(
                        "fixtures",
                        params={
                            "team": int(team_id),
                            "from": start.isoformat(),
                            "to": end.isoformat(),
                        },
                    )
                except FootballAPIError:
                    continue
                arr = list(d.get("response") or [])
                if not arr:
                    continue
                done_status: Set[str] = {
                    "FT",
                    "AET",
                    "PEN",
                    "PST",
                    "CANC",
                    "ABD",
                    "AWD",
                    "WO",
                }
                filt2: List[Dict[str, Any]] = []
                for fx in arr:
                    st = ((fx.get("fixture") or {}).get("status") or {}).get("short")
                    short = str(st or "").upper()
                    if short in done_status:
                        filt2.append(fx)
                _add_batch(filt2)
        pool.sort(key=self._fixture_ts, reverse=True)
        return pool[:last]

    def get_headtohead(
        self,
        team1_id: int,
        team2_id: int,
        last: int = 30,
    ) -> List[Dict[str, Any]]:
        h2h = f"{int(team1_id)}-{int(team2_id)}"
        d = self._get("fixtures/headtohead", params={"h2h": h2h, "last": min(last, 100)})
        return list(d.get("response") or [])

    @staticmethod
    def _is_fixture_between(fx: Dict[str, Any], a: int, b: int) -> bool:
        h = (fx.get("teams") or {}).get("home") or {}
        aw = (fx.get("teams") or {}).get("away") or {}
        hid, aid = h.get("id"), aw.get("id")
        if not hid or not aid:
            return False
        return {int(hid), int(aid)} == {int(a), int(b)}

    @staticmethod
    def _fixture_is_not_finished(fx: Dict[str, Any]) -> bool:
        st = (fx.get("fixture") or {}).get("status") or {}
        short = (st.get("short") or "").upper()
        if not short:
            return True
        done: Set[str] = {
            "FT",
            "AET",
            "PEN",
            "PST",
            "CANC",
            "ABD",
            "AWD",
            "WO",
        }
        return short not in done

    @staticmethod
    def _fixture_is_future(fx: Dict[str, Any]) -> bool:
        f = fx.get("fixture") or {}
        ts = f.get("timestamp")
        if ts is None:
            return True
        try:
            t = int(ts)
        except (TypeError, ValueError):
            return True
        return t > int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def _referee_str(fx: Optional[Dict[str, Any]]) -> Optional[str]:
        if not fx:
            return None
        r = (fx.get("fixture") or {}).get("referee")
        if r is None:
            return None
        s = str(r).strip()
        return s if s else None

    def find_referee_next_match_between(
        self,
        team1_id: int,
        team2_id: int,
        season: Optional[int] = None,
    ) -> Optional[str]:
        """
        Tenta achar o próximo jogo (agendado) entre as duas equipas e devolver
        o nome do árbitro, se a API o tiver. Senão None (ainda vazio / não publicado).
        Usa /fixtures?team=…&next= e, em fallback, H2H ordenado por data.
        """
        a, b = int(team1_id), int(team2_id)
        if a == b:
            return None

        def _scan_next(use_season: Optional[int]):
            for anchor in (a, b):
                # Janela larga: o próximo jogo A vs B pode não estar entre os 20–30
                # primeiros "next" de uma equipa com muitos calendários (várias provas).
                params: Dict[str, Any] = {"team": anchor, "next": 60}
                if use_season is not None:
                    params["season"] = int(use_season)
                try:
                    d = self._get("fixtures", params=params)
                except FootballAPIError:
                    continue
                for fx in d.get("response") or []:
                    if not self._is_fixture_between(fx, a, b):
                        continue
                    if not self._fixture_is_not_finished(fx):
                        continue
                    if not self._fixture_is_future(fx):
                        continue
                    return True, self._referee_str(fx)
            return False, None

        found, val = _scan_next(season)
        if found:
            return val
        if season is not None:
            found, val = _scan_next(None)
            if found:
                return val

        try:
            h2h = self.get_headtohead(a, b, last=40)
        except FootballAPIError:
            h2h = []
        best: Optional[Dict[str, Any]] = None
        best_ts: int = 0
        for fx in h2h:
            if not self._is_fixture_between(fx, a, b):
                continue
            if not self._fixture_is_not_finished(fx) or not self._fixture_is_future(fx):
                continue
            ts = (fx.get("fixture") or {}).get("timestamp") or 0
            try:
                tsi = int(ts)
            except (TypeError, ValueError):
                tsi = 0
            if tsi >= best_ts:
                best_ts, best = tsi, fx
        if best:
            return self._referee_str(best)
        return None

    @staticmethod
    def _norm_ref_name(s: str) -> str:
        s = (s or "").lower().replace(".", " ")
        s = re.sub(r"[\s,;]+", " ", s).strip()
        return s

    @staticmethod
    def _strip_accents(s: str) -> str:
        if not s:
            return ""
        nfd = unicodedata.normalize("NFD", s)
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

    def referee_name_matches(self, query: str, fixture_ref: str) -> bool:
        """
        Compara o nome vindo do utilizador (ex. «J. Sanchez») com o do fixture
        (ex. «Jose Sanchez», «J. Sánchez»). Iniciais + apelido; apelido sem
        acentos.
        """
        a, b = self._norm_ref_name(query), self._norm_ref_name(fixture_ref or "")
        if not a or not b:
            return False
        af, bf = self._strip_accents(a), self._strip_accents(b)
        if af == bf:
            return True
        if af in bf or bf in af:
            return True
        ta, tb = af.split(), bf.split()
        if not ta or not tb:
            return False
        la, lb = ta[-1], tb[-1]
        if len(la) < 2 or len(lb) < 2:
            return False
        # APIs diferentes podem devolver "England, Darren" (apelido primeiro).
        # Nestes casos o apelido do query pode não estar no fim de `tb`.
        surname_q = self._strip_accents(la)
        tb_norm = [self._strip_accents(x) for x in tb]
        if surname_q not in tb_norm:
            return False
        if len(ta) >= 2 and len(ta[0]) == 1 and ta[0].isalpha():
            ini = ta[0].lower()
            has_ini = any(x and x.lower().startswith(ini) for x in tb if self._strip_accents(x) != surname_q)
            if not has_ini:
                return False
        return True

    @staticmethod
    def _referee_query_variants(q: str) -> List[str]:
        """
        Formas extra para o parâmetro search/referee da API (o filtro fiel ao nome
        continua a ser `referee_name_matches(q_original, ref)`).
        """
        s = (q or "").strip()
        if not s:
            return []
        toks = re.sub(r"[\.,;]", " ", s).split()
        toks = [t.lower() for t in toks if t]
        alts: List[str] = []
        if toks and len(toks[-1]) > 2:
            alts.append(toks[-1])
        seen = {s.lower()}
        u: List[str] = []
        for x in alts:
            if x and x not in seen:
                seen.add(x)
                u.append(x)
        return u

    def _referee_name_hints_from_api(self, q: str) -> List[str]:
        """
        Se a API tiver /referees?search=, junta possíveis nomes completos.
        (Algumas contas têm; se não existir, retorna vazio em silêncio.)
        """
        toks = self._norm_ref_name(q).split()
        if not toks or len(toks[-1]) < 3:
            return []
        last = toks[-1]
        for params in ({"search": last},):
            try:
                d = self._get("referees", params=params)
            except (FootballAPIError, OSError, requests.RequestException):
                continue
            out: List[str] = []
            for item in d.get("response") or []:
                if not isinstance(item, dict):
                    continue
                n = item.get("name")
                if not n and isinstance(item.get("referee"), dict):
                    n = (item.get("referee") or {}).get("name")
                if not n:
                    continue
                n = str(n).strip()
                if n and self.referee_name_matches(q, n):
                    out.append(n)
            if out:
                return out
        return []

    def _referee_ids_from_api(self, q: str) -> List[int]:
        """
        Tenta descobrir IDs de árbitro no endpoint /referees para usar em
        /fixtures?referee=<id> (mais estável em alguns planos do que nome livre).
        """
        toks = self._norm_ref_name(q).split()
        if not toks or len(toks[-1]) < 3:
            return []
        last = toks[-1]
        out: List[int] = []
        for params in ({"search": last},):
            try:
                d = self._get("referees", params=params)
            except (FootballAPIError, OSError, requests.RequestException):
                continue
            for item in d.get("response") or []:
                if not isinstance(item, dict):
                    continue
                ref_obj = item.get("referee") if isinstance(item.get("referee"), dict) else {}
                name = item.get("name") or ref_obj.get("name")
                if not name or not self.referee_name_matches(q, str(name)):
                    continue
                rid = item.get("id")
                if rid is None:
                    rid = ref_obj.get("id")
                try:
                    iid = int(rid)
                except (TypeError, ValueError):
                    continue
                out.append(iid)
            if out:
                break
        # remover duplicados mantendo ordem
        return list(dict.fromkeys(out))

    def _enrich_fixtures_referee_data(self, fxs: List[Dict[str, Any]]) -> None:
        """
        Muitas respostas de /fixtures?league=…&page= (e similares) vêm com
        `fixture.referee` vazio; o mesmo jogo em /fixtures?ids=… traz o nome.
        Corrige in-place, em lotes de até 20 (limite da API).
        """
        if not fxs:
            return
        id_to_fx: Dict[int, List[Dict[str, Any]]] = {}
        for fx in fxs:
            if self._referee_str(fx):
                continue
            fid = (fx.get("fixture") or {}).get("id")
            if fid is None:
                continue
            try:
                iid = int(fid)
            except (TypeError, ValueError):
                continue
            id_to_fx.setdefault(iid, []).append(fx)
        if not id_to_fx:
            return
        ids_list = list(id_to_fx.keys())
        for i in range(0, len(ids_list), 20):
            chunk = ids_list[i : i + 20]
            try:
                d = self._get("fixtures", params={"ids": "-".join(str(x) for x in chunk)})
            except FootballAPIError:
                continue
            for item in d.get("response") or []:
                ref = self._referee_str(item)
                if not ref:
                    continue
                fi = (item.get("fixture") or {}).get("id")
                if fi is None:
                    continue
                try:
                    iid = int(fi)
                except (TypeError, ValueError):
                    continue
                for target in id_to_fx.get(iid, []):
                    fobj = target.get("fixture")
                    if isinstance(fobj, dict):
                        fobj["referee"] = ref

    def get_fixtures_by_referee(
        self,
        referee_name: str,
        need: int,
        anchor_team_ids: Optional[Tuple[int, ...]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Tenta juntar até `need` jogos FT arbitrados por um nome compatível.
        1) Parâmetro `referee` se a API aceitar. 2) Amostra em ligas/épocas.
        `fixture.referee` em listagens vem muitas vezes vazio — usa ids para preencher.
        """
        need = max(1, min(int(need), 100))
        q = (referee_name or "").strip()
        if not q:
            return []
        seen: Set[int] = set()
        pool: List[Dict[str, Any]] = []

        # Jogos concluídos (inclui prolongamento/penáltis).
        _ft_done = "FT-AET-PEN"

        def _take_from_list(batch: List[Dict[str, Any]], trust_referee: bool = False) -> None:
            for fx in batch:
                if len(pool) >= need:
                    return
                if not trust_referee:
                    ref = self._referee_str(fx) or ""
                    if not self.referee_name_matches(q, ref):
                        continue
                fid = (fx.get("fixture") or {}).get("id")
                if not fid:
                    continue
                try:
                    iid = int(fid)
                except (TypeError, ValueError):
                    continue
                if iid in seen:
                    continue
                seen.add(iid)
                pool.append(fx)

        if anchor_team_ids:
            for aid in anchor_team_ids:
                if len(pool) >= need:
                    break
                try:
                    last_f = self.get_fixtures_last(
                        int(aid), last=min(200, need * 5), status=API_FIXTURE_STATUS_FINISHED, season=None
                    )
                except FootballAPIError:
                    continue
                self._enrich_fixtures_referee_data(last_f)
                _take_from_list(last_f)
        # Termos a tentar no endpoint (apelido só ajuda quando search devolve muita coisa a filtrar)
        try:
            name_hints = self._referee_name_hints_from_api(q)
        except Exception:
            name_hints = []
        try:
            referee_ids = self._referee_ids_from_api(q)
        except Exception:
            referee_ids = []
        search_terms: List[str] = [q]
        for v in self._referee_query_variants(q):
            if v.lower() not in {t.lower() for t in search_terms}:
                search_terms.append(v)
        for h in name_hints:
            if h.lower() not in {t.lower() for t in search_terms}:
                search_terms.append(h)
        for rid in referee_ids:
            if len(pool) >= need:
                break
            try:
                d = self._get(
                    "fixtures",
                    params={"referee": int(rid), "status": _ft_done, "last": 200},
                )
                r = list(d.get("response") or [])
                self._enrich_fixtures_referee_data(r)
                _take_from_list(r, trust_referee=True)
            except FootballAPIError:
                continue
        # Em muitos planos, `referee=<id>&last=` devolve parcial.
        # Complementa por épocas paginadas para o mesmo ID de árbitro.
        now_year = int(datetime.now(timezone.utc).year)
        season_scan: List[int] = []
        for y in (
            now_year,
            now_year - 1,
            now_year - 2,
            now_year - 3,
            now_year - 4,
            now_year - 5,
            now_year - 6,
            now_year - 7,
            now_year - 8,
            now_year - 9,
        ):
            if y not in season_scan:
                season_scan.append(y)
        for rid in referee_ids:
            if len(pool) >= need:
                break
            for season in season_scan:
                if len(pool) >= need:
                    break
                page = 1
                max_pages = 1
                while page <= max_pages and len(pool) < need:
                    try:
                        d = self._get(
                            "fixtures",
                            params={
                                "referee": int(rid),
                                "season": int(season),
                                "status": _ft_done,
                                "page": int(page),
                            },
                        )
                    except FootballAPIError:
                        break
                    raw = list(d.get("response") or [])
                    if not raw:
                        break
                    self._enrich_fixtures_referee_data(raw)
                    _take_from_list(raw, trust_referee=True)
                    paging = d.get("paging") if isinstance(d, dict) else None
                    if isinstance(paging, dict):
                        try:
                            total_pages = int(paging.get("total") or 1)
                        except (TypeError, ValueError):
                            total_pages = 1
                        max_pages = max(1, min(total_pages, 20))
                    page += 1
        for pval in search_terms:
            if len(pool) >= need:
                break
            for pkey in ("referee", "search"):
                if len(pool) >= need:
                    break
                try:
                    d = self._get(
                        "fixtures",
                        params={pkey: pval, "status": _ft_done, "last": 200},
                    )
                    r = list(d.get("response") or [])
                    self._enrich_fixtures_referee_data(r)
                    if pkey == "referee":
                        # Se a API já filtrou por `referee=...`, não exigir nome textual
                        # no payload (muitas respostas vêm com fixture.referee vazio).
                        _take_from_list(r, trust_referee=True)
                    else:
                        good = [
                            fx
                            for fx in r
                            if self.referee_name_matches(q, self._referee_str(fx) or "")
                        ]
                        if good:
                            _take_from_list(good)
                except FootballAPIError:
                    continue
        # Fallback adicional por ID: paginação sem season (alguns planos retornam
        # mais jogos aqui do que em referee+season).
        for rid in referee_ids:
            if len(pool) >= need:
                break
            page = 1
            max_pages = 1
            while page <= max_pages and len(pool) < need:
                try:
                    d = self._get(
                        "fixtures",
                        params={"referee": int(rid), "status": _ft_done, "page": int(page)},
                    )
                except FootballAPIError:
                    break
                raw = list(d.get("response") or [])
                if not raw:
                    break
                self._enrich_fixtures_referee_data(raw)
                _take_from_list(raw, trust_referee=True)
                paging = d.get("paging") if isinstance(d, dict) else None
                if isinstance(paging, dict):
                    try:
                        total_pages = int(paging.get("total") or 1)
                    except (TypeError, ValueError):
                        total_pages = 1
                    max_pages = max(1, min(total_pages, 20))
                page += 1
        y0 = self._default_season_guess()
        now_year = int(datetime.now(timezone.utc).year)
        # Brasil (71/72) + copas; mistura com top europeus (ids API-Sports v3)
        # (D1F / UWCL: adiciona IDs vistos no dashboard, se ainda faltar amostra)
        leagues = (61, 62, 66, 140, 39, 135, 78, 88, 94, 144, 179, 71, 72, 128, 620, 45, 40, 3, 2, 6)
        season_scan: List[int] = []
        for y in (now_year, y0, y0 - 1, y0 - 2, y0 - 3):
            if y not in season_scan:
                season_scan.append(y)
        for season in season_scan:
            for lid in leagues:
                if len(pool) >= need:
                    break
                page = 1
                max_pages = 5
                while page <= max_pages:
                    if len(pool) >= need:
                        break
                    try:
                        d = self._get(
                            "fixtures",
                            params={
                                "league": lid,
                                "season": season,
                                "status": _ft_done,
                                "page": page,
                            },
                        )
                    except FootballAPIError:
                        break
                    raw = list(d.get("response") or [])
                    # Usa metadados de paginação quando disponíveis; limita para
                    # evitar varredura excessiva em ligas muito longas.
                    paging = d.get("paging") if isinstance(d, dict) else None
                    if isinstance(paging, dict):
                        try:
                            total_pages = int(paging.get("total") or max_pages)
                        except (TypeError, ValueError):
                            total_pages = max_pages
                        max_pages = max(max_pages, min(total_pages, 30))
                    if not raw:
                        break
                    self._enrich_fixtures_referee_data(raw)
                    for fx in raw:
                        ref = self._referee_str(fx) or ""
                        if not self.referee_name_matches(q, ref):
                            continue
                        fid = (fx.get("fixture") or {}).get("id")
                        if not fid:
                            continue
                        try:
                            iid = int(fid)
                        except (TypeError, ValueError):
                            continue
                        if iid in seen:
                            continue
                        seen.add(iid)
                        pool.append(fx)
                        if len(pool) >= need:
                            break
                    page += 1
        pool.sort(key=self._fixture_ts, reverse=True)
        return pool[:need]

    def get_fixtures_statistics(
        self, fixture_id: int, half: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"fixture": int(fixture_id)}
        if half:
            # API v3: first | second (tempos) para estatística ao intervalo / 2.ª parte
            params["half"] = str(half)
        d = self._get("fixtures/statistics", params=params)
        return list(d.get("response") or [])

    def get_fixtures_players(self, fixture_id: int) -> List[Dict[str, Any]]:
        d = self._get("fixtures/players", params={"fixture": fixture_id})
        return list(d.get("response") or [])

    def search_players(self, team_id: int, search: str, season: int, page: int = 1) -> List[Dict[str, Any]]:
        p = (search or "").strip()
        d = self._get(
            "players",
            params={"team": team_id, "season": season, "search": p, "page": page},
        )
        out: List[Dict[str, Any]] = []
        for item in d.get("response") or []:
            pl = item.get("player") if isinstance(item, dict) else None
            if pl:
                out.append(pl)
        return out

    @staticmethod
    def _norm_type(name: str) -> str:
        return (name or "").strip().lower().replace("%", "").replace("  ", " ")

    @staticmethod
    def _stat_map_from_block(block: Dict[str, Any]) -> Dict[str, Any]:
        items = block.get("statistics")
        if not isinstance(items, list):
            return {}
        m: Dict[str, Any] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            k = FootballAPIClient._norm_type(str(it.get("type", "")))
            if k:
                m[k] = it.get("value")
        return m

    @staticmethod
    def _get_label(raw_map: Dict[str, Any], *candidates: str) -> Optional[float]:
        for c in candidates:
            k = FootballAPIClient._norm_type(c)
            if not k:
                continue
            if k in raw_map:
                v = _to_number(raw_map[k])
                if v is not None:
                    return v
        for key, val in raw_map.items():
            for c in candidates:
                ck = FootballAPIClient._norm_type(c)
                if ck and (ck in key or key in ck):
                    v = _to_number(val)
                    if v is not None:
                        return v
        return None

    @staticmethod
    def team_ids_in_statistics(stat_blocks: List[Dict[str, Any]]) -> List[int]:
        out: List[int] = []
        for block in stat_blocks or []:
            t = block.get("team")
            if t and t.get("id") is not None:
                try:
                    out.append(int(t["id"]))
                except (TypeError, ValueError):
                    continue
        return list(dict.fromkeys(out))

    @staticmethod
    def parse_match_total_stat(stat_blocks: List[Dict[str, Any]], stat_type: str) -> Optional[float]:
        """
        Soma a estatística em **ambas** as equipas (total da partida). Usado para
        amarelos, vermelhos, total cartões (pontos: 1A+2V por equipa, depois soma), faltas.
        Se um lado tiver ponto a ponto (ex. 2 amarelos) e o outro vier vazio
        nessa chave, usa 0 nesse lado em vez de descartar o jogo inteiro (API inconsistente
        em taças / competições internacionais).
        stat_type: yellow_cards | red_cards | total_cards | fouls
        """
        tids = FootballAPIClient.team_ids_in_statistics(stat_blocks)
        if not tids:
            return None
        vals: List[Optional[float]] = []
        for tid in tids:
            v = FootballAPIClient.parse_team_stat(stat_blocks, int(tid), stat_type)
            vals.append(v)
        if all(x is None for x in vals):
            return None
        return float(sum(0.0 if x is None else float(x) for x in vals))

    @staticmethod
    def parse_team_stat(
        stat_blocks: List[Dict[str, Any]],
        team_id: int,
        stat_type: str,
    ) -> Optional[float]:
        """
        stat_type: corners | yellow_cards | red_cards | total_cards | fouls |
                   total_shots | shots_on_goal | finalizacoes
        (finalizacoes = remates totais, igual a total_shots na API)
        """
        for block in stat_blocks or []:
            if not isinstance(block, dict):
                continue
            t = block.get("team")
            try:
                block_team_id = int((t or {}).get("id"))
            except (TypeError, ValueError):
                continue
            if block_team_id != int(team_id):
                continue
            try:
                m = FootballAPIClient._stat_map_from_block(block)
            except Exception:
                return None
            if stat_type == "fouls":
                fv = FootballAPIClient._get_label(
                    m, "fouls", "foul commits", "fouls total", "total fouls"
                )
                if fv is None:
                    fv = FootballAPIClient._fuzzy_fouls_from_map(m)
                return fv
            if stat_type == "total_cards":
                # Regra usual em O/U "total cartões": 1 amarelo = 1, 1 vermelho = 2 (pontos).
                y = FootballAPIClient._get_label(
                    m, "yellow cards", "yellow card", "yellows", "yellow", "bookings", "yc"
                )
                if y is None:
                    y = FootballAPIClient._fuzzy_yellows_from_map(m)
                r = FootballAPIClient._get_label(
                    m, "red cards", "red card", "reds", "red", "straight red", "2nd red"
                )
                if r is None:
                    r = FootballAPIClient._fuzzy_reds_from_map(m)
                if y is None and r is None:
                    return None
                return (y or 0) + 2.0 * (r or 0)
            if stat_type in ("total_shots", "finalizacoes", "chutes"):
                v_total = FootballAPIClient._get_label(
                    m, "total shots", "goal attempts", "total shots on goal", "total shots (inc. blocked)"
                )
                return v_total if v_total is not None else FootballAPIClient._get_label(m, "total shots")
            if stat_type == "shots_on_goal":
                return FootballAPIClient._get_label(
                    m,
                    "shots on goal",
                    "shot on goal",
                    "shots on target",
                    "shot on target",
                    "on target",
                    "goal attempts on target",
                    "shots on",
                )
            if stat_type == "corners":
                return FootballAPIClient._get_label(m, "corner kicks", "corners", "total corners")
            if stat_type == "yellow_cards":
                yy = FootballAPIClient._get_label(
                    m,
                    "yellow cards",
                    "yellow card",
                    "yellowcard",
                    "yellow",
                    "bookings",
                    "yc",
                    "cards yellow",
                )
                if yy is not None:
                    return yy
                return FootballAPIClient._fuzzy_yellows_from_map(m)
            if stat_type == "red_cards":
                rr = FootballAPIClient._get_label(
                    m, "red cards", "red card", "redcard", "red", "straight red", "2nd red"
                )
                if rr is not None:
                    return rr
                return FootballAPIClient._fuzzy_reds_from_map(m)
            return None
        return None

    @staticmethod
    def _fuzzy_yellows_from_map(m: Dict[str, Any]) -> Optional[float]:
        for key, val in m.items():
            ks = (key or "").lower()
            if "second yellow" in ks or "2nd yellow" in ks:
                continue
            if "yellow" in ks and "red" not in ks and "2nd" not in ks:
                return _to_number(val)
        return None

    @staticmethod
    def _fuzzy_reds_from_map(m: Dict[str, Any]) -> Optional[float]:
        for key, val in m.items():
            ks = (key or "").lower()
            if "yellow" in ks or "2nd" in ks or "credited" in ks:
                continue
            if "red" in ks and "card" in ks:
                return _to_number(val)
        return None

    @staticmethod
    def _fuzzy_fouls_from_map(m: Dict[str, Any]) -> Optional[float]:
        for key, val in m.items():
            ks = (key or "").lower()
            if "foul" in ks and "won" not in ks and "drawn" not in ks:
                return _to_number(val)
        return None

    @staticmethod
    def _first_stat_block(statistics: Any) -> Dict[str, Any]:
        if isinstance(statistics, list) and statistics and isinstance(statistics[0], dict):
            return statistics[0]
        if isinstance(statistics, dict):
            return statistics
        return {}

    @staticmethod
    def player_minutes_in_match(player_row: Dict[str, Any]) -> int:
        """
        Minutos nessa partida (ficha em fixtures/players). 0 = não jogou
        (banco, não convocado, ou dado em falta).
        """
        s = FootballAPIClient._first_stat_block(player_row.get("statistics"))
        if not isinstance(s, dict):
            return 0
        g = s.get("games")
        if not isinstance(g, dict):
            return 0
        m = _to_number(g.get("minutes"))
        if m is not None and m > 0:
            return int(m)
        return 0

    @staticmethod
    def parse_player_stat_for_played_match(player_row: Dict[str, Any], stat: str) -> float:
        """
        Valor da estatística quando o jogador teve minutos. Se a API omite o
        campo (ex. 0 remates na baliza), devolve 0.0 (como Sofascore/feed explícito).
        """
        v = FootballAPIClient.parse_player_stat(player_row, stat)
        if v is not None:
            return float(v)
        return 0.0

    @staticmethod
    def parse_player_stat(player_row: Dict[str, Any], stat: str) -> Optional[float]:
        s = FootballAPIClient._first_stat_block(player_row.get("statistics"))
        st = s if isinstance(s, dict) else {}

        if stat == "shots_total":
            v = (st.get("shots") or {}).get("total")
            return _to_number(v)
        if stat == "shots_on":
            v = (st.get("shots") or {}).get("on")
            return _to_number(v)
        if stat == "fouls_drawn":
            v = (st.get("fouls") or {}).get("drawn")
            return _to_number(v)
        if stat == "fouls_committed":
            v = (st.get("fouls") or {}).get("committed")
            return _to_number(v)
        if stat == "tackles":
            v = (st.get("tackles") or {}).get("total")
            return _to_number(v)
        if stat == "passes":
            v = (st.get("passes") or {}).get("total")
            return _to_number(v)
        if stat == "shots_outside":
            sh = st.get("shots") or {}
            t = _to_number(sh.get("total"))
            on = _to_number(sh.get("on"))
            if t is not None and on is not None:
                return max(0.0, t - on)
            off = sh.get("off")
            o = _to_number(off) if off is not None else None
            if o is not None:
                return o
            if t is not None and on is not None:
                return max(0.0, t - on)
            return None
        return None
