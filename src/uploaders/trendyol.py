import base64
import aiohttp
from models.product import Product
from config.settings import settings


class TrendyolUploader:
    BASE_URL = "https://api.trendyol.com/sapigw"

    def __init__(self):
        credentials = f"{settings.trendyol_api_key}:{settings.trendyol_api_secret}"
        self.auth = base64.b64encode(credentials.encode()).decode()
        self.supplier_id = settings.trendyol_supplier_id
        self.headers = {
            "Authorization": f"Basic {self.auth}",
            "Content-Type": "application/json",
            "User-Agent": f"{self.supplier_id} - SelfIntegration",
        }

    async def upload(self, product: Product) -> dict:
        payload = self._build_payload(product)
        async with aiohttp.ClientSession() as session:
            url = f"{self.BASE_URL}/suppliers/{self.supplier_id}/v2/products"
            async with session.post(url, json=payload, headers=self.headers) as resp:
                data = await resp.json()
                if resp.status in (200, 201, 202):
                    return {"status": "success", "batch_id": data.get("batchRequestId", ""), "message": "Trendyol'a yüklendi."}
                raise Exception(f"Trendyol API hatası {resp.status}: {data}")

    def _build_payload(self, p: Product) -> dict:
        cat_id = p.attributes.get("_category_ids", {}).get("trendyol", 0)
        return {
            "items": [{
                "barcode": p.barcode or f"PRD{hash(p.title) % 10**12:012d}",
                "title": p.title[:150],
                "productMainId": p.sku or f"SKU-{abs(hash(p.title)) % 10**8}",
                "brandId": 0,
                "categoryId": cat_id,
                "quantity": p.stock,
                "stockCode": p.sku or f"STK-{abs(hash(p.title)) % 10**8}",
                "description": p.description[:30000],
                "currencyType": p.currency,
                "listPrice": round(p.price * 1.2, 2),
                "salePrice": round(p.price, 2),
                "cargoCompanyId": 17,
                "images": [{"url": img} for img in p.images[:8]],
                "attributes": [],
            }]
        }
