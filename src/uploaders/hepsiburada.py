import re
import aiohttp
from models.product import Product
from config.settings import settings

ALLOWED_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
HB_MAX_IMAGES = 5
BLOCKED = re.compile(
    r'logo|banner|icon|brand|seller|category|cms|static|assets|'
    r'campaign|slider|payment|cargo|trust|badge', re.IGNORECASE
)


class HepsiburadaUploader:
    BASE_URL = "https://listing-external.hepsiburada.com"
    PRODUCT_URL = "https://mpop.hepsiburada.com"

    def __init__(self):
        self.username = settings.hepsiburada_username
        self.password = settings.hepsiburada_password
        self.merchant_id = settings.hepsiburada_merchant_id

    async def upload(self, product: Product) -> dict:
        auth = aiohttp.BasicAuth(self.username, self.password)
        create_result = await self._create_product(product, auth)
        inventory_result = await self._upload_inventory(product, auth)
        return {
            "status": "success",
            "tracking_id": inventory_result.get("trackingId", ""),
            "message": "Hepsiburada'ya yüklendi.",
        }

    async def _create_product(self, product: Product, auth) -> dict:
        clean_images = self._validate_images(product.images)
        cat_id = product.attributes.get("_category_ids", {}).get("hepsiburada", "")
        payload = {
            "skuList": [{
                "sku": product.sku or f"MSKU-{abs(hash(product.title)) % 10**8}",
                "name": product.title[:500],
                "description": product.description[:30000],
                "categoryId": cat_id,
                "tax": 18,
                "brand": product.brand or "Diğer",
                "images": clean_images,
                "attributes": [],
            }]
        }
        async with aiohttp.ClientSession(auth=auth) as session:
            url = f"{self.PRODUCT_URL}/product/api/products/import"
            async with session.post(url, json=payload, headers={"Content-Type": "application/json"}) as resp:
                try:
                    return await resp.json()
                except Exception:
                    return {"status": resp.status}

    async def _upload_inventory(self, product: Product, auth) -> dict:
        payload = {
            "merchantId": self.merchant_id,
            "inventories": [{
                "hbSku": product.barcode or f"HB{abs(hash(product.title)) % 10**10}",
                "merchantSku": product.sku or f"MSKU-{abs(hash(product.title)) % 10**8}",
                "price": product.price,
                "availableStock": product.stock,
                "productCondition": 1,
                "listingAllowed": True,
            }]
        }
        async with aiohttp.ClientSession(auth=auth) as session:
            url = f"{self.BASE_URL}/listings/merchantid/{self.merchant_id}/inventory/import"
            async with session.post(url, json=payload, headers={"Content-Type": "application/json"}) as resp:
                data = await resp.json()
                if resp.status in (200, 201, 202):
                    return data
                raise Exception(f"Hepsiburada stok hatası {resp.status}: {data}")

    def _validate_images(self, images: list) -> list:
        result = []
        for img in images:
            if not img or not img.startswith("http"):
                continue
            clean = img.split("?")[0].lower()
            if BLOCKED.search(clean):
                continue
            if not any(clean.endswith(ext) for ext in ALLOWED_IMG_EXT):
                if not re.search(r'/(productimages|image|img|media|photo)', clean):
                    continue
            result.append(img)
            if len(result) >= HB_MAX_IMAGES:
                break
        return result
