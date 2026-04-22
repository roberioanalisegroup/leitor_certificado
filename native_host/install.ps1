# =====================================================================
# Registra o Native Host no Chrome / Edge (Chromium).
#
# Uso mais simples (ID derivado automaticamente do manifest da extensao):
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Uso explicito (passando o ID manualmente):
#   powershell -ExecutionPolicy Bypass -File install.ps1 -ExtensionId <id>
#
# Parametros:
#   -ExtensionId   (opcional) ID da extensao (32 letras a-p). Se omitido,
#                  o script garante que exista um campo 'key' em
#                  extension/manifest.json (gerando um par RSA-2048 se
#                  for a primeira vez) e usa o ID derivado desse key.
#   -HostName      (opcional) Nome do native host.
#                  Default: br.com.roberio.cert_reader
#   -HostExe       (opcional) Caminho absoluto para o cert_host.exe.
#                  Default: cert_host.exe na pasta deste script.
# =====================================================================

param(
    [string]$ExtensionId = "",
    [string]$HostName = "br.com.roberio.cert_reader",
    [string]$HostExe = ""
)

$ErrorActionPreference = "Stop"

$HostRoot      = $PSScriptRoot
$ExtensionRoot = Join-Path (Split-Path $HostRoot -Parent) "extension"
$ManifestJs    = Join-Path $ExtensionRoot "manifest.json"

if (-not $HostExe) {
    $HostExe = Join-Path $HostRoot "cert_host.exe"
}

if (-not (Test-Path $HostExe)) {
    Write-Error "Executavel nao encontrado: $HostExe. Rode build.ps1 antes."
}

if (-not $ExtensionId) {
    if (-not (Test-Path $ManifestJs)) {
        Write-Error "manifest.json da extensao nao encontrado em $ManifestJs."
    }
    $pyHelper = Join-Path $HostRoot "setup_extension_key.py"
    if (-not (Test-Path $pyHelper)) {
        Write-Error "setup_extension_key.py nao encontrado em $pyHelper."
    }

    Write-Host "Derivando ID fixo a partir do manifest da extensao..."
    $saida = python $pyHelper $ManifestJs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Falha ao preparar a chave da extensao."
    }
    if ($saida -is [System.Array]) {
        $ExtensionId = ($saida | Select-Object -Last 1).ToString().Trim()
    } else {
        $ExtensionId = [string]$saida
        $ExtensionId = $ExtensionId.Trim()
    }
    Write-Host "ID da extensao: $ExtensionId"
}

if ($ExtensionId -notmatch "^[a-p]{32}$") {
    Write-Warning "O ExtensionId '$ExtensionId' nao parece valido (esperado 32 letras de a a p). Prosseguindo mesmo assim."
}

$ManifestPath = Join-Path $HostRoot "host_manifest.json"

$manifest = [ordered]@{
    name            = $HostName
    description     = "Leitor de Certificados Digitais (ICP-Brasil) - native host"
    path            = $HostExe
    type            = "stdio"
    allowed_origins = @("chrome-extension://$ExtensionId/")
}

$json = $manifest | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText(
    $ManifestPath,
    $json,
    (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "Manifest gerado em: $ManifestPath"

$targets = @(
    "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName",
    "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$HostName",
    "HKCU:\Software\Chromium\NativeMessagingHosts\$HostName"
)

foreach ($regKey in $targets) {
    New-Item -Path $regKey -Force | Out-Null
    Set-ItemProperty -Path $regKey -Name "(default)" -Value $ManifestPath
    Write-Host "Registrado: $regKey"
}

Write-Host ""
Write-Host "=== Instalacao concluida ==="
Write-Host "Host name  : $HostName"
Write-Host "Executavel : $HostExe"
Write-Host "Manifest   : $ManifestPath"
Write-Host "Extension  : $ExtensionId"
Write-Host ""
Write-Host "A primeira vez que voce rodar este script ele adiciona um campo"
Write-Host "'key' no manifest.json da extensao. Se a extensao ja estava"
Write-Host "carregada, abra chrome://extensions e clique em Recarregar na"
Write-Host "extensao (ou remova e carregue de novo) - o ID ficara fixo a"
Write-Host "partir desse ponto e nunca mais vai mudar."
