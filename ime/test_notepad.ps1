# Automated end-to-end test: make Trio Input the default input method, open Notepad, type
# through the IME with SendKeys, read Notepad's text back via UI Automation, restore settings.
param([string]$Keys = "jintian women taolun yixia AI de neirong , I would like to go{ENTER}jag 'r hungrig , don't care ")
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, UIAutomationClient, UIAutomationTypes
$tip = '0804:{6B1A4C2E-7D3F-4A5B-9E8C-2F1D0A3B4C5D}{6B1A4C2E-7D3F-4A5B-9E8C-2F1D0A3B4C5D}'
$list = Get-WinUserLanguageList
$zh = $list | Where-Object LanguageTag -eq 'zh-Hans-CN'
$had = $zh.InputMethodTips -contains $tip
if (-not $had) { $zh.InputMethodTips.Add($tip); Set-WinUserLanguageList $list -Force }
$prev = (Get-WinDefaultInputMethodOverride).InputMethodTip
Set-WinDefaultInputMethodOverride -InputTip $tip
try {
    $np = Start-Process notepad.exe -PassThru
    Start-Sleep -Seconds 2
    [Microsoft.VisualBasic.Interaction]::AppActivate($np.Id) 2>$null
    Start-Sleep -Milliseconds 500
    foreach ($ch in [char[]]$Keys) {
        if ($ch -eq '{') { $braceBuf = '{'; continue }
        if ($braceBuf) { $braceBuf += $ch; if ($ch -eq '}') { [System.Windows.Forms.SendKeys]::SendWait($braceBuf); $braceBuf = $null; Start-Sleep -Milliseconds 400 }; continue }
        $s = $ch.ToString()
        if ('+^%~(){}[]' -contains $s) { $s = "{$s}" }
        [System.Windows.Forms.SendKeys]::SendWait($s)
        Start-Sleep -Milliseconds (if ($ch -eq ' ') { 700 } else { 120 })
    }
    Start-Sleep -Seconds 1
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($np.MainWindowHandle)
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
    $doc = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if (-not $doc) { $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit); $doc = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond) }
    $tp = $doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    $text = $tp.DocumentRange.GetText(-1)
    Write-Output "NOTEPAD TEXT: [$text]"
    Stop-Process -Id $np.Id -Force
} finally {
    if ($prev) { Set-WinDefaultInputMethodOverride -InputTip $prev } else { Set-WinDefaultInputMethodOverride }
    if (-not $had) { $list = Get-WinUserLanguageList; $zh = $list | Where-Object LanguageTag -eq 'zh-Hans-CN'; $zh.InputMethodTips.Remove($tip) | Out-Null; Set-WinUserLanguageList $list -Force }
}
