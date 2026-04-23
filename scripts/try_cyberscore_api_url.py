"""
Testa uma URL de API do Cyberscore.live que você descobriu no DevTools (Network).

Uso:
  1. Abra https://cyberscore.live/en/matches/164264/ no navegador.
  2. F12 → Network → filtro Fetch/XHR.
  3. Recarregue a página e encontre a requisição que retorna JSON da partida.
  4. Copie a URL completa e cole em CYBERSCORE_API_URL abaixo.
  5. Rode: python scripts/try_cyberscore_api_url.py
"""
import requests
import json
import os

# Cole aqui a URL que você viu no Network (ex.: _next/data/xxx/en/matches/164264.json)
CYBERSCORE_API_URL = ""

# Match ID para testar (pode mudar)
MATCH_ID = 164264

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://cyberscore.live/en/matches/",
}

def main():
    url = (CYBERSCORE_API_URL or os.environ.get("CYBERSCORE_API_URL", "")).strip()
    if not url:
        print("Cole a URL da API em CYBERSCORE_API_URL neste script,")
        print("ou defina a variável de ambiente: set CYBERSCORE_API_URL=<url>")
        return

    print("Testando:", url[:80], "...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print("Status:", r.status_code)
        print("Content-Type:", r.headers.get("Content-Type"))

        if r.status_code == 200:
            try:
                data = r.json()
                with open("cyberscore_api_sample.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print("Resposta JSON salva em cyberscore_api_sample.json")

                def keys_recursive(obj, prefix=""):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            keys_recursive(v, prefix + "." + k if prefix else k)
                    elif isinstance(obj, list) and obj and prefix:
                        print(f"  {prefix}: [list len={len(obj)}]")
                        keys_recursive(obj[0], prefix + "[0]")
                print("\nEstrutura (keys):")
                if isinstance(data, dict):
                    for k in list(data.keys())[:20]:
                        print(" ", k, "->", type(data[k]).__name__)
            except json.JSONDecodeError:
                print("Resposta não é JSON. Primeiros 500 chars:", r.text[:500])
        else:
            print("Body:", r.text[:400])
    except Exception as e:
        print("Erro:", e)


if __name__ == "__main__":
    main()
