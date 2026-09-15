# Automated end-to-end test: make Trio Input the default input method, open Notepad, type
# through the IME with SendKeys, read Notepad's text back via UI Automation, restore settings.
param([string]$Keys = "jintian women taolun yixia AI de neirong , I would like to go {ENTER}jag 'r hungrig , don't care . women qu chifan ")
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, UIAutomationClient, UIAutomationTypes, Microsoft.VisualBasic
# PIME's TSF service CLSID + our language-profile GUID (from ime\trio\ime.json)
$tip = '0804:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{6B1A4C2E-7D3F-4A5B-9E8C-2F1D0A3B4C5D}'
$list = Get-WinUserLanguageList
$zh = $list | Where-Object LanguageTag -eq 'zh-Hans-CN'
$had = $zh.InputMethodTips -contains $tip
if (-not $had) { $zh.InputMethodTips.Add($tip); Set-WinUserLanguageList $list -Force }
$py = Join-Path $PSScriptRoot '..\train\.venv\Scripts\python.exe'
$prevProfile = & $py (Join-Path $PSScriptRoot 'activate_profile.py') --current
Write-Output "before: $prevProfile"
try {
    $np = Start-Process notepad.exe -PassThru
    Start-Sleep -Seconds 2
    [Microsoft.VisualBasic.Interaction]::AppActivate($np.Id) 2>$null
    Start-Sleep -Milliseconds 500
    # switch the session's input method with Win+Space (synthesised) until Trio is active
    Add-Type -Namespace W -Name K -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, uint flags, UIntPtr extra);'
    function Win-Space { [W.K]::keybd_event(0x5B,0,0,[UIntPtr]::Zero); [W.K]::keybd_event(0x20,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 120; [W.K]::keybd_event(0x20,0,2,[UIntPtr]::Zero); [W.K]::keybd_event(0x5B,0,2,[UIntPtr]::Zero); Start-Sleep -Milliseconds 900 }
    $ok = $false
    for ($i = 0; $i -lt 6; $i++) {
        $cur = & $py (Join-Path $PSScriptRoot 'activate_profile.py') --current
        if ($cur -match '6B1A4C2E') { $ok = $true; break }
        Win-Space
    }
    Write-Output "Trio active: $ok ($cur)"
    [Microsoft.VisualBasic.Interaction]::AppActivate($np.Id) 2>$null
    Start-Sleep -Milliseconds 500
    foreach ($ch in [char[]]$Keys) {
        if ($ch -eq '{') { $braceBuf = '{'; continue }
        if ($braceBuf) { $braceBuf += $ch; if ($ch -eq '}') { [System.Windows.Forms.SendKeys]::SendWait($braceBuf); $braceBuf = $null; Start-Sleep -Milliseconds 400 }; continue }
        $s = $ch.ToString()
        if ('+^%~(){}[]' -contains $s) { $s = "{$s}" }
        [System.Windows.Forms.SendKeys]::SendWait($s)
        $ms = 120; if ($ch -eq ' ') { $ms = 700 }
        Start-Sleep -Milliseconds $ms
    }
    Start-Sleep -Seconds 1
    # read the edit control's text via Win32 (works for classic Notepad and RichEdit)
    Add-Type -Namespace W -Name U -MemberDefinition @'
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindowEx(IntPtr p, IntPtr c, string cls, string win);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int SendMessage(IntPtr h, int msg, int w, System.Text.StringBuilder sb);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int SendMessage(IntPtr h, int msg, int w, int l);
'@
    $np.Refresh(); $h = $np.MainWindowHandle
    $edit = [W.U]::FindWindowEx($h, [IntPtr]::Zero, 'Edit', $null)
    if ($edit -eq [IntPtr]::Zero) { $edit = [W.U]::FindWindowEx($h, [IntPtr]::Zero, 'RichEditD2DPT', $null) }
    if ($edit -eq [IntPtr]::Zero) {   # Windows 11 Notepad nests the edit control deeper: walk children
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
        $doc = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
        if ($doc) { $edit = [IntPtr]$doc.Current.NativeWindowHandle }
    }
    $len = [W.U]::SendMessage($edit, 0x000E, 0, 0)
    $sb = New-Object System.Text.StringBuilder ($len + 1)
    [W.U]::SendMessage($edit, 0x000D, $len + 1, $sb) | Out-Null
    $text = $sb.ToString()
    Write-Output "NOTEPAD TEXT: [$text]"
    $np.Refresh(); Write-Output ("PIME dll in notepad: " + (($np.Modules | Where-Object { $_.ModuleName -match 'PIME' } | Select-Object -ExpandProperty ModuleName) -join ','))
    Stop-Process -Id $np.Id -Force
} finally {
    # cycle back to the US English keyboard so the session is left as it was
    for ($i = 0; $i -lt 6; $i++) {
        $cur = & $py (Join-Path $PSScriptRoot 'activate_profile.py') --current
        if ($cur -match 'langid=0x0409') { break }
        Win-Space
    }
    Write-Output "restored: $cur"
}
