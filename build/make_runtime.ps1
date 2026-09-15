# Builds the portable Python runtime bundle for the installer:
#   build\dist\python-runtime-win64.zip  (embeddable Python 3.12 + torch CPU + transformers + pypinyin)
# The installer downloads this zip from the GitHub release and unpacks it to <app>\runtime.
param([string]$PyVersion = "3.12.10", [string]$Backend = "cpu")   # cpu | xpu (Intel GPU) | cuda (NVIDIA)
$ErrorActionPreference = 'Stop'
$build = $PSScriptRoot
$rt = Join-Path $build "runtime-$Backend"
$index = @{ cpu = 'https://download.pytorch.org/whl/cpu'; xpu = 'https://download.pytorch.org/whl/xpu'; cuda = 'https://download.pytorch.org/whl/cu126' }[$Backend]
$PartBytes = 3000MB    # uncompressed bytes per zip part; GitHub release assets must stay < 2 GB compressed
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

Get-ChildItem $dist -Filter "python-runtime-$Backend-win64*.zip" -ErrorAction SilentlyContinue | Remove-Item -Force
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$files = Get-ChildItem $rt -Recurse -File
$total = ($files | Measure-Object Length -Sum).Sum
Write-Host ("zipping {0:N0} MB uncompressed ..." -f ($total / 1MB))
# split into parts of <= $PartBytes uncompressed so every zip stays under GitHub's 2 GB limit
$parts = [Math]::Max(1, [Math]::Ceiling($total / $PartBytes))
$groups = @{}; for ($i = 1; $i -le $parts; $i++) { $groups[$i] = @() }
$sizes = @{}; for ($i = 1; $i -le $parts; $i++) { $sizes[$i] = 0 }
foreach ($f in ($files | Sort-Object Length -Descending)) {     # first-fit decreasing
    $best = 1; for ($i = 1; $i -le $parts; $i++) { if ($sizes[$i] -lt $sizes[$best]) { $best = $i } }
    $groups[$best] += $f; $sizes[$best] += $f.Length
}
$names = @()
for ($i = 1; $i -le $parts; $i++) {
    $name = if ($parts -eq 1) { "python-runtime-$Backend-win64.zip" } else { "python-runtime-$Backend-win64.part$i.zip" }
    $out = Join-Path $dist $name
    $zip = [System.IO.Compression.ZipFile]::Open($out, 'Create')
    foreach ($f in $groups[$i]) {
        $rel = $f.FullName.Substring($rt.Length + 1).Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $rel, 'Optimal') | Out-Null
    }
    $zip.Dispose()
    $names += $name
    Write-Host ("  {0}  {1:N0} MB" -f $name, ((Get-Item $out).Length / 1MB))
}
Set-Content (Join-Path $dist "python-runtime-$Backend-win64.parts") ($names -join "`n") -Encoding ascii
Write-Host "runtime bundle for '$Backend': $parts part(s)"
