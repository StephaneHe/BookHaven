@echo off
:: BookHaven Watchdog - checks every 30s if server is running, restarts if not
set PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe
set APP_DIR=H:\BookHaven
set PORT=8097

:loop
powershell -Command "(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue).OwningProcess" > nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] Server down, restarting...
    cd /d %APP_DIR%
    start /min "" "%PYTHON%" bookhaven.py
    echo [%date% %time%] Restart issued
)
timeout /t 30 /nobreak > nul
goto loop
