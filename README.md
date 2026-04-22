# Leitor de Certificados Digitais

Ferramenta para listar, inspecionar e excluir certificados digitais
ICP-Brasil (**e-CPF** e **e-CNPJ**) instalados no repositório nativo do
Windows (`crypt32.dll`).

O projeto tem três frentes que compartilham a mesma base de parsing:

| Frente | Destino | Onde mora |
|---|---|---|
| App desktop Tkinter | Uso pessoal no Windows | `main.py` |
| Extensão Chrome / Edge | Acesso via navegador | `extension/` |
| Native Messaging Host | Ponte Windows ↔ extensão | `native_host/` |

Toda a lógica de leitura X.509 e dos OIDs ICP-Brasil fica em
`cert_reader.py`, que é reaproveitado pelas três frentes.

## Requisitos

- Windows 10 ou superior
- Python 3.10+ (só para build / desenvolvimento; o usuário final recebe
  um `cert_host.exe` auto-contido)
- Chrome, Edge ou outro Chromium para a extensão

## Uso rápido – só o app desktop

```powershell
cd leitor_certificado
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Janela lista os certificados do repositório **Pessoal**, destaca vencidos
em vermelho e permite exclusão com confirmação.

## Uso da extensão Chrome (desenvolvimento)

Para desenvolver e testar rapidamente:

```powershell
cd leitor_certificado\native_host
powershell -ExecutionPolicy Bypass -File .\build.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Depois, em `chrome://extensions/` com o modo desenvolvedor ativado,
carregue a pasta `extension/`. Guia detalhado em
[`docs/INSTALL.md`](docs/INSTALL.md).

## Deploy corporativo (~100 máquinas)

Para distribuir para toda a empresa existe um instalador Inno Setup
único que registra tudo em HKLM e funciona tanto em máquinas do domínio
quanto em máquinas standalone.

Gere o instalador na máquina de build:

```powershell
cd leitor_certificado\installer
powershell -ExecutionPolicy Bypass -File .\build_release.ps1
```

O arquivo `dist\LeitorCertificados-Setup-<versão>.exe` pode ser:

- executado pelo usuário final (clique duplo, UAC);
- distribuído silenciosamente via GPO / Intune / SCCM (`/VERYSILENT /NORESTART`).

Guia completo em [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

Problemas? Veja [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## Arquitetura

```
┌─────────────────────────┐        stdio/JSON        ┌────────────────────────────┐
│  Extensão Chrome        │ ───────────────────────▶ │  cert_host.exe             │
│  (popup.html/.js/.css)  │ ◀─────────────────────── │  native_host/host.py       │
└─────────────────────────┘                          └────────────┬───────────────┘
                                                                  │
                                                                  ▼
                                                     ┌─────────────────────────────┐
                                                     │  cert_reader.py             │
                                                     │  (ctypes → crypt32.dll)     │
                                                     └─────────────────────────────┘
```

- A extensão se comunica com o host via **Chrome Native Messaging**
  (protocolo uint32 little-endian + JSON UTF-8).
- O host usa `ctypes` para enumerar certificados em
  `CertEnumCertificatesInStore` e os decodifica com `cryptography`.
- Exclusão é feita com `CertDeleteCertificateFromStore`.

## Segurança

- **Exclusão só é permitida no repositório `MY`** (Pessoal). Os
  repositórios `CA` e `ROOT` são somente-leitura via extensão para
  evitar que um ataque à extensão quebre cadeias de confiança do
  sistema.
- Toda exclusão exige **confirmação nativa do Windows** (`MessageBoxW`),
  que uma extensão comprometida não consegue suprimir.
- Whitelist estrita de nomes de repositórios no `host.py`.
- Limites rígidos de tamanho (128 KB por mensagem, 32 KB por DER).
- `allowed_origins` no manifest do host autoriza um único ID de
  extensão.

Detalhes em [`CHANGELOG.md`](CHANGELOG.md), seção *Segurança*.

## Logging

O host grava em `%LOCALAPPDATA%\LeitorCertificados\logs\cert_host.log`
(rotativo, 1 MB × 3 arquivos). **Nunca** são logados CPF/CNPJ ou dados
pessoais do titular – apenas número de série do certificado, loja e
ação executada (`list`, `delete`, `ping`) para auditoria.

## Testes

```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

A suíte gera certificados ICP-Brasil sintéticos com `cryptography` e
valida a extração de CPF, CNPJ, responsável, SAN extras etc.

## Estrutura de arquivos

```
leitor_certificado/
├── main.py                    App desktop Tkinter
├── cert_reader.py             Núcleo (leitura + exclusão)
├── requirements.txt           Runtime
├── requirements-dev.txt       Testes + pyinstaller
├── CHANGELOG.md
├── README.md
├── docs/
│   ├── INSTALL.md
│   ├── DEPLOYMENT.md          Deploy em massa (GPO, Intune, SCCM)
│   └── TROUBLESHOOTING.md
├── tests/
│   ├── conftest.py
│   └── test_cert_reader.py
├── extension/
│   ├── manifest.json          Versão dev (com campo "key")
│   ├── manifest.store.json    Versão para Chrome Web Store (sem "key")
│   ├── popup.html
│   ├── popup.css
│   ├── popup.js
│   └── build_extension.ps1    Empacota .zip para a Web Store
├── native_host/
│   ├── host.py                Loop Native Messaging
│   ├── build.ps1              Empacota cert_host.exe via PyInstaller
│   ├── install.ps1            Registra host em modo dev (HKCU)
│   ├── uninstall.ps1
│   └── setup_extension_key.py Gera/consulta o "key" do manifest
└── installer/
    ├── setup.iss              Script Inno Setup (gera o .exe final)
    ├── pack_crx.py            Empacota a extensão em CRX3 assinado
    └── build_release.ps1      Orquestrador do build corporativo
```

## Licença

Definir antes de publicar. Sugestão: MIT.

## Contribuindo

Testes devem passar (`python -m pytest tests/`) antes de qualquer PR.
Nunca logue dados pessoais. Segurança em primeiro lugar.
