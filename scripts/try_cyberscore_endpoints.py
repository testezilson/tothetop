"""
Tenta vários endpoints possíveis do Cyberscore.live (Next.js data, API, etc.)
"""
import requests
import json

BASE = "https://cyberscore.live"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://cyberscore.live/en/matches/",
}

# Endpoints comuns para Next.js e APIs
URLS = [
    # Next.js data (buildId típico é hash)
    f"{BASE}/_next/data/development/en/matches/164264.json",
    f"{BASE}/_next/data/development/en/matches.json",
    f"{BASE}/en/matches/164264.json",
    f"{BASE}/api/match/164264",
    f"{BASE}/api/matches/164264",
    f"{BASE}/api/v1/matches/164264",
    f"{BASE}/api/v2/matches/164264",
    f"{BASE}/api/matches/164264/",
    f"{BASE}/graphql",
    # Às vezes a API está em subdomínio
    "https://api.cyberscore.live/match/164264",
    "https://api.cyberscore.live/matches/164264",
    "https://api.cyberscore.live/v1/matches/164264",
]

def try_url(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                try:
                    d = r.json()
                    return "OK_JSON", r.status_code, list(d.keys())[:15] if isinstance(d, dict) else type(d).__name__
                except Exception:
                    return "OK_TEXT", r.status_code, len(r.text)
            return "OK", r.status_code, len(r.text)
        return "HTTP", r.status_code, None
    except requests.exceptions.Timeout:
        return "TIMEOUT", None, None
    except requests.exceptions.RequestException as e:
        return "ERR", None, str(e)[:80]

def main():
    print("Testando endpoints Cyberscore.live...\n")
    for url in URLS:
        status, code, extra = try_url(url)
        if status == "OK_JSON":
            print(f"[OK JSON] {code}  {url}")
            print(f"          -> keys: {extra}")
        elif status == "OK" or status == "OK_TEXT":
            print(f"[OK]      {code}  {url}  ({extra} bytes)")
        else:
            print(f"[{status:8}] {code or '-'}  {url}  {extra or ''}")

if __name__ == "__main__":
    main()
