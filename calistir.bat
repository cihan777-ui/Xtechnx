@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [HATA] venv bulunamadi! Once kur.bat calistirin!
    pause & exit /b 1
)

set PYTHONIOENCODING=utf-8
echo Baslatiliyor...
venv\Scripts\python.exe launcher.py
if errorlevel 1 (
    echo.
    echo [HATA] Program baslatılamadi! Hata kodu: %errorlevel%
    pause
)
