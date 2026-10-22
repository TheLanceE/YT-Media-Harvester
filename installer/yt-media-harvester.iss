; Inno Setup script for the one-click Windows installer (v0.4, #5).
; Build: iscc /DAppVersion=0.4.0 /DHelperDir=..\dist\helper installer\yt-media-harvester.iss
; HelperDir is the output of scripts/build_helper.py --tools. Per-user install: no admin prompt.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef HelperDir
  #define HelperDir "..\dist\helper"
#endif

[Setup]
AppId={{6A1C3E52-8F0B-4D7A-9C21-5B7E3F4A2D90}
AppName=YT Media Harvester
AppVersion={#AppVersion}
AppPublisher=Lance
AppPublisherURL=https://github.com/TheLanceE/YT-Media-Harvester
DefaultDirName={localappdata}\Programs\YT Media Harvester
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=YT-Media-Harvester-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
UninstallDisplayName=YT Media Harvester
UninstallDisplayIcon={app}\native_host.exe

[Tasks]
Name: chrome; Description: "Google Chrome"; GroupDescription: "Use the downloader in:"
Name: edge; Description: "Microsoft Edge"; GroupDescription: "Use the downloader in:"
Name: brave; Description: "Brave"; GroupDescription: "Use the downloader in:"

[Files]
Source: "{#HelperDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "GUIDE.html"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{app}\native_host.exe"; Parameters: "install {code:SelectedBrowsers}"; Flags: runhidden; StatusMsg: "Connecting the helper to your browsers..."
Filename: "{app}\extension"; Description: "Open the extension folder"; Flags: postinstall shellexec skipifsilent
Filename: "{app}\GUIDE.html"; Description: "Show how to add the extension (one minute)"; Flags: postinstall shellexec skipifsilent

[UninstallRun]
Filename: "{app}\native_host.exe"; Parameters: "uninstall"; Flags: runhidden; RunOnceId: "UnregisterHelper"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function SelectedBrowsers(Param: String): String;
begin
  Result := '';
  if WizardIsTaskSelected('chrome') then Result := Result + ' chrome';
  if WizardIsTaskSelected('edge') then Result := Result + ' edge';
  if WizardIsTaskSelected('brave') then Result := Result + ' brave';
  Result := Trim(Result);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectTasks) and (SelectedBrowsers('') = '') then
  begin
    MsgBox('Pick at least one browser.', mbError, MB_OK);
    Result := False;
  end;
end;
