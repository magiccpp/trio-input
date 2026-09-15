; Inno Setup script for Trio Input (build with: ISCC.exe installer\TrioInput.iss)
; The setup contains the app; the Python runtime (matching the detected GPU) and the model
; are downloaded from the GitHub release during installation.
#define AppName "Trio Input"
#define AppVersion "1.0.1"
#define AppPublisher "magiccpp"
#define AppURL "https://github.com/magiccpp/trio-input"
#define Release "https://github.com/magiccpp/trio-input/releases/download/v" + AppVersion
#define Src ".."

[Setup]
AppId={{7C2F0C3A-6E7B-4F2D-9C1B-5A1E2B3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={localappdata}\TrioInput
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir={#Src}\build\dist
OutputBaseFilename=TrioInput-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#Src}\LICENSE
UninstallDisplayName={#AppName}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "autostart"; Description: "Start Trio Input when I log in"; GroupDescription: "Startup:"; Flags: unchecked

[Components]
; the detected hardware pre-selects one of these (see InitializeWizard)
Name: "cpu";  Description: "CPU runtime — works everywhere (~2 GB RAM, download ~1.7 GB)";                       Types: full compact custom; Flags: exclusive
Name: "xpu";  Description: "Intel GPU / iGPU runtime — Arc, Core Ultra (needs a recent Intel driver, ~3.2 GB)"; Types: custom; Flags: exclusive
Name: "cuda"; Description: "NVIDIA GPU runtime — CUDA 12 (needs a recent NVIDIA driver, ~4.5 GB)";              Types: custom; Flags: exclusive

[Files]
Source: "{#Src}\proto\*"; DestDir: "{app}\proto"; Excludes: "data\*,__pycache__\*,*.log,probe_*.py,test_*.py,eval_*.py"; Flags: ignoreversion recursesubdirs
Source: "{#Src}\engine\*"; DestDir: "{app}\engine"; Excludes: "user\build\*,user\*.userdb\*,user\installation.yaml,user\user.yaml,log\*"; Flags: ignoreversion recursesubdirs
Source: "{#Src}\rime\en_words.dict.yaml"; DestDir: "{app}\rime"; Flags: ignoreversion
Source: "{#Src}\rime\sv_words.dict.yaml"; DestDir: "{app}\rime"; Flags: ignoreversion
Source: "{#Src}\train\*.py"; DestDir: "{app}\train"; Flags: ignoreversion
Source: "{#Src}\train\data\*"; DestDir: "{app}\train\data"; Flags: ignoreversion
Source: "{#Src}\llm\quantize_model.py"; DestDir: "{app}\llm"; Flags: ignoreversion
Source: "{#Src}\start.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Src}\stop.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Src}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Src}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Src}\THIRD_PARTY.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\runtime"
Name: "{app}\llm\models\Qwen3-0.6B"
Name: "{app}\proto\data"

[Icons]
Name: "{group}\Trio Input"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\start.ps1"""; WorkingDir: "{app}"; Comment: "Chinese / English / Swedish input without switching"
Name: "{group}\Stop Trio Input"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\stop.ps1"""; WorkingDir: "{app}"
Name: "{group}\Uninstall Trio Input"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Trio Input"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\start.ps1"""; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\Trio Input"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\start.ps1"""; WorkingDir: "{app}"; Tasks: autostart

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\start.ps1"""; WorkingDir: "{app}"; Description: "Start Trio Input now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\stop.ps1"""; RunOnceId: "stop"; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\llm"
Type: filesandordirs; Name: "{app}\engine\user\build"
Type: filesandordirs; Name: "{app}\engine\user\luna_pinyin.userdb"
Type: filesandordirs; Name: "{app}\engine\log"
Type: filesandordirs; Name: "{app}\proto\__pycache__"
Type: files; Name: "{app}\engine\user\installation.yaml"
Type: files; Name: "{app}\engine\user\user.yaml"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  DetectedGpu: String;
  RuntimeParts: TArrayOfString;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if Progress = ProgressMax then Log(Format('Downloaded %s', [FileName]));
  Result := True;
end;

{ ---- GPU detection: NVIDIA -> cuda, Intel Arc/Iris/Graphics -> xpu, else cpu ---- }
function DetectGpu: String;
var
  ResultCode: Integer;
  Raw: AnsiString;
  Names, TmpFile: String;
begin
  Result := 'cpu';
  TmpFile := ExpandConstant('{tmp}\gpus.txt');
  if Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ''|'' | Out-File -Encoding ascii ''' + TmpFile + '''"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and LoadStringFromFile(TmpFile, Raw) then begin
    Names := Uppercase(String(Raw));
    Log('Video controllers: ' + Names);
    if Pos('NVIDIA', Names) > 0 then Result := 'cuda'
    else if (Pos('INTEL', Names) > 0) and
            ((Pos('ARC', Names) > 0) or (Pos('IRIS', Names) > 0) or (Pos('GRAPHICS', Names) > 0)) then Result := 'xpu';
  end;
  Log('Detected GPU class: ' + Result);
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpSelectComponents) and (DetectedGpu = '') then begin
    DetectedGpu := DetectGpu;
    WizardSelectComponents(DetectedGpu);
    if DetectedGpu = 'cuda' then WizardForm.ComponentsList.Hint := 'NVIDIA GPU detected'
    else if DetectedGpu = 'xpu' then WizardForm.ComponentsList.Hint := 'Intel GPU detected';
  end;
end;

var
  ChosenBackend: String;

function Backend: String;
begin
  if ChosenBackend <> '' then Result := ChosenBackend
  else if WizardIsComponentSelected('cuda') then Result := 'cuda'
  else if WizardIsComponentSelected('xpu') then Result := 'xpu'
  else Result := 'cpu';
end;

{ Downloads run in PrepareToInstall so they also happen in /SILENT and /VERYSILENT installs. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  i: Integer;
  PartsFile: String;
begin
  Result := '';
  if DetectedGpu = '' then DetectedGpu := DetectGpu;
  { silent installs: /GPU=auto (default) uses the detected hardware; /GPU=cpu|xpu|cuda forces one }
  if WizardSilent then begin
    ChosenBackend := Lowercase(ExpandConstant('{param:GPU|auto}'));
    Log('GPU switch: ' + ChosenBackend);
    if (ChosenBackend <> 'cpu') and (ChosenBackend <> 'xpu') and (ChosenBackend <> 'cuda') then ChosenBackend := DetectedGpu;
    WizardSelectComponents(ChosenBackend);
  end;
  Log('Runtime backend: ' + Backend);
  DownloadPage.Clear;
  DownloadPage.Show;
  try
    try
      { the .parts manifest lists the zip parts of the runtime for this backend }
      DownloadTemporaryFile('{#Release}/python-runtime-' + Backend + '-win64.parts', 'runtime.parts', '', @OnDownloadProgress);
      PartsFile := ExpandConstant('{tmp}\runtime.parts');
      if not LoadStringsFromFile(PartsFile, RuntimeParts) then RaiseException('cannot read runtime.parts');
      for i := 0 to GetArrayLength(RuntimeParts) - 1 do
        if Trim(RuntimeParts[i]) <> '' then
          DownloadPage.Add('{#Release}/' + Trim(RuntimeParts[i]), Format('runtime%d.zip', [i]), '');
      DownloadPage.Add('{#Release}/Qwen3-0.6B-tokenizer.zip', 'tokenizer.zip', '');
      DownloadPage.Add('{#Release}/Qwen3-0.6B-int8.pt', 'Qwen3-0.6B-int8.pt', '');
      if Backend <> 'cpu' then
        DownloadPage.Add('{#Release}/model.safetensors', 'model.safetensors', '');
      DownloadPage.Download;
    except
      if DownloadPage.AbortedByUser then Result := 'Download cancelled.'
      else Result := 'Download failed: ' + AddPeriod(GetExceptionMessage);
    end;
  finally
    DownloadPage.Hide;
  end;
end;

procedure Unpack(const Zip, Dest: String);
var
  ResultCode: Integer;
  Cmd: String;
begin
  Cmd := '-NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath ''' + Zip + ''' -DestinationPath ''' + Dest + ''' -Force"';
  Log('Unpack: ' + Cmd);
  if not Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    MsgBox('Failed to unpack ' + Zip + ' (code ' + IntToStr(ResultCode) + ')', mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Tmp, App: String;
  ResultCode, i: Integer;
begin
  if CurStep = ssPostInstall then begin
    Tmp := ExpandConstant('{tmp}');
    App := ExpandConstant('{app}');
    for i := 0 to GetArrayLength(RuntimeParts) - 1 do begin
      WizardForm.StatusLabel.Caption := Format('Unpacking the Python runtime (part %d of %d) ...', [i + 1, GetArrayLength(RuntimeParts)]);
      if FileExists(Tmp + Format('\runtime%d.zip', [i])) then Unpack(Tmp + Format('\runtime%d.zip', [i]), App + '\runtime');
    end;
    WizardForm.StatusLabel.Caption := 'Installing the language model ...';
    Unpack(Tmp + '\tokenizer.zip', App + '\llm\models\Qwen3-0.6B');
    FileCopy(Tmp + '\Qwen3-0.6B-int8.pt', App + '\llm\models\Qwen3-0.6B-int8.pt', False);
    if FileExists(Tmp + '\model.safetensors') then
      FileCopy(Tmp + '\model.safetensors', App + '\llm\models\Qwen3-0.6B\model.safetensors', False);
    WizardForm.StatusLabel.Caption := 'Building the pinyin dictionary (one-off) ...';
    Exec(App + '\runtime\python.exe', '"' + App + '\proto\rime_engine.py" nihao', App, SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
