# Script para build em modo debug (com console para ver logs)
# Uso: .\build_scripts\build_debug.ps1

Write-Host "=== LoL Oracle ML - Build DEBUG (com console) ===" -ForegroundColor Green

# Verificar se está no diretório correto
if (-not (Test-Path "src\app\main.py")) {
    Write-Host "ERRO: Execute este script da raiz do projeto!" -ForegroundColor Red
    exit 1
}

Write-Host "`nModo DEBUG com console ativado para ver logs." -ForegroundColor Yellow
Write-Host "Isso ajudará a identificar onde o sistema está procurando os arquivos.`n" -ForegroundColor Yellow

Write-Host "Executando PyInstaller..." -ForegroundColor Yellow
pyinstaller build_pyinstaller_debug.spec --clean

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== BUILD CONCLUÍDO! ===" -ForegroundColor Green
    Write-Host "Executável criado em: dist\LoLOracleML\LoLOracleML.exe" -ForegroundColor Green
    Write-Host "`nIMPORTANTE: Esta versão tem CONSOLE ativado." -ForegroundColor Yellow
    Write-Host "Execute o .exe e veja os logs de debug no console." -ForegroundColor Yellow
    Write-Host "`nPara testar, execute: .\dist\LoLOracleML\LoLOracleML.exe" -ForegroundColor Cyan
    Write-Host "`nOs logs mostrarão onde o sistema está procurando os arquivos." -ForegroundColor Cyan
} else {
    Write-Host "`n=== ERRO NO BUILD ===" -ForegroundColor Red
    exit 1
}
