import base64
import asyncio
import logging
import aiohttp
from models.product import Product
from config.settings import settings
from category_mapper import get_trendyol_category

_log = logging.getLogger(__name__)

BASE_URL     = "https://api.trendyol.com/sapigw"
_brand_cache: dict = {}   # name.lower() → brand_id


def _make_auth(api_key: str, api_secret: str) -> str:
    return base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()


def _headers(supplier_id: str, auth: str) -> dict:
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "User-Agent": f"{supplier_id} - SelfIntegration",
        "Accept": "application/json",
    }


async def _lookup_brand(session: aiohttp.ClientSession, name: str, hdrs: dict) -> int | None:
    """Marka adına göre Trendyol brand ID'sini döner. Sonucu önbellekler."""
    key = name.strip().lower()
    if key in _brand_cache:
        return _brand_cache[key]
    try:
        url = f"{BASE_URL}/brands?name={name}&page=0&size=5"
        async with session.get(url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
            brands = data if isinstance(data, list) else data.get("brands", [])
            for b in brands:
                if (b.get("name") or "").strip().lower() == key:
                    bid = int(b["id"])
                    _brand_cache[key] = bid
                    _log.info("TY marka bulundu: '%s' → ID %d", name, bid)
                    return bid
    except Exception as ex:
        _log.warning("TY marka arama hatası: %s", ex)
    return None


async def _poll_batch(session: aiohttp.ClientSession, supplier_id: str,
                      batch_id: str, hdrs: dict) -> dict:
    """Batch durumunu 20 × 15s = 5 dakika boyunca sorgular."""
    url = f"{BASE_URL}/suppliers/{supplier_id}/v2/products/batch-requests/{batch_id}"
    for attempt in range(20):
        await asyncio.sleep(15)
        try:
            async with session.get(url, headers=hdrs,
                                   timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    _log.info("TY batch poll [%d] HTTP %d", attempt + 1, r.status)
                    continue
                d = await r.json(content_type=None)
                status = (d.get("status") or "").upper()
                items  = d.get("items") or []

                if status in ("COMPLETED", "DONE", "FAILED"):
                    failed  = [i for i in items if (i.get("status") or "").upper() != "SUCCESS"]
                    success = [i for i in items if (i.get("status") or "").upper() == "SUCCESS"]
                    if failed:
                        reasons = "; ".join(
                            f"{i.get('barcode','?')}: "
                            + ", ".join(e.get("message", "") for e in (i.get("reasons") or []))
                            for i in failed
                        )
                        return {"status": "error",
                                "batch_id": batch_id,
                                "message": f"Trendyol reddetti: {reasons}"}
                    return {"status": "success",
                            "batch_id": batch_id,
                            "message": f"Trendyol onayladı. BatchID: {batch_id}, {len(success)} ürün"}

                _log.info("TY batch [%d] durum: %s (%d item)", attempt + 1, status, len(items))
        except Exception as ex:
            _log.info("TY batch poll [%d] hata: %s", attempt + 1, ex)

    return {
        "status": "success_unconfirmed",
        "batch_id": batch_id,
        "message": f"Trendyol'a gönderildi, onay bekleniyor. BatchID: {batch_id}",
    }


def _build_payload(p: Product, brand_id: int, category_id: int) -> dict:
    images = [{"url": img} for img in (p.images or [])[:8]]
    if not images:
        images = [{"url": "https://xtechnx.com/image/no-image.jpg"}]

    return {
        "items": [{
            "barcode":       p.barcode,
            "title":         p.title[:150],
            "productMainId": p.sku,
            "brandId":       brand_id,
            "categoryId":    category_id,
            "quantity":      max(p.stock, 1),
            "stockCode":     p.sku,
            "description":   (p.description or p.title)[:30000],
            "currencyType":  "TRY",
            "listPrice":     round(p.price, 2),
            "salePrice":     round(p.price, 2),
            "vatRate":       20,
            "cargoCompanyId": 17,   # Yurtiçi Kargo
            "images":        images,
            "attributes":    [],
        }]
    }


class TrendyolUploader:

    def __init__(self):
        self.api_key     = settings.trendyol_api_key
        self.api_secret  = settings.trendyol_api_secret
        self.supplier_id = settings.trendyol_supplier_id
        self.auth        = _make_auth(self.api_key, self.api_secret)
        self.hdrs        = _headers(self.supplier_id, self.auth)

    async def upload(self, product: Product) -> dict:
        db_mapping = {}
        try:
            import database as _db
            db_mapping = _db.get_category_mapping_dict()
        except Exception:
            pass

        category_id = get_trendyol_category(
            product.attributes.get("source_category", ""), db_mapping
        )

        async with aiohttp.ClientSession() as session:
            # Marka ID'sini bul
            brand_id = await _lookup_brand(session, "Xtechnx", self.hdrs)
            if not brand_id:
                _log.warning("TY: 'Xtechnx' markası bulunamadı, brandId=0 ile deneniyor")
                brand_id = 0

            payload = _build_payload(product, brand_id, category_id)
            url = f"{BASE_URL}/suppliers/{self.supplier_id}/v2/products"

            async with session.post(url, json=payload, headers=self.hdrs,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                raw = await resp.text()
                if resp.status not in (200, 201, 202):
                    return {"status": "error",
                            "message": f"Trendyol API hatası {resp.status}: {raw[:300]}"}
                try:
                    import json
                    data = json.loads(raw)
                except Exception:
                    data = {}

            batch_id = data.get("batchRequestId") or data.get("id") or str(data)
            _log.info("TY batch oluştu: %s", batch_id)

            result = await _poll_batch(session, self.supplier_id, batch_id, self.hdrs)
            return result
