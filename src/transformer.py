"""
Ürün Dönüştürücü - Xtechnx kuralları:
1. Başlık:    Önce "Xtechnx" kelimesi temizlenir, sonra başa "Xtechnx " eklenir
2. Fiyat:     orijinal fiyat × 2
3. Barkod:    "Xtechnx" + 6 rastgele rakam = 13 karakter
4. Stok kodu: "Cihan"   + aynı 6 rakam
Duplicate koruması: SQLite barcode_registry tablosuna kaydedilir.
"""
import re
import random
import string
import hashlib
from models.product import Product

from app_config import get_config

PREFIX_TITLE   = "Xtechnx "
PREFIX_BARCODE = "Xtechnx"
PREFIX_SKU     = "Cihan"
NUMERIC_LEN    = 13 - len(PREFIX_BARCODE)   # 6


def _deterministic_suffix(seed: str) -> str:
    """Orijinal barkod/SKU'dan her zaman aynı 6 haneli suffix üretir."""
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    return str(h % 10 ** NUMERIC_LEN).zfill(NUMERIC_LEN)


def _generate_unique_suffix(seed: str = "") -> str:
    """Seed varsa deterministik, yoksa rastgele 6 haneli suffix üretir. Duplicate kontrolü yapar."""
    try:
        import database as db
        if seed:
            suffix = _deterministic_suffix(seed)
            candidate = PREFIX_BARCODE + suffix
            if not db.barcode_exists(candidate):
                return suffix
            # Çakışma: seed sonuna sayı ekleyerek farklı üret
            for i in range(1, 20):
                suffix = _deterministic_suffix(seed + str(i))
                if not db.barcode_exists(PREFIX_BARCODE + suffix):
                    return suffix
        # Seed yoksa rastgele
        for _ in range(100):
            suffix = ''.join(random.choices(string.digits, k=NUMERIC_LEN))
            if not db.barcode_exists(PREFIX_BARCODE + suffix):
                return suffix
    except Exception:
        if seed:
            return _deterministic_suffix(seed)
    return ''.join(random.choices(string.digits, k=NUMERIC_LEN))


def transform(product: Product) -> Product:
    if product.barcode and product.barcode.startswith(PREFIX_BARCODE):
        suffix = product.barcode[len(PREFIX_BARCODE):]
    else:
        # Aynı orijinal barkod daha önce kaydedilmişse onu yeniden kullan
        orig_barcode = (product.barcode or "").strip()
        try:
            import database as db
            existing = db.get_barcode_by_orig(orig_barcode) if orig_barcode else None
        except Exception:
            existing = None
        if existing and existing.startswith(PREFIX_BARCODE):
            suffix = existing[len(PREFIX_BARCODE):]
        else:
            seed = (orig_barcode or product.sku or product.title or "").strip()
            suffix = _generate_unique_suffix(seed)

    # Başlıktan "Xtechnx" kelimesini her yerden temizle, sonra başa ekle
    stripped_title = re.sub(r'\bXtechnx\b\s*', '', product.title, flags=re.IGNORECASE).strip()
    new_title = PREFIX_TITLE + stripped_title
    new_price   = round(product.price * get_config()["price_multiplier"], 2)
    new_barcode = PREFIX_BARCODE + suffix
    raw_sku     = (product.sku or "").strip()
    new_sku     = PREFIX_SKU + (raw_sku.zfill(6) if raw_sku else suffix)

    try:
        import database as db
        db.register_barcode(new_barcode, product.barcode or "")
    except Exception:
        pass

    data = product.model_dump()
    data.update(title=new_title, price=new_price, barcode=new_barcode, sku=new_sku)
    return Product(**data)


def preview(product: Product) -> dict:
    transformed = transform(product)
    return {
        "original": {
            "title": product.title, "price": product.price,
            "barcode": product.barcode or "(yok)", "sku": product.sku or "(yok)",
        },
        "transformed": {
            "title": transformed.title, "price": transformed.price,
            "barcode": transformed.barcode, "sku": transformed.sku,
        },
        "changes": {
            "title":   f"{product.title}  →  {transformed.title}",
            "price":   f"{product.price} TL  →  {transformed.price} TL",
            "barcode": f"{product.barcode or '(yok)'}  →  {transformed.barcode}",
            "sku":     f"{product.sku or '(yok)'}  →  {transformed.sku}",
        }
    }
