; Windows installer for PsyTags (Inno Setup 6).
; Build: ISCC /DAppVersion=0.1.0 /DSourceDir=..\dist\PsyTags packaging\psytags.iss
; Settings in %LOCALAPPDATA%\psytags stay when uninstalling.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\PsyTags"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{6F3B8E2A-4C1D-4E7B-9A52-2D8C1F0B7E43}
AppName=PsyTags
AppVersion={#AppVersion}
AppVerName=PsyTags {#AppVersion}
AppPublisher=Psychotoxical
AppPublisherURL=https://github.com/Psychotoxical/PsyTags
AppSupportURL=https://github.com/Psychotoxical/PsyTags/issues
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\PsyTags
DefaultGroupName=PsyTags
DisableProgramGroupPage=yes
; Installs for the current user without admin rights; the first page offers all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile=psytags.ico
UninstallDisplayIcon={app}\PsyTags.exe
UninstallDisplayName=PsyTags
OutputDir={#OutputDir}
OutputBaseFilename=PsyTags-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; A new version replaces the program folder completely, so no old library stays behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PsyTags"; Filename: "{app}\PsyTags.exe"
Name: "{autodesktop}\PsyTags"; Filename: "{app}\PsyTags.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PsyTags.exe"; Description: "{cm:LaunchProgram,PsyTags}"; Flags: nowait postinstall skipifsilent
