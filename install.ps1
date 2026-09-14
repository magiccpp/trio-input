# trio-input installer (Windows 10/11, x64)
#   powershell -ExecutionPolicy Bypass -File install.ps1            # auto-detect GPU
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Backend cpu
# Installs: uv (if missing), two Python 3.12 venvs, the torch build for your GPU
# (NVIDIA -> CUDA, Intel -> XPU, else CPU), the Qwen3-0.6B model from the GitHub release,
# and a desktop shortcut. Nothing is registered with Windows input settings.
param([string]$Backend = "auto", [switch]$NoShortcut)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$Release = "https://github.com/magiccpp/trio-input/releases/download/v1.0.0"

function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') }

Write-Host "== 1/5 uv (Python package manager)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    winget install --id astral-sh.uv --exact --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { $env:Path += ";$env:USERPROFILE\.local\bin" }
}
uv --version

Write-Host "== 2/5 Python environment for the input engine"
$py = Join-Path $root 'train\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { uv venv (Join-Path $root 'train\.venv') --python 3.12 }
uv pip install --python $py pypinyin

Write-Host "== 3/5 Python environment for the local LLM helper"
& (Join-Path $root 'proto\setup_llm.ps1') -Backend $Backend
$llmpy = Join-Path $root 'llm\.venv\Scripts\python.exe'
$isGpu = (& $llmpy -c "import torch; print(int(torch.cuda.is_available() or (hasattr(torch,'xpu') and torch.xpu.is_available())))") -eq '1'

Write-Host "== 4/5 Model files (Qwen3-0.6B, Apache-2.0)"
$mdir = Join-Path $root 'llm\models\Qwen3-0.6B'
New-Item -ItemType Directory -Force $mdir | Out-Null
function Get-Asset($name, $dest) {
    if (Test-Path $dest) { Write-Host "   present: $dest"; return }
    Write-Host "   downloading $name ..."
    Invoke-WebRequest -Uri "$Release/$name" -OutFile $dest -UseBasicParsing
}
Get-Asset 'Qwen3-0.6B-tokenizer.zip' (Join-Path $mdir 'tokenizer.zip')
if (-not (Test-Path (Join-Path $mdir 'tokenizer.json'))) { Expand-Archive (Join-Path $mdir 'tokenizer.zip') $mdir -Force }
Get-Asset 'Qwen3-0.6B-int8.pt' (Join-Path $root 'llm\models\Qwen3-0.6B-int8.pt')      # CPU path (~1.2 GB)
if ($isGpu) { Get-Asset 'model.safetensors' (Join-Path $mdir 'model.safetensors') }     # GPU path (~1.5 GB)

Write-Host "== 5/5 First build of the pinyin dictionary (one-off, ~10 s)"
& $py (Join-Path $root 'proto\rime_engine.py') nihao | Select-Object -First 1

if (-not $NoShortcut) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Trio Input.lnk'))
    $lnk.TargetPath = 'powershell.exe'
    $lnk.Arguments = "-ExecutionPolicy Bypass -WindowStyle Minimized -File `"$(Join-Path $root 'start.ps1')`""
    $lnk.WorkingDirectory = $root
    $lnk.Description = 'Trio Input: pinyin / English / Swedish without switching'
    $lnk.Save()
    Write-Host "Desktop shortcut created: Trio Input"
}
Write-Host ""
Write-Host "Installed. Start with start.ps1 (or the desktop shortcut); the UI opens at http://127.0.0.1:8766"
