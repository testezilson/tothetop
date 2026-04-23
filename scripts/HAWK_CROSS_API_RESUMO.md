# De onde Hawk.live e Cross.bet pegam os dados – e o que podemos usar

## Resumo rápido

| Site       | API própria exposta? | Fonte provável                         | Dá para “copiar”?        |
|-----------|-----------------------|----------------------------------------|---------------------------|
| **Hawk.live** | Não (404 em /api, /graphql) | Pipeline próprio + Valve/Steam (ou parceiro) | Não a API deles; sim fontes públicas |
| **Cross.bet** | Não (404 em /api, /graphql) | Provedor comercial (Bayes, GRID, BetsAPI, etc.) | Só se assinarmos um provedor pago |

---

## 1. Hawk.live

- **O que o site diz:** “Event-driven architecture”, “real-time data pipelines”, “zero delay”, “process thousands of in-game events per second” ([About Hawk Live](https://hawk.live/about)).
- **O que encontramos:**  
  - Página responde 200, mas **não há `__NEXT_DATA__`** (não é Next.js com dados embutidos na página).  
  - **Nenhum endpoint público** respondeu: `/api/*` e `/graphql` deram **404**.  
  - No HTML há menções a **Valve** e **Steam** (texto genérico, não dá para saber se é API ou só referência).
- **Conclusão:**  
  - Eles têm **backend próprio** (não é “só um cliente” de uma API pública).  
  - Os dados ao vivo muito provavelmente vêm de **Valve/Steam** (ex.: Steam Web API para Dota 2) e/ou de algum **provedor comercial**.  
  - **Não existe API pública do Hawk** para replicarmos as chamadas deles.

---

## 2. Cross.bet

- **O que é:** Site de apostas em esports (Dota 2, CS, etc.).
- **O que encontramos:**  
  - **Todos os endpoints testados** (`/api/match/...`, `/api/v1/...`, `/graphql`, `/_next/data/...`) deram **404**.  
  - No HTML há menção a **Steam** (comum em sites de esports).
- **Conclusão:**  
  - Dados de partidas ao vivo costumam vir de **provedores de dados para betting** (ex.: [Bayes Esports](https://docs.bayesesports.com/), [GRID](https://grid.gg/), [BetsAPI](https://betsapi.com/), etc.).  
  - Esses provedores são **pagos** e **não públicos**.  
  - **Não dá para “copiar” a API do Cross.bet**; só usar a mesma fonte se fecharmos contrato com um desses provedores.

---

## 3. O que podemos usar (e já usamos)

Fontes **públicas** que podemos usar sem depender de Hawk ou Cross.bet:

### 3.1 OpenDota (já integrado no projeto)

- **URL:** [docs.opendota.com](https://docs.opendota.com/)
- **Ao vivo:** `GET https://api.opendota.com/api/live`  
  - Lista jogos ao vivo; filtramos por `league_id` para só profissionais.  
- **Sem API key** (com key aumenta rate limit).  
- É isso que a aba **“Dota - Ao vivo”** do seu app já usa.

### 3.2 Stratz

- **URL:** [api.stratz.com](https://api.stratz.com) / [docs.stratz.com](https://docs.stratz.com) (GraphQL e REST).
- **Ao vivo:** Experiência de partida ao vivo em [stratz.com/matches/live](https://stratz.com/matches/live); a API suporta dados de partidas (incl. ao vivo).
- **Acesso:** Gratuito, com limites (anon: algumas centenas req/hora; logado: 2000 req/hora).
- **Dá para “copiar” no sentido de:** usar a **mesma fonte pública** (Stratz) no seu app, não a do Hawk. Ou seja, podemos integrar a **API do Stratz** para enriquecer dados ao vivo, independente de Hawk/Cross.bet.

### 3.3 Valve Steam Web API

- **Ex.:** `GetLiveLeagueGames` (e relacionados) para Dota 2.
- **Requer:** [Steam Web API Key](https://steamcommunity.com/dev) (grátis, cadastro).
- **Uso:** Dados “oficiais” de ligas ao vivo; OpenDota provavelmente usa isso (ou fonte parecida) por baixo dos panos.

---

## 4. Resposta direta às suas perguntas

- **De onde esses sites pegam API?**  
  - **Hawk.live:** pipeline próprio; fonte dos dados muito provavelmente Valve/Steam e/ou parceiro comercial (não divulgado).  
  - **Cross.bet:** provedor comercial de dados para betting (Bayes, GRID, BetsAPI ou similar), não API pública.

- **Eles têm API própria?**  
  - **Hawk:** não expõe API pública (tudo que testamos deu 404).  
  - **Cross.bet:** não expõe API pública para nós.

- **É possível copiarmos?**  
  - **Copiar a API deles:** não; não está exposta.  
  - **Usar as mesmas fontes que eles (quando públicas):** sim.  
    - Já fazemos isso com **OpenDota** (aba Dota - Ao vivo).  
    - Podemos ainda usar **Stratz** e, se quiser ir “mais na fonte”, a **Steam Web API** com sua própria key.

Se quiser, no próximo passo podemos desenhar como integrar a **API do Stratz** (REST ou GraphQL) no seu app para enriquecer a aba “Dota - Ao vivo” com mais dados ao vivo, sem depender de Hawk ou Cross.bet.
