# Builds the portable Python runtime bundle for the installer:
#   build\dist\python-runtime-win64.zip  (embeddable Python 3.12 + torch CPU + transformers + pypinyin)
# The installer downloads this zip from the GitHub release and unpacks it to <app>\runtime.
param([string]$PyVersion = "3.12.10", [string]$Backend = "cpu")   # cpu | xpu (Intel GPU)
$ErrorActionPreference = 'Stop'
$build = $PSScriptRoot
$rt = Join-Path $build "runtime-$Backend"
$index = @{ cpu = 'https://download.pytorch.org/whl/cpu'; xpu = 'https://download.pytorch.org/whl/xpu' }[$Backend]
$dist = Join-Path $build 'dist'
New-Item -ItemType Directory -Force $dist | Out-Null
if (Test-Path $rt) { Remove-Item -Recurse -Force $rt }
New-Item -ItemType Directory -Force $rt | Out-Null

$zip = Join-Path $build "python-$PyVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    Write-Host "downloading embeddable Python $PyVersion ..."
    Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" -OutFile $zip -UseBasicParsing
}
Expand-Archive $zip $rt -Force
# enable site-packages (embeddable python ships with 'import site' commented out)
$pth = Get-ChildItem $rt -Filter 'python3*._pth' | Select-Object -First 1
(Get-Content $pth.FullName) -replace '^#import site', 'import site' | Set-Content $pth.FullName -Encoding ascii
Add-Content $pth.FullName "Lib\site-packages"

$getpip = Join-Path $build 'get-pip.py'
if (-not (Test-Path $getpip)) { Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getpip -UseBasicParsing }
$py = Join-Path $rt 'python.exe'
& $py $getpip --no-warn-script-location
& $py -m pip install --no-warn-script-location --index-url $index torch
& $py -m pip install --no-warn-script-location transformers pypinyin
# trim: caches, tests
Get-ChildItem $rt -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
& $py -c "import torch, transformers, pypinyin; print('runtime ok: torch', torch.__version__, 'transformers', transformers.__version__)"

$out = Join-Path $dist "python-runtime-$Backend-win64.zip"
if (Test-Path $out) { Remove-Item $out -Force }
Write-Host "zipping ..."
Compress-Archive -Path (Join-Path $rt '*') -DestinationPath $out -CompressionLevel Optimal
Write-Host ("runtime bundle: {0}  {1:N0} MB" -f $out, ((Get-Item $out).Length / 1MB))
