# Stops the Trio Input background processes (UI server and LLM helper).
$root = $PSScriptRoot
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match [regex]::Escape($root) -and $_.CommandLine -match 'app\.py|llm_server\.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
