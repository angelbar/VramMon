$code = @'
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern IntPtr FindWindow(string c, string w);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
'@
Add-Type -TypeDefinition $code
$h = [Win32]::FindWindow($null, "VramMon")
if ($h -ne [IntPtr]::Zero) {
    [Win32]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 300
    $r = New-Object "Win32+RECT"
    [Win32]::GetWindowRect($h, [ref]$r)
    Write-Output "$($r.Left),$($r.Top),$($r.Right),$($r.Bottom)"
}
