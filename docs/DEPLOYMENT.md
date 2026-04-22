# Guia de Deploy Corporativo

Cenário alvo: ~100 máquinas Windows, algumas em domínio Active Directory e
outras fora do domínio. Este documento descreve como gerar o pacote de
instalação único e distribuí-lo nos dois cenários.

---

## 1. O que o instalador faz

O arquivo `LeitorCertificados-Setup-<versão>.exe` (gerado em `dist/`) é um
instalador Inno Setup que:

1. Copia `cert_host.exe` e `extension.crx` para `%ProgramFiles%\LeitorCertificados\`.
2. Gera `host_manifest.json` com o caminho correto do `cert_host.exe`.
3. Gera `updates.xml` apontando para o `extension.crx` local (via `file://`).
4. Registra o Native Messaging Host em HKLM para **Chrome, Edge e Chromium**.
5. Grava a policy `ExtensionInstallForcelist` em `HKLM\Software\Policies\{Google\Chrome,Microsoft\Edge}` apontando para o `updates.xml` — isso faz Chrome/Edge instalarem a extensão automaticamente e sem prompt.
6. Cria a pasta de logs em `%ProgramData%\LeitorCertificados\logs\` com permissão de escrita para qualquer usuário.
7. Remove chaves do método antigo de external extensions (`HKLM\Software\Google\Chrome\Extensions\<id>`), que foi depreciado pelo Google no Chrome ~139 e não funciona mais.

Como tudo é gravado em **HKLM** (máquina, não usuário), funciona para todos
os usuários que fizerem login na máquina. Exige privilégio administrativo
para instalar.

A extensão aparece no Chrome/Edge marcada como **"Instalado pelo
administrador"** — o usuário não precisa aprovar, ativar nem pode
desinstalar. Esse é o comportamento esperado para deploy corporativo.

---

## 2. Gerando o instalador (uma vez, na máquina de build)

**Pré-requisitos** (só na máquina onde você compila):

- Python 3.11+ com as dependências do `requirements.txt` e `requirements-dev.txt`
- PyInstaller (já em `requirements-dev.txt`)
- [Inno Setup 6](https://jrsoftware.org/isdl.php)

**Passos**:

```powershell
cd installer
.\build_release.ps1
```

O script faz tudo: compila o `cert_host.exe`, gera o `.crx` assinado,
compila o instalador. Saída em `..\dist\LeitorCertificados-Setup-1.1.0.exe`.

> A chave `extension_private_key.pem` em `native_host/` é o que mantém o
> **Extension ID estável** (`dkohgecpdfcjjeebcldiffdbgpbbjmim`). Guarde
> essa chave em local seguro (cofre/keyvault) e faça backup. Se a chave
> sumir você precisa gerar uma nova e o Chrome tratará como extensão
> diferente em todas as máquinas.

---

## 3. Deploy em máquinas SEM Active Directory (usuário final)

Para máquinas avulsas (notebooks fora do domínio, home office etc.):

1. Envie o `.exe` do instalador para o usuário (e-mail, pendrive, SharePoint).
2. O usuário executa como administrador (clique direito → Executar como administrador, ou a UAC pede a senha).
3. Na próxima abertura do Chrome/Edge, a extensão já estará lá, marcada como *"Instalado pelo administrador"*. **Sem prompt, sem ativar, sem clicar em nada.**

Para **atualizar** depois, basta rodar a nova versão do instalador; ele
sobrescreve tudo.

Para **desinstalar**: Painel de Controle → Programas → "Leitor de
Certificados Digitais" → Desinstalar.

---

## 4. Deploy em máquinas COM Active Directory (silencioso, em massa)

O mesmo `.exe` suporta instalação silenciosa:

```cmd
LeitorCertificados-Setup-1.1.0.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES
```

Parâmetros úteis do Inno Setup:

| Parâmetro | Efeito |
|---|---|
| `/VERYSILENT` | Sem nenhuma janela |
| `/SILENT` | Só barra de progresso |
| `/NORESTART` | Não pede reboot |
| `/SUPPRESSMSGBOXES` | Suprime qualquer diálogo |
| `/LOG="C:\logs\setup.log"` | Log da instalação |
| `/DIR="C:\Apps\LeitorCertificados"` | Altera destino |

### 4.1 Via GPO (Computer Configuration → Software Installation)

GPO padrão **não aceita `.exe`** — aceita MSI. Opções:

**Opção A (mais simples)**: distribuir o `.exe` via um *startup script* de
máquina (Computer Configuration → Policies → Windows Settings → Scripts
→ Startup):

```powershell
$setup = "\\servidor\share\LeitorCertificados-Setup-1.1.0.exe"
$marker = "C:\ProgramData\LeitorCertificados\installed-1.1.0.flag"
if (-not (Test-Path $marker)) {
    & $setup /VERYSILENT /NORESTART /SUPPRESSMSGBOXES
    New-Item -ItemType File -Path $marker -Force | Out-Null
}
```

**Opção B**: converter o Inno em MSI com uma ferramenta como
[Advanced Installer](https://www.advancedinstaller.com/) ou empacotar em
um `.intunewin` e publicar pelo Microsoft Intune.

### 4.2 Via Intune (Win32 App)

1. Em `Apps → Windows → Add → Windows app (Win32)`
2. Empacote o `.exe` como `.intunewin` via `IntuneWinAppUtil.exe`
3. Comando de instalação: `LeitorCertificados-Setup-1.1.0.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES`
4. Comando de desinstalação: `"%ProgramFiles%\LeitorCertificados\unins000.exe" /VERYSILENT`
5. Regra de detecção: existe o arquivo `%ProgramFiles%\LeitorCertificados\cert_host.exe` com versão 1.1.0

### 4.3 Via SCCM / ConfigMgr

Cria-se uma Application com:

- **Installer**: `LeitorCertificados-Setup-1.1.0.exe /VERYSILENT /NORESTART`
- **Uninstaller**: `"%ProgramFiles%\LeitorCertificados\unins000.exe" /VERYSILENT`
- **Detection method**: presença do arquivo `%ProgramFiles%\LeitorCertificados\cert_host.exe`

---

## 5. Como a extensão é instalada (detalhe técnico)

A partir de 2024 o Google removeu do Chrome o mecanismo antigo de
*external extensions* via registro (`HKLM\Software\Google\Chrome\Extensions\<id>`).
Extensões que não estão na Chrome Web Store são aceitas apenas pela
policy `ExtensionInstallForcelist`, com um `updates.xml` referenciando o CRX.

O instalador faz isso automaticamente em toda máquina:

- Grava o `updates.xml` local em `%ProgramFiles%\LeitorCertificados\`:

  ```xml
  <?xml version='1.0' encoding='UTF-8'?>
  <gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
    <app appid='dkohgecpdfcjjeebcldiffdbgpbbjmim'>
      <updatecheck codebase='file:///C:/Program%20Files/LeitorCertificados/extension.crx' version='1.1.0' />
    </app>
  </gupdate>
  ```

- Grava a policy:

  ```
  HKLM\Software\Policies\Google\Chrome\ExtensionInstallForcelist\1 =
      "dkohgecpdfcjjeebcldiffdbgpbbjmim;file:///C:/Program%20Files/LeitorCertificados/updates.xml"
  ```
  (e o equivalente para Edge)

Como efeito, a extensão aparece marcada como **"Instalado pelo administrador"**,
sem popup de aprovação e sem opção de desinstalar pelo usuário.

### Alternativa: hospedar em compartilhamento de rede

Se preferir centralizar o CRX em um fileserver (menos recomendado — cria
dependência de rede), mude o `updates.xml` para apontar para:

```xml
<updatecheck codebase='file:///\\fileserver\chrome-ext\LeitorCertificados\extension.crx' version='1.1.0' />
```

E o valor do `ExtensionInstallForcelist` para:

```
dkohgecpdfcjjeebcldiffdbgpbbjmim;file:///\\fileserver\chrome-ext\LeitorCertificados\updates.xml
```

---

## 6. Verificação pós-instalação

Em qualquer máquina instalada:

```powershell
# Host nativo
Get-ItemProperty "HKLM:\Software\Google\Chrome\NativeMessagingHosts\br.com.roberio.cert_reader"

