# Starts the LLM helper and the input backend, then opens the browser page (unless -NoBrowser:
# the system-wide IME only needs the backend).
# Uses the bundled runtime (installer) if present, else the dev venvs (install.ps1).
param([switch]$NoBrowser)
$root = $PSScriptRoot
$rt = Join-Path $root 'runtime\python.exe'
if (Test-Path $rt) { $py = $rt; $llmpy = $rt }
else { $py = Join-Path $root 'train\.venv\Scripts\python.exe'; $llmpy = Join-Path $root 'llm\.venv\Scripts\python.exe' }
if (-not (Test-Path $py)) { Write-Host "Runtime not found. Run the installer or install.ps1 first."; exit 1 }

# one instance only (the IME and the shortcut may both call this): check what is already running
$running = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match [regex]::Escape($root) }
if (Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue) { $running += [pscustomobject]@{ CommandLine = 'app.py (port busy)' } }
if (Get-NetTCPConnection -LocalPort 8791 -State Listen -ErrorAction SilentlyContinue) { $running += [pscustomobject]@{ CommandLine = 'llm_server.py (port busy)' } }
if (-not ($running | Where-Object { $_.CommandLine -match 'llm_server\.py' }) -and (Test-Path $llmpy)) {
    $env:DEVICE = 'auto'; $env:QUANT = 'int8'; $env:THREADS = '6'; $env:HF_HUB_OFFLINE = '1'; $env:PYTHONIOENCODING = 'utf-8'
    Start-Process $llmpy -ArgumentList @('-u', (Join-Path $root 'proto\llm_server.py')) -WindowStyle Hidden -WorkingDirectory $root
}
if (-not ($running | Where-Object { $_.CommandLine -match 'app\.py' })) {
    $env:PYTHONIOENCODING = 'utf-8'
    Start-Process $py -ArgumentList (Join-Path $root 'proto\app.py') -WindowStyle Hidden -WorkingDirectory $root
    Start-Sleep -Seconds 3
}
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8766' }
