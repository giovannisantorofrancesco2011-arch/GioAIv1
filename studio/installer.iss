; MyDevAgent Studio: installer per Windows (Inno Setup 6). Lo compila studio\build.ps1 con:
;   ISCC /DVersione=0.1.0 /DSorgente=<VSCodium modificato> /DExe=VSCodium.exe /DCli=codium.cmd /DBranding=<icone>
#define Nome "MyDevAgent Studio"

[Setup]
AppId={{6F1C2D3A-8B4E-4F7A-9C21-5D3E7A9B1F42}
AppName={#Nome}
AppVersion={#Versione}
AppVerName={#Nome} {#Versione}
AppPublisher=MyDevAgent
AppPublisherURL=https://github.com/giovannisantorofrancesco2011-arch/MyDevAgent
AppSupportURL=https://github.com/giovannisantorofrancesco2011-arch/MyDevAgent/issues
DefaultDirName={localappdata}\Programs\{#Nome}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=MyDevAgent-Studio-Setup
SetupIconFile={#Branding}\vio.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nome}
WizardStyle=modern
WizardImageFile={#Branding}\wizard.bmp,{#Branding}\wizard-2x.bmp
WizardSmallImageFile={#Branding}\wizard-small.bmp,{#Branding}\wizard-small-2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Messages]
it.WelcomeLabel2=Installo [name/ver]: l'editor di codice con Vio, il tuo agente di programmazione che lavora sul tuo computer, senza cloud.%n%nSe mancano, posso installare anche Python, Ollama e MyDevAgent.

[Tasks]
Name: "mydevagent"; Description: "Installa anche Python, Ollama e MyDevAgent se mancano (serve Internet: i modelli pesano qualche GB)"
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Icone:"
Name: "contextmenu"; Description: "Aggiungi «Apri con {#Nome}» al menu delle cartelle"; GroupDescription: "Altro:"

[InstallDelete]
; via i file della versione precedente (VSCodium può cambiare struttura tra una versione e l'altra)
Type: filesandordirs; Name: "{app}\resources"
Type: filesandordirs; Name: "{app}\locales"
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\extras"

[Files]
Source: "{#Sorgente}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Nome}"; Filename: "{app}\{#Exe}"; AppUserModelID: "MyDevAgent.Studio"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\{#Exe}"; AppUserModelID: "MyDevAgent.Studio"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MyDevAgentStudio"; ValueType: expandsz; ValueName: ""; ValueData: "Apri con {#Nome}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MyDevAgentStudio"; ValueType: expandsz; ValueName: "Icon"; ValueData: "{app}\{#Exe}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MyDevAgentStudio\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#Exe}"" ""%V"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MyDevAgentStudio"; ValueType: expandsz; ValueName: ""; ValueData: "Apri con {#Nome}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MyDevAgentStudio"; ValueType: expandsz; ValueName: "Icon"; ValueData: "{app}\{#Exe}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MyDevAgentStudio\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#Exe}"" ""%V"""; Tasks: contextmenu

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\extras\installa-mydevagent.ps1"" -Pausa"; StatusMsg: "Installo Python, Ollama e MyDevAgent: segui la finestra che si è aperta..."; Tasks: mydevagent; Flags: waituntilterminated
Filename: "{app}\{#Exe}"; Description: "Avvia {#Nome}"; Flags: nowait postinstall skipifsilent

[Code]
// Lingua italiana: il language pack si installa con la CLI di Studio e argv.json sceglie "it" al primo avvio.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Argv: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Installo la lingua italiana...';
    Exec(ExpandConstant('{cmd}'), '/c ""' + ExpandConstant('{app}\bin\{#Cli}') + '" --install-extension "' +
      ExpandConstant('{app}\extras\italiano.vsix') + '" --force"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Argv := ExpandConstant('{%USERPROFILE}\.mydevagent-studio\argv.json');
    if not FileExists(Argv) then
    begin
      ForceDirectories(ExtractFileDir(Argv));
      SaveStringToFile(Argv, '{' + #13#10 + '  "locale": "it"' + #13#10 + '}' + #13#10, False);
    end;
  end;
end;
