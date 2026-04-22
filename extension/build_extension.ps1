# =====================================================================
# Empacota a extensao em um arquivo .zip pronto para envio a Chrome
# Web Store.
#
# O arquivo de saida usa o manifest.store.json (SEM o campo "key" e sem
# o "key" local) para que a Web Store possa gerar um ID oficial.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File build_extension.ps1
#
# Gera: leitor_certificados_<versao>.zip na pasta extension/.
# =====================================================================

$ErrorActionPreference = "Stop"

$ExtDir      = $PSScriptRoot
$ManifestDev = Join-Path $ExtDir "manifest.json"
$ManifestSto = Join-Path $ExtDir "manifest.store.json"

if (-not (Test-Path $ManifestSto)) {
    Write-Error "manifest.store.json nao encontrado em $ExtDir."
}

# Le a versao do manifest de loja
$manifestObj = Get-Content $ManifestSto -Raw -Encoding UTF8 | ConvertFrom-Json
$versao = $manifestObj.version
if (-not $versao) {
    Write-Error "Campo 'version' ausente em manifest.store.json."
}

$StageDir = Join-Path $ExtDir "build"
$ZipPath  = Join-Path $ExtDir "leitor_certificados_v$versao.zip"

if (Test-Path $StageDir) {
    Remove-Item $StageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $StageDir | Out-Null

$arquivosComuns = @(
    "popup.html",
    "popup.css",
    "popup.js"
)

$iconDir = Join-Path $ExtDir "icons"
if (Test-Path $iconDir) {
    Copy-Item $iconDir (Join-Path $StageDir "icons") -Recurse
}

foreach ($a in $arquivosComuns) {
    $src = Join-Path $ExtDir $a
    if (Test-Path $src) {
        Copy-Item $src $StageDir
    } else {
        Write-Warning "Arquivo $a nao encontrado - pulando."
    }
}

# Usa o manifest sem "key" (Web Store gera um proprio).
Copy-Item $ManifestSto (Join-Path $StageDir "manifest.json")

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force

Remove-Item $StageDir -Recurse -Force

Write-Host ""
Write-Host "=== Pacote da Chrome Web Store gerado ==="
Write-Host "Arquivo : $ZipPath"
Write-Host "Versao  : $versao"
Write-Host ""
Write-Host "Passos:"
Write-Host "  1. Acesse https://chrome.google.com/webstore/devconsole"
Write-Host "  2. Clique em 'Novo item' e envie o .zip acima."
Write-Host "  3. Preencha a ficha (descricao, screenshots, politica de privacidade)."
Write-Host "  4. Apos a aprovacao, copie o ID definitivo da extensao e"
Write-Host "     atualize o host_manifest.json chamando:"
Write-Host "       install.ps1 -ExtensionId <ID_DEFINITIVO>"
