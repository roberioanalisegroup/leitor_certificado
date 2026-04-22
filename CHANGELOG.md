# Changelog

Todas as mudanças relevantes do projeto **Leitor de Certificados Digitais**
estão documentadas aqui. O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Planejado
- Internacionalização (PT-BR + EN) da extensão.
- CI/CD via GitHub Actions com release automatizado.

## [1.1.0] - 2026-04-17

### Adicionado
- **Pacote de instalação corporativo único (`LeitorCertificados-Setup-*.exe`)**
  via Inno Setup 6. Instala para todos os usuários da máquina, registra
  o Native Messaging Host em HKLM (Chrome, Edge, Chromium) e força a
  instalação da extensão via `ExtensionInstallForcelist`. Suporta
  instalação silenciosa (`/VERYSILENT /NORESTART`) para GPO, Intune,
  SCCM.
- **Packer CRX3 em Python (`installer/pack_crx.py`)** que assina o
  `.crx` com a chave já existente (`extension_private_key.pem`),
  mantendo o Extension ID estável em todas as máquinas.
- **Orquestrador `installer/build_release.ps1`** que automatiza o build
  completo: compila `cert_host.exe`, empacota `extension.crx` e chama o
  Inno Setup para gerar o `.exe` final.
- **Geração automática de `updates.xml`** local (via Pascal em `[Code]`
  do Inno) apontando para `file:///{app}/extension.crx`, consumido pelo
  `ExtensionInstallForcelist` — solução 100% offline, sem hospedar
  nada em servidor.
- **`installer/RODAR_FIX.bat`** + **`installer/fix_forcelist.ps1`**:
  ferramenta de troubleshooting para aplicar a policy manualmente em
  máquinas que instalaram versões anteriores do pacote (opcional).
- **`docs/DEPLOYMENT.md`**: guia de deploy corporativo com roteiros
  para máquinas standalone, Active Directory (Startup Script, GPO,
  Intune, SCCM).
- Logs do host agora também podem ficar em
  `%ProgramData%\LeitorCertificados\logs\` (pasta com permissão de
  escrita para todos os usuários), criada pelo instalador.

### Mudado
- **Método de distribuição da extensão**: não usamos mais o mecanismo
  antigo `HKLM\Software\Google\Chrome\Extensions\<id>` (path + version)
  porque o Google o **depreciou e desabilitou no Chrome ~139** em 2024.
  Chrome e Edge modernos simplesmente ignoram esse registro. O único
  método oficial que funciona para extensões que não estão na Chrome
  Web Store é `ExtensionInstallForcelist` em
  `HKLM\Software\Policies\{Google\Chrome,Microsoft\Edge}`, apontando
  para um `updates.xml`. O instalador agora já grava isso em todas as
  instalações — a extensão aparece automaticamente como "Instalado
  pelo administrador", sem prompt, sem botão de desinstalar.
- Chaves do método antigo são **removidas** no post-install (caso
  tenham sobrado de instalações anteriores).

### Corrigido
- `build.ps1` e `uninstall.ps1` passam a usar somente ASCII em mensagens
  para evitar erros de parsing em PowerShell com encoding não-UTF8.

## [1.0.0] - 2026-04-17

Primeiro release funcional completo, com três entregáveis independentes
usando a mesma base de código (`cert_reader.py`):

### Adicionado

#### Core (`cert_reader.py`)
- Leitura de certificados do repositório do Windows via `crypt32.dll`
  (ctypes), sem dependência de ferramentas externas.
- Decodificação de campos ICP-Brasil no `SubjectAlternativeName`:
  - `2.16.76.1.3.1` – dados do titular PF (nascimento, CPF, PIS, RG).
  - `2.16.76.1.3.2` – nome do responsável pelo e-CNPJ.
  - `2.16.76.1.3.3` – CNPJ da pessoa jurídica.
  - `2.16.76.1.3.4` – dados do responsável pelo e-CNPJ.
  - `2.16.76.1.3.5` – título de eleitor.
  - `2.16.76.1.3.6` – CEI-PJ.
  - `2.16.76.1.3.7` – CEI-PF.
- Classificação automática como `e-CPF`, `e-CNPJ` ou `Outro`.
- Função `remover_certificado(der, store)` que localiza o certificado
  no repositório pelos bytes DER e chama `CertDeleteCertificateFromStore`.
- Formatação de CPF/CNPJ com máscaras brasileiras.

#### App desktop (`main.py`)
- Interface gráfica Tkinter com lista + painel de detalhes.
- Filtros de repositório (Pessoal, CA, Root).
- Coluna única na lista com nome do titular e data de validade.
- Destaque visual para certificados vencidos (fundo vermelho).
- Exclusão de certificado selecionado com confirmação.
- Exportação para CSV (compatível com Excel, UTF-8 com BOM).

#### Extensão Chrome (`extension/`)
- Manifest V3, declarando `nativeMessaging`.
- Layout compacto (380 px) com duas views:
  - Lista de certificados com busca em tempo real (filtra por nome,
    CPF, CNPJ, empresa, e-mail, emissor).
  - Detalhes do certificado em tela dedicada, com botão X (fecha
    o popup) e seta de voltar.
- Menu de 3 pontinhos com checkboxes para os repositórios.
- Certificados vencidos destacados em vermelho na lista.
- Filtragem automática: só exibe e-CPF e e-CNPJ (oculta certificados
  de aplicativos/sistema).
- Campo `key` no `manifest.json` gerado automaticamente pelo
  `setup_extension_key.py` para fixar o ID da extensão (não precisa
  passar o ID manualmente no script de instalação).

#### Native Host (`native_host/`)
- `host.py`: implementa o protocolo Chrome Native Messaging (uint32
  little-endian + JSON UTF-8), compartilhando código com `cert_reader.py`.
- `build.ps1`: empacota `host.py` em `cert_host.exe` via PyInstaller.
- `install.ps1`: gera `host_manifest.json`, registra o host em
  `HKCU\Software\{Google\Chrome,Microsoft\Edge,Chromium}\NativeMessagingHosts\`
  e, se a extensão ainda não tem `key`, invoca `setup_extension_key.py`
  para gerá-lo.
- `uninstall.ps1`: remove o registro dos três navegadores.

### Segurança
- Whitelist estrita de repositórios em `host.py`: só `MY`, `CA`, `ROOT`
  são aceitos como destino de leitura.
- **Exclusão bloqueada em `CA` e `ROOT`** – apenas `MY` (pessoal)
  aceita `delete` via extensão. Mexer em cadeias de confiança do
  sistema deve ser feito manualmente via `certmgr.msc` com admin.
- Confirmação nativa (`MessageBoxW` do Win32) antes de qualquer
  exclusão. Impede que uma extensão comprometida consiga excluir
  certificados sem interação do usuário no nível do sistema operacional.
- Limite de 128 KB por mensagem do protocolo (defesa contra DoS).
- Limite de 32 KB no DER do certificado recebido via `delete`.
- `allowed_origins` no manifest do host restringe a comunicação à
  extensão oficial (único ID autorizado).

### Logging
- Log rotativo em `%LOCALAPPDATA%\LeitorCertificados\logs\cert_host.log`
  (máx. 1 MB × 3 arquivos). Nunca grava dados pessoais (CPF, CNPJ etc.),
  apenas número de série, store e ação para auditoria.
