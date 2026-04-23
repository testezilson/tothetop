# Script para build em modo --onedir (mais confiável)
# Uso: .\build_scripts\build_onedir.ps1

Write-Host "=== LoL Oracle ML - Build PyInstaller (ONEDIR) ===" -ForegroundColor Green

# Verificar se está no diretório correto
if (-not (Test-Path "src\app\main.py")) {
    Write-Host "ERRO: Execute este script da raiz do projeto!" -ForegroundColor Red
    exit 1
}

Write-Host "`nModo ONEDIR cria uma pasta com o .exe e todos os arquivos." -ForegroundColor Yellow
Write-Host "Isso é mais confiável que --onefile para arquivos de dados.`n" -ForegroundColor Yellow

Write-Host "Executando PyInstaller..." -ForegroundColor Yellow
pyinstaller build_pyinstaller_onedir.spec --clean

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== BUILD CONCLUÍDO COM SUCESSO! ===" -ForegroundColor Green
    Write-Host "Executável criado em: dist\LoLOracleML\LoLOracleML.exe" -ForegroundColor Green
    Write-Host "`nEstrutura criada:" -ForegroundColor Yellow
    Write-Host "  dist\LoLOracleML\" -ForegroundColor Gray
    Write-Host "    LoLOracleML.exe" -ForegroundColor Gray
    Write-Host "    data\" -ForegroundColor Gray
    Write-Host "    model_artifacts\" -ForegroundColor Gray
    Write-Host "    [outros arquivos]" -ForegroundColor Gray
    Write-Host "`nPara testar, execute: .\dist\LoLOracleML\LoLOracleML.exe" -ForegroundColor Yellow
    Write-Host "`nPara distribuir, copie toda a pasta dist\LoLOracleML\" -ForegroundColor Cyan
} else {
    Write-Host "`n=== ERRO NO BUILD ===" -ForegroundColor Red
    exit 1
}
