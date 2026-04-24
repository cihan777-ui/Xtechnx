import re
import aiohttp
from models.product import Product
from config.settings import settings
from category_mapper import get_hepsiburada_category

ALLOWED_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
HB_MAX_IMAGES = 5
BLOCKED = re.compile(
    r'logo|banner|icon|brand|seller|category|cms|static|assets|'
    r'campaign|slider|payment|cargo|trust|badge', re.IGNORECASE
)


def _resolve_category(p: Product) -> str:
    manual = p.attributes.get("_category_ids", {}).get("hepsiburada", "")
    if manual:
        return str(manual)
    try:
        import database as db
        db_mappings = {
            m["source_category"]: m["hepsiburada_id"]
            for m in db.get_category_mappings()
            if m.get("hepsiburada_id")
        }
    except Exception:
        db_mappings = {}
    return get_hepsiburada_category(p.category or "", db_mappings)


def _stable_id(text: str, length: int) -> str:
    """Metinden deterministik sayısal ID üretir."""
    import hashlib
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return str(h % (10 ** length)).zfill(length)


def _build_sku(p: Product) -> str:
    return p.sku or f"HB-{_stable_id(p.title, 8)}"


def _build_hb_sku(p: Product) -> str:
    raw = p.barcode or ""
    digits = "".join(c for c in raw if c.isdigit())
    if digits:
        return digits[:13].zfill(8)
    return f"HB{_stable_id(p.sku or p.title, 10)}"


class HepsiburadaUploader:
    BASE_URL = "https://listing-external.hepsiburada.com"
    PRODUCT_URL = "https://mpop.hepsiburada.com"

    def __init__(self):
        self.username = settings.hepsiburada_username
        self.password = settings.hepsiburada_password
        self.merchant_id = settings.hepsiburada_merchant_id
        self.developer_username = settings.hepsiburada_developer_username

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "User-Agent": self.developer_username,
        }

    async def upload(self, product: Product) -> dict:
        auth = aiohttp.BasicAuth(self.username, self.password)
        create_result = await self._create_product(product, auth)
        tracking_id = create_result.get("trackingId", "")

        inventory_result = await self._upload_inventory(product, auth)
        inv_tracking = inventory_result.get("trackingId", "")

        return {
            "status": "pending",
            "tracking_id": inv_tracking or tracking_id,
            "message": f"Hepsiburada'ya gönderildi. TrackingID: {inv_tracking or tracking_id}",
        }

    async def _create_product(self, product: Product, auth) -> dict:
        clean_images = self._validate_images(product.images)
        cat_id = _resolve_category(product)
        sku = _build_sku(product)
        payload = {
            "skuList": [{
                "sku": sku,
                "name": product.title[:500],
                "description": product.description[:30000],
                "categoryId": cat_id,
                "tax": 20,
                "brand": "Diğer",
                "images": clean_images,
                "attributes": [],
            }]
        }
        async with aiohttp.ClientSession(auth=auth) as session:
            url = f"{self.PRODUCT_URL}/product/api/products/import"
            async with session.post(
                url, json=payload,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201, 202):
                    raise Exception(f"Hepsiburada ürün oluşturma hatası {resp.status}: {data}")
                return data

    async def _upload_inventory(self, product: Product, auth) -> dict:
        sku = _build_sku(product)
        hb_sku = _build_hb_sku(product)
        payload = {
            "merchantId": self.merchant_id,
            "inventories": [{
                "hbSku": hb_sku,
                "merchantSku": sku,
                "price": round(product.price, 2),
                "availableStock": product.stock,
                "productCondition": 1,
                "listingAllowed": True,
            }]
        }
        async with aiohttp.ClientSession(auth=auth) as session:
            url = f"{self.BASE_URL}/listings/merchantid/{self.merchant_id}/inventory/import"
            async with session.post(
                url, json=payload,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201, 202):
                    raise Exception(f"Hepsiburada stok hatası {resp.status}: {data}")
                return data

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
