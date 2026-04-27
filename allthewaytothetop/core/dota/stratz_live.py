"""
Cliente para a API Stratz (GraphQL) — partidas ao vivo e dados de jogos profissionais.
Requer API key (JWT) em STRATZ_API_KEY ou passada no construtor.
A Stratz usa Cloudflare; se der 403, instale: pip install cloudscraper
Documentação: https://docs.stratz.com/ (REST + GraphQL em api.stratz.com)
"""
import os
import requests

STRATZ_GRAPHQL_URL = "https://api.stratz.com/graphql"

# Headers de navegador para reduzir 403 (Cloudflare)
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://stratz.com",
    "Referer": "https://stratz.com/",
}


def _headers(token: str):
    return {
        **_BROWSER_HEADERS,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _make_session(api_key: str):
    """Usa cloudscraper se disponível (contorna Cloudflare), senão requests com headers de browser."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows"}
        )
        s = scraper
    except ImportError:
        s = requests.Session()
    s.headers.update(_headers(api_key))
    return s


class StratzLiveClient:
    """Cliente Stratz para dados ao vivo (GraphQL). Use STRATZ_API_KEY no ambiente."""

    def __init__(self, api_key: str = None):
        self.api_key = (api_key or os.environ.get("STRATZ_API_KEY") or "").strip()
        if not self.api_key:
            raise ValueError("Stratz exige API key. Defina STRATZ_API_KEY ou passe api_key=.")
        self._session = _make_session(self.api_key)

    def _graphql(self, query: str, variables: dict = None) -> dict:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        r = self._session.post(STRATZ_GRAPHQL_URL, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(f"Stratz GraphQL errors: {data['errors']}")
        return data.get("data") or {}

    def get_live_matches(self):
        """
        Partidas ao vivo via Stratz (live.matches).
        Retorna dict com chave "live" -> "matches" -> lista de MatchLiveType.
        Campos: matchId, radiantScore, direScore, leagueId, gameTime, radiantLead,
                radiantTeamId, direTeamId, radiantTeam, direTeam, players, etc.
        """
        query = """
        query GetLiveMatches {
            live {
                matches {
                    matchId
                    radiantScore
                    direScore
                    leagueId
                    gameTime
                    radiantLead
                    radiantTeamId
                    direTeamId
                    delay
                    spectators
                    averageRank
                    buildingState
                    completed
                    gameMode
                    gameState
                    gameMinute
                    radiantTeam {
                        id
                        name
                        tag
                    }
                    direTeam {
                        id
                        name
                        tag
                    }
                    league {
                        id
                        name
                    }
                    players {
                        steamAccountId
                        heroId
                        isRadiant
                        goldPerMinute
                        experiencePerMinute
                        networth
                        level
                    }
                }
            }
        }
        """
        data = self._graphql(query)
        return data.get("live", {}).get("matches") or []

    def get_match(self, match_id: int):
        """Detalhes de uma partida por ID (pode ser ao vivo ou finalizada)."""
        query = """
        query GetMatch($id: Long!) {
            match(id: $id) {
                id
                didRadiantWin
                durationSeconds
                startDateTime
                leagueId
                radiantTeamId
                direTeamId
                radiantScore
                direScore
                players {
                    steamAccountId
                    heroId
                    isRadiant
                    kills
                    deaths
                    assists
                    goldPerMinute
                }
            }
        }
        """
        return self._graphql(query, {"id": match_id})
