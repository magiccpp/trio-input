# Starts the local LLM helper natively on Windows (llm\.venv, see setup_llm.ps1).
# Device order at runtime: NVIDIA GPU -> Intel GPU (XPU) -> CPU (int8, ~2 GB RAM).
#   proto\start_llm.ps1                 # auto
#   proto\start_llm.ps1 -Device cpu     # force CPU
param([string]$Device = "auto", [string]$Quant = "int8", [int]$Threads = 6, [string]$Model = "")
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root 'llm\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "Run proto\setup_llm.ps1 first (creates llm\.venv)." }
$env:DEVICE = $Device; $env:QUANT = $Quant; $env:THREADS = "$Threads"; $env:HF_HUB_OFFLINE = "1"
if ($Model) { $env:MODEL = $Model }
Start-Process $py -ArgumentList @('-u', (Join-Path $PSScriptRoot 'llm_server.py'))
Write-Host "LLM helper starting on http://127.0.0.1:8791 (device=$Device). First start takes ~20 s."
