# =====================================================================
# Empacota o Native Host em um unico EXE usando PyInstaller.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# Gera "cert_host.exe" na pasta deste script.
# =====================================================================

$ErrorActionPreference = "Stop"

$HostRoot   = $PSScriptRoot
$ParentRoot = Split-Path $HostRoot -Parent
$BuildDir   = Join-Path $HostRoot "build"
$SpecDir    = $BuildDir
$HostPy     = Join-Path $HostRoot "host.py"

Write-Host "=== Instalando/atualizando dependencias ==="
python -m pip install --upgrade pip | Out-Host
python -m pip install --upgrade pyinstaller cryptography | Out-Host

if (Test-Path $BuildDir) {
    Remove-Item $BuildDir -Recurse -Force
}

Write-Host "=== Empacotando cert_host.exe ==="
pyinstaller `
    --onefile `
    --name cert_host `
    --console `
    --paths $ParentRoot `
    --hidden-import cert_reader `
    --distpath $HostRoot `
    --workpath $BuildDir `
    --specpath $SpecDir `
    $HostPy

if (-not (Test-Path (Join-Path $HostRoot "cert_host.exe"))) {
    Write-Error "Falha ao gerar cert_host.exe"
}

Write-Host ""
Write-Host "OK. Executavel em:"
Write-Host "  $HostRoot\cert_host.exe"
Write-Host ""
Write-Host "Proximo passo: rode install.ps1 -ExtensionId <ID_DA_EXTENSAO>"
