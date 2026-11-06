; Installateur NPUScribe — Inno Setup 6.
; Genere aussi le desinstallateur (unins000.exe), enregistre dans
; « Applications et fonctionnalites » de Windows.
;
; Compilation :  ISCC.exe installer\npuscribe.iss
; Le dossier ..\dist\NPUScribe doit avoir ete produit par PyInstaller.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "NPUScribe"
#define AppPublisher "NPUScribe"
#define AppExe "NPUScribe.exe"
#define AppMutex "NPUScribe.SingleInstance"

[Setup]
AppId={{7E4C1A52-9B3D-4C87-9F21-5D6A0C2B8E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} — dictée locale sur NPU Intel
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist_installer
OutputBaseFilename=NPUScribe-Setup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
AppMutex={#AppMutex}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "autostart"; Description: "Lancer {#AppName} au démarrage de Windows"; GroupDescription: "Démarrage :"; Flags: checkedonce
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
Source: "..\dist\NPUScribe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NPUScribe"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
{ Le modele pese plusieurs gigaoctets : on demande avant de le supprimer. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\NPUScribe');
    if DirExists(DataDir) then
    begin
      if MsgBox('Supprimer aussi le modèle et les données (environ 4 Go) ?' + #13#10 +
                'Vos transcriptions et réglages seront perdus.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
