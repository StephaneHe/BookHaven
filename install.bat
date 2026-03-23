@echo off
echo ===================================
echo  BookHaven - Installation
echo ===================================
echo.

set PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe

echo Checking Python...
"%PYTHON%" --version
if errorlevel 1 (
    echo ERROR: Python 3.12 not found at %PYTHON%
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
"%PYTHON%" -m pip install --upgrade pip
"%PYTHON%" -m pip install -r requirements.txt

echo.
echo Checking unrar for CBR support...
where unrar >nul 2>&1
if errorlevel 1 (
    echo WARNING: unrar not found in PATH.
    echo CBR files will not be readable.
    echo Download UnRAR from: https://www.rarlab.com/rar_add.htm
    echo Add UnRAR.exe to your PATH or copy it to this folder.
)

echo.
echo ===================================
echo  Installation complete!
echo  Run: run.bat
echo ===================================
pause
