@echo off
:: ============================================================================
:: restart-bookhaven.cmd — kill le serveur BookHaven et le relance.
::
:: Appelé par le watchdog Node.js (bookhaven-watchdog.mjs), sans console et
:: sans entrée standard. Leçons de l'incident du 2026-10-04 21:11 :
::   * `timeout /t` échoue sans console (« la redirection de l'entrée n'est pas
::     prise en charge ») : les pauses utilisent `ping -n`.
::   * server.log est tenu ouvert par le serveur en cours : écrire dedans
::     échouait et le bloc de kill n'était pas exécuté. Ce script journalise
::     dans logs\restart.log.
::   * un serveur bloqué ÉCOUTE toujours sur le port : le succès ne se juge
::     plus au port en écoute mais à une réponse HTTP de /api/version.
::
:: Exit codes :
::   0 — serveur opérationnel (HTTP 200) après relance
::   1 — échec (le port reste occupé, ou pas de réponse HTTP en 120 s)
:: ============================================================================
setlocal EnableDelayedExpansion

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if not defined BOOKHAVEN_PYTHON set "BOOKHAVEN_PYTHON=python"
set "PYTHON=%BOOKHAVEN_PYTHON%"
set "PORT=8097"
set "LOG=%ROOT%\server.log"
set "LOG_ERR=%ROOT%\server_err.log"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
set "RLOG=%ROOT%\logs\restart.log"

call :log restart-bookhaven.cmd invoked

:: --- Kill everything listening on the port, until it is free (max ~20 s) ---
set /a KTRIES=0
:kill_loop
set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set "FOUND=1"
    call :log killing PID %%p
    taskkill /PID %%p /F /T >nul 2>&1
)
if not defined FOUND goto port_free
set /a KTRIES+=1
if !KTRIES! GEQ 10 (
    call :log ERROR port %PORT% still busy after 10 kill attempts
    exit /b 1
)
ping -n 3 127.0.0.1 >nul
goto kill_loop
:port_free
call :log port %PORT% free

:: --- Start the server (stdout/stderr appended to server logs) ---------------
call :log starting server
start "" /B cmd /c ^
  ""%PYTHON%" "%ROOT%\bookhaven.py" >> "%LOG%" 2>> "%LOG_ERR%""

:: --- Wait for a real HTTP answer (max 120 s) ---------------------------------
set /a TRIES=0
:wait_loop
ping -n 4 127.0.0.1 >nul
for /f %%c in ('curl.exe -s -m 3 -o nul -w "%%{http_code}" http://127.0.0.1:%PORT%/api/version 2^>nul') do set "CODE=%%c"
if "!CODE!"=="200" (
    call :log server answers HTTP 200 - restart OK
    exit /b 0
)
set /a TRIES+=1
if !TRIES! GEQ 40 (
    call :log TIMEOUT no HTTP answer on port %PORT% after restart
    exit /b 1
)
goto wait_loop

:log
echo [%date% %time%] %* >> "%RLOG%" 2>nul
exit /b 0
