# Copy the current proto\ code into the real per-user install and restart its backend.
# Needed because the Claude desktop sandbox redirects %LOCALAPPDATA% writes; run elevated:
#   Start-Process powershell -Verb RunAs -ArgumentList '-File build\hotfix_local.ps1'
$src = Split-Path $PSScriptRoot -Parent
$dst = 'C:\Users\dell\AppData\Local\TrioInput'
$log = Join-Path $env:TEMP 'trio_hotfix.log'
"start $(Get-Date)" | Out-File $log -Encoding utf8
foreach ($f in 'proto\app.py', 'proto\llm_server.py', 'proto\truecase.json', 'proto\static\index.html') {
    Copy-Item (Join-Path $src $f) (Join-Path $dst $f) -Force
    "copied $f" | Out-File $log -Append -Encoding utf8
}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*TrioInput*' } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
    "stopped $($_.ProcessId)" | Out-File $log -Append -Encoding utf8
}
"done" | Out-File $log -Append -Encoding utf8
