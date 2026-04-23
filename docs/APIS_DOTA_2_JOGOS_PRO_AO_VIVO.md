# APIs de Dota 2 para jogos profissionais ao vivo — que a gente pode usar

Pesquisa feita com base em documentação e artigos públicos. Todas são utilizáveis no projeto (com limites e termos de cada serviço).

---

## 1. OpenDota — **já usamos no projeto**

| Item | Detalhe |
|------|--------|
| **Docs** | [docs.opendota.com](https://docs.opendota.com/) |
| **Base** | `https://api.opendota.com/api` |
| **Jogos ao vivo** | `GET /live` — lista partidas em andamento (inclui pro quando `league_id` > 0) |
| **Jogos pro (histórico)** | `GET /proMatches` — partidas profissionais já finalizadas |
| **Custo** | Grátis. Sem key: 50k req/mês, 60 req/min. [Key](https://www.opendota.com/api-keys) aumenta limite. |
| **Uso no app** | Aba **"Dota - Ao vivo"** já usa `get_pro_live()` filtrando por `league_id` / times nomeados. |

**Resumo:** É a opção principal que já está integrada para **jogos profissionais ao vivo**.

---

## 2. Stratz

| Item | Detalhe |
|------|--------|
| **Site / API** | [stratz.com](https://stratz.com), [api.stratz.com](https://api.stratz.com), [docs.stratz.com](https://docs.stratz.com) |
| **Formato** | REST + GraphQL |
| **Ao vivo** | Experiência de partida ao vivo em [stratz.com/matches/live](https://stratz.com/matches/live); a API oferece dados de partidas (incl. ao vivo e torneios). |
| **Custo** | Grátis. Anônimo: algumas centenas de req/hora; logado: 2.000 req/hora. |
| **Dados** | Match stats, jogadores, heróis, torneios, estatísticas; foco em live e analytics. |

**Resumo:** Boa opção para **complementar** OpenDota (mais dados ao vivo e analytics). Requer criar conta para limite maior.

---

## 3. Steam Web API (Valve) — fonte “oficial”

| Item | Detalhe |
|------|--------|
| **Docs** | [steamcommunity.com/dev](https://steamcommunity.com/dev) |
| **Key** | Obrigatória; grátis em [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey) |
| **Dota 2 ao vivo** | Interface **IDOTA2Match** — método **GetLiveLeagueGames** (partidas de liga ao vivo). |
| **Formato** | `https://api.steampowered.com/IDOTA2Match_570/GetLiveLeagueGames/v1/?key=SUA_KEY` |
| **Exemplos** | [GitHub - dota2webapiexamples](https://github.com/danieljennings/dota2webapiexamples) (ex.: live_league_signature.php) |

**Resumo:** Fonte direta da Valve para **jogos de liga ao vivo**. OpenDota provavelmente consome algo equivalente por baixo.

---

## 4. PandaScore

| Item | Detalhe |
|------|--------|
| **Docs** | [developers.pandascore.co](https://developers.pandascore.co/) — [Dota 2](https://developers.pandascore.co/docs/dota-2), [List matches](https://developers.pandascore.co/reference/get_dota2_matches) |
| **Base** | `https://api.pandascore.co/dota2/matches` |
| **Custo** | Plano grátis: 1.000 req/hora, calendário, pré-jogo (torneios, times, jogadores). **Dados em tempo real** (live) em planos pagos (a partir de ~€400–1000/mês). |
| **Dados** | Torneios, partidas, times, jogadores, estatísticas; live completo só pago. |

**Resumo:** Útil para **calendário e pré-jogo** de torneios; para **ao vivo completo** é pago.

---

## 5. Outras fontes (pagos ou sem foco em “live pro”)

- **Bayes Esports**, **GRID (grid.gg)** — dados ao vivo para betting/empresas; API comercial.
- **BetsAPI** — esports odds e fixtures; tem API, foco em apostas.
- **dota2.balldontlie.io** — API Dota 2 com outro modelo de key; menos citada para “live pro”.

---

## Resumo: o que usar para “jogos profissionais ao vivo”

| Objetivo | API recomendada | Observação |
|----------|-----------------|------------|
| **Listar jogos pro ao vivo** | **OpenDota** `GET /live` | Já integrado; filtrar por `league_id` ou times nomeados. |
| **Mais dados ao vivo / analytics** | **Stratz** | REST/GraphQL; criar conta para 2k req/h. |
| **Fonte oficial (ligas)** | **Steam Web API** (GetLiveLeagueGames) | Requer Steam API key (grátis). |
| **Calendário / torneios** | **PandaScore** (tier grátis) | Live detalhado é pago. |

**Conclusão:** Para o nosso caso (buscar **jogos profissionais ao vivo** e poder usar na aplicação), as opções que **já podemos usar** hoje são:

1. **OpenDota** — já está no projeto.  
2. **Stratz** — adicionar integração (REST ou GraphQL) para enriquecer.  
3. **Steam Web API** — opcional, para ter fonte direta Valve; precisa só de API key.

Referências usadas na pesquisa: [OpenDota API](https://docs.opendota.com/), [Stratz API](https://stratz.medium.com/stratz-api-major-update-5557335dbdfd), [Dota 2 Live Matches (Stratz)](https://medium.com/stratz/dota-2-live-matches-639021bede36), [Steam Web API](https://steamcommunity.com/dev), [PandaScore Dota 2](https://developers.pandascore.co/docs/dota-2), [PandaScore pricing](https://www.pandascore.co/pricing).
