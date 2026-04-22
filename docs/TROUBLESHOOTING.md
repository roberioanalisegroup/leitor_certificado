# Troubleshooting

Problemas mais comuns e como resolver.

## Índice

- [Extensão: não aparece após instalação](#extensão-não-aparece-após-instalação)
- [Extensão: "O host nativo não respondeu"](#extensão-o-host-nativo-não-respondeu)
- [Extensão: lista vazia / sem certificados](#extensão-lista-vazia--sem-certificados)
- [Exclusão falha com "Código: 5"](#exclusão-falha-com-código-5)
- [Exclusão bloqueada em CA/ROOT](#exclusão-bloqueada-em-caroot)
- [`build.ps1` falha: pyinstaller não encontrado](#buildps1-falha-pyinstaller-não-encontrado)
- [`install.ps1` falha: "python" não é reconhecido](#installps1-falha-python-não-é-reconhecido)
- [Caracteres estranhos nos scripts PowerShell](#caracteres-estranhos-nos-scripts-powershell)
- [SmartScreen bloqueia o cert_host.exe](#smartscreen-bloqueia-o-cert_hostexe)
- [Token A3 não aparece](#token-a3-não-aparece)
- [Onde ficam os logs?](#onde-ficam-os-logs)

---

## Extensão: não aparece após instalação

Você rodou o `.exe`, deu "Concluir", mas em `chrome://extensions` não
aparece nada.

### Verificação rápida

No PowerShell (não precisa admin):

```powershell
Get-ItemProperty "HKLM:\Software\Policies\Google\Chrome\ExtensionInstallForcelist" -ErrorAction SilentlyContinue
Test-Path "$env:ProgramFiles\LeitorCertificados\updates.xml"
```

Se algum dos dois retornar vazio/False, a policy não foi aplicada.

### Causa #1: Chrome ficou aberto durante a instalação

O Chrome só processa `ExtensionInstallForcelist` em **startup completo**.
Se só fechou a janela mas o Chrome continua rodando na bandeja
(Update, Google Drive, etc.), nada acontece.

Solução: mate todos os processos e reabra:

```powershell
Get-Process chrome | Stop-Process -Force
Start-Process chrome.exe
```

### Causa #2: Instalou versão antiga (< 1.1.0)

Versões 1.0.x usavam o mecanismo antigo (`HKLM\...\Chrome\Extensions\<id>`)
que o Google desabilitou em ~2024. Precisa do pacote >= 1.1.0.

Solução: desinstale pelo Painel de Controle e instale o `.exe` novo.

### Causa #3: A policy foi gravada mas em hive errado

Só acontece se o instalador rodou em processo 32-bit num Windows 64-bit.
Verifique a chave "espelho":

```powershell
Get-ItemProperty "HKLM:\Software\WOW6432Node\Policies\Google\Chrome\ExtensionInstallForcelist" -ErrorAction SilentlyContinue
```

Se estiver lá e na chave 64-bit não, o instalador foi corrompido.
Rebuild com `installer\build_release.ps1`.

### Fix manual

Em último caso, rode como administrador (duplo clique):

```
C:\...\installer\RODAR_FIX.bat
```

Ele cria o `updates.xml` e as policies na mão. Depois feche e reabra o Chrome.

### Validação

Em `chrome://policy/`, a linha `ExtensionInstallForcelist` deve aparecer
com nível **"Obrigatória"** e valor começando com o ID
`dkohgecpdfcjjeebcldiffdbgpbbjmim`.

---

## Extensão: "O host nativo não respondeu"

Aparece como um box amarelo no popup. Causas possíveis:

1. **Chrome está com processo antigo em memória.** Feche todas as
   janelas do Chrome (inclua os ícones de segundo plano na bandeja)
   e reabra.
2. **Host não foi registrado.** Confirme no PowerShell:
   ```powershell
   Get-ItemProperty "HKCU:\Software\Google\Chrome\NativeMessagingHosts\br.com.roberio.cert_reader"
   ```
   Se a chave não existe, rode `install.ps1` de novo.
3. **Caminho do `.exe` quebrado.** Abra o `host_manifest.json` em
   `native_host/`, confira que o campo `path` aponta para um arquivo
   que existe mesmo.
4. **ID da extensão mudou.** Se você apagou o `manifest.json` ou
   recriou a pasta, o ID pode ter mudado. Rode `install.ps1` de novo
   (sem parâmetros) – ele deriva o ID automaticamente.
5. **Antivírus bloqueou o EXE.** Veja
   [SmartScreen bloqueia o cert_host.exe](#smartscreen-bloqueia-o-cert_hostexe).

### Diagnóstico manual

Execute o host direto pelo terminal e mande uma mensagem de teste:

```powershell
cd leitor_certificado\native_host
python host.py
```

Agora digite (não vai ecoar; é stdin binário). Você pode usar o
seguinte script para simular o Chrome:

```python
import json, struct, subprocess
proc = subprocess.Popen(
    ["python", "host.py"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE
)
msg = json.dumps({"action": "ping"}).encode()
proc.stdin.write(struct.pack("<I", len(msg)) + msg)
proc.stdin.flush()
n = struct.unpack("<I", proc.stdout.read(4))[0]
print(proc.stdout.read(n).decode())
```

Se o `ping` responde `{"ok": true, ...}`, o host está OK – o problema
é no registro ou no Chrome.

---

## Extensão: lista vazia / sem certificados

- Confirme que você tem certificados instalados em `certmgr.msc` →
  *Pessoal → Certificados*.
- Se só aparecem certificados de aplicativos (não-ICP-Brasil), a
  extensão **oculta** eles por padrão (só e-CPF/e-CNPJ aparecem).
  Isso é intencional.
- No menu de 3 pontinhos, confirme que pelo menos **Pessoal** está
  marcado.

---

## Exclusão falha com "Código: 5"

Código 5 = `ERROR_ACCESS_DENIED`. Três possibilidades:

1. O certificado está armazenado no **contexto de máquina** (não do
   usuário). O host abre apenas o store do usuário; não mexe no store
   da máquina.
2. A chave privada está em token/cartão (A3) que exige autenticação
   e o driver não liberou a operação.
3. Outro programa está com o certificado aberto.

Feche programas que usam o certificado e tente de novo.

---

## Exclusão bloqueada em CA/ROOT

Intencional. A extensão proíbe exclusão nos repositórios de
Autoridades Intermediárias e Raiz — remover um certificado dessas
cadeias pode inutilizar o navegador ou causar falhas de SSL em sites
reais. Para mexer nesses stores, use `certmgr.msc` rodando como
administrador.

---

## `build.ps1` falha: pyinstaller não encontrado

O script instala o PyInstaller via `pip`. Se o ambiente não tem o
Scripts do pip no `PATH`:

```powershell
python -m pip install --user pyinstaller
$env:Path += ";$env:APPDATA\Python\Python313\Scripts"
```

Depois rode `build.ps1` de novo.

---

## `install.ps1` falha: "python" não é reconhecido

Significa que o Python não está no `PATH` do usuário. Correção:

1. Reinstale o Python marcando **Add python.exe to PATH**.
2. Ou, se já está instalado, execute no PowerShell:
   ```powershell
   $py = (Get-Command py.exe).Source
   Write-Host "Use: $py -3 host.py"
   ```
   E adapte o `build.ps1` trocando `python` por `py -3`.

---

## Caracteres estranhos nos scripts PowerShell

Se aparecer algo como:

```
'}' de fechamento ausente no bloco de instru��o
```

É porque o PowerShell leu o arquivo como ANSI (CP-1252) e não UTF-8.
Os scripts do projeto são em ASCII puro exatamente para evitar isso.
Se você editar algum e colocar acentos, salve com UTF-8 **com BOM**
ou mantenha ASCII.

---

## SmartScreen bloqueia o `cert_host.exe`

Esperado enquanto o EXE não for assinado com certificado de code
signing EV. Em máquinas de desenvolvimento/teste:

1. Na mensagem do SmartScreen, clique em **Mais informações** →
   **Executar assim mesmo**.
2. Ou assine o EXE localmente com um cert auto-assinado (não vai
   remover o aviso, mas ajuda em antivírus corporativos).

Produção: comprar cert EV (Sectigo, DigiCert, GlobalSign) e assinar
no pipeline. Veja roadmap no `CHANGELOG.md`.

---

## Token A3 não aparece

- Conecte o token **antes** de abrir o Chrome / o app.
- Confirme que o driver do fabricante (SafeNet Authentication Client,
  Watchdata, GEMALTO, etc.) está instalado e o serviço correspondente
  está rodando (`services.msc` → procurar "SafeNet", "WatchKey"…).
- Abra `certmgr.msc` → *Pessoal → Certificados*. Se não aparece lá
  também, o problema é no driver do token, não no nosso código.
- Alguns drivers só publicam o certificado depois do primeiro PIN.
  Tente assinar algo simples (abrir o site da Receita, por exemplo)
  e reabrir a extensão.

---

## Onde ficam os logs?

```
%LOCALAPPDATA%\LeitorCertificados\logs\cert_host.log
```

(Em geral: `C:\Users\<seu_usuario>\AppData\Local\LeitorCertificados\logs\`.)

Rotação automática: até 4 arquivos de 1 MB cada (`cert_host.log`,
`.log.1`, `.log.2`, `.log.3`). Nada de dados pessoais é gravado — só
número de série do certificado, loja e a operação executada.

Se estiver sem permissão de escrita na pasta acima, o host continua
funcionando mas sem log (o diretório `LeitorCertificados` é criado
silenciosamente pelo próprio host na primeira execução).
