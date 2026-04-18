# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

SRC = Path('src')
block_cipher = None

datas = [
    (str(SRC / 'ui.html'), 'src'),
    ('.env.example', '.'),
]

hidden_imports = [
    'uvicorn.logging','uvicorn.loops','uvicorn.loops.auto','uvicorn.loops.asyncio',
    'uvicorn.protocols','uvicorn.protocols.http','uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl','uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto','uvicorn.lifespan','uvicorn.lifespan.off',
    'uvicorn.lifespan.on',
    'fastapi','starlette','starlette.routing','starlette.middleware',
    'starlette.responses','anyio','anyio._backends._asyncio',
    'aiohttp','aiohttp.connector','multidict','yarl',
    'pydantic','pydantic_settings',
    'bs4','lxml','lxml.etree',
    'openpyxl','openpyxl.styles','openpyxl.utils',
    'keyring','keyring.backends',
    'dotenv','sqlite3','email','logging.handlers',
    'multipart','h11','httptools','watchfiles','websockets',
    'main','database','barcode_manager','transformer',
    'credentials','report','sync_service',
    'scrapers.product_scraper','scrapers.merter_scraper',
    'uploaders.trendyol','uploaders.hepsiburada','uploaders.n11','uploaders.amazon',
    'models.product','config.settings',
]

a = Analysis(
    ['launcher.py'],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter','matplotlib','numpy','pandas','scipy','cv2','torch'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── GUI exe (penceresiz, tepsi simgesi) ──
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='XtechnxProductSync',
    debug=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    # icon='icon.ico',
)

# ── Debug exe (konsol pencereli, hata ayıklama için) ──
exe_debug = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='XtechnxProductSync_debug',
    debug=True,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
)
