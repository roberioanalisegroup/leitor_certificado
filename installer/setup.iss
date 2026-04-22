; =============================================================================
; Leitor de Certificados Digitais - instalador corporativo
; Inno Setup 6 (https://jrsoftware.org/isinfo.php)
;
; Compila com:
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
;
; Ou via orquestrador:
;     powershell -ExecutionPolicy Bypass -File .\build_release.ps1
;
; O pacote resultante vai para ..\dist\LeitorCertificados-Setup-<versao>.exe
; =============================================================================

#define MyAppName      "Leitor de Certificados Digitais"
#define MyAppVersion   "1.1.0"
#define MyAppPublisher "TI Interna"
#define MyAppExeName   "cert_host.exe"
#define HostName       "br.com.roberio.cert_reader"
#define ExtensionId    "dkohgecpdfcjjeebcldiffdbgpbbjmim"

[Setup]
; GUID fixo: identifica o produto para upgrades e Adicionar/Remover Programas.
AppId={{7B3F1C2D-5A4E-4BCF-9E12-0A7D4F2C8E11}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\LeitorCertificados
DefaultGroupName=Leitor de Certificados
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=LeitorCertificados-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=force
; Fecha Chrome/Edge ao desinstalar para poder remover o CRX travado
RestartApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\native_host\cert_host.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\extension\extension.crx"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\docs\INSTALL.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\docs\TROUBLESHOOTING.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\docs\DEPLOYMENT.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
; Pasta de logs do host, acessivel por qualquer usuario que rode a extensao
Name: "{commonappdata}\LeitorCertificados\logs"; Permissions: users-modify

[Registry]
; -------------------------------------------------------------------
; Native Messaging Host - Chrome, Edge, Chromium
; -------------------------------------------------------------------
Root: HKLM; Subkey: "Software\Google\Chrome\NativeMessagingHosts\{#HostName}"; ValueType: string; ValueName: ""; ValueData: "{app}\host_manifest.json"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Edge\NativeMessagingHosts\{#HostName}"; ValueType: string; ValueName: ""; ValueData: "{app}\host_manifest.json"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Chromium\NativeMessagingHosts\{#HostName}"; ValueType: string; ValueName: ""; ValueData: "{app}\host_manifest.json"; Flags: uninsdeletekey

; -------------------------------------------------------------------
; Force-install via policy (Chrome / Edge)
;
; O mecanismo antigo (HKLM\Software\Google\Chrome\Extensions\<id>) foi
; depreciado pelo Google a partir do Chrome 139 (~2024). O unico metodo
; que funciona em Chrome/Edge atuais para extensoes nao publicadas na
; Chrome Web Store e a policy ExtensionInstallForcelist apontando para
; um updates.xml local (gerado em [Code]).
;
; Valor: "<extension_id>;<update_url>"
; Efeito: extensao aparece automaticamente, marcada como
;         "Instalado pelo administrador", sem opcao de desinstalar.
; -------------------------------------------------------------------
Root: HKLM; Subkey: "Software\Policies\Google\Chrome\ExtensionInstallForcelist"; ValueType: string; ValueName: "1"; ValueData: "{#ExtensionId};{code:GetUpdatesUrl}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "Software\Policies\Microsoft\Edge\ExtensionInstallForcelist"; ValueType: string; ValueName: "1"; ValueData: "{#ExtensionId};{code:GetUpdatesUrl}"; Flags: uninsdeletevalue

[UninstallDelete]
; Arquivos gerados em [Code] - remover na desinstalacao
Type: files; Name: "{app}\host_manifest.json"
Type: files; Name: "{app}\updates.xml"
Type: filesandordirs; Name: "{commonappdata}\LeitorCertificados"

[Code]
// Converte um path tipo 'C:\Program Files\LeitorCertificados'
// para 'C:/Program%20Files/LeitorCertificados' (para usar em file:// URLs).
function EncodeFileUrlPath(const Path: string): string;
var
  s: string;
begin
  s := Path;
  StringChangeEx(s, '\', '/', True);
  StringChangeEx(s, ' ', '%20', True);
  Result := s;
end;

// Expoe a URL do updates.xml para a secao [Registry].
function GetUpdatesUrl(Param: string): string;
begin
  Result := 'file:///' + EncodeFileUrlPath(ExpandConstant('{app}')) + '/updates.xml';
end;

procedure GravarHostManifest();
var
  appPath, escPath, manifest: string;
begin
  appPath := ExpandConstant('{app}');
  escPath := appPath + '\cert_host.exe';
  // Escapa as contrabarras para o JSON
  StringChangeEx(escPath, '\', '\\', True);

  manifest :=
    '{' + #13#10 +
    '  "name": "{#HostName}",' + #13#10 +
    '  "description": "Leitor de Certificados Digitais - native host",' + #13#10 +
    '  "path": "' + escPath + '",' + #13#10 +
    '  "type": "stdio",' + #13#10 +
    '  "allowed_origins": [' + #13#10 +
    '    "chrome-extension://{#ExtensionId}/"' + #13#10 +
    '  ]' + #13#10 +
    '}' + #13#10;

  SaveStringToFile(appPath + '\host_manifest.json', manifest, False);
end;

procedure GravarUpdatesXml();
var
  appPath, crxUrl, xml: string;
begin
  appPath := ExpandConstant('{app}');
  crxUrl := 'file:///' + EncodeFileUrlPath(appPath) + '/extension.crx';

  xml :=
    '<?xml version=''1.0'' encoding=''UTF-8''?>' + #13#10 +
    '<gupdate xmlns=''http://www.google.com/update2/response'' protocol=''2.0''>' + #13#10 +
    '  <app appid=''{#ExtensionId}''>' + #13#10 +
    '    <updatecheck codebase=''' + crxUrl + ''' version=''{#MyAppVersion}'' />' + #13#10 +
    '  </app>' + #13#10 +
    '</gupdate>' + #13#10;

  SaveStringToFile(appPath + '\updates.xml', xml, False);
end;

procedure LimparChavesAntigas();
begin
  // Limpa residuos do metodo de external extensions (Chrome <= 138)
  // caso uma versao anterior do instalador tenha sido usada.
  RegDeleteKeyIncludingSubkeys(HKLM,
    'Software\Google\Chrome\Extensions\{#ExtensionId}');
  RegDeleteKeyIncludingSubkeys(HKLM,
    'Software\Microsoft\Edge\Extensions\{#ExtensionId}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    GravarHostManifest();
    GravarUpdatesXml();
    LimparChavesAntigas();
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    // Fecha Chrome/Edge para liberar o CRX (o proprio Inno tambem tenta)
    Exec(ExpandConstant('{cmd}'), '/C taskkill /IM chrome.exe /F >nul 2>&1',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{cmd}'), '/C taskkill /IM msedge.exe /F >nul 2>&1',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

[Run]
Filename: "{app}\README.md"; Description: "Abrir README (opcional)"; Flags: shellexec postinstall skipifsilent unchecked
