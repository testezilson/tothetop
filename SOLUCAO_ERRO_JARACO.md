# Solução para Erro "No module named 'jaraco'"

## Problema

Ao executar o .exe, você recebe o erro:
```
Failed to execute script 'pyi_rth_pkgres' due to unhandled exception: No module named 'jaraco'
```

## Causa

O PyInstaller tenta incluir automaticamente o hook `pyi_rth_pkgres` que depende de `pkg_resources` e `jaraco`, mas esses módulos não são necessários para a aplicação e não estão sendo incluídos corretamente.

## Soluções

### Solução 1: Usar arquivo .spec corrigido (RECOMENDADO)

Use o arquivo `build_pyinstaller_fix.spec` que exclui `pkg_resources`:

```powershell
pyinstaller build_pyinstaller_fix.spec
```

### Solução 2: Instalar jaraco e rebuildar

Se você realmente precisar de `pkg_resources`:

```powershell
pip install jaraco
pyinstaller build_pyinstaller.spec
```

### Solução 3: Desabilitar hook do pkg_resources manualmente

Edite o arquivo `.spec` e adicione:

```python
excludes=['pkg_resources'],
```

E remova qualquer referência a hooks do pkg_resources.

## Verificação

Após rebuildar, teste o executável:

```powershell
.\dist\LoLOracleML.exe
```

Se abrir sem erros, o problema foi resolvido!
