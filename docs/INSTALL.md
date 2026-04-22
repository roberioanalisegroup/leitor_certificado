# Guia de Instalação

Este guia cobre a instalação das três frentes do projeto. Para testes
rápidos do parser, pule direto para *App Desktop*.

## Sumário

1. [App Desktop Tkinter](#1-app-desktop-tkinter)
2. [Extensão Chrome/Edge (modo desenvolvedor)](#2-extensão-chromeedge-modo-desenvolvedor)
3. [Pacote da Chrome Web Store](#3-pacote-da-chrome-web-store)
4. [Desinstalação](#4-desinstalação)

---

## 1. App Desktop Tkinter

Para quem só quer listar/excluir certificados sem navegador.

### Pré-requisitos
- Windows 10 ou 11
- Python 3.10 ou superior com `tkinter` (padrão no instalador oficial)

### Passos

```powershell
cd leitor_certificado
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Executável standalone (opcional)

Se quiser distribuir só um `.exe`:

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name leitor_certificados main.py
```

O binário fica em `dist/leitor_certificados.exe`.

---

## 2. Extensão Chrome/Edge (modo desenvolvedor)

Fluxo usado durante o desenvolvimento. O ID da extensão fica fixo
graças ao campo `key` gerado automaticamente.

### Passo a passo

```powershell
cd leitor_certificado\native_host

# 1) Gera cert_host.exe com PyInstaller
powershell -ExecutionPolicy Bypass -File .\build.ps1

# 2) Gera o "key" do manifest (se ainda nao existir), deriva o ID
#    da extensao e registra o host em HKCU.
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Depois:

1. Abra `chrome://extensions/`.
2. Ative **Modo do desenvolvedor** no canto superior direito.
3. Clique em **Carregar sem compactação** e selecione a pasta
   `leitor_certificado/extension`.
4. O ID mostrado deve bater com o que o `install.ps1` imprimiu.
5. Feche o Chrome completamente e reabra.
6. Clique no ícone da extensão.

### O que exatamente o `install.ps1` faz

- Checa que `cert_host.exe` existe.
- Se o `extension/manifest.json` não tem o campo `"key"`, chama
  `setup_extension_key.py`, que:
  - gera um par RSA-2048;
  - grava a chave pública (DER, base64) em `manifest.json` como `"key"`;
  - salva um backup da chave privada em `native_host/extension_private_key.pem`.
- Deriva o ID determinístico da extensão a partir dessa chave.
- Cria `host_manifest.json` com o caminho absoluto do `.exe` e o
  `allowed_origins` apontando **só** para o ID gerado.
- Cria três chaves de registro no `HKCU`:
  - `Software\Google\Chrome\NativeMessagingHosts\br.com.roberio.cert_reader`
  - `Software\Microsoft\Edge\NativeMessagingHosts\br.com.roberio.cert_reader`
  - `Software\Chromium\NativeMessagingHosts\br.com.roberio.cert_reader`

---

## 3. Pacote da Chrome Web Store

Para submeter oficialmente:

```powershell
cd leitor_certificado\extension
powershell -ExecutionPolicy Bypass -File .\build_extension.ps1
```

Isso gera `leitor_certificados_v<versao>.zip` usando `manifest.store.json`
(**sem** o campo `key`, porque a Web Store gera a sua própria). O
arquivo é o que você sobe em
[Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole).

Depois da aprovação, a extensão recebe um **ID definitivo** diferente
do ID de desenvolvimento. Atualize o host chamando:

```powershell
cd ..\native_host
powershell -ExecutionPolicy Bypass -File .\install.ps1 -ExtensionId <ID_DEFINITIVO>
```

---

## 4. Desinstalação

### Extensão (dev)
- `chrome://extensions/` → botão **Remover** no card da extensão.

### Native host
```powershell
cd leitor_certificado\native_host
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Isso apaga as chaves de registro dos três navegadores. O `cert_host.exe`
e os logs em `%LOCALAPPDATA%\LeitorCertificados\` permanecem; apague
manualmente se quiser remover por completo.

### App desktop
Apague a pasta `leitor_certificado/` ou só o `.venv/`.
