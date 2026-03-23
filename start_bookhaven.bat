@echo off
:: BookHaven Server Launcher
:: Starts the BookHaven library server on port 8097

cd /d H:\BookHaven
start /min "" "C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" bookhaven.py
echo BookHaven started on http://localhost:8097
