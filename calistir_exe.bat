@echo off
title Xtechnx Product Sync
color 0A

:: .env kontrolu
if not exist ".env" (
    if exist ".env.example" (
        echo [!] .env bulunamadi, ornekten olusturuluyor...
        copy .env.example .env
        echo.
        echo  API anahtarlarinizi girmek icin:
        echo  Uygulama acilinca Ayarlar sekmesine gidin.
        echo.
    )
)

:: Gerekli klasorler
if not exist "logs"    mkdir logs
if not exist "data"    mkdir data
if not exist "reports" mkdir reports
if not exist "barcodes" mkdir barcodes

echo [..] Xtechnx Product Sync baslatiliyor...
start "" "XtechnxProductSync.exe"
