# Script PowerShell para build do executável com PyInstaller
# Uso: .\build_scripts\build_pyinstaller.ps1

Write-Host "=== LoL Oracle ML - Build PyInstaller ===" -ForegroundColor Green

# Verificar se está no diretório correto
if (-not (Test-Path "src\app\main.py")) {
    Write-Host "ERRO: Execute este script da raiz do projeto!" -ForegroundColor Red
    exit 1
}

# Nome do executável
$APP_NAME = "LoLOracleML"
$ICON_PATH = "resources\icon.ico"  # Opcional - criar depois se quiser

# Preparar argumentos do PyInstaller
$pyinstallerArgs = @(
    "--name=$APP_NAME",
    "--windowed",  # Sem console
    "--onefile",   # Um único .exe
    "--clean",
    "--noconfirm",
    "--add-data=data;data",  # Incluir pasta data
    "--add-data=model_artifacts;model_artifacts",  # Incluir modelos
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=pandas",
    "--hidden-import=numpy",
    "--hidden-import=sklearn",
    "--hidden-import=joblib",
    "--hidden-import=sqlite3",
    "--hidden-import=src.load_and_predict_v3",
    "--hidden-import=core.shared.paths",
    "--hidden-import=core.shared.db",
    "--hidden-import=core.shared.utils",
    "--hidden-import=core.lol.draft",
    "--hidden-import=core.lol.prebets",
    "--hidden-import=core.lol.prebets_secondary",
    "--hidden-import=core.lol.prebets_player",
    "--hidden-import=core.lol.db_converter",
    "--hidden-import=core.lol.compare",
    "--hidden-import=app.ui.pages.lol_prebets_secondary",
    "--hidden-import=app.ui.pages.lol_prebets_player",
    "--hidden-import=app.ui.pages.lol_compare",
    "--hidden-import=jaraco",
    "--hidden-import=jaraco.text",
    "--hidden-import=jaraco.functools",
    "--hidden-import=jaraco.context",
    "--hidden-import=pkg_resources",
    "src\app\main.py"
)

# Se tiver ícone, adicionar ANTES do script principal
if (Test-Path $ICON_PATH) {
    # Inserir antes do último item (main.py)
    $pyinstallerArgs = $pyinstallerArgs[0..($pyinstallerArgs.Count-2)] + "--icon=$ICON_PATH" + $pyinstallerArgs[-1]
}

Write-Host "`nExecutando PyInstaller..." -ForegroundColor Yellow
Write-Host "Comando: python -m PyInstaller $($pyinstallerArgs -join ' ')" -ForegroundColor Gray

# Executar PyInstaller
& python -m PyInstaller $pyinstallerArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== BUILD CONCLUÍDO COM SUCESSO! ===" -ForegroundColor Green
    Write-Host "Executável criado em: dist\$APP_NAME.exe" -ForegroundColor Green
    Write-Host "`nPara testar, execute: .\dist\$APP_NAME.exe" -ForegroundColor Yellow
} else {
    Write-Host "`n=== ERRO NO BUILD ===" -ForegroundColor Red
    exit 1
}
