"""
Descobre de onde hawk.live e cross.bet pegam dados (API própria ou externa).
Analisa HTML e testa endpoints comuns.
"""
import requests
import re
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_and_analyze(name, url):
    print(f"\n{'='*60}\n{name}\n{url}\n{'='*60}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"Status: {r.status_code}")
        if r.status_code != 200:
            return None, url
        text = r.text
        # __NEXT_DATA__
        m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
        if m:
            try:
                data = json.loads(m.group(1))
                print("  [OK] __NEXT_DATA__ encontrado. Keys:", list(data.keys()))
                if "props" in data and isinstance(data["props"], dict):
                    print("      props.pageProps keys:", list(data["props"].get("pageProps", {}).keys())[:15])
            except Exception:
                print("  __NEXT_DATA__ (JSON inválido)")
        # Nuxt / __NUXT__
        if "__NUXT" in text or "nuxt" in text.lower():
            print("  Possível Nuxt.js (__NUXT)")
        # API URLs em " ou '
        api_urls = re.findall(r'["\'](https?://[^"\']*(?:api|graphql|v1|v2|/data/)[^"\']*)["\']', text, re.I)
        if api_urls:
            for u in list(set(api_urls))[:10]:
                print("  URL tipo API:", u[:90])
        # _next/data (Next.js)
        build = re.search(r'/_next/static/([a-zA-Z0-9_-]+)/', text)
        bid = build.group(1) if build else None
        if bid:
            print("  Next.js buildId:", bid)
        # Referências a fontes externas
        for term in ["stratz", "opendota", "dotabuff", "valve", "steam", "graphql", "/api/", "getMatch", "fetchMatch"]:
            if term.lower() in text.lower():
                print("  Contém referência:", term)
        return bid, url
    except Exception as e:
        print("  Erro:", e)
    return None, url

def try_endpoints(domain_name, base_url, paths):
    print(f"\n--- Testando endpoints {domain_name} ---")
    for path in paths:
        url = path if path.startswith("http") else (base_url.rstrip("/") + "/" + path.lstrip("/"))
        try:
            r = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=10)
            if r.status_code == 200:
                try:
                    j = r.json()
                    print(f"  [200 JSON] {url[:70]}... keys={list(j.keys())[:8]}")
                except Exception:
                    print(f"  [200] {url[:70]}... ({len(r.text)} bytes)")
            else:
                print(f"  [{r.status_code}] {path[:50]}")
        except requests.exceptions.Timeout:
            print(f"  [TIMEOUT] {path[:50]}")
        except Exception as e:
            print(f"  [ERR] {path[:50]} {e}")

def main():
    # Hawk.live
    build, _ = fetch_and_analyze(
        "Hawk Live",
        "https://hawk.live/dota-2/matches/dreamleague-division-2-season-3/aurora-vs-zero-tenacity"
    )
    try_endpoints("hawk.live", "https://hawk.live", [
        "/api/match/aurora-vs-zero-tenacity",
        "/api/matches/aurora-vs-zero-tenacity",
        "/api/dota-2/matches/dreamleague-division-2-season-3/aurora-vs-zero-tenacity",
        "/api/v1/matches/aurora-vs-zero-tenacity",
        "/graphql",
        f"/_next/data/{build}/dota-2/matches/dreamleague-division-2-season-3/aurora-vs-zero-tenacity.json" if build else "",
    ])

    # Cross.bet
    fetch_and_analyze("Cross.bet", "https://cross.bet/match/00001344890")
    try_endpoints("cross.bet", "https://cross.bet", [
        "/api/match/00001344890",
        "/api/matches/00001344890",
        "/api/v1/match/00001344890",
        "/graphql",
        "/_next/data/development/match/00001344890.json",
    ])

if __name__ == "__main__":
    main()
