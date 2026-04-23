"""
Cliente para a API OpenDota: jogos ao vivo (GET /live).
Filtro para exibir apenas jogos profissionais (league_id > 0 ou times nomeados).
Documentação: https://docs.opendota.com/
"""
import requests

OPENDOTA_BASE = "https://api.opendota.com/api"


def _is_pro_game(game: dict) -> bool:
    """
    Considera profissional se tem league_id > 0 ou nomes de times (radiant/dire).
    """
    league_id = game.get("league_id") or 0
    if league_id > 0:
        return True
    rn = (game.get("team_name_radiant") or "").strip()
    dn = (game.get("team_name_dire") or "").strip()
    return bool(rn or dn)


class OpenDotaLiveClient:
    """Cliente para jogos ao vivo da OpenDota (apenas profissionais)."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "LoLOracleML-Dota/1.0",
        })
        self._heroes_cache = None

    def get_live(self):
        """
        Retorna todos os jogos ao vivo da API OpenDota (GET /live).
        Returns: list[dict]
        """
        url = f"{OPENDOTA_BASE}/live"
        try:
            r = self._session.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                return []
            return list(data)
        except requests.RequestException as e:
            raise RuntimeError(f"Erro ao buscar jogos ao vivo: {e}") from e
        except (TypeError, ValueError) as e:
            raise RuntimeError(f"Resposta inesperada da API: {e}") from e

    def get_pro_live(self):
        """
        Retorna apenas jogos ao vivo considerados profissionais.
        """
        all_games = self.get_live()
        return [g for g in all_games if _is_pro_game(g)]

    def get_heroes(self):
        """
        Retorna mapa hero_id -> localized_name (cacheado).
        GET /heroes da OpenDota.
        """
        if self._heroes_cache is not None:
            return self._heroes_cache
        url = f"{OPENDOTA_BASE}/heroes"
        try:
            r = self._session.get(url, timeout=10)
            r.raise_for_status()
            heroes = r.json()
            if not isinstance(heroes, list):
                self._heroes_cache = {}
                return self._heroes_cache
            out = {}
            for h in heroes:
                hid = h.get("id")
                name = h.get("localized_name") or h.get("name") or str(hid)
                if hid is not None:
                    out[int(hid)] = name
            self._heroes_cache = out
            return self._heroes_cache
        except Exception:
            self._heroes_cache = {}
            return self._heroes_cache

    def get_league_name(self, league_id):
        """
        Opcional: retorna nome da liga por ID (GET /leagues/{id}).
        Por simplicidade não cacheamos todas as ligas; pode ser expandido.
        """
        if not league_id:
            return str(league_id) if league_id is not None else "?"
        url = f"{OPENDOTA_BASE}/leagues/{league_id}"
        try:
            r = self._session.get(url, timeout=5)
            if r.status_code != 200:
                return str(league_id)
            data = r.json()
            return data.get("name") or str(league_id)
        except Exception:
            return str(league_id)


def game_time_str(seconds: int) -> str:
    """Converte game_time em segundos para string M:SS ou H:MM:SS."""
    if seconds is None or seconds < 0:
        return "0:00"
    s = int(seconds)
    m = s // 60
    s = s % 60
    h = m // 60
    m = m % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_live_game_summary(game: dict, heroes_map: dict = None) -> dict:
    """
    Extrai resumo de um jogo ao vivo para exibição na tabela.
    Returns: league_id, league_display, radiant_name, dire_name,
             radiant_score, dire_score, game_time_str, radiant_lead.
    """
    heroes_map = heroes_map or {}
    league_id = game.get("league_id") or 0
    radiant_name = (game.get("team_name_radiant") or "").strip() or "Radiant"
    dire_name = (game.get("team_name_dire") or "").strip() or "Dire"
    radiant_score = game.get("radiant_score") or 0
    dire_score = game.get("dire_score") or 0
    game_time = game.get("game_time") or 0
    radiant_lead = game.get("radiant_lead") or 0
    return {
        "match_id": game.get("match_id"),
        "league_id": league_id,
        "league_display": str(league_id) if league_id else "—",
        "radiant_name": radiant_name,
        "dire_name": dire_name,
        "radiant_score": radiant_score,
        "dire_score": dire_score,
        "game_time_str": game_time_str(game_time),
        "radiant_lead": radiant_lead,
        "game_time": game_time,
    }


def format_live_game_details(game: dict, heroes_map: dict = None) -> str:
    """
    Formata detalhes do jogo para o painel de texto (match_id, tempo, placar,
    vantagem de ouro, estado das torres, jogadores com heróis).
    """
    heroes_map = heroes_map or {}
    lines = []
    lines.append(f"Match ID: {game.get('match_id', '?')}")
    lines.append(f"Liga ID: {game.get('league_id') or '—'}")
    lines.append(f"Tempo de jogo: {game_time_str(game.get('game_time'))}")
    lines.append(f"Placar: Radiant {game.get('radiant_score') or 0} x {game.get('dire_score') or 0} Dire")
    lead = game.get("radiant_lead") or 0
    lines.append(f"Vantagem de ouro (Radiant): {lead:+d}")
    lines.append(f"Delay transmissão: {game.get('delay') or 0} s")
    lines.append("")
    # building_state: bitmask torres/barracks (opcional mostrar)
    building = game.get("building_state")
    if building is not None:
        lines.append(f"Building state (bitmask): {building}")
    lines.append("")
    lines.append("Jogadores:")
    players = game.get("players") or []
    radiant = [p for p in players if (p.get("team") or 0) == 0]
    dire = [p for p in players if (p.get("team") or 0) == 1]
    for label, side in [("Radiant", radiant), ("Dire", dire)]:
        lines.append(f"  [{label}]")
        for p in side:
            hero_id = p.get("hero_id")
            hero_name = heroes_map.get(hero_id, f"Hero {hero_id}") if hero_id is not None else "?"
            name = p.get("name") or p.get("personaname") or ""
            extra = f" — {name}" if name else ""
            lines.append(f"    {hero_name}{extra}")
    return "\n".join(lines)
