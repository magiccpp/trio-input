# One-time setup of the native Windows LLM helper environment (llm\.venv).
# Picks the torch build for the hardware: NVIDIA GPU -> CUDA, Intel GPU/iGPU -> XPU,
# otherwise CPU. Re-run with -Backend cpu|cuda|xpu to force one.
param([string]$Backend = "auto")
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$venv = Join-Path $root 'llm\.venv'
$py = Join-Path $venv 'Scripts\python.exe'

if ($Backend -eq 'auto') {
    $gpus = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name
    if ($gpus -match 'NVIDIA') { $Backend = 'cuda' }
    elseif ($gpus -match 'Intel.*(Arc|Iris|Graphics)') { $Backend = 'xpu' }
    else { $Backend = 'cpu' }
    Write-Host "Detected GPUs: $($gpus -join ', ') -> torch backend '$Backend'"
}
$index = @{ cuda = 'https://download.pytorch.org/whl/cu126'; xpu = 'https://download.pytorch.org/whl/xpu'; cpu = 'https://download.pytorch.org/whl/cpu' }[$Backend]
Write-Host "torch index: $index  (cuda ~2.5 GB, xpu ~1.5 GB, cpu ~0.2 GB download)"

if (-not (Test-Path $py)) { uv venv $venv --python 3.12 }
uv pip install --python $py --index-url $index torch
uv pip install --python $py transformers
& $py -c "import torch; print('torch', torch.__version__, '| cuda:', torch.cuda.is_available(), '| xpu:', hasattr(torch,'xpu') and torch.xpu.is_available())"

$model = Join-Path $root 'llm\models\Qwen3-0.6B'
if (-not (Test-Path (Join-Path $model 'config.json'))) {
    Write-Host "Model not found at $model. Download it with:"
    Write-Host "  $py -c `"from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-0.6B', local_dir=r'$model')`""
} else { Write-Host "Model present: $model" }
