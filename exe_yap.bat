@echo off
title Xtechnx Product Sync — EXE Builder
color 0A

:: !! ONEMLI: Bu bat dosyasinin bulundugu klasore gec !!
cd /d "%~dp0"

echo.
echo  ============================================
echo   Xtechnx Product Sync — EXE Yapimi
echo  ============================================
echo  Klasor: %CD%
echo.

:: ZIP icinden calistirilip calistirilmadigini kontrol et
echo %CD% | findstr /i "Temp\Rar" >nul
if not errorlevel 1 goto ZIP_UYARI
echo %CD% | findstr /i "Temp\7z" >nul
if not errorlevel 1 goto ZIP_UYARI
echo %CD% | findstr /i "Temp\Zip" >nul
if not errorlevel 1 goto ZIP_UYARI
echo %CD% | findstr /i "AppData\Local\Temp" >nul
if not errorlevel 1 goto ZIP_UYARI
goto DEVAM

:ZIP_UYARI
echo.
echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo  DIKKAT: ZIP/RAR icinden calistiriyorsunuz!
echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo.
echo  Yapmaniz gereken:
echo  1. Zip dosyasina sag tiklayin
echo  2. "Tumunu Cikar" secin  (ornek: C:\Users\Sule\Desktop\)
echo  3. Cikartilan klasordeki exe_yap.bat'i calistirin
echo.
pause
exit /b 1

:DEVAM

:: Python kontrolu
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo Indirin: https://www.python.org/downloads/
    pause & exit /b 1
)
echo [OK] Python bulundu

:: spec dosyasi kontrolu
if not exist "xtechnx.spec" (
    echo [HATA] xtechnx.spec bulunamadi!
    echo Lutfen exe_yap.bat dosyasinin product-sync klasorunde oldugunu kontrol edin.
    pause & exit /b 1
)
echo [OK] xtechnx.spec bulundu

:: Venv olustur
if not exist "venv" (
    echo [..] Sanal ortam olusturuluyor...
    python -m venv venv
)
call venv\Scripts\activate.bat

:: Bagimliliklar (pip upgrade hatasi icin python -m pip kullan)
echo [..] Bagimliliklar yukleniyor...
python -m pip install -q --upgrade pip
python -m pip install -q fastapi "uvicorn[standard]" aiohttp beautifulsoup4 ^
    pydantic pydantic-settings python-dotenv openpyxl keyring ^
    python-multipart lxml "pyinstaller>=6.0" pystray pillow

:: Python 3.14+ icin ek uyumluluk paketi
python -m pip install -q setuptools

echo.
echo [..] EXE olusturuluyor (1-3 dakika surebilir)...
echo.

pyinstaller xtechnx.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo [HATA] EXE olusturulamadi! Yukaridaki hatalara bakin.
    pause & exit /b 1
)

echo.
echo  ============================================
echo   BASARILI!
echo   EXE konumu: dist\XtechnxProductSync.exe
echo  ============================================
echo.
echo  NOT: .exe'yi calistirmadan once
echo       .env dosyasini yanina kopyalayin!
echo.

:: dist klasorune .env.example kopyala
if exist "dist\XtechnxProductSync.exe" (
    copy .env.example dist\
    mkdir dist\logs 2>nul
    mkdir dist\data 2>nul
    mkdir dist\reports 2>nul
    mkdir dist\barcodes 2>nul
    echo [OK] Gerekli klasorler dist\ altinda olusturuldu
)

pause
