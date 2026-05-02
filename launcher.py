"""
Xtechnx Product Sync — Windows Masaüstü Başlatıcı
- Sistem tepsisine simge ekler
- Tarayıcıyı otomatik açar
- Sunucuyu arka planda çalıştırır
- Çıkışta sunucuyu temiz kapatır
"""
import sys
import os
import threading
import webbrowser
import time
import logging
import signal
from pathlib import Path

# ── PyInstaller _MEIPASS desteği ──────────────────────────────
if getattr(sys, 'frozen', False):
    # .exe olarak çalışıyor
    BASE_DIR = Path(sys._MEIPASS)
    # Çalışma dizinini .exe'nin yanına taşı
    WORK_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
    WORK_DIR = BASE_DIR

# Kaynak dizini src/ içinde
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(BASE_DIR))

# Çalışma dizinine geç (veritabanı, loglar burada oluşur)
os.chdir(str(WORK_DIR))

# Gerekli klasörler
for folder in ['logs', 'data', 'reports', 'barcodes']:
    Path(folder).mkdir(exist_ok=True)

# .env yoksa örnek oluştur
if not Path('.env').exists() and Path('.env.example').exists():
    import shutil
    shutil.copy('.env.example', '.env')

HOST = "127.0.0.1"
PORT = 8000
URL  = f"http://{HOST}:{PORT}"

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def start_server():
    """uvicorn'u ayrı thread'de başlatır."""
    import uvicorn
    # main.py'deki logging handler'ını devre dışı bırak
    # (launcher kendi handler'ını kurdu)
    config = uvicorn.Config(
        "main:app",
        host=HOST,
        port=PORT,
        log_level="warning",
        reload=False,
        workers=1,
    )
    server = uvicorn.Server(config)
    server.run()


def open_browser():
    """Sunucu hazır olunca tarayıcıyı açar."""
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"{URL}/health", timeout=1)
            webbrowser.open(URL)
            logger.info(f"Tarayıcı açıldı: {URL}")
            return
        except Exception:
            time.sleep(0.5)
    webbrowser.open(URL)


def show_tray():
    """
    Windows sistem tepsisi simgesi.
    pystray varsa kullan, yoksa basit console modunda çalış.
    """
    try:
        import pystray
        from PIL import Image, ImageDraw

        # Basit simge oluştur
        img = Image.new('RGB', (64, 64), color='#7c5cfc')
        draw = ImageDraw.Draw(img)
        draw.text((8, 16), "XT", fill='white')

        def on_open(icon, item):
            webbrowser.open(URL)

        def on_quit(icon, item):
            logger.info("Uygulama kapatılıyor...")
            icon.stop()
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("Arayüzü Aç", on_open, default=True),
            pystray.MenuItem("Çıkış", on_quit),
        )
        icon = pystray.Icon("Xtechnx", img, "Xtechnx Product Sync", menu)
        icon.run()

    except ImportError:
        # pystray yoksa sadece çalışmaya devam et
        logger.info("Sistem tepsisi desteği yok, console modunda çalışıyor.")
        logger.info(f"Arayüz: {URL}")
        logger.info("Durdurmak için Ctrl+C")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Kapatılıyor...")
            os._exit(0)


def main():
    logger.info("=" * 50)
    logger.info("  Xtechnx Product Sync v4.2 başlatılıyor...")
    logger.info("=" * 50)

    # Sunucuyu arka planda başlat
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    logger.info("Sunucu başlatıldı")

    # Tarayıcıyı arka planda aç
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Sistem tepsisi (veya console) — bu çağrı blokladığı için en sona
    show_tray()


if __name__ == "__main__":
    main()
