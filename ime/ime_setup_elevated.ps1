# Runs elevated (UAC). Installs PIME if missing, copies the Trio module into PIME and
# (re)registers the text service. Used by the Trio Input installer and by install_ime.ps1.
#   ime_setup_elevated.ps1 -ModuleDir <dir with ime.json + trio_ime.py> [-PimeSetup <PIME-setup.exe>]
#   ime_setup_elevated.ps1 -Remove
param([string]$ModuleDir = "", [string]$PimeSetup = "", [switch]$Remove)
$ErrorActionPreference = 'Stop'
$pime = "${env:ProgramFiles(x86)}\PIME"
$dst = "$pime\python\input_methods\trio"

# a complete PIME has the DLLs, the launcher and the python server (a half-removed one may keep only the DLLs)
$pimeOk = (Test-Path "$pime\x64\PIMETextService.dll") -and (Test-Path "$pime\PIMELauncher.exe") -and (Test-Path "$pime\python\server.py")
if (-not $Remove -and -not $pimeOk) {
    if (-not $PimeSetup -or -not (Test-Path $PimeSetup)) { throw "PIME is not installed and no PIME setup was given" }
    $p = Start-Process -FilePath $PimeSetup -ArgumentList '/S' -Wait -PassThru
    if (-not (Test-Path "$pime\PIMELauncher.exe")) { throw "PIME setup failed ($($p.ExitCode))" }
}
Get-Process PIMELauncher -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
if ($Remove) {
    Remove-Item -Recurse -Force $dst -ErrorAction SilentlyContinue
} else {
    New-Item -ItemType Directory -Force $dst | Out-Null
    Copy-Item "$ModuleDir\*" $dst -Recurse -Force
}
if (Test-Path "$pime\x64\PIMETextService.dll") {
    & regsvr32 /s "$pime\x86\PIMETextService.dll"
    & regsvr32 /s "$pime\x64\PIMETextService.dll"
}
exit 0
