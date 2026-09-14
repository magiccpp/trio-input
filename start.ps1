# Starts the LLM helper and the input UI, then opens the browser.
$root = $PSScriptRoot
$llmpy = Join-Path $root 'llm\.venv\Scripts\python.exe'
$py = Join-Path $root 'train\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { Write-Host "Run install.ps1 first."; exit 1 }

if (Test-Path $llmpy) {
    $env:DEVICE = 'auto'; $env:QUANT = 'int8'; $env:THREADS = '6'; $env:HF_HUB_OFFLINE = '1'
    Start-Process $llmpy -ArgumentList @('-u', (Join-Path $root 'proto\llm_server.py')) -WindowStyle Minimized
}
Start-Process $py -ArgumentList (Join-Path $root 'proto\app.py') -WindowStyle Minimized
Start-Sleep -Seconds 3
Start-Process 'http://127.0.0.1:8766'
