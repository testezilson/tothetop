# Testar Stratz API para jogos ao vivo (sua máquina)

A API Stratz (`api.stratz.com`) está atrás de **Cloudflare**. Se você receber **403 Forbidden**, tente:

1. **Instalar o cloudscraper** (contorna Cloudflare em muitos casos):
   ```powershell
   .\venv\Scripts\pip install cloudscraper
   ```
2. O cliente e o script de teste já usam **headers de navegador** (Chrome) e, se disponível, **cloudscraper** em vez de `requests` puro.

## 1. Configurar a API key

**Não commite o token.** Use variável de ambiente:

```powershell
# PowerShell (sessão atual)
$env:STRATZ_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Ou crie um arquivo `.env` na raiz do projeto (e adicione `.env` ao `.gitignore`):

```
STRATZ_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## 2. Rodar o teste

Na raiz do projeto, com o token definido:

```powershell
$env:PYTHONPATH = "src"
.\venv\Scripts\python.exe scripts\test_stratz_live.py
```

Se der **403**, rode no seu PC (onde você acessa stratz.com normalmente) e envie a saída para ajustarmos as queries.

## 3. O que a Stratz retorna para partidas ao vivo (já integrado)

O cliente `StratzLiveClient.get_live_matches()` usa a query `live { matches { ... } }`. Cada item em `matches` (tipo **MatchLiveType**) pode ter:

| Campo | Descrição |
|-------|-----------|
| `matchId` | ID da partida |
| `radiantScore` / `direScore` | Placar (kills) |
| `leagueId` | ID da liga (0 = não pro) |
| `gameTime` | Tempo de jogo em segundos |
| `radiantLead` | Vantagem de ouro (Radiant) |
| `radiantTeamId` / `direTeamId` | IDs dos times |
| `radiantTeam` / `direTeam` | `{ id, name, tag }` |
| `league` | `{ id, name }` |
| `delay`, `spectators`, `averageRank` | Metadados |
| `buildingState` | Estado das torres/barracks |
| `gameState`, `gameMinute`, `gameMode` | Estado do jogo |
| `players` | Lista com `steamAccountId`, `heroId`, `isRadiant`, `goldPerMinute`, `experiencePerMinute`, `networth`, `level` |

**Jogos profissionais:** filtre por `leagueId > 0` ou por `radiantTeam`/`direTeam` com nome. Retornar **0 partidas** significa que não há jogos ao vivo no momento (a API está ok).

## 4. Cliente no projeto

- **`src/core/dota/stratz_live.py`** — `StratzLiveClient(api_key=...)` com `get_live_matches()` e `get_match(match_id)`.
- A query GraphQL atual é uma **suposição**; quando a API responder, adaptamos aos nomes reais do schema.

## 5. Segurança

- **Nunca** commite o JWT no repositório.
- Use sempre `STRATZ_API_KEY` em ambiente ou em `.env` (e mantenha `.env` no `.gitignore`).
