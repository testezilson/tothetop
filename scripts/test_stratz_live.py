"""
Testa a API Stratz para partidas ao vivo (com API key).
Defina STRATZ_API_KEY no ambiente ou passe como argumento.
Uso: set STRATZ_API_KEY=seu_jwt && python scripts/test_stratz_live.py
"""
import os
import sys
import requests
import json

STRATZ_TOKEN = os.environ.get("STRATZ_API_KEY", "").strip()
if not STRATZ_TOKEN and len(sys.argv) > 1:
    STRATZ_TOKEN = sys.argv[1].strip()

# Headers de navegador (Cloudflare costuma bloquear sem isso)
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://stratz.com",
    "Referer": "https://stratz.com/",
}
HEADERS = {
    **_BROWSER_HEADERS,
    "Authorization": f"Bearer {STRATZ_TOKEN}",
    "Content-Type": "application/json",
} if STRATZ_TOKEN else {"Content-Type": "application/json", "Accept": "application/json"}

# Usar cloudscraper se instalado (ajuda a passar no Cloudflare)
try:
    import cloudscraper
    _scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows"})
    _scraper.headers.update(HEADERS)
    _session = _scraper
except ImportError:
    _session = requests.Session()
    _session.headers.update(HEADERS)

# GraphQL endpoint
GRAPHQL_URL = "https://api.stratz.com/graphql"


def graphql_query(query: str, variables: dict = None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = _session.post(GRAPHQL_URL, json=payload, timeout=15)
    return r.status_code, r.json() if "application/json" in (r.headers.get("content-type") or "") else r.text


def main():
    if not STRATZ_TOKEN:
        print("Defina STRATZ_API_KEY no ambiente ou passe o token como argumento.")
        return
    try:
        import cloudscraper
        print("(Usando cloudscraper para tentar passar no Cloudflare)\n")
    except ImportError:
        print("(Dica: pip install cloudscraper pode ajudar a evitar 403)\n")
    print("=== 1. Introspection: tipos que contêm 'live' ou 'match' ===\n")
    # Query para listar tipos disponíveis (schema)
    intro_query = """
    query {
        __schema {
            queryType {
                fields {
                    name
                    description
                }
            }
        }
    }
    """
    code, data = graphql_query(intro_query)
    print("Status:", code)
    if isinstance(data, dict) and "data" in data and data.get("data", {}).get("__schema"):
        fields = data["data"]["__schema"]["queryType"]["fields"]
        for f in fields:
            name = f.get("name", "")
            if "live" in name.lower() or "match" in name.lower() or "game" in name.lower():
                print(f"  {name}: {f.get('description', '')[:80]}")
    elif isinstance(data, dict) and "errors" in data:
        print("Errors:", data["errors"])
    else:
        print("Response:", str(data)[:500])

    print("\n=== 2. Tentativa: query 'live' ou 'match' (nomes comuns) ===\n")
    # Tentar queries comuns
    for qname, query in [
        ("findLiveMatch", "{ findLiveMatch { matchId } }"),
        ("liveMatches", "{ liveMatches { matchId } }"),
        ("live", "{ live { matchId } }"),
        ("match", "{ match(id: 1) { id } }"),
    ]:
        code, data = graphql_query(query)
        if isinstance(data, dict):
            if "data" in data and data["data"]:
                print(f"  [OK] {qname}:", json.dumps(data)[:200])
            elif "errors" in data:
                print(f"  [ERR] {qname}:", data["errors"][0].get("message", "")[:80])
        else:
            print(f"  [???] {qname}:", str(data)[:80])

    print("\n=== 3. REST: GET /v1/... (se existir) ===\n")
    for path in ["/v1/live", "/v1/match/live", "/live", "/match/live"]:
        url = "https://api.stratz.com" + path
        try:
            r = _session.get(url, timeout=10)
            print(f"  {path}: {r.status_code}")
            if r.status_code == 200 and r.text:
                try:
                    j = r.json()
                    print(f"       keys: {list(j.keys()) if isinstance(j, dict) else type(j)}")
                except Exception:
                    print(f"       body: {r.text[:150]}")
        except Exception as e:
            print(f"  {path}: {e}")

    print("\n=== 3b. Introspection: LiveQuery e MatchLiveType ===\n")
    for type_name in ["LiveQuery", "MatchLiveType"]:
        schema_q = """
        query($name: String!) {
            __type(name: $name) {
                name
                fields { name type { name kind ofType { name } } }
            }
        }
        """
        code, data = graphql_query(schema_q, {"name": type_name})
        if isinstance(data, dict) and data.get("data", {}).get("__type"):
            t = data["data"]["__type"]
            print(f"  {type_name}:", [f["name"] for f in (t.get("fields") or [])])
        else:
            print(f"  {type_name}: (erro ou vazio)")

    print("\n=== 4. Cliente core.dota.stratz_live.StratzLiveClient ===\n")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from core.dota.stratz_live import StratzLiveClient
        client = StratzLiveClient(STRATZ_TOKEN)
        data = client.get_live_matches()
        print("Resposta (get_live_matches):")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
    except Exception as e:
        print("Erro:", e)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
