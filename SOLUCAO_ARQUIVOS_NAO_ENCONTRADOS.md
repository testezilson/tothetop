# Solução: Arquivos não encontrados no .exe

## Problema

O .exe não encontra os arquivos em `data/` e `model_artifacts/` porque:

1. No modo `--onefile`, o PyInstaller extrai tudo para um diretório temporário (`_MEIPASS`)
2. Os dados devem estar **na mesma pasta do .exe**, não dentro do .exe

## Solução

### Opção 1: Modo --onedir (Recomendado)

Use `--onedir` em vez de `--onefile`. Isso cria uma pasta com o .exe e todos os arquivos:

```python
# No build_pyinstaller.spec, mudar:
exe = EXE(
    ...
    # Remover ou comentar para usar onedir
    # onefile=True,  # Comentar esta linha
)
```

Ou usar diretamente:
```powershell
pyinstaller --name=LoLOracleML --windowed --onedir --add-data="data;data" --add-data="model_artifacts;model_artifacts" src/app/main.py
```

### Opção 2: Copiar arquivos manualmente

Se usar `--onefile`, copie manualmente as pastas `data/` e `model_artifacts/` para a mesma pasta do .exe:

```
dist/
  LoLOracleML.exe
  data/
    champion_impacts.csv
    league_stats_v3.pkl
    ...
  model_artifacts/
    trained_models_v3.pkl
    scaler_v3.pkl
    ...
```

### Opção 3: Ajustar o sistema de paths

O sistema de paths já está configurado para procurar na pasta do .exe. Se ainda não funcionar, verifique se os arquivos estão lá.

## Verificação

Após rebuildar, verifique se os arquivos estão na mesma pasta do .exe:

```powershell
# Listar arquivos na pasta dist
dir dist\LoLOracleML.exe
dir dist\data
dir dist\model_artifacts
```

Se os arquivos não estiverem lá, eles precisam ser copiados manualmente ou usar `--onedir`.
