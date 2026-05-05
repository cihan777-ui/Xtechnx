"""
xtechnx.com admin paneline requests ile ürün yükler (Selenium yok).
Login → user_token al → resim yükle → ürün POST et.
"""
import re
import time
import logging
import asyncio
import os
import tempfile
from functools import partial

import requests as _req

from models.product import Product
from config.settings import settings

log = logging.getLogger(__name__)

ADMIN_URL  = settings.xtechnx_admin_url   # https://xtechnx.com/admin/
ADMIN_USER = settings.xtechnx_admin_user
ADMIN_PASS = settings.xtechnx_admin_pass

MANUFACTURER_ID = 4    # Xtechnx markası
TAX_CLASS_ID    = 1    # %20 KDV
LANG_ID         = 1    # Türkçe
STORE_ID        = 0    # Ana mağaza

_session    = None
_user_token = ""


# ── Oturum ───────────────────────────────────────────────────────

def _get_session() -> tuple:
    """Admin oturumu aç, (session, user_token) döndür. Önbellekler."""
    global _session, _user_token
    if _session and _user_token:
        # Token geçerli mi kontrol et
        r = _session.get(f"{ADMIN_URL}index.php?route=common/dashboard&user_token={_user_token}", timeout=10)
        if "login" not in r.url and _user_token in r.url:
            return _session, _user_token

    s = _req.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    r = s.post(f"{ADMIN_URL}index.php?route=common/login",
               data={"username": ADMIN_USER, "password": ADMIN_PASS},
               timeout=15)
    m = re.search(r"user_token=([^&\s\"]+)", r.url)
    if not m:
        raise RuntimeError(f"Admin login basarisiz: {r.url}")

    _session    = s
    _user_token = m.group(1)
    log.info(f"[xtechnx-api] Admin login OK, token: {_user_token[:16]}...")
    return _session, _user_token


# ── Resim Yükleme ─────────────────────────────────────────────────

