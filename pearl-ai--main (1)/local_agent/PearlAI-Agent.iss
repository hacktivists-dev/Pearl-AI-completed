#define MyAppName "Pearl AI Agent"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "PearlAI"
#define MyAppExeName "PearlAI-Agent.exe"

[Setup]
AppId={{90F16382-C815-469E-A341-600A15B7B556}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\PearlAI Agent
DefaultGroupName=Pearl AI Agent
PrivilegesRequired=lowest
OutputDir=..\downloads
OutputBaseFilename=PearlAI-Agent
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{code:GetAgentExeName}
DisableProgramGroupPage=yes

[InstallDelete]
Type: files; Name: "{app}\PearlAI-Agent--*.exe"

[Files]
Source: "..\.clean-build-dist\PearlAI-Agent\PearlAI-Agent.exe"; DestDir: "{app}"; DestName: "{code:GetAgentExeName}"; Flags: ignoreversion
Source: "..\.clean-build-dist\PearlAI-Agent\*"; Excludes: "PearlAI-Agent.exe"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Pearl AI Agent"; Filename: "{app}\{code:GetAgentExeName}"
Name: "{autodesktop}\Pearl AI Agent"; Filename: "{app}\{code:GetAgentExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{code:GetAgentExeName}"; Description: "Open Pearl AI Agent"; Flags: nowait postinstall skipifsilent

[Code]
function GetAgentExeName(Param: String): String;
var
  SourceName: String;
begin
  SourceName := ExtractFileName(ExpandConstant('{srcexe}'));
  if Pos('PearlAI-Agent--', SourceName) = 1 then
    Result := SourceName
  else
    Result := '{#MyAppExeName}';
end;
