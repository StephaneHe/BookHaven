@echo off
:: ============================================================================
:: start-server.cmd — démarre le serveur BookHaven Python en arrière-plan.
::
:: Idempotent : kill l'éventuel process écoutant sur le port 8097 avant de
:: relancer. Stdout/stderr redirigés dans server.log / server_err.log.
::
:: Usage :
::   start-server.cmd          (depuis n'importe où)
::
:: Appelé par la tâche Task Scheduler "BookHaven-server" au logon.
:: ============================================================================
setlocal

set "ROOT=C:\Dev\BookHaven"
set "PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
set "PORT=8097"
set "LOG=%ROOT%\server.log"
set "LOG_ERR=%ROOT%\server_err.log"

echo [%date% %time%] start-server.cmd invoked >> "%LOG%"

:: --- Kill any process currently listening on port 8097 -----------------
echo Checking for existing process on port %PORT%...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Killing PID %%p on port %PORT%...
    echo [%date% %time%] Killing existing PID %%p on port %PORT% >> "%LOG%"
    taskkill /PID %%p /F /T >nul 2>&1
)
:: Small grace for the port to be released
timeout /t 2 /nobreak >nul

:: --- Rotate server logs (no in-process rotation on these files) --------
:: Must run after the kill above: the old server holds server.log open.
if exist "%LOG%" (
    del "%LOG%.1" >nul 2>&1
    ren "%LOG%" server.log.1 >nul 2>&1
)
if exist "%LOG_ERR%" (
    del "%LOG_ERR%.1" >nul 2>&1
    ren "%LOG_ERR%" server_err.log.1 >nul 2>&1
)

:: --- Launch Python server detached, logs to file -----------------------
echo Starting BookHaven server...
echo [%date% %time%] Launching python.exe bookhaven.py >> "%LOG%"

start "" /B cmd /c ^
  ""%PYTHON%" "%ROOT%\bookhaven.py" >> "%LOG%" 2>> "%LOG_ERR%""

echo BookHaven server launched (port %PORT%).
echo Logs : %LOG%
echo       %LOG_ERR%

endlocal
