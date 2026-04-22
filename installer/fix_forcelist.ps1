# =============================================================================
# Fix: configura ExtensionInstallForcelist para Chrome/Edge
#
# O mecanismo antigo (HKLM\Software\Google\Chrome\Extensions\<id>) foi
# depreciado pelo Google em versoes recentes. Este script aplica o metodo
# atual suportado: Force Install via policy, apontando para um updates.xml
# local que referencia o extension.crx ja instalado.
#
# >>> RODE ESTE SCRIPT COMO ADMINISTRADOR <<<
# =============================================================================

$ErrorActionPreference = "Stop"

# Checa admin (nao tenta auto-elevar - Start-Process -Wait tem bugs com UAC)
$admin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host ""
    Write-Host "ESTE SCRIPT PRECISA SER EXECUTADO COMO ADMINISTRADOR" -ForegroundColor Red
    Write-Host ""
    Write-Host "Clique no Menu Iniciar, digite 'powershell', clique com botao direito em"
    Write-Host "'Windows PowerShell' e escolha 'Executar como administrador'."
    Write-Host "Depois rode:"
    Write-Host ""
    Write-Host "  cd '$PSScriptRoot'"
    Write-Host "  .\fix_forcelist.ps1"
    Write-Host ""
    exit 1
}

$appDir = "$env:ProgramFiles\LeitorCertificados"
$extId = "dkohgecpdfcjjeebcldiffdbgpbbjmim"
$version = "1.1.0"

Write-Host ""
Write-Host "=== Aplicando fix ExtensionInstallForcelist ===" -ForegroundColor Cyan
Write-Host ""

# 1. updates.xml
$updatesXml = Join-Path $appDir "updates.xml"
$crxPath = Join-Path $appDir "extension.crx"
if (-not (Test-Path $crxPath)) {
    throw "CRX nao encontrado em $crxPath. Rode o instalador primeiro."
}

$dirEncoded = $appDir.Replace('\','/').Replace(' ','%20')
$crxUrl = "file:///$dirEncoded/extension.crx"
$updateUrl = "file:///$dirEncoded/updates.xml"

$xml = @"
<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='$extId'>
    <updatecheck codebase='$crxUrl' version='$version' />
  </app>
</gupdate>
"@
Set-Content -Path $updatesXml -Value $xml -Encoding UTF8
Write-Host "[OK] $updatesXml" -ForegroundColor Green

# 2. Policies
$valor = "$extId;$updateUrl"
$chaves = @(
    "HKLM:\Software\Policies\Google\Chrome\ExtensionInstallForcelist",
    "HKLM:\Software\Policies\Microsoft\Edge\ExtensionInstallForcelist"
)
foreach ($k in $chaves) {
    if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
    Set-ItemProperty -Path $k -Name "1" -Value $valor -Type String
    Write-Host "[OK] $k\1 = $valor" -ForegroundColor Green
}

# 3. Remover mecanismo antigo (ja nao funciona em Chrome moderno)
$antigas = @(
    "HKLM:\Software\Google\Chrome\Extensions\$extId",
    "HKLM:\Software\Microsoft\Edge\Extensions\$extId"
)
foreach ($k in $antigas) {
    if (Test-Path $k) {
        Remove-Item -Path $k -Force
        Write-Host "[OK] Removida chave antiga $k" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "=== PRONTO ===" -ForegroundColor Green
Write-Host ""
Write-Host "Agora:"
Write-Host "  1. Feche TODAS as janelas do Chrome (Get-Process chrome | Stop-Process -Force)"
Write-Host "  2. Reabra o Chrome"
Write-Host "  3. Vá em chrome://extensions - deve aparecer 'Leitor de Certificados'"
Write-Host "     com o rótulo 'Instalado pelo administrador'."
Write-Host ""
