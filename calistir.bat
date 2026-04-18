@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [HATA] Once kur.bat calistirin!
    pause & exit /b 1
)

set PYTHONIOENCODING=utf-8
venv\Scripts\python.exe launcher.py
