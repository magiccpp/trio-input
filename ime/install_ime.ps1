# Installs the Trio Input method into PIME and registers it system-wide (needs admin: UAC prompt).
#   powershell -ExecutionPolicy Bypass -File ime\install_ime.ps1          # install / update
#   powershell -ExecutionPolicy Bypass -File ime\install_ime.ps1 -Remove  # remove
param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$pime = "${env:ProgramFiles(x86)}\PIME"
if (-not (Test-Path "$pime\x64\PIMETextService.dll")) { throw "PIME is not installed. Get PIME-1.3.0-stable-setup.exe from https://github.com/EasyIME/PIME/releases" }
$src = Join-Path $PSScriptRoot 'trio'
$dst = "$pime\python\input_methods\trio"

$script = @"
`$ErrorActionPreference = 'Stop'
if ('$($Remove.IsPresent)' -eq 'True') { Remove-Item -Recurse -Force '$dst' -ErrorAction SilentlyContinue }
else { New-Item -ItemType Directory -Force '$dst' | Out-Null; Copy-Item '$src\*' '$dst' -Recurse -Force }
Get-Process PIMELauncher -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
& regsvr32 /s '$pime\x86\PIMETextService.dll'
& regsvr32 /s '$pime\x64\PIMETextService.dll'
"@
$tmp = Join-Path $env:TEMP 'trio-ime-install.ps1'
Set-Content $tmp $script -Encoding UTF8
$p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$tmp`"" -Verb RunAs -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "elevated step failed ($($p.ExitCode))" }
# the launcher runs as the normal user (it is what the TSF DLL connects to); start it unelevated
if (-not $Remove) { Start-Process "$pime\PIMELauncher.exe" }
if ($Remove) { Write-Host "Trio Input removed from PIME." }
else { Write-Host "Trio Input installed. Add it under Settings > Time & Language > Language > Chinese (Simplified) > Keyboards, or switch with Win+Space." }
