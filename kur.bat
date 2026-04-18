@echo off
echo ============================================
echo  Xtechnx Product Sync - Windows Kurulum
echo ============================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi! https://www.python.org/downloads/
    pause & exit /b 1
)
echo [OK] Python bulundu
python -m pip install --upgrade pip
python -m venv venv
call venv\Scripts\activate.bat
pip install fastapi "uvicorn[standard]" aiohttp beautifulsoup4 pydantic pydantic-settings python-dotenv
pip install lxml
if errorlevel 1 echo [UYARI] lxml kurulamadi, html.parser kullanilacak
echo.
echo ============================================
echo  Kurulum tamamlandi!
echo  1. copy .env.example .env
echo  2. .env dosyasini duzenlleyin
echo  3. calistir.bat ile baslatin
echo ============================================
pause
