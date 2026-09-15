# Starts the LLM helper and the input UI, then opens the browser.
# Uses the bundled runtime (installer) if present, else the dev venvs (install.ps1).
$root = $PSScriptRoot
$rt = Join-Path $root 'runtime\python.exe'
if (Test-Path $rt) { $py = $rt; $llmpy = $rt }
else { $py = Join-Path $root 'train\.venv\Scripts\python.exe'; $llmpy = Join-Path $root 'llm\.venv\Scripts\python.exe' }
if (-not (Test-Path $py)) { Write-Host "Runtime not found. Run the installer or install.ps1 first."; exit 1 }

$running = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match [regex]::Escape($root) }
if (-not ($running | Where-Object { $_.CommandLine -match 'llm_server\.py' }) -and (Test-Path $llmpy)) {
    $env:DEVICE = 'auto'; $env:QUANT = 'int8'; $env:THREADS = '6'; $env:HF_HUB_OFFLINE = '1'; $env:PYTHONIOENCODING = 'utf-8'
    Start-Process $llmpy -ArgumentList @('-u', (Join-Path $root 'proto\llm_server.py')) -WindowStyle Hidden -WorkingDirectory $root
}
if (-not ($running | Where-Object { $_.CommandLine -match 'app\.py' })) {
    $env:PYTHONIOENCODING = 'utf-8'
    Start-Process $py -ArgumentList (Join-Path $root 'proto\app.py') -WindowStyle Hidden -WorkingDirectory $root
    Start-Sleep -Seconds 3
}
Start-Process 'http://127.0.0.1:8766'
