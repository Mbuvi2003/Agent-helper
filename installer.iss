[Setup]
AppName=Agent Helper
AppVersion=1.7.2
AppPublisher=Mbuvi2003
DefaultDirName={localappdata}\Programs\Agent Helper
DefaultGroupName=Agent Helper
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=AgentHelper_Setup
SetupIconFile=images\icon.ico
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\AgentHelper.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\AgentHelper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Agent Helper"; Filename: "{app}\AgentHelper.exe"; IconFilename: "{app}\images\icon.ico"
Name: "{commondesktop}\Agent Helper"; Filename: "{app}\AgentHelper.exe"; Tasks: desktopicon; IconFilename: "{app}\images\icon.ico"

[Run]
Filename: "{app}\AgentHelper.exe"; Description: "{cm:LaunchProgram,Agent Helper}"; Flags: nowait postinstall skipifsilent
