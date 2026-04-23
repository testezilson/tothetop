# Explicação das Métricas - Comparador de Composições

## 1. Win Rate Médio dos Campeões

### O que é?
É a **média simples** dos win rates individuais de cada campeão na composição.

### Como é calculado?
1. Para cada campeão na composição, busca-se seu win rate individual na liga
2. O win rate individual é calculado como: `(vitórias do campeão / total de jogos do campeão) * 100`
3. Soma-se todos os win rates e divide pelo número de campeões (5)

### Exemplo:
Composição: Gnar, Nocturne, Orianna, Varus, Neeko

- Gnar: 42.59% WR (23 vitórias em 54 jogos)
- Nocturne: 45.00% WR (exemplo)
- Orianna: 52.00% WR (exemplo)
- Varus: 48.00% WR (exemplo)
- Neeko: 50.00% WR (exemplo)

**Win Rate Médio = (42.59 + 45.00 + 52.00 + 48.00 + 50.00) / 5 = 47.32%**

### O que significa?
- Indica a "força média" dos campeões individuais
- Valores acima de 50% = campeões acima da média da liga
- Valores abaixo de 50% = campeões abaixo da média da liga

---

## 2. Impacto Médio de Sinergias

### O que é?
É a **média dos impactos de sinergia** de todos os pares de campeões que jogam juntos no mesmo time.

### Como é calculado?
1. Para cada par de campeões na composição (ex: Gnar + Varus), busca-se o win rate quando eles jogam juntos
2. Calcula-se o **impacto de sinergia**: `win_rate_do_par - win_rate_médio_da_liga`
3. Soma-se todos os impactos e divide pelo número de pares (10 pares em uma composição de 5 campeões)

### Exemplo:
Composição: Gnar, Nocturne, Orianna, Varus, Neeko

Pares de sinergia (10 pares):
- Gnar + Nocturne: WR = 40%, Impacto = 40% - 49.50% = -9.50%
- Gnar + Orianna: WR = 45%, Impacto = 45% - 49.50% = -4.50%
- Gnar + Varus: WR = 33.33%, Impacto = 33.33% - 49.50% = -16.17%
- Gnar + Neeko: WR = 50%, Impacto = 50% - 49.50% = +0.50%
- Nocturne + Orianna: WR = 48%, Impacto = 48% - 49.50% = -1.50%
- ... (outros 5 pares)

**Impacto Médio = média de todos os 10 impactos**

### O que significa?
- **Impacto positivo (+5%)**: Os campeões jogam bem juntos, aumentando o win rate acima da média
- **Impacto negativo (-5%)**: Os campeões não combinam bem, reduzindo o win rate abaixo da média
- **Impacto zero (0%)**: Os campeões jogam juntos de forma neutra, sem benefício ou prejuízo

### Importante:
- O impacto é calculado **além** do win rate individual dos campeões
- Mesmo que dois campeões tenham win rates altos individualmente, eles podem ter sinergia negativa quando jogam juntos
- Ou vice-versa: campeões com win rates médios podem ter excelente sinergia juntos

---

## 3. Como são usados no Score Total?

O score final combina esses fatores:

```
Score = (Win Rate Médio * 30%) + (Impacto Sinergias * 30%) + (Win Rate Composição Completa * 40%)
```

Se não houver dados da composição completa, os outros fatores têm peso maior.

---

## Resumo Visual

```
Win Rate Médio dos Campeões (47.32%)
├─ Gnar: 42.59%
├─ Nocturne: 45.00%
├─ Orianna: 52.00%
├─ Varus: 48.00%
└─ Neeko: 50.00%

Impacto Médio de Sinergias (-9.67%)
├─ Gnar + Nocturne: -9.50%
├─ Gnar + Orianna: -4.50%
├─ Gnar + Varus: -16.17%
├─ Gnar + Neeko: +0.50%
├─ Nocturne + Orianna: -1.50%
└─ ... (outros 5 pares)
```
