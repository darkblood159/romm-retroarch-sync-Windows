; Inno Setup script for RomM-RetroArch Sync.
;
; Prerequisite: run build_windows.ps1 first so dist\RomM-RetroArch-Sync\
; exists. Then, with Inno Setup installed (https://jrsoftware.org/isinfo.php):
;
;   iscc packaging\installer.iss
;
; Output: packaging\output\RomM-RetroArch-Sync-Setup.exe

#define MyAppName "RomM - RetroArch Sync"
#define MyAppVersion "1.6.0"
#define MyAppPublisher "RomM-RetroArch Sync Contributors"
#define MyAppURL "https://github.com/Covin90/romm-retroarch-sync"
#define MyAppExeName "RomM-RetroArch-Sync.exe"

[Setup]
AppId={{B5B3C4C6-5B6B-4B6C-9C1D-ROMMRASYNC01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\RomM-RetroArch-Sync
DefaultGroupName=RomM - RetroArch Sync
AllowNoIcons=yes
; Per-user install by default avoids a UAC prompt and matches the app's own
; per-user %APPDATA% config -- switch to "lowest" is already the default,
; listed for clarity. Use "admin" instead if you want an all-users install.
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=RomM-RetroArch-Sync-Setup
SetupIconFile=..\assets\icons\romm_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start RomM - RetroArch Sync when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Everything PyInstaller collected -- the exe, GTK runtime DLLs, typelibs,
; icon theme, gdk-pixbuf loaders, and the app's own assets.
Source: "..\dist\RomM-RetroArch-Sync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; The "autostart" task ticks the same box the app's own in-app autostart
; toggle does (a Task Scheduler entry, created by the app itself on first
; run if this is checked) -- this registry entry is a simpler, install-time-
; only alternative some users may prefer instead. Left both are available:
; the app manages its own Task Scheduler entry independently of this.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "RomM-RetroArch-Sync"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The app's own %APPDATA% config/cache is intentionally left in place on
; uninstall (same as the Linux build leaves ~/.config alone) so settings and
; the download cache survive a reinstall/upgrade. Delete manually via
; %APPDATA%\romm-retroarch-sync if a clean wipe is wanted.
