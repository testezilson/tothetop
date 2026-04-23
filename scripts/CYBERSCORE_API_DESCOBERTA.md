# Como descobrir a API do Cyberscore.live (manual)

O site retorna **403 Forbidden** para requisições feitas por scripts (provavelmente proteção anti-bot). Por isso a descoberta precisa ser feita **no seu navegador**, usando as ferramentas de desenvolvedor.

## Passo a passo

1. **Abra o site**  
   https://cyberscore.live/en/matches/164264/  
   (ou qualquer partida ao vivo)

2. **Abra o DevTools**  
   - Chrome/Edge: `F12` ou `Ctrl+Shift+I`  
   - Aba **Network** (Rede)

3. **Filtre as requisições**  
   - Marque **Fetch/XHR** (ou "XHR" apenas) para ver só chamadas de API.  
   - Opcional: em "Filter", digite `json` ou `data`.

4. **Recarregue a página**  
   - `F5` ou `Ctrl+R`  
   - Ou clique em outra partida e volte.  
   - Fique de olho na lista de requisições que aparecem.

5. **Identifique a requisição de dados da partida**  
   Procure por algo como:
   - `/_next/data/XXXXXXXX/en/matches/164264.json`  
     (Next.js: `XXXXXXXX` é o buildId)
   - `/api/...`  
   - Qualquer URL que retorne **JSON** com dados do jogo (times, placar, jogadores).

6. **Anote**  
   - **URL completa** (ex.: `https://cyberscore.live/_next/data/abc123/en/matches/164264.json`)  
   - **Método**: GET (na maioria dos casos)  
   - **Headers** (se houver algo especial): em "Headers" da requisição, veja Request Headers (ex.: algum token ou header obrigatório).

7. **Testar no script**  
   No arquivo `try_cyberscore_api_url.py` você pode colar a URL descoberta e rodar o script para ver se conseguimos consumir a mesma API a partir do Python (pode continuar dando 403 se o servidor bloquear por User-Agent/origem).

## O que esperar (Next.js)

Se o site for **Next.js**, a chamada de dados da página costuma ser:

- **URL:**  
  `https://cyberscore.live/_next/data/<buildId>/en/matches/164264.json`  
  O `<buildId>` aparece no HTML da página (em algum `<script>` que carrega chunks) ou na própria URL de uma requisição que você ver na aba Network.

- **Resposta:**  
  JSON com `props`, `page`, etc., incluindo os dados da partida (times, jogadores, placar, etc.).

Depois de descobrir a URL e, se possível, salvar um exemplo de resposta JSON, podemos montar um cliente (ex.: em `core/dota/`) que use essa API no app.
