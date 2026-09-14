# Installs the RIME/Weasel schema variant into %APPDATA%\Rime and redeploys.
# Requires Weasel (winget install Rime.Weasel). This DOES change Windows input settings
# (adds the Weasel IME) — the standalone prototype in ..\proto does not.
$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
$dst = Join-Path $env:APPDATA 'Rime'
$py  = Join-Path $PSScriptRoot '..\train\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

New-Item -ItemType Directory -Force -Path (Join-Path $dst 'lua') | Out-Null
Copy-Item (Join-Path $src '*.yaml') $dst -Force
Copy-Item (Join-Path $src 'lua\*.lua') (Join-Path $dst 'lua') -Force
Write-Host "Copied files to $dst"

$root = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel' -ErrorAction SilentlyContinue).WeaselRoot
if (-not $root) { $root = (Get-ItemProperty 'HKLM:\SOFTWARE\Rime\Weasel' -ErrorAction SilentlyContinue).WeaselRoot }
if (-not $root) { throw "Weasel is not installed (no WeaselRoot in registry). winget install Rime.Weasel" }

# "WeaselDeployer.exe /deploy" does not reliably rebuild from a script: deploy in-process via rime.dll
Get-Process WeaselServer -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
& $py (Join-Path $PSScriptRoot '..\train\deploy_rime.py') $dst
$ok = $LASTEXITCODE -eq 0
Start-Process -FilePath (Join-Path $root 'WeaselServer.exe')
if (-not $ok) { throw "Deploy failed; see $env:TEMP\rime.deploy\*.log" }
Write-Host "Done. Switch to the 中英瑞 schema with Ctrl+` or F4."
