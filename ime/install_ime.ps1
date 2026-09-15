# Installs the Trio Input method into PIME and registers it system-wide (one UAC prompt).
#   powershell -ExecutionPolicy Bypass -File ime\install_ime.ps1 [-PimeSetup PIME-1.3.0-stable-setup.exe]
#   powershell -ExecutionPolicy Bypass -File ime\install_ime.ps1 -Remove
param([switch]$Remove, [string]$PimeSetup = "")
$ErrorActionPreference = 'Stop'
$pime = "${env:ProgramFiles(x86)}\PIME"
$pimeOk = (Test-Path "$pime\x64\PIMETextService.dll") -and (Test-Path "$pime\PIMELauncher.exe") -and (Test-Path "$pime\python\server.py")
if (-not $Remove -and -not $pimeOk -and -not $PimeSetup) {
    throw "PIME is not installed. Get PIME-1.3.0-stable-setup.exe from https://github.com/EasyIME/PIME/releases and pass -PimeSetup <path>"
}
$elev = Join-Path $PSScriptRoot 'ime_setup_elevated.ps1'
$args = if ($Remove) { "-Remove" } else { "-ModuleDir `"$(Join-Path $PSScriptRoot 'trio')`"" + $(if ($PimeSetup) { " -PimeSetup `"$PimeSetup`"" } else { "" }) }
$p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$elev`" $args" -Verb RunAs -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "elevated step failed ($($p.ExitCode))" }
if ($Remove) { Write-Host "Trio Input removed from PIME." }
else {
    Start-Process "$pime\PIMELauncher.exe"      # runs as the normal user
    # make sure the profile is in the user's Chinese (Simplified) keyboard list
    $tip = '0804:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{6B1A4C2E-7D3F-4A5B-9E8C-2F1D0A3B4C5D}'
    $list = Get-WinUserLanguageList
    $zh = $list | Where-Object LanguageTag -eq 'zh-Hans-CN'
    if (-not $zh) { $list.Add('zh-Hans-CN'); $zh = $list | Where-Object LanguageTag -eq 'zh-Hans-CN' }
    if ($zh.InputMethodTips -notcontains $tip) { $zh.InputMethodTips.Add($tip); Set-WinUserLanguageList $list -Force }
    Write-Host "Trio Input installed. Switch to 'Trio Input 中/EN/SV' with Win+Space."
}
