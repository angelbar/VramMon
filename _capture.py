import subprocess, re, json

ps = '''
Add-Type -AssemblyName System.Windows.Forms
$f = [System.Windows.Forms.Form]::new()
$f.Text = "VramMon"
$found = $false
Get-Process | Where-Object { $_.MainWindowTitle -eq "VramMon" } | ForEach-Object {
    $h = $_.MainWindowHandle
    $r = New-Object System.Drawing.Rectangle
    [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
        $r2 = $_.Bounds
    }
    Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        public class Win32 {
            [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
            public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
        }
"@
    $rc = New-Object "Win32+RECT"
    [Win32]::GetWindowRect($h, [ref]$rc)
    Write-Output "$($rc.Left),$($rc.Top),$($rc.Right),$($rc.Bottom)"
    $found = $true
}
if (-not $found) { Write-Output "NOT_FOUND" }
'''

r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                   capture_output=True, text=True, timeout=10)
print('STDOUT:', repr(r.stdout))
print('STDERR:', repr(r.stderr))
