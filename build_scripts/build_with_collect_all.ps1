# Script para build com --collect-all scipy (força inclusão de tudo do scipy)
# Uso: .\build_scripts\build_with_collect_all.ps1

Write-Host "=== LoL Oracle ML - Build com --collect-all scipy ===" -ForegroundColor Green

# Verificar se está no diretório correto
if (-not (Test-Path "src\app\main.py")) {
    Write-Host "ERRO: Execute este script da raiz do projeto!" -ForegroundColor Red
    exit 1
}

Write-Host "`nUsando --collect-all scipy para forçar inclusão de todos os módulos do scipy.`n" -ForegroundColor Yellow

Write-Host "Executando PyInstaller..." -ForegroundColor Yellow

# O .spec já inclui collect_all para scipy e sklearn
pyinstaller build_pyinstaller_onedir.spec --clean --noconfirm

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== BUILD CONCLUÍDO! ===" -ForegroundColor Green
    Write-Host "Executável criado em: dist\LoLOracleML\LoLOracleML.exe" -ForegroundColor Green
    Write-Host "`nTeste o executável agora." -ForegroundColor Cyan
} else {
    Write-Host "`n=== ERRO NO BUILD ===" -ForegroundColor Red
    exit 1
}
