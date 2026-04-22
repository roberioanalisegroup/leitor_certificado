# =============================================================================
# Leitor de Certificados Digitais - build de release
# Executa todas as etapas: compila o host, empacota a extensao e gera o .exe
# de instalacao com Inno Setup.
#
# Uso:
#     powershell -ExecutionPolicy Bypass -File .\build_release.ps1
#
# Saida: ..\dist\LeitorCertificados-Setup-<versao>.exe
# =============================================================================

[CmdletBinding()]
param(
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host ">>> $msg" -ForegroundColor Cyan
}

function Find-Iscc {
    if ($IsccPath -and (Test-Path $IsccPath)) { return $IsccPath }
    $candidatos = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) { return $c }
    }
    $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$hostDir = Join-Path $root "native_host"
$extDir = Join-Path $root "extension"
$installerDir = $PSScriptRoot
$distDir = Join-Path $root "dist"

# -----------------------------------------------------------------------------
# 1. Compilar o host nativo (cert_host.exe) se necessario
# -----------------------------------------------------------------------------
Write-Step "Etapa 1/4 - cert_host.exe"
$exePath = Join-Path $hostDir "cert_host.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "cert_host.exe nao encontrado; rodando build.ps1..."
    & (Join-Path $hostDir "build.ps1")
}
if (-not (Test-Path $exePath)) {
    throw "Falha ao produzir cert_host.exe"
}
Write-Host ("OK: {0}" -f $exePath)

# -----------------------------------------------------------------------------
# 2. Gerar / garantir chave privada da extensao
# -----------------------------------------------------------------------------
Write-Step "Etapa 2/4 - chave da extensao"
$keyPath = Join-Path $hostDir "extension_private_key.pem"
if (-not (Test-Path $keyPath)) {
    Write-Host "Chave nao encontrada, gerando via setup_extension_key.py..."
    Push-Location $hostDir
    try {
        python setup_extension_key.py
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path $keyPath)) {
    throw "Falha ao obter extension_private_key.pem"
}
Write-Host ("OK: {0}" -f $keyPath)

# -----------------------------------------------------------------------------
# 3. Empacotar extensao em .crx
# -----------------------------------------------------------------------------
Write-Step "Etapa 3/4 - extension.crx"
$crxPath = Join-Path $extDir "extension.crx"
python (Join-Path $installerDir "pack_crx.py") $extDir $keyPath $crxPath
if (-not (Test-Path $crxPath)) {
    throw "Falha ao gerar extension.crx"
}

# -----------------------------------------------------------------------------
# 4. Compilar instalador com Inno Setup
# -----------------------------------------------------------------------------
Write-Step "Etapa 4/4 - Inno Setup"
$iscc = Find-Iscc
if (-not $iscc) {
    Write-Warning "Inno Setup (ISCC.exe) nao encontrado."
    Write-Host "Baixe em https://jrsoftware.org/isdl.php e instale, depois rode novamente."
    Write-Host "Artefatos parciais disponiveis:"
    Write-Host ("  - {0}" -f $exePath)
    Write-Host ("  - {0}" -f $crxPath)
    exit 2
}
Write-Host ("Usando: {0}" -f $iscc)

if (-not (Test-Path $distDir)) {
    New-Item -ItemType Directory -Path $distDir | Out-Null
}

& $iscc (Join-Path $installerDir "setup.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup retornou codigo $LASTEXITCODE"
}

$setup = Get-ChildItem -Path $distDir -Filter "LeitorCertificados-Setup-*.exe" `
    | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($setup) {
    Write-Host ""
    Write-Host "===================================================="
    Write-Host ("Instalador pronto: {0}" -f $setup.FullName) -ForegroundColor Green
    Write-Host ("Tamanho: {0:N0} KB" -f ($setup.Length / 1KB))
    Write-Host "===================================================="
}
