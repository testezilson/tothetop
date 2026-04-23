# Script PowerShell simplificado para build
# Uso: .\build_scripts\build_simple.ps1

Write-Host "=== LoL Oracle ML - Build PyInstaller (Simplificado) ===" -ForegroundColor Green

# Verificar se está no diretório correto
if (-not (Test-Path "src\app\main.py")) {
    Write-Host "ERRO: Execute este script da raiz do projeto!" -ForegroundColor Red
    exit 1
}

Write-Host "`nUsando arquivo .spec (recomendado)..." -ForegroundColor Yellow
Write-Host "Comando: pyinstaller build_pyinstaller.spec`n" -ForegroundColor Gray

# Usar o arquivo .spec na raiz (mais confiável)
pyinstaller build_pyinstaller.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== BUILD CONCLUÍDO COM SUCESSO! ===" -ForegroundColor Green
    
    # Verificar se é onedir ou onefile
    $loLOracleDir = "dist\LoLOracleML"
    if (Test-Path $loLOracleDir) {
        Write-Host "Executável criado em: dist\LoLOracleML\LoLOracleML.exe" -ForegroundColor Green
        Write-Host "`nCopiando arquivos data/ e model_artifacts/..." -ForegroundColor Yellow
        & .\build_scripts\copy_data_to_dist.ps1
        Write-Host "`nPara testar, execute: .\dist\LoLOracleML\LoLOracleML.exe" -ForegroundColor Yellow
    } else {
        Write-Host "Executável criado em: dist\LoLOracleML.exe" -ForegroundColor Green
        Write-Host "`nCopiando arquivos data/ e model_artifacts/..." -ForegroundColor Yellow
        & .\build_scripts\copy_data_to_dist.ps1
        Write-Host "`nPara testar, execute: .\dist\LoLOracleML.exe" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n=== ERRO NO BUILD ===" -ForegroundColor Red
    Write-Host "Tente executar manualmente: pyinstaller build_scripts\build_pyinstaller.spec" -ForegroundColor Yellow
    exit 1
}
