# Guia de Build - LoL Oracle ML Desktop App

## Pré-requisitos

1. Python 3.8+ instalado
2. Virtual environment ativado (se estiver usando)
3. Todas as dependências instaladas: `pip install -r requirements.txt`

## Estrutura do Projeto

```
lol_oracle_ml_v3/
├── src/
│   ├── app/              # Interface gráfica (PySide6)
│   │   ├── main.py       # Ponto de entrada
│   │   └── ui/           # Componentes de UI
│   └── core/             # Lógica de negócio (sem UI)
│       ├── shared/       # Utilitários compartilhados
│       └── lol/          # Módulos específicos do LoL
├── data/                 # Dados (CSV, PKL) - será incluído no .exe
├── model_artifacts/      # Modelos ML - será incluído no .exe
└── build_scripts/        # Scripts de build
```

## Como Fazer o Build

### Opção 1: Usando o script PowerShell (Windows)

```powershell
.\build_scripts\build_pyinstaller.ps1
```

### Opção 2: Usando o arquivo .spec (recomendado)

```powershell
pyinstaller build_pyinstaller.spec
```

### Opção 3: Comando manual

```powershell
pyinstaller --name=LoLOracleML --windowed --onefile --clean --noconfirm --add-data="data;data" --add-data="model_artifacts;model_artifacts" src\app\main.py
```

## Resultado

O executável será criado em `dist/LoLOracleML.exe`.

## Testando o Executável

1. Execute `dist/LoLOracleML.exe`
2. Verifique se a janela abre corretamente
3. Teste as funcionalidades:
   - LoL Pré-bets: Selecione liga, times, odd e calcule
   - LoL Draft Live: Digite os campeões e analise

## Problemas Comuns

### "Arquivo não encontrado" ao executar o .exe

- Verifique se `data/` e `model_artifacts/` estão sendo incluídos corretamente
- O sistema de paths (`src/core/shared/paths.py`) deve funcionar tanto em dev quanto no .exe

### App abre mas não carrega dados

- Verifique os logs (se houver console)
- Confirme que os arquivos estão na pasta `data/` e `model_artifacts/`

### App muito lento para abrir

- Normal com PyInstaller (pode levar 5-10 segundos)
- Considere usar Nuitka para builds mais rápidos (mais complexo)

## Próximos Passos

1. Adicionar ícone personalizado (`resources/icon.ico`)
2. Implementar módulos Dota
3. Adicionar página de histórico de apostas na UI
4. Otimizar tamanho do .exe (excluir módulos não usados)
