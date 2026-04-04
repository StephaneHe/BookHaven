<#
.SYNOPSIS
    BookHaven watchdog - restarts server if it's not running.
    Designed to run as a Windows Scheduled Task every minute.
#>
$Port = 8097
$PythonExe = "C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
$AppDir = "H:\BookHaven"
$LogFile = Join-Path $AppDir "watchdog.log"

$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conn) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "$ts - Server down, restarting..."
    Start-Process -FilePath $PythonExe -ArgumentList "bookhaven.py" `
        -WorkingDirectory $AppDir -WindowStyle Minimized
    Start-Sleep -Seconds 5
    $check = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($check) {
        Add-Content -Path $LogFile -Value "$ts - Restart OK (PID $($check.OwningProcess))"
    } else {
        Add-Content -Path $LogFile -Value "$ts - Restart FAILED"
    }
}
