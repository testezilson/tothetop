# Guia de Uso - LoL Oracle ML Desktop App

## Como Executar

### Modo Desenvolvimento

```powershell
# Ativar virtual environment (se estiver usando)
.\venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt

# Executar aplicação
python src\app\main.py
```

### Modo Executável

1. Fazer build do .exe (ver `README_BUILD.md`)
2. Executar `dist\LoLOracleML.exe`

## Funcionalidades

### 1. LoL - Pré-bets

Análise de apostas pré-jogo usando histórico H2H.

**Como usar:**
1. Selecione a liga (ex: LCK, LPL, LEC)
2. Selecione Time 1 e Time 2
3. Digite a odd oferecida pela casa de apostas
4. Clique em "Calcular"
5. Veja as probabilidades, fair odds e EV
6. Se o EV for positivo, clique em "Salvar no Histórico"

**Interpretação:**
- **EV positivo (verde)**: Aposta com valor esperado positivo
- **EV negativo (vermelho)**: Aposta com valor esperado negativo
- **Fair Odd**: Odd justa baseada na probabilidade real

### 2. LoL - Draft Live

Análise de draft em tempo real durante o jogo.

**Como usar:**
1. Selecione a liga
2. Ajuste o threshold (padrão: 0.55)
3. Digite os 5 campeões do Time 1 (Blue Side)
4. Digite os 5 campeões do Time 2 (Red Side)
5. Clique em "Analisar Draft"
6. Veja as recomendações por linha de kills

**Interpretação:**
- **Kills Estimados**: Total de kills previsto para o jogo
- **Impacto Time 1/2**: Soma dos impactos individuais dos campeões
- **Prob(UNDER/OVER)**: Probabilidade de ficar abaixo/acima da linha
- **Recomendação**: UNDER ou OVER com nível de confiança (High/Medium/Low)
- **Sinergias**: Pares de campeões que jogam bem juntos
- **Matchups**: Confrontos diretos entre campeões

## Histórico de Apostas

Todas as apostas salvas são armazenadas em:
- Windows: `%APPDATA%\LoLOracleML\bets.db`

Você pode exportar o histórico para CSV (funcionalidade a ser adicionada na UI).

## Dicas

1. **Ligas Major**: LPL, LCK, LEC, CBLOL, LCS, LCP têm mais dados e previsões mais confiáveis
2. **Threshold**: Valores mais altos (0.60+) são mais conservadores, valores mais baixos (0.50-0.55) são mais agressivos
3. **Nomes de Campeões**: Use os nomes exatos como aparecem no jogo (ex: "Kai'Sa", não "Kaisa")
4. **Dados Insuficientes**: Se um campeão não aparecer nos resultados, pode não ter dados suficientes na liga selecionada

## Troubleshooting

### App não abre
- Verifique se todas as dependências estão instaladas
- Execute em modo desenvolvimento para ver erros no console

### Dados não carregam
- Verifique se `data/` e `model_artifacts/` existem e têm os arquivos necessários
- No .exe, esses arquivos devem estar na mesma pasta do executável

### Análise não funciona
- Verifique se os nomes dos campeões/times estão corretos
- Alguns campeões podem não ter dados suficientes em ligas menores
