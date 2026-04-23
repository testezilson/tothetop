"""
Análise de pré-bets de futebol (Over/Under) com API-Sports, alinhada à lógica LoL/Dota.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.football.api_client import FootballAPIClient, FootballAPIError

TEAM_STATS = {
    "corners_1h": "Escanteios — 1.º tempo (equipa)",
    "corners_2h": "Escanteios — 2.º tempo (equipa)",
    "corners": "Escanteios — jogo completo (equipa)",
    "chutes_1h": "Chutes (totais) — 1.º tempo (equipa)",
    "chutes_2h": "Chutes (totais) — 2.º tempo (equipa)",
    "chutes": "Chutes / remates totais — jogo completo (equipa)",
    "finalizacoes_1h": "Finalizacoes — 1.º tempo (equipa)",
    "finalizacoes_2h": "Finalizacoes — 2.º tempo (equipa)",
    "finalizacoes": "Finalizacoes — jogo completo (remates totais, API)",
    "yellow_cards": "Cartões amarelos (equipa)",
    "red_cards": "Cartões vermelhos (equipa)",
    "total_cards": "Total cartões (pontos: 1 amarelo, 2 vermelhos — por equipa na API)",
    "shots_on_goal": "Chutes ao gol (equipa)",
}

PLAYER_STATS = {
    "shots_total": "Chutes (totais)",
    "shots_on": "Chutes ao gol",
    "fouls_drawn": "Faltas sofridas",
    "fouls_committed": "Faltas cometidas",
    "tackles": "Desarmes",
    "passes": "Passes",
    "shots_outside": "Chutes fora (não ao gol aprox.)",
}

# Cartões: a amostra de cada jogo = total da partida (ambas as equipas).
TEAM_STAT_MATCH_TOTAL = frozenset({"yellow_cards", "red_cards", "total_cards"})


def split_football_stat(user_key: str) -> Tuple[str, Optional[str]]:
    """
    (chave interna parse_team_stat, half API ou None). half: 'first' | 'second'.
    """
    m: Dict[str, Tuple[str, Optional[str]]] = {
        "corners_1h": ("corners", "first"),
        "corners_2h": ("corners", "second"),
        "corners": ("corners", None),
        "chutes_1h": ("total_shots", "first"),
        "chutes_2h": ("total_shots", "second"),
        "chutes": ("total_shots", None),
        "finalizacoes_1h": ("total_shots", "first"),
        "finalizacoes_2h": ("total_shots", "second"),
        "finalizacoes": ("total_shots", None),
    }
    if user_key in m:
        return m[user_key]
    return (user_key, None)


def _abbrev_team(name: str, max_chars: int = 3) -> str:
    if not name or not str(name).strip():
        return "—"
    words = re.sub(r"\s+", " ", str(name).strip()).split()
    if not words:
        return "—"
    return "".join(w[0].upper() for w in words if w)[:max_chars] or "—"


def _norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _label_team_name(s: str) -> str:
    """Remove Sufixo « (id 123) » do nome vindo do UI."""
    return re.sub(r"\s*\(id\s*\d+\)\s*$", "", (s or "").strip(), flags=re.IGNORECASE)


def _parse_fixture_ts(fx: Dict[str, Any]) -> Optional[datetime]:
    f = fx.get("fixture") or {}
    ts = f.get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    d = f.get("date")
    if d:
        try:
            return datetime.fromisoformat(str(d).replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


def default_api_season_year(now: Optional[datetime] = None) -> int:
    """
    Ano de época esperado na API-Sports (API-Football v3):
    o parâmetro «season» é o **ano de início** da liga (ex. La Liga 2025/26 → 2025).
    Regra simples: Jul–Dez = ano civil; Jan–Jun = ano civil − 1 (2.ª metade da época).
    """
    dt = now or datetime.now(timezone.utc)
    if int(dt.month) >= 7:
        return int(dt.year)
    return int(dt.year) - 1


# Pós-jogo (API): incluir pénaltis e prolongamento como no Sofascore / tabela.
_PLAYER_FIXTURE_STATUS_DONE = frozenset({"FT", "AET", "PEN"})


def _player_fixture_is_finished(fx: Dict[str, Any]) -> bool:
    st = (fx.get("fixture") or {}).get("status", {}) or {}
    sh = str(st.get("short") or "").upper()
    if not sh:
        return True
    return sh in _PLAYER_FIXTURE_STATUS_DONE


def _side_team_id(side: Any) -> Optional[int]:
    """ID do clube no bloco home/away (formato plano ou aninhado `team.id`)."""
    if not isinstance(side, dict) or not side:
        return None
    x = side.get("id")
    if x is not None:
        try:
            return int(x)
        except (TypeError, ValueError):
            pass
    t = side.get("team")
    if isinstance(t, dict) and t.get("id") is not None:
        try:
            return int(t["id"])
        except (TypeError, ValueError):
            return None
    return None


def _side_team_name(side: Any) -> str:
    if not isinstance(side, dict):
        return "—"
    n = side.get("name")
    if n:
        return str(n)
    t = side.get("team")
    if isinstance(t, dict) and t.get("name"):
        return str(t.get("name") or "—")
    return "—"


def _fixture_sides(fx: Dict[str, Any]) -> Tuple[Any, Any]:
    """Pares (home, away) da API, no topo do item ou aninhado em `fixture.teams`."""
    teams = fx.get("teams")
    if not isinstance(teams, dict) or (not (teams or {}).get("home") and not (teams or {}).get("away")):
        fobj = fx.get("fixture")
        if isinstance(fobj, dict) and isinstance(fobj.get("teams"), dict):
            teams = fobj.get("teams")
    if not isinstance(teams, dict):
        return {}, {}
    return teams.get("home") or {}, teams.get("away") or {}


def _opponent_name(fx: Dict[str, Any], team_id: int) -> str:
    h, a = _fixture_sides(fx)
    try:
        tid = int(team_id)
    except (TypeError, ValueError):
        return "—"
    hid, aid = _side_team_id(h), _side_team_id(a)
    if hid is not None and hid == tid:
        return _side_team_name(a)
    if aid is not None and aid == tid:
        return _side_team_name(h)
    return "—"


def _fixture_ts(fx: Dict[str, Any]) -> int:
    t = (fx.get("fixture") or {}).get("timestamp")
    try:
        return int(t) if t is not None else 0
    except (TypeError, ValueError):
        return 0


def _team_venue_in_fixture(
    fx: Dict[str, Any], team_id: int, name_hint: Optional[str] = None
) -> Optional[str]:
    """'home' | 'away' se o clube joga aí; None se não for este jogo."""
    h, a = _fixture_sides(fx)
    try:
        tid = int(team_id)
    except (TypeError, ValueError):
        return None
    hid, aid = _side_team_id(h), _side_team_id(a)
    if hid is not None and hid == tid:
        return "home"
    if aid is not None and aid == tid:
        return "away"
    if name_hint and _norm_name(name_hint):
        qn = _norm_name(name_hint)
        hnm = _norm_name(_side_team_name(h))
        anm = _norm_name(_side_team_name(a))
        if hnm and (hnm == qn or qn in hnm or hnm in qn):
            return "home"
        if anm and (anm == qn or qn in anm or anm in qn):
            return "away"
    return None


def _pick_player_row(players_blocks: List[Dict[str, Any]], player_id: int) -> Optional[Dict[str, Any]]:
    pid = int(player_id)
    for block in players_blocks:
        for row in block.get("players") or []:
            p = row.get("player") or {}
            if p.get("id") == pid:
                return row
    return None


class FootballPrebetsAnalyzer:
    def __init__(self, api: Optional[FootballAPIClient] = None):
        self.api = api or FootballAPIClient()

    def _value_for_stat(
        self, stat_internal: str, team_id: int, blocks: List[Dict[str, Any]]
    ) -> Optional[float]:
        if stat_internal in TEAM_STAT_MATCH_TOTAL:
            v = self.api.parse_match_total_stat(blocks, stat_internal)
        else:
            v = self.api.parse_team_stat(blocks, int(team_id), stat_internal)
        return v

    def _collect_team_stat_from_fixtures(
        self,
        team_id: int,
        user_stat: str,
        ordered_fixtures: List[Dict[str, Any]],
        limit: int,
        venue_name_hint: Optional[str] = None,
    ) -> Tuple[List[Optional[float]], List[Dict[str, Any]]]:
        """Percorre jogos já ordenados (mais recente primeiro)."""
        stat_internal, half = split_football_stat(user_stat)
        n = max(1, int(limit))
        values: List[Optional[float]] = []
        meta: List[Dict[str, Any]] = []
        match_total = stat_internal in TEAM_STAT_MATCH_TOTAL
        tid = int(team_id)
        for fx in ordered_fixtures:
            if len(values) >= n:
                break
            fid = FootballAPIClient.fixture_id_from_item(fx)
            if fid is None:
                continue
            v: Optional[float] = None
            try:
                blocks = self.api.get_fixtures_statistics(int(fid), half=half)
            except (FootballAPIError, OSError):
                blocks = None
            if (os.environ.get("FOOTBALL_DEBUG_STAT_BLOCKS") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "y",
                "on",
            ):
                nb = len(blocks) if blocks else 0
                print(f"[FOOTBALL_DEBUG] fixture_id={fid} stats_blocks={nb}", flush=True)
            if blocks:
                w = self._value_for_stat(stat_internal, tid, blocks)
                if w is not None:
                    v = float(w)
            values.append(v)
            ven = _team_venue_in_fixture(fx, tid, venue_name_hint)
            meta.append(
                {
                    "value": v,
                    "opponent": _opponent_name(fx, tid),
                    "fixture_id": int(fid),
                    "match_total": match_total,
                    "venue": ven,
                }
            )
        return values, meta

    def team_stat_values(
        self,
        team_id: int,
        user_stat: str,
        limit: int,
    ) -> Tuple[List[Optional[float]], List[Dict[str, Any]], int]:
        """
        Últimos N **jogos consecutivos** do clube (ordem: mais recente → mais antigo),
        todas as competições, como o Sofascore. Se a API não tiver a estatística
        nesse jogo (ex. taça regional com feed incompleto), o valor fica `None`
        (mostrar «—»), mas a linha de jogo continua a aparecer.
        O cálculo de média/Over usa só as entradas com valor não nulo.
        O terceiro valor é len(raw): jogos devolvidos por get_fixtures_last (antes de
        percorrer estatísticas) — distingue “sem partidas” de “partidas sem métrica”.
        """
        n = max(1, int(limit))
        raw = self.api.get_fixtures_last(team_id, last=max(40, n * 2))
        raw.sort(key=_fixture_ts, reverse=True)
        v, m = self._collect_team_stat_from_fixtures(team_id, user_stat, raw, n, None)
        return v, m, len(raw)

    def team_stats_all_home_away(
        self,
        team_id: int,
        user_stat: str,
        limit: int,
        name_hint: str = "",
    ) -> Tuple[
        Tuple[List[Optional[float]], List[Dict[str, Any]]],
        Tuple[List[Optional[float]], List[Dict[str, Any]]],
        Tuple[List[Optional[float]], List[Dict[str, Any]]],
        int,
    ]:
        """
        Uma leitura de jogos; deriva totais, mandante e visitante (últimos N em cada
        categoria, mais recente primeiro). `name_hint` desambigua mandante/visitante
        se os IDs do JSON vierem noutro sítio. O int final é len(raw) (jogos
        recebidos antes de percorrer estatísticas).
        """
        n = max(1, int(limit))
        # Janela para derivar N jogos (total/casa/fora). Valores 100+ costumam vir vazios
        # com alguns parâmetros da API; o cliente agrega com last≤32 por pedido.
        need_fetch = min(100, max(32, n * 4))
        raw = self.api.get_fixtures_last(int(team_id), last=need_fetch)
        raw.sort(key=_fixture_ts, reverse=True)
        nm = _label_team_name(name_hint) or None
        tid = int(team_id)
        home_f: List[Dict[str, Any]] = []
        away_f: List[Dict[str, Any]] = []
        for fx in raw:
            vloc = _team_venue_in_fixture(fx, tid, nm)
            if vloc == "home":
                home_f.append(fx)
            elif vloc == "away":
                away_f.append(fx)
        all_p = self._collect_team_stat_from_fixtures(tid, user_stat, raw, n, nm)
        h_p = self._collect_team_stat_from_fixtures(tid, user_stat, home_f, n, nm)
        a_p = self._collect_team_stat_from_fixtures(tid, user_stat, away_f, n, nm)
        return all_p, h_p, a_p, len(raw)

    def team_stat_values_by_venue(
        self,
        team_id: int,
        user_stat: str,
        limit: int,
        venue: str,
        name_hint: str = "",
    ) -> Tuple[List[Optional[float]], List[Dict[str, Any]]]:
        """
        Últimos N jogos do clube só em casa ou só fora (mais recentes primeiro).
        `venue`: "home" | "away"
        """
        n = max(1, int(limit))
        # Janela larga para N só em casa ou só fora; last por pedido continua capado no cliente.
        need_fetch = min(100, max(40, n * 8))
        raw = self.api.get_fixtures_last(team_id, last=need_fetch)
        raw.sort(key=_fixture_ts, reverse=True)
        tid = int(team_id)
        nm = _label_team_name(name_hint) or None
        filtered: List[Dict[str, Any]] = []
        for fx in raw:
            vloc = _team_venue_in_fixture(fx, tid, nm)
            if vloc == venue:
                filtered.append(fx)
        return self._collect_team_stat_from_fixtures(team_id, user_stat, filtered, n, nm)

    def h2h_stat_values(
        self,
        team1_id: int,
        team2_id: int,
        stat: str,
        h2h_months: int,
        limit: int,
    ) -> Tuple[List[float], int]:
        """
        Confrontos diretos: usa a estatística do Time 1 (como no teu critério de aposta por equipa).
        """
        stat_internal, half = split_football_stat(stat)
        raw = self.api.get_headtohead(team1_id, team2_id, last=60)
        if h2h_months and h2h_months > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30 * int(h2h_months))
        else:
            cutoff = None
        values: List[float] = []
        for fx in raw:
            if limit and len(values) >= limit:
                break
            dt = _parse_fixture_ts(fx)
            if cutoff and dt and dt < cutoff:
                continue
            st = (fx.get("fixture") or {}).get("status", {}) or {}
            sh = (st.get("short") or "").upper()
            if sh and sh not in ("FT", "AET", "PEN"):
                continue
            fid = FootballAPIClient.fixture_id_from_item(fx)
            if fid is None:
                continue
            try:
                blocks = self.api.get_fixtures_statistics(int(fid), half=half)
            except (FootballAPIError, OSError):
                continue
            v = self._value_for_stat(stat_internal, team1_id, blocks)
            if v is None:
                continue
            values.append(float(v))
        return values, len(values)

    def referee_match_averages(
        self,
        referee_name: str,
        n_games: int,
        team1_id: Optional[int] = None,
        team2_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Médias por jogo: amarelos, vermelhos, total cartões e faltas (tudo **total da partida**).
        Jogos = último arbitragem com nome semelhante (API, amostra de ligas se necessário).
        """
        n_games = max(3, min(int(n_games), 100))
        q = (referee_name or "").strip()
        if not q:
            return {"n": 0, "ok": False, "message": "Sem nome de árbitro."}
        # Para relatório do juiz, o esperado é "últimos jogos do árbitro" em geral.
        # Não ancorar por times A/B por padrão, pois isso enviesa e encurta a amostra.
        fetch_need = max(n_games, 30)
        fxs = self.api.get_fixtures_by_referee(q, fetch_need, anchor_team_ids=None)
        # Fallback: se a API vier muito curta, tenta expandir com âncora dos clubes.
        if len(fxs) < n_games and team1_id and team2_id and int(team1_id) != int(team2_id):
            anchor = (int(team1_id), int(team2_id))
            extra = self.api.get_fixtures_by_referee(q, fetch_need, anchor_team_ids=anchor)
            seen = set()
            merged: List[Dict[str, Any]] = []
            for fx in (fxs + extra):
                iid = FootballAPIClient.fixture_id_from_item(fx)
                if iid is None:
                    continue
                if iid in seen:
                    continue
                seen.add(iid)
                merged.append(fx)
            merged.sort(key=lambda x: self.api._fixture_ts(x), reverse=True)
            fxs = merged
        fxs.sort(key=lambda x: self.api._fixture_ts(x), reverse=True)
        fxs = fxs[:n_games]
        if not fxs:
            return {
                "n": 0,
                "ok": False,
                "message": "Nenhum jogo FT com este árbitro na amostra (nome como na API, ex. «J. Sanchez»).",
            }
        matches: List[Dict[str, Any]] = []
        yl: List[float] = []
        rd: List[float] = []
        tot: List[float] = []
        fl: List[float] = []
        for fx in fxs:
            fid = FootballAPIClient.fixture_id_from_item(fx)
            if fid is None:
                continue
            tm = fx.get("teams") or {}
            home = (tm.get("home") or {}).get("name") or "?"
            away = (tm.get("away") or {}).get("name") or "?"
            dt = _parse_fixture_ts(fx)
            dts = dt.astimezone(timezone.utc).strftime("%Y-%m-%d") if dt else "?"
            matches.append(
                {
                    "date": dts,
                    "home": str(home),
                    "away": str(away),
                    "fixture_id": int(fid),
                    "yellow": None,
                    "red": None,
                    "total_cards": None,
                }
            )
            try:
                blocks = self.api.get_fixtures_statistics(int(fid))
            except (FootballAPIError, OSError):
                continue
            a = self.api.parse_match_total_stat(blocks, "yellow_cards")
            b = self.api.parse_match_total_stat(blocks, "red_cards")
            c = self.api.parse_match_total_stat(blocks, "total_cards")
            d = self.api.parse_match_total_stat(blocks, "fouls")
            if matches:
                matches[-1]["yellow"] = float(a) if a is not None else None
                matches[-1]["red"] = float(b) if b is not None else None
                matches[-1]["total_cards"] = float(c) if c is not None else None
            if a is not None:
                yl.append(a)
            if b is not None:
                rd.append(b)
            if c is not None:
                tot.append(c)
            if d is not None:
                fl.append(d)
        n = len(fxs)
        if not yl and not tot:
            return {
                "n": n,
                "ok": False,
                "message": "Jogos encontrados mas sem bloco de estatística completo.",
            }
        return {
            "n": n,
            "ok": True,
            "message": "",
            "avg_yellow": float(np.mean(yl)) if yl else None,
            "avg_red": float(np.mean(rd)) if rd else None,
            "avg_total_cards": float(np.mean(tot)) if tot else None,
            "avg_fouls": float(np.mean(fl)) if fl else None,
            "n_with_yellow": len(yl),
            "n_with_red": len(rd),
            "n_with_total_cards": len(tot),
            "n_with_fouls": len(fl),
            "matches": matches,
        }

    def _resolve_team_id_from_label(self, team_label: str, fallback_id: int) -> Tuple[int, str]:
        """
        Resolve id/nome a partir do rótulo da UI (remove «(id N)») via /teams?search=.
        Prioridade: 1) nome normalizado exato; 2) sufixo/prefixo (parcial);
        3) o id vindo do mapa, se ainda estiver na lista; 4) o id de fallback.
        Isto evita tratar o id do combobox como verdade absoluta se o mapa estiver
        desatualizado ou tiver trocado cliques.
        """
        clean = _label_team_name(team_label)
        if not clean:
            try:
                return int(fallback_id), (team_label or "").strip()
            except (TypeError, ValueError):
                return 0, ""
        try:
            cands = self.api.search_teams(clean)
        except (FootballAPIError, OSError):
            cands = []
        if not cands:
            try:
                return int(fallback_id), clean
            except (TypeError, ValueError):
                return 0, clean
        try:
            fid = int(fallback_id)
        except (TypeError, ValueError):
            fid = 0
        rows: List[Tuple[int, str]] = []
        for t in cands:
            if not isinstance(t, dict):
                continue
            try:
                tidi = int(t.get("id"))
            except (TypeError, ValueError):
                continue
            tname = str((t.get("name") or "")).strip()
            if tname:
                rows.append((tidi, tname))
        if not rows:
            try:
                return int(fallback_id), clean
            except (TypeError, ValueError):
                return 0, clean
        qn = _norm_name(clean)
        for tidi, tname in rows:
            if _norm_name(tname) == qn:
                return tidi, tname
        for tidi, tname in rows:
            nn = _norm_name(tname)
            if qn and (qn in nn or nn in qn):
                return tidi, tname
        for tidi, tname in rows:
            if tidi == fid:
                return tidi, tname
        try:
            return int(fallback_id), clean
        except (TypeError, ValueError):
            return 0, clean

    def _diagnostic_snapshot_team(self, team_id: int, team_name: str) -> str:
        """3–4 pedidos: teams?id, search, get_fixtures_last (para a caixa de erro)."""
        clean = _label_team_name(team_name)
        lines: List[str] = [f"clean_name={clean!r} team_id={int(team_id)}"]
        try:
            t = self.api.get_team_info(int(team_id))
            if t:
                lines.append(
                    f"teams?id= -> {t.get('name')!r} (pais {t.get('country')!r}, id={t.get('id')})"
                )
            else:
                lines.append("teams?id= -> vazio (id desconhecido ou sem resposta)")
        except (FootballAPIError, OSError, TypeError, ValueError) as e:
            lines.append(f"teams?id= -> ERRO: {e}")
        if clean:
            try:
                c = self.api.search_teams(clean)
                top = [f"{x.get('id')}: {x.get('name')!r}" for x in c[:5] if isinstance(x, dict)]
                lines.append(
                    f"teams?search= -> {len(c)}; primeiros: {', '.join(top) if top else '—'}"
                )
            except (FootballAPIError, OSError) as e:
                lines.append(f"teams?search= -> ERRO: {e}")
        try:
            n = len(self.api.get_fixtures_last(int(team_id), last=10))
            lines.append(f"get_fixtures_last(last=10) -> {n} partidas")
        except (FootballAPIError, OSError) as e:
            lines.append(f"get_fixtures_last -> ERRO: {e}")
        return "\n".join(lines)

    def debug_team_fetch(self, team_id: int, team_name: str) -> str:
        """Diagnóstico alargado (muitas chamadas à API). Ativar com FOOTBALL_DEBUG_TEAMS=1 na caixa de erro."""
        lines: List[str] = []
        clean_name = _label_team_name(team_name)
        lines.append(f"[DEBUG] team_name_ui={team_name!r}")
        lines.append(f"[DEBUG] clean_name={clean_name!r}")
        lines.append(f"[DEBUG] team_id={team_id}")
        try:
            info = self.api.get_team_info(int(team_id))
            if info:
                lines.append(
                    f"[teams?id] id={info.get('id')!r} name={info.get('name')!r} country={info.get('country')!r}"
                )
            else:
                lines.append("[teams?id] -> None")
        except (FootballAPIError, OSError, TypeError, ValueError) as e:
            lines.append(f"[teams?id] ERRO -> {e}")
        if clean_name:
            try:
                cands = self.api.search_teams(clean_name)
                preview = [
                    {"id": x.get("id"), "name": x.get("name"), "country": x.get("country")}
                    for x in cands[:10]
                    if isinstance(x, dict)
                ]
                lines.append(f"[teams?search] -> {preview}")
            except (FootballAPIError, OSError) as e:
                lines.append(f"[teams?search] ERRO -> {e}")
        for params in (
            {"team": int(team_id), "current": "true"},
            {"team": int(team_id), "current": "1"},
            {"team": int(team_id)},
        ):
            try:
                d = self.api._get("leagues", params=params)
                arr = d.get("response") or []
                lines.append(f"[leagues {params!r}] -> {len(arr)} resultados")
            except (FootballAPIError, OSError) as e:
                lines.append(f"[leagues {params!r}] ERRO -> {e}")
        y0 = FootballAPIClient._default_season_guess()
        cy = int(datetime.now(timezone.utc).year)
        season_years: List[int] = []
        for sy in (y0, y0 - 1, y0 + 1, cy, cy - 1):
            if sy not in season_years:
                season_years.append(sy)
        extra_fix: List[Dict[str, Any]] = []
        for sy in season_years:
            extra_fix.append({"team": int(team_id), "season": sy, "last": 10})
            extra_fix.append(
                {
                    "team": int(team_id),
                    "season": sy,
                    "last": 10,
                    "status": "FT-AET-PEN",
                }
            )
        for params in (
            {"team": int(team_id), "last": 10},
            {"team": int(team_id), "last": 10, "status": "FT-AET-PEN"},
            *extra_fix,
        ):
            try:
                d = self.api._get("fixtures", params=params)
                arr = d.get("response") or []
                lines.append(f"[fixtures {params!r}] -> {len(arr)} resultados")
                if arr:
                    sample = arr[0]
                    hid = (sample.get("teams") or {}).get("home") or {}
                    aid = (sample.get("teams") or {}).get("away") or {}
                    lines.append(
                        f"   sample fixture_id={FootballAPIClient.fixture_id_from_item(sample)} "
                        f"home={hid!r} away={aid!r}"
                    )
            except (FootballAPIError, OSError) as e:
                lines.append(f"[fixtures {params!r}] ERRO -> {e}")
        try:
            raw = self.api.get_fixtures_last(int(team_id), last=10)
            lines.append(f"[get_fixtures_last] -> {len(raw)} resultados")
            if raw:
                ids5 = [FootballAPIClient.fixture_id_from_item(x) for x in raw[:5]]
                lines.append(f"   ids={ids5}")
        except (FootballAPIError, OSError) as e:
            lines.append(f"[get_fixtures_last] ERRO -> {e}")
        return "\n".join(lines)

    def analyze_team_bet(
        self,
        team1_id: int,
        team1_name: str,
        team2_id: int,
        team2_name: str,
        stat: str,
        line: float,
        odd_over: float,
        odd_under: float,
        limit_games: int,
        h2h_months: int,
        use_h2h: bool,
        referee_name: str = "",
        referee_sample_games: int = 20,
    ) -> Dict[str, Any]:
        if not self.api.has_key():
            return {"error": "Chave API em falta (FOOTBALL_API_KEY ou data/football_api_key.txt)."}
        label1_raw = (team1_name or "").strip()
        label2_raw = (team2_name or "").strip()
        team1_id, team1_name = self._resolve_team_id_from_label(team1_name, team1_id)
        team2_id, team2_name = self._resolve_team_id_from_label(team2_name, team2_id)
        if team1_id == team2_id:
            return {"error": "Os dois times não podem ser o mesmo."}
        user_stat = stat
        stat_internal, _ = split_football_stat(user_stat)
        is_card = stat_internal in TEAM_STAT_MATCH_TOTAL
        v1h = m1h = v1a = m1a = v2h = m2h = v2a = m2a = None
        n_raw1 = n_raw2 = 0
        if is_card:
            v1, m1, n_raw1 = self.team_stat_values(team1_id, user_stat, limit_games)
            v2, m2, n_raw2 = self.team_stat_values(team2_id, user_stat, limit_games)
        else:
            (v1, m1), (v1h, m1h), (v1a, m1a), n_raw1 = self.team_stats_all_home_away(
                team1_id, user_stat, limit_games, team1_name
            )
            (v2, m2), (v2h, m2h), (v2a, m2a), n_raw2 = self.team_stats_all_home_away(
                team2_id, user_stat, limit_games, team2_name
            )
        team1_resolved = None
        team2_resolved = None
        if n_raw1 < 1 and team1_name:
            clean1 = _label_team_name(team1_name)
            try:
                cands = self.api.search_teams(clean1)
            except (FootballAPIError, OSError):
                cands = []
            qn = _norm_name(clean1)
            for t in cands:
                tid = t.get("id") if isinstance(t, dict) else None
                tname = (t.get("name") if isinstance(t, dict) else "") or ""
                try:
                    tidi = int(tid)
                except (TypeError, ValueError):
                    continue
                if tidi == int(team1_id):
                    continue
                if qn and qn not in _norm_name(str(tname)) and _norm_name(str(tname)) not in qn:
                    continue
                if is_card:
                    vv, mm, n_raw1 = self.team_stat_values(tidi, user_stat, limit_games)
                else:
                    (vv, mm), (v1h, m1h), (v1a, m1a), n_raw1 = self.team_stats_all_home_away(
                        tidi, user_stat, limit_games, str(tname) or clean1
                    )
                if n_raw1 >= 1:
                    v1, m1 = vv, mm
                    team1_id = tidi
                    team1_name = str(tname) or team1_name
                    team1_resolved = {"id": team1_id, "name": team1_name}
                    break
        if n_raw2 < 1 and team2_name:
            clean2 = _label_team_name(team2_name)
            try:
                cands = self.api.search_teams(clean2)
            except (FootballAPIError, OSError):
                cands = []
            qn = _norm_name(clean2)
            for t in cands:
                tid = t.get("id") if isinstance(t, dict) else None
                tname = (t.get("name") if isinstance(t, dict) else "") or ""
                try:
                    tidi = int(tid)
                except (TypeError, ValueError):
                    continue
                if tidi == int(team2_id):
                    continue
                if qn and qn not in _norm_name(str(tname)) and _norm_name(str(tname)) not in qn:
                    continue
                if is_card:
                    vv, mm, n_raw2 = self.team_stat_values(tidi, user_stat, limit_games)
                else:
                    (vv, mm), (v2h, m2h), (v2a, m2a), n_raw2 = self.team_stats_all_home_away(
                        tidi, user_stat, limit_games, str(tname) or clean2
                    )
                if n_raw2 >= 1:
                    v2, m2 = vv, mm
                    team2_id = tidi
                    team2_name = str(tname) or team2_name
                    team2_resolved = {"id": team2_id, "name": team2_name}
                    break
        w1 = [x for x in v1 if x is not None]
        w2 = [x for x in v2 if x is not None]
        if n_raw1 < 1 or n_raw2 < 1:
            fix_msg = ""
            if team1_resolved or team2_resolved:
                parts: List[str] = []
                if team1_resolved:
                    parts.append(f"time 1 -> {team1_resolved.get('name')} (id {team1_resolved.get('id')})")
                if team2_resolved:
                    parts.append(f"time 2 -> {team2_resolved.get('name')} (id {team2_resolved.get('id')})")
                fix_msg = " Ajuste automatico de ID aplicado: " + "; ".join(parts) + "."
            diag_txt: Optional[str] = None
            if not (os.environ.get("FOOTBALL_SKIP_EMPTY_DIAG", "").strip().lower() in ("1", "true", "yes")):
                full_dbg = (os.environ.get("FOOTBALL_DEBUG_TEAMS", "").strip().lower() in ("1", "true", "yes", "y", "on"))
                if full_dbg:
                    diag_txt = (
                        f"Rótulo UI: time1={label1_raw!r} time2={label2_raw!r}\n\n"
                        f"=== Após resolução de id: time1 id={team1_id!r} name={team1_name!r} | "
                        f"time2 id={team2_id!r} name={team2_name!r}\n\n"
                        f"=== Time 1 ===\n{self.debug_team_fetch(team1_id, team1_name)}\n\n"
                        f"=== Time 2 ===\n{self.debug_team_fetch(team2_id, team2_name)}"
                    )
                else:
                    diag_txt = (
                        f"Rótulo UI: time1={label1_raw!r} time2={label2_raw!r}\n"
                        f"Resolvido: time1 id={team1_id} «{team1_name}» | time2 id={team2_id} «{team2_name}»\n\n"
                        f"— Diagnóstico rápido (teams + search + get_fixtures_last) —\n\n"
                        f"=== Time 1 ===\n{self._diagnostic_snapshot_team(team1_id, team1_name)}\n\n"
                        f"=== Time 2 ===\n{self._diagnostic_snapshot_team(team2_id, team2_name)}\n\n"
                        f"Defina a variável de ambiente FOOTBALL_DEBUG_TEAMS=1 e volte a calcular para o relatório completo. "
                        f"Defina FOOTBALL_SKIP_EMPTY_DIAG=1 para suprimir este bloco (poupar quota da API)."
                    )
            return {
                "error": (
                    "A API nao devolveu partidas (fixtures) recentes na janela para um dos times — "
                    "nao e um problema de estatistica de jogo, e sim de lista vazia no pedido de jogos. "
                    f"Jogos na janela: time 1 = {n_raw1}, time 2 = {n_raw2} (pedido: {limit_games} por categoria de analise)."
                    f"{fix_msg}"
                ),
                "diagnostics": diag_txt,
                "team1_games": len(m1),
                "team2_games": len(m2),
                "team1_fixtures_in_window": n_raw1,
                "team2_fixtures_in_window": n_raw2,
                "team1_resolved": team1_resolved,
                "team2_resolved": team2_resolved,
            }
        if len(w1) < 3 or len(w2) < 3:
            return {
                "error": (
                    "Jogos encontrados na API, mas poucos com a estatistica completa (para media e EV sao necessarios "
                    f"pelo menos 3 jogos com valor nao nulo). "
                    f"Fixtures na janela: time 1 = {n_raw1}, time 2 = {n_raw2}. "
                    f"Com metrica: time 1 = {len(w1)} (linhas de jogo {len(m1)} com id de partida), "
                    f"time 2 = {len(w2)} (linhas {len(m2)}). "
                    "Segunda liga, taças e competições menores muitas vezes sem a metrica na API. "
                    "Nao e «0 chutes no jogo»: aqui a API nao forneceu o bloco de estatistica; tenta outro mercado."
                ),
                "team1_games": len(m1),
                "team2_games": len(m2),
                "team1_fixtures_in_window": n_raw1,
                "team2_fixtures_in_window": n_raw2,
                "team1_resolved": team1_resolved,
                "team2_resolved": team2_resolved,
            }

        arr1 = np.array(w1, dtype=float)
        arr2 = np.array(w2, dtype=float)
        arr_all = np.concatenate([arr1, arr2])
        prob_form = float((arr_all > line).mean())

        h2h_rate: Optional[float] = None
        nh2h = 0
        h2h_mean = 0.0
        over_h2h = 0
        under_h2h = 0
        if use_h2h:
            h2h_vals, nh2h = self.h2h_stat_values(
                team1_id, team2_id, user_stat, h2h_months, limit_games * 2
            )
            if h2h_vals:
                a = np.array(h2h_vals, dtype=float)
                h2h_mean = float(a.mean())
                over_h2h = int((a > line).sum())
                under_h2h = len(a) - over_h2h
                h2h_rate = over_h2h / len(a) if len(a) else None

        if use_h2h and h2h_rate is not None and nh2h >= 3:
            w_h2h = min(0.8, nh2h / (nh2h + 10))
            w_form = 1.0 - w_h2h
            prob_over = w_h2h * h2h_rate + w_form * prob_form
        else:
            w_h2h = 0.0
            w_form = 1.0
            prob_over = prob_form

        prob_under = 1.0 - prob_over

        def _ev_pinnacle(prob: float, odd: float, stake: float = 1.0) -> Tuple[float, float, float]:
            win = (odd - 1.0) * stake
            lose = stake
            ev = prob * win - (1 - prob) * lose
            fair = 1.0 / prob if prob > 0 else float("inf")
            return ev, ev / stake if stake else 0.0, fair

        ev_over, ev_over_pct, fair_over = _ev_pinnacle(prob_over, odd_over)
        ev_under, ev_under_pct, fair_under = _ev_pinnacle(prob_under, odd_under)

        p1 = float((arr1 > line).mean()) if len(arr1) else 0.0
        p2 = float((arr2 > line).mean()) if len(arr2) else 0.0
        t1_ev_o, t1_evo_pct, t1_fair_o = _ev_pinnacle(p1, odd_over)
        t1_ev_u, t1_evu_pct, t1_fair_u = _ev_pinnacle(1.0 - p1, odd_under)
        t2_ev_o, t2_evo_pct, t2_fair_o = _ev_pinnacle(p2, odd_over)
        t2_ev_u, t2_evu_pct, t2_fair_u = _ev_pinnacle(1.0 - p2, odd_under)

        over1 = int((arr1 > line).sum())
        under1 = len(arr1) - over1
        over2 = int((arr2 > line).sum())
        under2 = len(arr2) - over2
        over_all = int((arr_all > line).sum())
        under_all = len(arr_all) - over_all

        def _venue_line_block(
            vals: List[Optional[float]], meta: List[Dict[str, Any]], lim: int
        ) -> Dict[str, Any]:
            wloc = [x for x in vals if x is not None]
            arr_l = np.array(wloc, dtype=float) if wloc else np.array([], dtype=float)
            ng = len(vals)
            ns = len(wloc)
            if len(arr_l):
                o = int((arr_l > line).sum())
                u = int((arr_l <= line).sum())
                mu = float(arr_l.mean())
                p_over = float((arr_l > line).mean())
                p_under = float(1.0 - p_over)
                fair_o = (1.0 / p_over) if p_over > 0 else None
                fair_u = (1.0 / p_under) if p_under > 0 else None
            else:
                o, u, mu = 0, 0, 0.0
                p_over = 0.0
                p_under = 0.0
                fair_o = fair_u = None
            return {
                "mean": mu,
                "over": o,
                "under": u,
                "n_games": ng,
                "n_with_stat": ns,
                "p_over_emp": p_over,
                "p_under_emp": p_under,
                "fair_over_emp": fair_o,
                "fair_under_emp": fair_u,
                "last_values": (meta or [])[: max(1, int(lim))],
            }

        venue_split = not is_card
        t1_home: Optional[Dict[str, Any]] = None
        t1_away: Optional[Dict[str, Any]] = None
        t2_home: Optional[Dict[str, Any]] = None
        t2_away: Optional[Dict[str, Any]] = None
        t1_total_emp: Optional[Dict[str, Any]] = None
        t2_total_emp: Optional[Dict[str, Any]] = None
        if venue_split:
            t1_home = _venue_line_block(v1h, m1h, limit_games)
            t1_away = _venue_line_block(v1a, m1a, limit_games)
            t2_home = _venue_line_block(v2h, m2h, limit_games)
            t2_away = _venue_line_block(v2a, m2a, limit_games)
            t1_total_emp = _venue_line_block(v1, m1, limit_games)
            t2_total_emp = _venue_line_block(v2, m2, limit_games)

        rec = "Nenhuma aposta com EV positivo"
        if ev_over > 0 and ev_over >= ev_under:
            rec = f"OVER {line} (EV {ev_over:+.2f}u)"
        elif ev_under > 0 and ev_under > ev_over:
            rec = f"UNDER {line} (EV {ev_under:+.2f}u)"

        ref_info: Dict[str, Any] = {"computed": False}
        if (referee_name or "").strip():
            ref_info = self.referee_match_averages(
                (referee_name or "").strip(),
                int(max(3, referee_sample_games)),
                int(team1_id),
                int(team2_id),
            )
            ref_info["computed"] = True

        return {
            "mode": "team",
            "team1": team1_name,
            "team2": team2_name,
            "team1_id": team1_id,
            "team2_id": team2_id,
            "stat": user_stat,
            "stat_label": TEAM_STATS.get(user_stat, user_stat),
            "stat_match_total": stat_internal in TEAM_STAT_MATCH_TOTAL,
            "line": line,
            "odd_over": odd_over,
            "odd_under": odd_under,
            "team1_games": len(m1),
            "team2_games": len(m2),
            "team1_resolved": team1_resolved,
            "team2_resolved": team2_resolved,
            "team1_n_with_stat": len(w1),
            "team2_n_with_stat": len(w2),
            "last_values_team1": m1[:10],
            "last_values_team2": m2[:10],
            "mean_team1": float(np.mean(arr1)),
            "mean_team2": float(np.mean(arr2)),
            "prob_over": prob_over,
            "prob_under": prob_under,
            "prob_form": prob_form,
            "fair_over": fair_over,
            "fair_under": fair_under,
            "ev_over": ev_over,
            "ev_over_pct": ev_over_pct,
            "ev_under": ev_under,
            "ev_under_pct": ev_under_pct,
            "p_team1": p1,
            "p_team2": p2,
            "t1_ev_over": t1_ev_o,
            "t1_ev_over_pct": t1_evo_pct,
            "t1_fair_over": t1_fair_o,
            "t1_ev_under": t1_ev_u,
            "t1_ev_under_pct": t1_evu_pct,
            "t1_fair_under": t1_fair_u,
            "t2_ev_over": t2_ev_o,
            "t2_ev_over_pct": t2_evo_pct,
            "t2_fair_over": t2_fair_o,
            "t2_ev_under": t2_ev_u,
            "t2_ev_under_pct": t2_evu_pct,
            "t2_fair_under": t2_fair_u,
            "use_h2h": use_h2h,
            "h2h_rate": h2h_rate,
            "h2h_games": nh2h,
            "h2h_mean": h2h_mean,
            "h2h_over": over_h2h,
            "h2h_under": under_h2h,
            "w_h2h": w_h2h,
            "w_form": w_form,
            "team1_over": over1,
            "team1_under": under1,
            "team2_over": over2,
            "team2_under": under2,
            "over_all": over_all,
            "under_all": under_all,
            "recommendation": rec,
            "is_first_stat": False,
            "referee_name": (referee_name or "").strip(),
            "referee_stats": ref_info,
            "venue_split": venue_split,
            "team1_split_home": t1_home,
            "team1_split_away": t1_away,
            "team2_split_home": t2_home,
            "team2_split_away": t2_away,
            "team1_split_total_emp": t1_total_emp,
            "team2_split_total_emp": t2_total_emp,
        }

    def player_stat_values(
        self,
        team_id: int,
        player_id: int,
        stat: str,
        limit: int,
    ) -> Tuple[List[float], List[Dict[str, Any]]]:
        """
        Últimos N jogos em que o jogador teve minutos (como alinhador tipo Sofascore):
        percorre os jogos do clube (mais recente primeiro) e só conta quem
        `fixtures/players` mostra com minutos > 0. Valor da estatística pedida:
        0.0 se a API omitir o campo nesse jogo. Duas mãos contra o mesmo clube
        entram as duas se jogou as duas.
        """
        need = max(1, int(limit))
        fetch_last = min(80, max(32, need * 5))
        raw = self.api.get_fixtures_last(team_id, last=fetch_last)
        values: List[float] = []
        meta: List[Dict[str, Any]] = []
        for fx in raw:
            if len(values) >= need:
                break
            if not _player_fixture_is_finished(fx):
                continue
            fid = FootballAPIClient.fixture_id_from_item(fx)
            if fid is None:
                continue
            try:
                blocks = self.api.get_fixtures_players(int(fid))
            except (FootballAPIError, OSError):
                continue
            row = _pick_player_row(blocks, int(player_id))
            if not row:
                continue
            if self.api.player_minutes_in_match(row) <= 0:
                continue
            v = self.api.parse_player_stat_for_played_match(row, stat)
            values.append(float(v))
            meta.append(
                {
                    "value": float(v),
                    "opponent": _opponent_name(fx, int(team_id)),
                    "fixture_id": int(fid),
                    "minutes": self.api.player_minutes_in_match(row),
                }
            )
        return values, meta

    def analyze_player_bet(
        self,
        team_id: int,
        team_name: str,
        player_id: int,
        player_name: str,
        stat: str,
        line: float,
        odd_over: float,
        odd_under: float,
        limit_games: int,
    ) -> Dict[str, Any]:
        if not self.api.has_key():
            return {"error": "Chave API em falta (FOOTBALL_API_KEY ou data/football_api_key.txt)."}
        vals, metas = self.player_stat_values(team_id, player_id, stat, limit_games)
        if len(vals) < 3:
            return {
                "error": (
                    f"Poucos jogos com minutos de jogo contabilizados na API ({len(vals)}; pedido: {limit_games}). "
                    "Aumenta «Jogos recentes a analisar» ou confirma o id do jogador."
                ),
                "n_games": len(vals),
            }
        arr = np.array(vals, dtype=float)
        prob_form = float((arr > line).mean())
        prob_over = prob_form
        prob_under = 1.0 - prob_over

        def _ev_pinnacle(prob: float, odd: float, stake: float = 1.0) -> Tuple[float, float, float]:
            win = (odd - 1.0) * stake
            lose = stake
            ev = prob * win - (1 - prob) * lose
            fair = 1.0 / prob if prob > 0 else float("inf")
            return ev, ev / stake if stake else 0.0, fair

        ev_over, ev_over_pct, fair_over = _ev_pinnacle(prob_over, odd_over)
        ev_under, ev_under_pct, fair_under = _ev_pinnacle(prob_under, odd_under)
        over_c = int((arr > line).sum())
        under_c = len(arr) - over_c
        rec = "Nenhuma aposta com EV positivo"
        if ev_over > 0 and ev_over >= ev_under:
            rec = f"OVER {line} (EV {ev_over:+.2f}u)"
        elif ev_under > 0 and ev_under > ev_over:
            rec = f"UNDER {line} (EV {ev_under:+.2f}u)"
        return {
            "mode": "player",
            "team1": f"{player_name} ({team_name})",
            "team2": "",
            "stat": stat,
            "stat_label": PLAYER_STATS.get(stat, stat),
            "line": line,
            "team1_games": len(arr),
            "team2_games": 0,
            "last_values_team1": metas[:10],
            "last_values_team2": [],
            "mean_team1": float(np.mean(arr)),
            "mean_team2": 0.0,
            "prob_over": prob_over,
            "prob_under": prob_under,
            "prob_form": prob_form,
            "fair_over": fair_over,
            "fair_under": fair_under,
            "ev_over": ev_over,
            "ev_over_pct": ev_over_pct,
            "ev_under": ev_under,
            "ev_under_pct": ev_under_pct,
            "use_h2h": False,
            "h2h_rate": None,
            "h2h_games": 0,
            "h2h_mean": 0.0,
            "h2h_over": 0,
            "h2h_under": 0,
            "w_h2h": 0.0,
            "w_form": 1.0,
            "team1_over": over_c,
            "team1_under": under_c,
            "team2_over": 0,
            "team2_under": 0,
            "over_all": over_c,
            "under_all": under_c,
            "recommendation": rec,
            "is_first_stat": False,
            "odd_over": odd_over,
            "odd_under": odd_under,
        }
