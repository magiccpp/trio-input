# Runs as the normal user after the elevated registration: starts PIME's launcher and adds
# "Trio Input" to the user's Chinese (Simplified) keyboard list so Win+Space reaches it.
$pime = "${env:ProgramFiles(x86)}\PIME"
if (-not (Get-Process PIMELauncher -ErrorAction SilentlyContinue)) { Start-Process "$pime\PIMELauncher.exe" }
$tip = '0804:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{6B1A4C2E-7D3F-4A5B-9E8C-2F1D0A3B4C5D}'
# Get-WinUserLanguageList returns a generic List that the pipeline does not unroll: use foreach
$list = Get-WinUserLanguageList
$zh = $null; foreach ($x in $list) { if ($x.LanguageTag -eq 'zh-Hans-CN') { $zh = $x } }
if (-not $zh) { $list.Add('zh-Hans-CN'); foreach ($x in $list) { if ($x.LanguageTag -eq 'zh-Hans-CN') { $zh = $x } } }
if ($zh -and $zh.InputMethodTips -notcontains $tip) { $zh.InputMethodTips.Add($tip); Set-WinUserLanguageList $list -Force }
