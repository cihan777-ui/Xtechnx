@echo off
if not exist "venv\Scripts\activate.bat" (
    echo [HATA] Once kur.bat calistirin!
    pause & exit /b 1
)
if not exist ".env" (
    echo [HATA] .env dosyasi yok! copy .env.example .env
    pause & exit /b 1
)
call venv\Scripts\activate.bat
cd src
echo.
echo ============================================
echo  Xtechnx Product Sync Baslatildi!
echo  Arayuz: http://localhost:8000
echo  API:    http://localhost:8000/docs
echo  Durdurmak: Ctrl + C
echo ============================================
echo.
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
