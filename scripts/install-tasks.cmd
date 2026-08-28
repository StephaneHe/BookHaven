@echo off
:: ============================================================================
:: install-tasks.cmd � installe les t�ches Windows Task Scheduler pour
:: BookHaven. DOIT �TRE LANC� EN ADMINISTRATEUR.
::
:: Cr�e deux t�ches "� l'ouverture de session" (onlogon) :
::   BookHaven-server   � lance start-server.cmd au logon (/rl HIGHEST /it)
::   BookHaven-watchdog � lance le watchdog Node.js au logon avec un d�lai
::                        de 90s (/delay 0001:30) pour laisser le serveur
::                        d�marrer avant le premier probe.
::
:: IMPORTANT : ce script N'ex�cute PAS les t�ches imm�diatement.
::   Lancez-les manuellement si besoin :
::     schtasks /run /tn "BookHaven-server"
::     schtasks /run /tn "BookHaven-watchdog"
::   Ou red�marrez / fermez/rouvrez votre session.
::
:: ----------------------------------------------------------------------------
:: TEST MANUEL DU WATCHDOG
:: ----------------------------------------------------------------------------
:: 1. V�rifiez que les deux t�ches tournent :
::      schtasks /query /tn "BookHaven-server"   /v /fo LIST
::      schtasks /query /tn "BookHaven-watchdog" /v /fo LIST
::
:: 2. Tuez le process Python sur le port 8097 pour simuler un crash :
::      for /f "tokens=5" %p in ('netstat -ano ^| findstr ":8097 " ^| findstr "LISTENING"') do taskkill /PID %p /F /T
::
:: 3. Dans les ~20s (2 �checs � 10s) le watchdog doit d�clencher un restart.
::    V�rifiez les logs :
::      type "%ROOT%\logs\watchdog.log"
::
:: 4. Sous ~60s suppl�mentaires, le serveur doit �tre de nouveau disponible :
::      curl -s -o nul -w "%{http_code}" http://127.0.0.1:8097/
::
:: STOP PROPRE DU WATCHDOG (sans tuer la t�che) :
::   echo.> "%ROOT%\logs\watchdog.stop"
:: ============================================================================
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "NODE=C:\Program Files\nodejs\node.exe"
set "SCRIPTS=%ROOT%\scripts"

echo ============================================================
echo  BookHaven � installation des t�ches Task Scheduler
echo  R�pertoire : %ROOT%
echo ============================================================
echo.

:: --- Supprimer les anciennes t�ches si elles existent ------------------
echo Suppression des t�ches existantes (si pr�sentes)...
schtasks /delete /tn "BookHaven-server"   /f >nul 2>&1
schtasks /delete /tn "BookHaven-watchdog" /f >nul 2>&1

echo.
echo === T�che 1 : BookHaven-server (logon, sans d�lai) ===
schtasks /create /tn "BookHaven-server" ^
  /tr "\"%SCRIPTS%\start-server.cmd\"" ^
  /sc onlogon ^
  /rl HIGHEST ^
  /it ^
  /f
if errorlevel 1 (
    echo ERREUR lors de la creation de BookHaven-server.
    exit /b 1
)

echo.
echo === T�che 2 : BookHaven-watchdog (logon, d�lai 90s) ===
schtasks /create /tn "BookHaven-watchdog" ^
  /tr "\"%NODE%\" \"%SCRIPTS%\bookhaven-watchdog.mjs\"" ^
  /sc onlogon ^
  /delay 0001:30 ^
  /rl HIGHEST ^
  /it ^
  /f
if errorlevel 1 (
    echo ERREUR lors de la creation de BookHaven-watchdog.
    exit /b 1
)

echo.
echo === V�rification des t�ches cr��es ===
schtasks /query /tn "BookHaven-server"   /v /fo LIST | findstr /i "TaskName Status"
echo.
schtasks /query /tn "BookHaven-watchdog" /v /fo LIST | findstr /i "TaskName Status"

echo.
echo ============================================================
echo  T�ches cr��es avec succ�s.
echo.
echo  Les t�ches d�marreront automatiquement � la PROCHAINE
echo  ouverture de session. Pour les lancer MAINTENANT :
echo.
echo    schtasks /run /tn "BookHaven-server"
echo    (attendre ~5s)
echo    schtasks /run /tn "BookHaven-watchdog"
echo.
echo  G�rer via : taskschd.msc (Biblioth�que du Planificateur)
echo  Arr�ter   : schtasks /end /tn "BookHaven-watchdog"
echo              schtasks /end /tn "BookHaven-server"
echo  Supprimer : schtasks /delete /tn "BookHaven-server" /f
echo              schtasks /delete /tn "BookHaven-watchdog" /f
echo ============================================================
endlocal
