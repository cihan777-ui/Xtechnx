import aiohttp
from models.product import Product
from config.settings import settings
from category_mapper import get_n11_category

CREATE_URL = "https://api.n11.com/ms/product/tasks/product-create"
TASK_URL   = "https://api.n11.com/ms/product/tasks/{task_id}"


def _resolve_category(p: Product) -> int:
    manual = p.attributes.get("_category_ids", {}).get("n11", 0)
    if manual and manual != 0:
        return manual
    try:
        import database as db
        db_mappings = {
            m["source_category"]: m["n11_id"]
            for m in db.get_category_mappings()
            if m.get("n11_id")
        }
    except Exception:
        db_mappings = {}
    return get_n11_category(p.category or "", db_mappings)


def _extract_brand(p: Product) -> str:
    if p.brand:
        return p.brand
    # "Xtechnx Marka ..." → "Marka"
    title = p.title or ""
    if title.startswith("Xtechnx "):
        title = title[len("Xtechnx "):]
    return title.split()[0] if title.split() else "Diger"


def _numeric_barcode(p: Product) -> str:
    """'Xtechnx123456' → '0000000123456' (13 haneli sayısal barkod)"""
    raw = p.barcode or ""
    digits = "".join(c for c in raw if c.isdigit())
    return digits.zfill(13)[:13] if digits else str(abs(hash(p.title)) % 10**13).zfill(13)


def _build_payload(p: Product) -> dict:
    cat_id = _resolve_category(p)
    images = [{"url": img, "order": i + 1} for i, img in enumerate(p.images[:8]) if img]
    brand = _extract_brand(p)
    barcode = _numeric_barcode(p)
    tmpl = getattr(settings, "n11_shipment_template", "") or "Aras Kargo"
    return {
        "payload": {
            "integrator": "Xtechnx",
            "skus": [{
                "title": p.title[:255],
                "description": p.description[:30000],
                "categoryId": cat_id,
                "currencyType": "TL",
                "productMainId": p.sku or f"XTECH-{abs(hash(p.title)) % 10**8}",
                "preparingDay": 2,
                "shipmentTemplate": tmpl,
                "stockCode": p.sku or f"XTECH-{abs(hash(p.title)) % 10**8}",
                "barcode": barcode,
                "quantity": p.stock,
                "images": images,
                "attributes": [{"id": 1, "customValue": brand, "valueId": None}],
                "salePrice": round(p.price, 2),
                "listPrice": round(p.price, 2),
                "vatRate": 10,
            }]
        }
    }


class N11Uploader:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "appkey": settings.n11_app_key,
            "appsecret": settings.n11_app_secret,
        }

    async def upload(self, product: Product) -> dict:
        payload = _build_payload(product)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CREATE_URL, json=payload, headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201, 202):
                    raise Exception(f"N11 REST {resp.status}: {data}")

                task_id = data.get("taskId") or data.get("id") or str(data)
                return {
                    "status": "success",
                    "task_id": task_id,
                    "message": f"N11'e gönderildi. TaskID: {task_id}",
                }
