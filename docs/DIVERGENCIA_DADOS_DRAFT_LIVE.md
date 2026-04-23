# Por que Draft Live e TESTE LOL LIVE GAME não mostram todos os jogos (ex.: Twisted Fate)

## Resumo

**LoL - Draft Live** e **TESTE LOL LIVE GAME** (e Comparar Composições, etc.) usam sempre o arquivo **`data/oracle_prepared.csv`** dentro do projeto — **não** o CSV que está em `C:\Users\Lucas\Documents\db2026`.

Se esse `oracle_prepared.csv` tiver poucos jogos (por exemplo só 3 partidas com Twisted Fate), a aplicação só “enxerga” esses jogos. A divergência acontece porque **o CSV do db2026 não é usado diretamente** pela app; é preciso **atualizar** o `oracle_prepared.csv` a partir dele.

---

## Fluxo de dados

```
┌─────────────────────────────────────────────────────────────────────────┐
│  C:\Users\Lucas\Documents\db2026\                                        │
│  2026_LoL_esports_match_data_from_OraclesElixir.csv                      │
│  (formato Oracles Elixir: 1 linha por JOGADOR)                           │
│  → Aqui estão todos os 8+ jogos de Twisted Fate que você viu no site.   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  Só entra no projeto se você rodar
                                    │  a ATUALIZAÇÃO (ver abaixo)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  lol_oracle_ml_v3/data/oracle_prepared.csv                              │
│  (formato do projeto: 1 linha por TIME por partida, pick1..pick5)        │
│  → Este é o arquivo que Draft Live, TESTE LOL LIVE GAME e Compare usam.  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
         champion_impacts.csv   champion_winrates   synergy/comp/matchup
         (generate_champion_    (generate_champion_ (outros scripts)
          impacts.py)           winrates.py, etc.)
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                    ┌───────────────────────────────────┐
                    │  LoL - Draft Live                  │
                    │  TESTE LOL LIVE GAME               │
                    │  Comparar Composições              │
                    │  (todos leem data/ do projeto)     │
                    └───────────────────────────────────┘
```

- **db2026**: fonte completa (Oracles Elixir).
- **oracle_prepared.csv**: única fonte usada pela app; precisa ser gerado/atualizado a partir do db2026.
- **champion_impacts.csv** e demais estatísticas são **derivados** do `oracle_prepared.csv`. Se ele tiver poucos jogos, esses arquivos também terão poucos jogos/campeões.

Por isso: mesmo tendo todos os jogos no db2026, se o `oracle_prepared.csv` não for atualizado com esse CSV, **continuamos sem achar todos os jogos** no Draft Live e no TESTE LOL LIVE GAME.

---

## Por que há divergência para vários campeões?

- **Draft Live** e **TESTE LOL LIVE GAME** usam:
  - Lista de campeões e impacto/n de jogos: vinda de `champion_impacts.csv` e/ou `oracle_prepared.csv`.
  - Esses arquivos são gerados **a partir de `data/oracle_prepared.csv`**.
- Se `oracle_prepared.csv` tiver só um subconjunto de partidas (ex.: só algumas de 2026 ou de um export antigo), então:
  - Só esses jogos entram em `champion_impacts.csv` e nos win rates.
  - Só os campeões que aparecem nesse subconjunto têm “n” e impacto; os outros ficam “faltando” ou com poucos jogos.
- Ou seja: a divergência é a **mesma** para Twisted Fate e para outros campeões — **fonte de verdade da app é só `data/oracle_prepared.csv`**, e ele está desatualizado em relação ao db2026.

---

## Como alinhar: usar os jogos do db2026 no Draft Live e no TESTE LOL LIVE GAME

É preciso **substituir** o `data/oracle_prepared.csv` pelos jogos do CSV do db2026 (convertidos para o formato do projeto) e **regenerar** os arquivos que dependem dele.

### Opção 1: Pela aplicação (recomendado)

1. Abra a aba **“Atualizar Bancos”** (ou equivalente).
2. Selecione o CSV do db2026 (ou deixe o app usar o padrão, se estiver configurado para `C:\Users\Lucas\Documents\db2026`).
3. Clique em **“Atualizar Draft/Compare LoL”** (ou “Atualizar LoL Draft/Compare”).
4. Isso roda o script que:
   - Converte o CSV Oracles Elixir → formato `oracle_prepared` (1 linha por time, pick1..pick5, etc.).
   - **Substitui** `data/oracle_prepared.csv` por esse resultado.
   - Regenera `champion_impacts.csv`, win rates, sinergias, matchups, etc.

Depois disso, Draft Live e TESTE LOL LIVE GAME passam a usar **todos os jogos** que estavam no CSV do db2026 (incluindo os 8 de Twisted Fate e os outros campeões).

### Opção 2: Pelo terminal

Na raiz do projeto:

```bash
python atualizar_apenas_2026.py "C:\Users\Lucas\Documents\db2026\2026_LoL_esports_match_data_from_OraclesElixir.csv" --yes
```

Isso faz o mesmo: substitui `data/oracle_prepared.csv` e regenera os arquivos necessários.

---

## Conferência rápida

Depois de rodar a atualização:

- **Twisted Fate no script de histórico** (que lê `data/oracle_prepared.csv`):
  ```bash
  python scripts/show_champion_history_lol.py --campeao "Twisted Fate" --liga MAJOR
  ```
  Deve mostrar bem mais do que 1 jogo em MAJOR.

- **No app**: em **TESTE LOL LIVE GAME**, Twisted Fate deve aparecer na lista de campeões e, em **LoL - Draft Live**, os impactos e “n” de jogos devem bater com o que você vê no site/db2026.

---

## Resumo em uma frase

**Os jogos do db2026 só entram no Draft Live e no TESTE LOL LIVE GAME depois de você rodar a atualização que regrava `data/oracle_prepared.csv` a partir do CSV do db2026 e regenera os arquivos de impacto e win rate.**