def _resim_yukle_api(session, token, resim_url: str, sira: int) -> str:
    """
    Resmi indir → filemanager'a yükle → server path döndür.
    Başarısız olursa "" döner.
    """
    try:
        resp = _req.get(resim_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200 or len(resp.content) < 2000:
            log.info(f"[xtechnx-api] Resim {sira}: indirilemedi ({resp.status_code})")
            return ""

        ext = "jpg"
        fname = f"xtechnx_{sira}_{int(time.time())}.{ext}"
        tmp = os.path.join(tempfile.gettempdir(), fname)
        with open(tmp, "wb") as f:
            f.write(resp.content)

        upload_url = f"{ADMIN_URL}index.php?route=common/filemanager/upload&user_token={token}&target=catalog/"
        with open(tmp, "rb") as f:
            r = session.post(upload_url, files={"file[]": (fname, f, "image/jpeg")}, timeout=30)

        try:
            os.unlink(tmp)
        except Exception:
            pass

        if r.status_code != 200:
            log.info(f"[xtechnx-api] Resim {sira}: upload HTTP {r.status_code}")
            return ""

        log.info(f"[xtechnx-api] Resim {sira}: upload yaniti: {r.text[:200]}")

        # Strateji 1: JSON yanıtından path al
        try:
            data = r.json()
            path = data.get("path") or data.get("filename") or data.get("name") or ""
            if not path and isinstance(data, list) and data:
                path = data[0].get("path") or data[0].get("name") or ""
            if path:
                log.info(f"[xtechnx-api] Resim {sira}: JSON path -> {path}")
                return path
        except Exception:
            pass

        # Strateji 2: Filemanager listesinden en son dosyayı bul
        try:
            list_url = f"{ADMIN_URL}index.php?route=common/filemanager&user_token={token}&target=catalog/"
            lr = session.get(list_url, timeout=10,
                             headers={"X-Requested-With": "XMLHttpRequest"})
            if lr.status_code == 200:
                ldata = lr.json()
                files = ldata if isinstance(ldata, list) else ldata.get("files", [])
                for f_item in files:
                    fpath = f_item.get("path") or f_item.get("name") or ""
                    if fname in fpath:
                        log.info(f"[xtechnx-api] Resim {sira}: listing ile bulundu -> {fpath}")
                        return fpath
        except Exception:
            pass

        # Strateji 3: OpenCart her zaman image/catalog/ altına kaydeder → catalog/fname
        constructed = f"catalog/{fname}"
        log.info(f"[xtechnx-api] Resim {sira}: path olusturuldu -> {constructed}")
        return constructed

    except Exception as e:
        log.info(f"[xtechnx-api] Resim {sira}: hata: {e}")
        return ""


# ── Ürün Ekleme ───────────────────────────────────────────────────

def _urun_ekle_sync(p: Product) -> dict:
    try:
        session, token = _get_session()
    except Exception as e:
        return {"status": "error", "message": f"Login hatasi: {e}"}

    baslik       = p.title[:255]
    fiyat        = str(round(p.price, 2))
    aciklama     = (p.description or "").replace("\n", "<br>")[:5000]
    sku          = p.sku or ""
    barkod       = p.barcode or ""
    stok         = str(p.stock or 1)

    # ── Resimleri yükle ─────────────────────────────────────────
    resim_paths = []
    for i, url in enumerate(p.images[:5], 1):
        path = _resim_yukle_api(session, token, url, i)
        if path:
            resim_paths.append(path)
        time.sleep(0.5)

    log.info(f"[xtechnx-api] {len(resim_paths)}/{len(p.images[:5])} resim yuklendi")

    # ── Form verisi ──────────────────────────────────────────────
    data = {
        f"product_description[{LANG_ID}][name]":             baslik,
        f"product_description[{LANG_ID}][description]":      aciklama,
        f"product_description[{LANG_ID}][tag]":              "",
        f"product_description[{LANG_ID}][meta_title]":       baslik,
        f"product_description[{LANG_ID}][meta_description]": "",
        f"product_description[{LANG_ID}][meta_keyword]":     "",
        "model":                sku,
        "sku":                  "",
        "upc":                  "",
        "ean":                  barkod,
        "jan":                  "",
        "isbn":                 "",
        "mpn":                  "",
        "location":             "",
        "price":                fiyat,
        "tax_class_id":         str(TAX_CLASS_ID),
        "quantity":             stok,
        "minimum":              "1",
        "subtract":             "1",
        "stock_status_id":      "7",
        "shipping":             "1",
        "keyword":              "",
        "image":                resim_paths[0] if resim_paths else "",
        "manufacturer_id":      str(MANUFACTURER_ID),
        "sort_order":           "0",
        "status":               "1",
        "date_available":       "",
        "weight":               "0.00",
        "weight_class_id":      "1",
        "length":               "0.00",
        "width":                "0.00",
        "height":               "0.00",
        "length_class_id":      "1",
        "product_store[]":      str(STORE_ID),
    }

    # Ek resimler
    for i, path in enumerate(resim_paths[1:], 0):
        data[f"product_image[{i}][image]"]      = path
        data[f"product_image[{i}][sort_order]"] = str(i + 1)

    # Kategori
    if p.category:
        data["product_category[]"] = p.category

    # ── POST et ──────────────────────────────────────────────────
    add_url = f"{ADMIN_URL}index.php?route=catalog/product/add&user_token={token}"
    try:
        r = session.post(add_url, data=data, timeout=30)
        log.info(f"[xtechnx-api] Product POST: HTTP {r.status_code}, URL: {r.url[-60:]}")

        if "product_id" in r.url or "alert-success" in r.text:
            pid = re.search(r"product_id=(\d+)", r.url)
            product_id = int(pid.group(1)) if pid else 0
            msg = f"xtechnx.com API ile yuklendi: {baslik[:50]}"
            if product_id:
                msg += f" (ID:{product_id})"
            return {"status": "success", "message": msg, "xtechnx_product_id": product_id}
        elif "alert-danger" in r.text or "alert-error" in r.text:
            err = re.search(r'alert-danger[^>]*>(.*?)</div>', r.text, re.S)
            return {"status": "error", "message": err.group(1).strip()[:200] if err else "Form hatasi"}
        else:
            return {"status": "success", "message": f"xtechnx.com API ile yuklendi (kontrol edin): {baslik[:50]}"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get_xtechnx_stock_sync(product_id: int) -> int | None:
    """xtechnx.com admin panelinden ürünün mevcut stokunu okur."""
    try:
        session, token = _get_session()
        url = f"{ADMIN_URL}index.php?route=catalog/product/edit&user_token={token}&product_id={product_id}"
        r = session.get(url, timeout=15)
        m = re.search(r'name=["\']quantity["\'][^>]+value=["\'](\d+)["\']', r.text)
        if not m:
            m = re.search(r'id=["\']input-quantity["\'][^>]+value=["\'](\d+)["\']', r.text)
        if not m:
            m = re.search(r'name="quantity"\s+value="(\d+)"', r.text)
        if m:
            return int(m.group(1))
        log.warning(f"[xtechnx-api] Stok okunamadı, product_id={product_id}")
        return None
    except Exception as e:
        log.warning(f"[xtechnx-api] Stok okuma hatası: {e}")
        return None


def _update_xtechnx_stock_sync(product_id: int, new_qty: int) -> bool:
    """xtechnx.com admin panelinde ürünün stokunu günceller."""
    try:
        session, token = _get_session()
        edit_url = f"{ADMIN_URL}index.php?route=catalog/product/edit&user_token={token}&product_id={product_id}"

        # Edit sayfasını çek, mevcut form alanlarını al
        r = session.get(edit_url, timeout=15)
        if r.status_code != 200:
            return False

        # Temel zorunlu alanları parse et
        def _fval(name, default=""):
            m = re.search(rf'name="{re.escape(name)}"\s+[^>]*value="([^"]*)"', r.text)
            return m.group(1) if m else default

        def _tval(name):
            m = re.search(rf'name="{re.escape(name)}"[^>]*>([^<]*)</textarea>', r.text, re.S)
            return m.group(1).strip() if m else ""

        # Minimum zorunlu alanlar
        data = {
            f"product_description[{LANG_ID}][name]":             _fval(f"product_description[{LANG_ID}][name]", "Ürün"),
            f"product_description[{LANG_ID}][description]":      _tval(f"product_description[{LANG_ID}][description]"),
            f"product_description[{LANG_ID}][tag]":              "",
            f"product_description[{LANG_ID}][meta_title]":       _fval(f"product_description[{LANG_ID}][meta_title]", ""),
            f"product_description[{LANG_ID}][meta_description]": "",
            f"product_description[{LANG_ID}][meta_keyword]":     "",
            "model":           _fval("model"),
            "sku":             _fval("sku"),
            "ean":             _fval("ean"),
            "price":           _fval("price", "0.00"),
            "tax_class_id":    _fval("tax_class_id", str(TAX_CLASS_ID)),
            "quantity":        str(max(0, new_qty)),
            "minimum":         _fval("minimum", "1"),
            "subtract":        "1",
            "stock_status_id": _fval("stock_status_id", "7"),
            "shipping":        "1",
            "image":           _fval("image"),
            "manufacturer_id": _fval("manufacturer_id", str(MANUFACTURER_ID)),
            "sort_order":      _fval("sort_order", "0"),
            "status":          _fval("status", "1"),
            "weight":          _fval("weight", "0.00"),
            "weight_class_id": _fval("weight_class_id", "1"),
            "length":          _fval("length", "0.00"),
            "width":           _fval("width", "0.00"),
            "height":          _fval("height", "0.00"),
            "length_class_id": _fval("length_class_id", "1"),
            "product_store[]": str(STORE_ID),
        }

        post_url = f"{ADMIN_URL}index.php?route=catalog/product/edit&user_token={token}&product_id={product_id}"
        resp = session.post(post_url, data=data, timeout=30)
        log.info(f"[xtechnx-api] Stok güncelleme HTTP {resp.status_code}, qty={new_qty}")
        return resp.status_code == 200
    except Exception as e:
        log.warning(f"[xtechnx-api] Stok güncelleme hatası: {e}")
        return False


def _get_xtechnx_orders_sync(limit: int = 50) -> list:
    """xtechnx.com'dan son siparişleri çeker (Processing + Complete). [{order_id, sku, qty}]"""
    try:
        session, token = _get_session()
        orders = []
        for status_id in [2, 5]:  # 2=Processing, 5=Complete
            url = (f"{ADMIN_URL}index.php?route=sale/order"
                   f"&user_token={token}&filter_order_status_id={status_id}&limit={limit}")
            r = session.get(url, timeout=15)
            # order_id'leri parse et
            order_ids = re.findall(r'route=sale/order/info[^"]*order_id=(\d+)', r.text)
            for oid in order_ids[:limit]:
                # Sipariş detayına bak
                detail_url = (f"{ADMIN_URL}index.php?route=sale/order/info"
                              f"&user_token={token}&order_id={oid}")
                rd = session.get(detail_url, timeout=15)
                # model (SKU) ve qty parse et
                # OpenCart order info sayfasında ürün satırları: Model sütunu
                rows = re.findall(
                    r'<td[^>]*>([^<]+)</td>\s*<td[^>]*>\s*(\d+)\s*</td>',
                    rd.text
                )
                for model_raw, qty_raw in rows:
                    sku = model_raw.strip()
                    qty = int(qty_raw.strip())
                    if sku and qty > 0 and sku.startswith("Cihan"):
                        orders.append({
                            "order_id": f"xtechnx_{oid}",
                            "sku": sku,
                            "qty": qty,
                        })
        return orders
    except Exception as e:
        log.warning(f"[xtechnx-api] Sipariş çekme hatası: {e}")
        return []


class XtechnxSiteApiUploader:

    async def upload(self, product: Product) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(_urun_ekle_sync, product))

    async def get_stock(self, product_id: int) -> int | None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_xtechnx_stock_sync, product_id)

    async def update_stock(self, product_id: int, new_qty: int) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _update_xtechnx_stock_sync, product_id, new_qty)

    async def get_orders(self) -> list:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_xtechnx_orders_sync)