# Policy de force install
Get-ItemProperty "HKLM:\Software\Policies\Google\Chrome\ExtensionInstallForcelist"

# Arquivos presentes
Test-Path "$env:ProgramFiles\LeitorCertificados\cert_host.exe"
Test-Path "$env:ProgramFiles\LeitorCertificados\extension.crx"
Test-Path "$env:ProgramFiles\LeitorCertificados\host_manifest.json"
Test-Path "$env:ProgramFiles\LeitorCertificados\updates.xml"

# Log do host
Get-Content "$env:ProgramData\LeitorCertificados\logs\cert_host.log" -Tail 20
```

No Chrome/Edge: abrir `chrome://extensions` e confirmar que
*"Leitor de Certificados Digitais"* aparece com o rótulo
**"Instalado pelo administrador"**.

Se não aparecer:

1. Abra `chrome://policy/` e procure por `ExtensionInstallForcelist`.
   Se não listar, a policy não foi aplicada.
2. Rode `C:\Program Files\LeitorCertificados\..\installer\RODAR_FIX.bat`
   (ou `fix_forcelist.ps1` direto como admin) para reaplicar a policy.
3. Feche **todas** as janelas do Chrome/Edge e reabra. O Chrome só
   processa policies em startup completo.

---

## 7. Atualizações futuras

Para lançar a versão `1.1.0`:

1. Alterar `__version__` em `host.py`, `cert_reader.py`, `main.py`.
2. Alterar `version` em `extension/manifest.json` e `extension/manifest.store.json`.
3. Alterar `MyAppVersion` em `installer/setup.iss`.
4. Atualizar `CHANGELOG.md`.
5. Rodar `installer\build_release.ps1`.
6. Redistribuir o novo `.exe` pelo mesmo canal (GPO/Intune/e-mail).

O instalador sobrescreve a versão anterior automaticamente graças ao
`AppId` fixo no `setup.iss`.

Para *force install* via GPO, lembre-se de **atualizar também o
`updates.xml`** com a nova versão e copiar o novo `.crx` para o share.

---

## 8. Backup e segredos

Itens críticos que **devem** ter backup externo (cofre/keyvault):

- `native_host/extension_private_key.pem` — chave que define o Extension ID
- `installer/setup.iss` — `AppId` (GUID) que identifica o produto para upgrades

Sem a chave privada da extensão, uma próxima versão terá um ID diferente
e Chrome tratará como extensão nova — todas as máquinas vão precisar
aceitar o "Ativar extensão" de novo.
