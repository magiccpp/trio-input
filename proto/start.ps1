# Starts the standalone prototype UI on http://127.0.0.1:8766 (LLM helper optional).
$py = Join-Path $PSScriptRoot '..\train\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
Start-Process $py -ArgumentList (Join-Path $PSScriptRoot 'app.py')
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8766"
