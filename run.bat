@echo off
echo ===================================
echo  BookHaven - Starting server
echo ===================================
echo.

set PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe

cd /d "%~dp0"
echo Server: http://localhost:8097
echo Press Ctrl+C to stop.
echo.

"%PYTHON%" bookhaven.py
pause
