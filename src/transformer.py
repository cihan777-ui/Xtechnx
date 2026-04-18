"""
Ürün Dönüştürücü - Xtechnx kuralları:
1. Başlık:    "Xtechnx " + orijinal başlık
2. Fiyat:     orijinal fiyat × 2
3. Barkod:    "Xtechnx" + 6 rastgele rakam = 13 karakter
4. Stok kodu: "Cihan"   + aynı 6 rakam
Duplicate koruması: SQLite barcode_registry tablosuna kaydedilir.
"""
import random
import string
from models.product import Product

PREFIX_TITLE   = "Xtechnx "
PREFIX_BARCODE = "Xtechnx"
PREFIX_SKU     = "Cihan"
NUMERIC_LEN    = 13 - len(PREFIX_BARCODE)   # 6


def _generate_unique_suffix() -> str:
    """Duplicate olmayan 6 haneli suffix üretir."""
    try:
        import database as db
        for _ in range(100):
            suffix = ''.join(random.choices(string.digits, k=NUMERIC_LEN))
            if not db.barcode_exists(PREFIX_BARCODE + suffix):
                return suffix
    except Exception:
        pass
    return ''.join(random.choices(string.digits, k=NUMERIC_LEN))


def transform(product: Product) -> Product:
    if product.barcode and product.barcode.startswith(PREFIX_BARCODE):
        suffix = product.barcode[len(PREFIX_BARCODE):]
    else:
        suffix = _generate_unique_suffix()

    new_title   = product.title if product.title.startswith(PREFIX_TITLE) else PREFIX_TITLE + product.title
    new_price   = round(product.price * 2, 2)
    new_barcode = PREFIX_BARCODE + suffix
    new_sku     = PREFIX_SKU + suffix

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
