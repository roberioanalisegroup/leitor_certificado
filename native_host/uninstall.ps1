# =====================================================================
# Remove o registro do Native Host do Chrome / Edge.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1
# =====================================================================

param(
    [string]$HostName = "br.com.roberio.cert_reader"
)

$ErrorActionPreference = "Stop"

$targets = @(
    "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName",
    "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$HostName",
    "HKCU:\Software\Chromium\NativeMessagingHosts\$HostName"
)

foreach ($regKey in $targets) {
    if (Test-Path $regKey) {
        Remove-Item $regKey -Force
        Write-Host "Removido: $regKey"
    } else {
        Write-Host "Nao existia: $regKey"
    }
}

Write-Host ""
Write-Host "Pronto. O cert_host.exe e o host_manifest.json continuam no disco;"
Write-Host "apague-os manualmente se quiser remover por completo."
