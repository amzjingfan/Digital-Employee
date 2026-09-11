; packaging/installer/ultrarag.iss — Inno Setup 脚本（产物为九骥 Joukir）
; 由 build_windows.ps1 调用：ISCC.exe packaging\installer\ultrarag.iss
; VERSION 通过环境变量传入（GetEnv）

[Setup]
AppId=StaffDeck
AppName=九骥 Joukir
AppVersion={#GetEnv('VERSION')}
AppVerName=九骥 Joukir {#GetEnv('VERSION')}
AppPublisher=九骥 Joukir
DefaultDirName={autopf}\StaffDeck
DefaultGroupName=九骥 Joukir
OutputDir=..\out
OutputBaseFilename=StaffDeck-setup
SetupIconFile=..\assets\staffdeck.ico
UninstallDisplayIcon={app}\staffdeck.exe
UninstallDisplayName=九骥 Joukir
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64os
PrivilegesRequired=lowest
WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no
DisableReadyPage=no
VersionInfoVersion={#GetEnv('WINDOWS_VERSION_INFO_VERSION')}
VersionInfoProductName=九骥 Joukir
VersionInfoProductVersion={#GetEnv('WINDOWS_VERSION_INFO_VERSION')}
VersionInfoCompany=九骥 Joukir
VersionInfoDescription=九骥 Joukir Installer
#if GetEnv('WINDOWS_SIGN_ENABLED') == '1'
SignTool=staffdeck
SignedUninstaller=yes
#endif

[Files]
; PyInstaller onedir 产物整体安装
Source: "..\out\staffdeck\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Dirs]
; The dedicated SRT account must be able to launch bundled runtimes.
Name: "{app}"; Permissions: users-readexec

[Registry]
Root: HKCU; Subkey: "Software\Classes\staffdeck"; ValueType: string; ValueData: "URL:九骥 Joukir Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\staffdeck"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\staffdeck\DefaultIcon"; ValueType: string; ValueData: "{app}\staffdeck.exe,0"
Root: HKCU; Subkey: "Software\Classes\staffdeck\shell\open\command"; ValueType: string; ValueData: """{app}\staffdeck.exe"" ""%1"""

[Icons]
Name: "{group}\九骥 Joukir"; Filename: "{app}\staffdeck.exe"; AppUserModelID: "ai.staffdeck.desktop"
Name: "{autodesktop}\九骥 Joukir"; Filename: "{app}\staffdeck.exe"; AppUserModelID: "ai.staffdeck.desktop"

[Run]
Filename: "{app}\staffdeck.exe"; Description: "启动九骥 Joukir"; Flags: postinstall nowait skipifsilent
