@echo off
:: ============================================================================
:: install-tasks.cmd — installe les tâches Windows Task Scheduler pour
:: BookHaven. DOIT ÊTRE LANCÉ EN ADMINISTRATEUR.
::
:: Crée deux tâches "À l'ouverture de session" (onlogon) :
::   BookHaven-server   — lance start-server.cmd au logon (/rl HIGHEST /it)
::   BookHaven-watchdog — lance le watchdog Node.js au logon avec un délai
::                        de 90s (/delay 0001:30) pour laisser le serveur
::                        démarrer avant le premier probe.
::
:: IMPORTANT : ce script N'exécute PAS les tâches immédiatement.
::   Lancez-les manuellement si besoin :
::     schtasks /run /tn "BookHaven-server"
::     schtasks /run /tn "BookHaven-watchdog"
::   Ou redémarrez / fermez/rouvrez votre session.
::
:: ----------------------------------------------------------------------------
:: TEST MANUEL DU WATCHDOG
:: ----------------------------------------------------------------------------
:: 1. Vérifiez que les deux tâches tournent :
::      schtasks /query /tn "BookHaven-server"   /v /fo LIST
::      schtasks /query /tn "BookHaven-watchdog" /v /fo LIST
::
:: 2. Tuez le process Python sur le port 8097 pour simuler un crash :
::      for /f "tokens=5" %p in ('netstat -ano ^| findstr ":8097 " ^| findstr "LISTENING"') do taskkill /PID %p /F /T
::
:: 3. Dans les ~20s (2 échecs × 10s) le watchdog doit déclencher un restart.
::    Vérifiez les logs :
::      type C:\Dev\BookHaven\logs\watchdog.log
::
:: 4. Sous ~60s supplémentaires, le serveur doit être de nouveau disponible :
::      curl -s -o nul -w "%{http_code}" http://127.0.0.1:8097/
::
:: STOP PROPRE DU WATCHDOG (sans tuer la tâche) :
::   echo.> C:\Dev\BookHaven\logs\watchdog.stop
:: ============================================================================
setlocal

set "ROOT=C:\Dev\BookHaven"
set "NODE=C:\Program Files\nodejs\node.exe"
set "SCRIPTS=%ROOT%\scripts"

echo ============================================================
echo  BookHaven — installation des tâches Task Scheduler
echo  Répertoire : %ROOT%
echo ============================================================
echo.

:: --- Supprimer les anciennes tâches si elles existent ------------------
echo Suppression des tâches existantes (si présentes)...
schtasks /delete /tn "BookHaven-server"   /f >nul 2>&1
schtasks /delete /tn "BookHaven-watchdog" /f >nul 2>&1

echo.
echo === Tâche 1 : BookHaven-server (logon, sans délai) ===
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
echo === Tâche 2 : BookHaven-watchdog (logon, délai 90s) ===
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
echo === Vérification des tâches créées ===
schtasks /query /tn "BookHaven-server"   /v /fo LIST | findstr /i "TaskName Status"
echo.
schtasks /query /tn "BookHaven-watchdog" /v /fo LIST | findstr /i "TaskName Status"

echo.
echo ============================================================
echo  Tâches créées avec succès.
echo.
echo  Les tâches démarreront automatiquement à la PROCHAINE
echo  ouverture de session. Pour les lancer MAINTENANT :
echo.
echo    schtasks /run /tn "BookHaven-server"
echo    (attendre ~5s)
echo    schtasks /run /tn "BookHaven-watchdog"
echo.
echo  Gérer via : taskschd.msc (Bibliothèque du Planificateur)
echo  Arrêter   : schtasks /end /tn "BookHaven-watchdog"
echo              schtasks /end /tn "BookHaven-server"
echo  Supprimer : schtasks /delete /tn "BookHaven-server" /f
echo              schtasks /delete /tn "BookHaven-watchdog" /f
echo ============================================================
endlocal
