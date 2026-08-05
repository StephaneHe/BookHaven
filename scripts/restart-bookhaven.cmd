@echo off
:: ============================================================================
:: restart-bookhaven.cmd — kill le serveur BookHaven et le relance.
::
:: Appelé par le watchdog Node.js (bookhaven-watchdog.mjs).
:: Attend que le port 8097 réponde HTTP (jusqu'à 120s) avant de rendre
:: la main, afin que le watchdog puisse réinitialiser son compteur d'échecs.
::
:: Exit codes :
::   0 — serveur opérationnel après relance
::   1 — timeout dépassé (serveur pas encore en écoute après 120s)
:: ============================================================================
setlocal

set "ROOT=C:\Dev\BookHaven"
set "PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
set "PORT=8097"
set "LOG=%ROOT%\server.log"
set "LOG_ERR=%ROOT%\server_err.log"

echo [%date% %time%] restart-bookhaven.cmd invoked >> "%LOG%"

:: --- Kill all processes on port 8097 -----------------------------------
echo [%date% %time%] Killing processes on port %PORT% ... >> "%LOG%"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo [%date% %time%] Killing PID %%p >> "%LOG%"
    taskkill /PID %%p /F /T >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: --- Relancer le serveur -----------------------------------------------
echo [%date% %time%] Starting BookHaven server ... >> "%LOG%"
start "" /B cmd /c ^
  ""%PYTHON%" "%ROOT%\bookhaven.py" >> "%LOG%" 2>> "%LOG_ERR%""

:: --- Attendre que le port soit actif (max 120s) -----------------------
echo [%date% %time%] Waiting for port %PORT% to be ready ... >> "%LOG%"
set /a TRIES=0
:wait_loop
  timeout /t 3 /nobreak >nul
  netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
  if not errorlevel 1 (
    echo [%date% %time%] Port %PORT% is now LISTENING — restart OK >> "%LOG%"
    exit /b 0
  )
  set /a TRIES+=1
  if %TRIES% GEQ 40 (
    echo [%date% %time%] TIMEOUT waiting for port %PORT% after restart >> "%LOG%"
    exit /b 1
  )
goto wait_loop

endlocal
