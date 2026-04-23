# Instruções de Distribuição - LoL Oracle ML

## Problema Atual

No modo `--onefile`, o PyInstaller empacota tudo em um único .exe, mas os arquivos `data/` e `model_artifacts/` precisam estar **na mesma pasta** do .exe para funcionar.

## Solução: Usar --onedir

O build atual está configurado para `--onedir`, que cria uma estrutura assim:

```
dist/
  LoLOracleML/
    LoLOracleML.exe
    data/
      champion_impacts.csv
      league_stats_v3.pkl
      ...
    model_artifacts/
      trained_models_v3.pkl
      scaler_v3.pkl
      ...
    [outros arquivos do PyInstaller]
```

## Como Distribuir

1. **Após o build**, vá para a pasta `dist/LoLOracleML/`
2. **Copie toda a pasta** `LoLOracleML/` para onde quiser distribuir
3. O usuário deve executar `LoLOracleML.exe` de dentro dessa pasta

## Alternativa: Modo Onefile (Mais Complexo)

Se quiser um único .exe, você precisa:

1. Buildar com `--onefile`
2. **Copiar manualmente** as pastas `data/` e `model_artifacts/` para a mesma pasta do .exe
3. Distribuir tudo junto

O sistema de paths já está configurado para procurar na pasta do .exe, então funcionará em ambos os casos.

## Verificação

Após buildar, verifique se os arquivos estão presentes:

```powershell
# Verificar estrutura
dir dist\LoLOracleML
dir dist\LoLOracleML\data
dir dist\LoLOracleML\model_artifacts
```

Se os arquivos não estiverem lá, o PyInstaller não os incluiu. Verifique o arquivo `.spec`.
