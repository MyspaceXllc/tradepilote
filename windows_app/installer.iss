#define MyAppName "TradePilot Connector"
#define MyAppVersion "2.9.2"
#define MyAppPublisher "TradePilot"
#define MyAppExeName "TradePilotConnector.exe"

[Setup]
AppId={{E5BFF353-BBB3-4C70-A858-B473D659823F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TradePilot Connector
DefaultGroupName=TradePilot
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=TradePilotSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile=tradepilot.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\TradePilotConnector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TradePilot Connector"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\TradePilot Connector"; Filename: "{app}\{#MyAppExeName}"
Name: "{userstartup}\TradePilot Connector"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TradePilot Web App"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""TradePilot Web App"" dir=in action=allow protocol=TCP localport=8765 profile=private"; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TradePilot Tailscale"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""TradePilot Tailscale"" dir=in action=allow protocol=TCP localport=8765 remoteip=100.64.0.0/10 profile=any"; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "Launch TradePilot Connector"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Stop an older tray instance so the upgraded executable and web assets }
  { are used immediately after installation. }
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM TradePilotConnector.exe',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Result := '';
end;

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TradePilot Web App"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TradePilot Tailscale"""; Flags: runhidden