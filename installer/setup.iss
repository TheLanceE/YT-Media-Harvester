; Inno Setup script for the Windows installer. Built by scripts/build_installer.py, which stages the files and
; passes AppVersion, VersionName, Stage, OutDir and OutputName on the ISCC command line.
;
; Installs per user (no admin prompt) into %LOCALAPPDATA%\Programs\YT Media Harvester, registers the native
; messaging host for Chrome, Edge and Brave, and opens setup-guide.html, which walks through Load unpacked.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef VersionName
  #define VersionName AppVersion
#endif
#ifndef Stage
  #define Stage "..\build\stage"
#endif
#ifndef OutDir
  #define OutDir "..\dist"
#endif
#ifndef OutputName
  #define OutputName "YT-Media-Harvester-Setup"
#endif
#define HelperExe "YTMediaHarvesterHelper.exe"

[Setup]
; Never change AppId: Windows uses it to find the installed copy for upgrades and uninstall.
AppId={{6F2B8C1E-4D7A-4B9E-9C3F-2A5D8E1F7B40}
AppName=YT Media Harvester
AppVersion={#AppVersion}
AppVerName=YT Media Harvester {#VersionName}
AppPublisher=TheLanceE
AppPublisherURL=https://github.com/TheLanceE/YT-Media-Harvester
AppSupportURL=https://github.com/TheLanceE/YT-Media-Harvester/issues
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\YT Media Harvester
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename={#OutputName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; The browser may have the helper running; let Setup close it instead of failing on a locked file.
CloseApplications=force
RestartApplications=no
UninstallDisplayName=YT Media Harvester
UninstallDisplayIcon={app}\{#HelperExe}

[InstallDelete]
; yt-dlp updates the helper downloaded for the previous version; this version ships a newer yt-dlp itself.
Type: filesandordirs; Name: "{app}\lib"
; PyInstaller's support files, replaced as a whole so nothing from an older build lingers.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Run]
Filename: "{app}\{#HelperExe}"; Parameters: "install"; Flags: runhidden waituntilterminated; \
  StatusMsg: "Registering the helper with Chrome, Edge and Brave..."
Filename: "{app}\setup-guide.html"; Description: "Show how to add the extension to your browser"; \
  Flags: postinstall shellexec skipifsilent nowait
Filename: "{app}\extension"; Description: "Open the extension folder"; \
  Flags: postinstall shellexec skipifsilent nowait unchecked

[UninstallRun]
Filename: "{app}\{#HelperExe}"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; \
  RunOnceId: "UnregisterHost"

[UninstallDelete]
; Written by the helper at runtime. Downloads live elsewhere and are never touched.
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\helper.log"
Type: files; Name: "{app}\updater.json"
Type: files; Name: "{app}\com.yt_tab_downloader.helper.json"
Type: filesandordirs; Name: "{app}\lib"
Type: filesandordirs; Name: "{app}\lib.new"
Type: filesandordirs; Name: "{app}\lib.old"
