"""
Descobre possíveis endpoints de API do Cyberscore.live analisando o HTML/JS.
"""
import requests
import re
import json

def main():
    url = "https://cyberscore.live/en/matches/164264/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://cyberscore.live/en/matches/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        text = r.text
    except Exception as e:
        print("Erro ao buscar página:", e)
        return

    print("=== Tamanho da página:", len(text), "chars ===\n")

    # 1. __NEXT_DATA__ (Next.js)
    next_match = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', text)
    if next_match:
        try:
            data = json.loads(next_match.group(1))
            print("__NEXT_DATA__ encontrado! Keys:", list(data.keys()))
            if "props" in data:
                print("  props keys:", list(data["props"].keys()) if isinstance(data["props"], dict) else type(data["props"]))
            # Save sample
            with open("cyberscore_next_data.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("  (amostra salva em cyberscore_next_data.json)")
        except json.JSONDecodeError as e:
            print("  __NEXT_DATA__ JSON inválido:", e)
    else:
        print("__NEXT_DATA__: não encontrado")

    # 2. Outros dados embutidos (window.__INITIAL_STATE__, etc.)
    for pattern_name, pattern in [
        ("window.__INITIAL_STATE__", r'window\.__INITIAL_STATE__\s*=\s*(\{[^;]+\});'),
        ("buildId / assetPrefix", r'["\']([^"\']*/_next/static/[^"\']+)["\']'),
        ("/api/", r'["\']([^"\']*/api/[^"\']*)["\']'),
        ("api.cyberscore", r'(https?://[^"\'\s]*api[^"\'\s]*cyberscore[^"\'\s]*)'),
        ("graphql", r'["\']([^"\']*graphql[^"\']*)["\']'),
        ("/v1/ ou /v2/", r'["\']([^"\']*/(?:v1|v2)/[^"\']*)["\']'),
    ]:
        matches = re.findall(pattern, text, re.I)
        if matches:
            print(f"\n{pattern_name}: {list(set(matches))[:8]}")

    # 3. Scripts externos
    script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text)
    print("\nScripts externos (src):")
    for s in script_srcs[:20]:
        if "api" in s.lower() or "chunk" in s or "_next" in s:
            print(" ", s[:100])

    # 4. Links que parecem API (href ou fetch)
    api_like = re.findall(r'["\'](https?://[^"\']*cyberscore[^"\']*(?:api|v1|v2|graphql|data)[^"\']*)["\']', text, re.I)
    if api_like:
        print("\nURLs tipo API:", list(set(api_like))[:10])

    # 5. Tentar endpoint comum Next.js para dados da página
    # Next.js usa /_next/data/<buildId>/en/matches/164264.json
    build_id = re.search(r'/_next/static/([^/]+)/', text)
    if build_id:
        bid = build_id.group(1)
        print("\nBuildId (Next):", bid)
        data_url = f"https://cyberscore.live/_next/data/{bid}/en/matches/164264.json"
        print("Tentando URL de dados Next.js:", data_url)
        try:
            r2 = requests.get(data_url, headers=headers, timeout=15)
            print("  Status:", r2.status_code)
            if r2.status_code == 200:
                j = r2.json()
                print("  Keys:", list(j.keys()) if isinstance(j, dict) else type(j))
                with open("cyberscore_match_data.json", "w", encoding="utf-8") as f:
                    json.dump(j, f, indent=2, ensure_ascii=False)
                print("  Dados salvos em cyberscore_match_data.json")
        except Exception as e:
            print("  Erro:", e)


if __name__ == "__main__":
    main()
