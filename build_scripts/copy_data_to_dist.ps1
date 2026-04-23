# Script para copiar data/ e model_artifacts/ para o local correto após build
# Uso: .\build_scripts\copy_data_to_dist.ps1

Write-Host "=== Copiando arquivos para dist/ ===" -ForegroundColor Green

$distDir = "dist"
$dataSource = "data"
$modelsSource = "model_artifacts"

# Verificar se dist existe
if (-not (Test-Path $distDir)) {
    Write-Host "ERRO: Pasta dist/ não encontrada! Execute o build primeiro." -ForegroundColor Red
    exit 1
}

# Verificar se os arquivos fonte existem
if (-not (Test-Path $dataSource)) {
    Write-Host "ERRO: Pasta data/ não encontrada!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $modelsSource)) {
    Write-Host "ERRO: Pasta model_artifacts/ não encontrada!" -ForegroundColor Red
    exit 1
}

# Verificar se há pasta LoLOracleML (modo onedir)
$loLOracleDir = Join-Path $distDir "LoLOracleML"
if (Test-Path $loLOracleDir) {
    Write-Host "Modo --onedir detectado. Copiando para $loLOracleDir..." -ForegroundColor Yellow
    $targetDir = $loLOracleDir
} else {
    Write-Host "Modo --onefile detectado. Copiando para $distDir..." -ForegroundColor Yellow
    $targetDir = $distDir
}

# Copiar data/
$dataTarget = Join-Path $targetDir "data"
if (Test-Path $dataTarget) {
    Write-Host "Removendo $dataTarget antiga..." -ForegroundColor Yellow
    Remove-Item -Path $dataTarget -Recurse -Force
}
Write-Host "Copiando $dataSource para $dataTarget..." -ForegroundColor Yellow
Copy-Item -Path $dataSource -Destination $dataTarget -Recurse -Force

# Copiar model_artifacts/
$modelsTarget = Join-Path $targetDir "model_artifacts"
if (Test-Path $modelsTarget) {
    Write-Host "Removendo $modelsTarget antiga..." -ForegroundColor Yellow
    Remove-Item -Path $modelsTarget -Recurse -Force
}
Write-Host "Copiando $modelsSource para $modelsTarget..." -ForegroundColor Yellow
Copy-Item -Path $modelsSource -Destination $modelsTarget -Recurse -Force

Write-Host "`n=== CÓPIA CONCLUÍDA! ===" -ForegroundColor Green
Write-Host "Arquivos copiados para: $targetDir" -ForegroundColor Green

# Verificar se os arquivos críticos estão presentes
$criticalFiles = @(
    "data\champion_impacts.csv",
    "data\league_stats_v3.pkl",
    "model_artifacts\trained_models_v3.pkl",
    "model_artifacts\scaler_v3.pkl",
    "model_artifacts\feature_columns_v3.pkl"
)

Write-Host "`nVerificando arquivos críticos..." -ForegroundColor Yellow
$allOk = $true
foreach ($file in $criticalFiles) {
    $fullPath = Join-Path $targetDir $file
    if (Test-Path $fullPath) {
        Write-Host "  [OK] $file" -ForegroundColor Green
    } else {
        Write-Host "  [ERRO] $file NÃO ENCONTRADO!" -ForegroundColor Red
        $allOk = $false
    }
}

if ($allOk) {
    Write-Host "`nTodos os arquivos críticos estão presentes!" -ForegroundColor Green
} else {
    Write-Host "`nATENÇÃO: Alguns arquivos críticos estão faltando!" -ForegroundColor Red
}
