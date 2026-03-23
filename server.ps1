<#
.SYNOPSIS
    BookHaven server management script
.PARAMETER Action
    One of: start, stop, restart, status
#>
param(
    [Parameter(Position=0)]
    [ValidateSet("start","stop","restart","status")]
    [string]$Action = "status"
)

$PythonExe  = "C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
$AppDir     = "H:\BookHaven"
$Script     = "bookhaven.py"
$Port       = 8097
$PidFile    = Join-Path $AppDir "server.pid"
$LogFile    = Join-Path $AppDir "bookhaven.log"

function Get-ServerPid {
    if (Test-Path $PidFile) {
        $savedPid = [int](Get-Content $PidFile -ErrorAction SilentlyContinue)
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc -and $proc.Path -like "*python*") { return $savedPid }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conn) { return $conn.OwningProcess }
    return $null
}

function Stop-Server {
    $serverPid = Get-ServerPid
    if ($serverPid) {
        Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 800
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "Server stopped (PID $serverPid)" -ForegroundColor Yellow
    } else {
        Write-Host "Server not running" -ForegroundColor Gray
    }
}

function Start-Server {
    $existing = Get-ServerPid
    if ($existing) {
        Write-Host "Server already running (PID $existing)" -ForegroundColor Cyan
        return
    }
    $proc = Start-Process -FilePath $PythonExe -ArgumentList $Script `
        -WorkingDirectory $AppDir -PassThru -WindowStyle Minimized
    $proc.Id | Out-File -FilePath $PidFile -Encoding ascii -NoNewline
    Write-Host "Starting server (PID $($proc.Id))..." -ForegroundColor Green -NoNewline

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conn) { $ready = $true; break }
        $check = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
        if (-not $check) {
            Write-Host " FAILED (process exited)" -ForegroundColor Red
            Get-Content $LogFile -Tail 10
            return
        }
        Write-Host "." -NoNewline
    }
    if ($ready) {
        Write-Host " OK -> http://localhost:$Port" -ForegroundColor Green
    } else {
        Write-Host " TIMEOUT" -ForegroundColor Red
        Get-Content $LogFile -Tail 10
    }
}

function Show-Status {
    $serverPid = Get-ServerPid
    if ($serverPid) {
        $proc = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
        $mem = if ($proc) { [math]::Round($proc.WorkingSet64 / 1MB) } else { "?" }
        $up = if ($proc) { ((Get-Date) - $proc.StartTime).ToString("hh\:mm\:ss") } else { "?" }
        Write-Host "RUNNING  PID=$serverPid  Mem=${mem}MB  Up=$up  http://localhost:$Port" -ForegroundColor Green
    } else {
        Write-Host "STOPPED" -ForegroundColor Red
    }
}

switch ($Action) {
    "start"   { Start-Server }
    "stop"    { Stop-Server }
    "restart" { Stop-Server; Start-Sleep 1; Start-Server }
    "status"  { Show-Status }
}
