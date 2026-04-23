"""
Cliente para a API não-oficial de LoL Esports (getLive, getEventDetails, livestats).
Baseado na documentação: https://github.com/vickz84259/lolesports-api-docs
"""
import json
import requests
from datetime import datetime, timezone, timedelta

# API key usada pelo site lolesports.com (pública nos requests do front)
DEFAULT_API_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
ESPORTS_BASE = "https://esports-api.lolesports.com/persisted/gw"
LIVESTATS_BASE = "https://feed.lolesports.com/livestats/v1"
DEFAULT_HL = "pt-BR"


def _starting_time_iso(delay_seconds=30):
    """
    Retorna um timestamp UTC no passado para startingTime (como no live-lol-esports).
    Delay menor = janela mais recente = tempo de jogo e dados mais em dia (ex.: 30s).
    """
    now = datetime.now(timezone.utc)
    # Arredondar segundos para múltiplo de 10 (para baixo)
    sec = now.second - (now.second % 10)
    base = now.replace(second=sec, microsecond=0)
    past = base - timedelta(seconds=delay_seconds)
    return past.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class LiveEsportsClient:
    """Cliente para buscar jogos ao vivo e detalhes da API Lolesports."""

    def __init__(self, api_key=None, hl=DEFAULT_HL):
        self.api_key = api_key or DEFAULT_API_KEY
        self.hl = hl
        self._session = requests.Session()
        self._session.headers.update({
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "LoLOracleML/1.0",
        })

    def get_live(self):
        """
        Retorna todos os eventos (partidas) ao vivo.
        Returns: list[dict] - lista de eventos; cada um tem id, league, match (teams, etc.)
        """
        url = f"{ESPORTS_BASE}/getLive"
        params = {"hl": self.hl}
        try:
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            schedule = data.get("data", {}).get("schedule", {})
            events = schedule.get("events")
            if events is None:
                return []
            return list(events)
        except requests.RequestException as e:
            raise RuntimeError(f"Erro ao buscar jogos ao vivo: {e}") from e
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Resposta inesperada da API: {e}") from e

    def get_event_details(self, event_id):
        """
        Detalhes de um evento (série): jogos, times, placar da série, streams.
        event_id: id do evento (ex: do getLive).
        Returns: dict com event (games, match.teams, match.strategy, streams, etc.)
        """
        url = f"{ESPORTS_BASE}/getEventDetails"
        params = {"id": event_id, "hl": self.hl}
        try:
            r = self._session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            return data.get("data", {}).get("event")
        except requests.RequestException as e:
            raise RuntimeError(f"Erro ao buscar detalhes do evento: {e}") from e
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Resposta inesperada da API: {e}") from e

    def get_window(self, game_id, starting_time=None, first_window=False):
        """
        Dados em tempo real da janela do jogo (ouro, torres, dragões, barão, kills, etc.).
        game_id: id do jogo (ex: game.id de getEventDetails).
        starting_time: opcional; usado só se first_window=False. Se None, usa _starting_time_iso().
        first_window: se True, não envia startingTime (como getFirstWindow do andydanger),
                      para a API retornar a janela mais antiga e obter o tempo real desde 0:00.
        Returns: dict com estrutura da API livestats (window).
        """
        game_id_str = str(game_id) if game_id is not None else ""
        if not game_id_str:
            raise RuntimeError("ID do jogo inválido.")
        url = f"{LIVESTATS_BASE}/window/{game_id_str}"
        params = {}
        if not first_window:
            if starting_time is not None:
                params["startingTime"] = starting_time
            else:
                params["startingTime"] = _starting_time_iso()
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 400 and params.get("startingTime"):
                # 400 com startingTime: tentar delays maiores (janela mais no passado) para obter janela RECENTE.
                # Não usar fallback sem params aqui: sem startingTime a API devolve a PRIMEIRA janela (0:00, dados zerados).
                for delay in (60, 90, 120):
                    params["startingTime"] = _starting_time_iso(delay)
                    r = requests.get(url, params=params, timeout=10)
                    if r.status_code == 200:
                        return r.json()
                # Último recurso: sem startingTime (pode devolver primeira janela = dados antigos)
                r2 = requests.get(url, timeout=10)
                r2.raise_for_status()
                return r2.json()
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Erro ao buscar janela ao vivo: {e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Resposta da API não é JSON válido: {e}") from e

    def get_details(self, game_id, starting_time=None, participant_ids=None):
        """
        Detalhes por frame (participantes, gold, etc.) do jogo ao vivo.
        participant_ids: opcional, string com ids separados por underscore (ex: "1_2_3_4_5_6_7_8_9_10").
        """
        url = f"{LIVESTATS_BASE}/details/{game_id}"
        params = {}
        if starting_time is not None:
            params["startingTime"] = starting_time
        if participant_ids is not None:
            params["participantIds"] = participant_ids
        try:
            r = requests.get(url, params=params or None, timeout=10)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Erro ao buscar detalhes ao vivo: {e}") from e


def parse_window_for_hud(window_data):
    """
    Extrai dados da resposta do endpoint /window para exibição na HUD.
    Compatível com a estrutura usada pelo live-lol-esports (frames, gameMetadata).
    Returns: dict com game_state, game_time_str, patch_version, blue_team, red_team,
             blue_participants, red_participants; ou None se dados inválidos.
    """
    if not window_data or not isinstance(window_data, dict):
        return None
    root = window_data.get("data", window_data)
    frames = root.get("frames")
    if not frames or not isinstance(frames, list):
        return None
    meta = root.get("gameMetadata") or root.get("gameMetaData") or {}
    last = frames[-1]
    first = frames[0]
    blue = last.get("blueTeam") or {}
    red = last.get("redTeam") or {}
    # Timestamps para o cliente calcular tempo como andydanger: primeiro frame (fixo) vs último (atual)
    first_frame_rfc460 = first.get("rfc460Timestamp") or ""
    last_frame_rfc460 = last.get("rfc460Timestamp") or ""
    # game_time_str: fallback se o widget não usar first/last (ex.: primeira carga)
    game_time_str = "0:00"
    try:
        if first_frame_rfc460 and last_frame_rfc460:
            t0 = datetime.fromisoformat(first_frame_rfc460.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_frame_rfc460.replace("Z", "+00:00"))
            delta = (t1 - t0).total_seconds()
            m = int(delta // 60)
            s = int(delta % 60)
            game_time_str = f"{m}:{s:02d}"
    except Exception:
        pass
    blue_meta = meta.get("blueTeamMetadata") or {}
    red_meta = meta.get("redTeamMetadata") or {}
    blue_participants_meta = blue_meta.get("participantMetadata") or []
    red_participants_meta = red_meta.get("participantMetadata") or []
    blue_participants = blue.get("participants") or []
    red_participants = red.get("participants") or []
    # Enriquecer cada participante com summonerName e championId do metadata (participantId 1-5 = blue, 6-10 = red)
    def _num(d, *keys, default=0):
        for k in keys:
            v = d.get(k)
            if v is not None and v != "":
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return default

    def enrich(participants, meta_list, side):
        out = []
        for i, p in enumerate(participants):
            if not isinstance(p, dict):
                continue
            pid = p.get("participantId") or (i + 1 if side == "blue" else i + 6)
            meta_idx = pid - (1 if side == "blue" else 6)
            meta_entry = meta_list[meta_idx] if 0 <= meta_idx < len(meta_list) else {}
            # API pode usar camelCase ou snake_case
            level = _num(p, "level", default=1)
            kills = _num(p, "kills")
            deaths = _num(p, "deaths")
            assists = _num(p, "assists")
            creep_score = _num(p, "creepScore", "creep_score")
            total_gold = _num(p, "totalGold", "total_gold")
            cur_hp = _num(p, "currentHealth", "current_health")
            max_hp = _num(p, "maxHealth", "max_health")
            if max_hp <= 0:
                max_hp = 1
            out.append({
                "participantId": pid,
                "level": level,
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "creepScore": creep_score,
                "totalGold": total_gold,
                "currentHealth": cur_hp,
                "maxHealth": max_hp,
                "summonerName": meta_entry.get("summonerName") or meta_entry.get("summoner_name") or "?",
                "championId": meta_entry.get("championId") or meta_entry.get("champion_id") or "?",
            })
        return out
    blue_players = enrich(blue_participants, blue_participants_meta, "blue")
    red_players = enrich(red_participants, red_participants_meta, "red")

    def _team_stats(team):
        return {
            "totalGold": team.get("totalGold") or team.get("total_gold") or 0,
            "totalKills": team.get("totalKills") or team.get("total_kills") or team.get("championsKilled") or 0,
            "towers": team.get("towers") or team.get("towersKilled") or 0,
            "inhibitors": team.get("inhibitors") or team.get("inhibitorKills") or 0,
            "dragons": team.get("dragons") or [],
            "barons": team.get("barons") or team.get("baronKills") or 0,
        }

    return {
        "game_state": last.get("gameState", "in_game"),
        "game_time_str": game_time_str,
        "first_frame_rfc460": first_frame_rfc460,
        "last_frame_rfc460": last_frame_rfc460,
        "patch_version": meta.get("patchVersion") or meta.get("patch_version") or "",
        "blue_team": _team_stats(blue),
        "red_team": _team_stats(red),
        "blue_participants": blue_players,
        "red_participants": red_players,
    }


def format_live_event_summary(event):
    """
    Extrai um resumo legível de um evento retornado por get_live().
    Returns: dict com keys: event_id, league_name, team1, team2, score1, score2, state, match_id.
    """
    league = event.get("league") or {}
    league_name = league.get("name") or league.get("slug") or "?"
    match = event.get("match") or {}
    teams = match.get("teams") or []
    team1 = team2 = "?"
    score1 = score2 = 0
    if len(teams) >= 1:
        t0 = teams[0]
        team1 = t0.get("name") or t0.get("slug") or "?"
        res0 = t0.get("result") or {}
        score1 = res0.get("gameWins", 0)
    if len(teams) >= 2:
        t1 = teams[1]
        team2 = t1.get("name") or t1.get("slug") or "?"
        res1 = t1.get("result") or {}
        score2 = res1.get("gameWins", 0)
    state = event.get("state") or "?"
    return {
        "event_id": event.get("id"),
        "league_name": league_name,
        "team1": team1,
        "team2": team2,
        "score1": score1,
        "score2": score2,
        "state": state,
        "match_id": match.get("id"),
    }
