# Solução Final: Arquivos não encontrados no .exe

## Problema Identificado

O erro mostra que o sistema está procurando em `_MEIPASS` (diretório temporário do PyInstaller), mas os arquivos não estão lá. Isso significa que o PyInstaller **não está incluindo** os arquivos `data/` e `model_artifacts/` no bundle.

## Solução: Verificar Build

O problema pode ser:

1. **Os arquivos não estão sendo incluídos no build** - O PyInstaller pode não estar encontrando os arquivos durante o build
2. **Caminhos relativos no .spec** - Podem não estar funcionando corretamente

## Passos para Resolver

### 1. Verificar se os arquivos existem na raiz

```powershell
dir data
dir model_artifacts
```

### 2. Rebuildar com caminhos absolutos

O arquivo `.spec` foi atualizado para usar caminhos absolutos. Rebuilde:

```powershell
pyinstaller build_pyinstaller.spec --clean
```

### 3. Verificar se os arquivos foram incluídos

Após o build, verifique o arquivo de log do PyInstaller:

```powershell
# Verificar se data/ e model_artifacts/ aparecem no log
type build\build_pyinstaller\warn-build_pyinstaller.txt | Select-String "data|model_artifacts"
```

### 4. Alternativa: Usar --onedir

Se o `--onefile` continuar com problemas, use `--onedir` que é mais confiável:

```powershell
# Editar build_pyinstaller.spec e adicionar COLLECT
# Ou usar diretamente:
pyinstaller --name=LoLOracleML --windowed --onedir --add-data="data;data" --add-data="model_artifacts;model_artifacts" src/app/main.py
```

No modo `--onedir`, os arquivos ficam na mesma pasta do .exe, facilitando a distribuição.

## Verificação Manual

Após rebuildar, execute o .exe e verifique a mensagem de erro. Ela deve mostrar onde está procurando. Se ainda mostrar `_MEIPASS`, os arquivos não foram incluídos no bundle.
