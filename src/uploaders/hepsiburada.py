import re
import io
import json
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

_SIT_MPOP  = "https://mpop-sit.hepsiburada.com"
_LIVE_MPOP = "https://mpop.hepsiburada.com"
_SIT_LIST  = "https://listing-external-sit.hepsiburada.com"
_LIVE_LIST = "https://listing-external.hepsiburada.com"
_SIT_OMS   = "https://oms-external-sit.hepsiburada.com"
_LIVE_OMS  = "https://oms-external.hepsiburada.com"


def _base_urls():
    if settings.hepsiburada_env == "test":
        return _SIT_MPOP, _SIT_LIST, _SIT_OMS
    return _LIVE_MPOP, _LIVE_LIST, _LIVE_OMS


def _resolve_category(p: Product) -> int:
    manual = p.attributes.get("_category_ids", {}).get("hepsiburada", "")
    if manual:
        return int(manual)
    try:
        import database as db
        db_mappings = {
            m["source_category"]: m["hepsiburada_id"]
            for m in db.get_category_mappings()
            if m.get("hepsiburada_id")
        }
    except Exception:
        db_mappings = {}
    cat_str = get_hepsiburada_category(p.category or "", db_mappings)
    try:
        return int(cat_str)
    except (ValueError, TypeError):
        return 60003862  # fallback: genel kategori


def _stable_id(text: str, length: int) -> str:
    import hashlib
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return str(h % (10 ** length)).zfill(length)


def _build_sku(p: Product) -> str:
    return p.sku or f"HB-{_stable_id(p.title, 8)}"


class HepsiburadaUploader:

    def __init__(self):
        self.username        = settings.hepsiburada_username
        self.password        = settings.hepsiburada_password
        self.merchant_id     = settings.hepsiburada_merchant_id
        self.developer_username = settings.hepsiburada_developer_username

    @property
    def PRODUCT_URL(self):
        return _base_urls()[0]

    @property
    def BASE_URL(self):
        return _base_urls()[1]

    @property
    def OMS_URL(self):
        return _base_urls()[2]

    def _auth(self):
        return aiohttp.BasicAuth(self.username, self.password)

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "User-Agent": self.developer_username,
        }

    def _base_headers(self) -> dict:
        return {"User-Agent": self.developer_username}

    async def upload(self, product: Product) -> dict:
        auth = self._auth()
        create_result = await self._create_product(product, auth)
        tracking_id = create_result.get("trackingId", "")

        inv_result = await self._upload_inventory(product, auth)
        price_id = inv_result.get("price_upload_id", "")
        stock_id = inv_result.get("stock_upload_id", "")

        return {
            "status": "pending",
            "tracking_id": tracking_id,
            "message": (
                f"Hepsiburada'ya gonderildi. "
                f"TrackingID: {tracking_id}  "
                f"PriceUpload: {price_id}  StockUpload: {stock_id}"
            ),
        }

    async def _create_product(self, product: Product, auth) -> dict:
        clean_images = self._validate_images(product.images)
        cat_id = _resolve_category(product)
        sku = _build_sku(product)

        # Fiyati Turkce formatinda gonder (virgul ondalik ayiraci)
        price_str = f"{product.price:.2f}".replace(".", ",")

        attrs = {
            "merchantSku":    sku,
            "UrunAdi":        product.title[:500],
            "UrunAciklamasi": product.description[:5000] if product.description else product.title[:500],
            "Barcode":        product.barcode or sku,
            "Marka":          "Diger",
            "GarantiSuresi":  "24",
            "tax_vat_rate":   "20",
            "kg":             "1",
            "price":          price_str,
            "stock":          str(product.stock),
        }

        # Gorselleri Image1, Image2, ... olarak ekle
        for i, url in enumerate(clean_images[:HB_MAX_IMAGES], start=1):
            attrs[f"Image{i}"] = url

        payload = [{"categoryId": cat_id, "merchant": self.merchant_id, "attributes": attrs}]
        json_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        form = aiohttp.FormData()
        form.add_field("file", io.BytesIO(json_bytes),
                       filename="products.json", content_type="application/json")

        async with aiohttp.ClientSession(auth=auth) as session:
            url = f"{self.PRODUCT_URL}/product/api/products/import"
            async with session.post(
                url, data=form,
                headers=self._base_headers(),
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201, 202):
                    raise Exception(f"HB urun olusturma hatasi {resp.status}: {data}")
                tracking = data.get("trackingId") or data.get("data", {}).get("trackingId", "")
                return {"trackingId": tracking, "raw": data}

    async def _upload_inventory(self, product: Product, auth) -> dict:
        sku = _build_sku(product)

        # Listeleme stok durumu - oncelikle mevcut urun SKU'larini bul
        hb_sku = await self._find_hb_sku(sku, auth)
        if not hb_sku:
            return {"price_upload_id": "", "stock_upload_id": ""}

        price_payload = [{
            "hepsiburadaSku": hb_sku,
            "merchantSku":    sku,
            "price":          round(product.price, 2),
        }]
        stock_payload = [{
            "hepsiburadaSku":  hb_sku,
            "merchantSku":     sku,
            "availableStock":  product.stock,
        }]

        result = {}
        async with aiohttp.ClientSession(auth=auth) as session:
            for name, payload, path in [
                ("price", price_payload, "price-uploads"),
                ("stock", stock_payload, "stock-uploads"),
            ]:
                url = f"{self.BASE_URL}/listings/merchantid/{self.merchant_id}/{path}"
                async with session.post(
                    url, json=payload,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status not in (200, 201, 202):
                        raise Exception(f"HB {name} upload hatasi {resp.status}: {data}")
                    result[f"{name}_upload_id"] = data.get("id", "")
        return result

    async def _find_hb_sku(self, merchant_sku: str, auth) -> str:
        """Merchant SKU'ya karsilik gelen HepsiburadaSku'yu bulur."""
        async with aiohttp.ClientSession(auth=auth) as session:
            url = f"{self.BASE_URL}/listings/merchantid/{self.merchant_id}?limit=100&offset=0"
            async with session.get(
                url, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json(content_type=None)
                items = data.get("listings", data) if isinstance(data, dict) else data
                for item in items:
                    if item.get("merchantSku") == merchant_sku:
                        return item.get("hepsiburadaSku", "")
        return ""

    async def list_orders(self, limit: int = 10) -> dict:
        async with aiohttp.ClientSession(auth=self._auth()) as session:
            url = f"{self.OMS_URL}/orders/merchantid/{self.merchant_id}?limit={limit}&offset=0"
            async with session.get(
                url, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201):
                    raise Exception(f"Siparis listeleme hatasi {resp.status}: {data}")
                return data

    async def list_packages(self, limit: int = 10) -> list:
        async with aiohttp.ClientSession(auth=self._auth()) as session:
            url = f"{self.OMS_URL}/packages/merchantid/{self.merchant_id}?limit={limit}&offset=0"
            async with session.get(
                url, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                raw = await resp.text()
                if resp.status not in (200, 201):
                    raise Exception(f"Paket listeleme hatasi {resp.status}: {raw}")
                data = json.loads(raw) if raw.strip() else []
                return data if isinstance(data, list) else data.get("data", [])

    async def list_packable_orders(self, limit: int = 50) -> list:
        """Paketlenmeyi bekleyen siparisleri dondurur (GET /orders/merchantid/{mid}/pack)."""
        async with aiohttp.ClientSession(auth=self._auth()) as session:
            url = f"{self.OMS_URL}/orders/merchantid/{self.merchant_id}/pack?limit={limit}&offset=0"
            async with session.get(
                url, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                raw = await resp.text()
                if resp.status not in (200, 201):
                    raise Exception(f"Paketlenecek siparis hatasi {resp.status}: {raw}")
                data = json.loads(raw) if raw.strip() else {}
                return data.get("items", []) if isinstance(data, dict) else data

    async def create_package(self, line_items: list) -> dict:
        """Paketlenecek siparis itemlarindan paket olusturur.
        line_items: [{"id": lineItemId, "quantity": qty}, ...]
        """
        payload = {"lineItems": line_items}
        async with aiohttp.ClientSession(auth=self._auth()) as session:
            url = f"{self.OMS_URL}/packages/merchantid/{self.merchant_id}"
            async with session.post(
                url, json=payload,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                raw = await resp.text()
                if resp.status not in (200, 201, 202):
                    raise Exception(f"Paket olusturma hatasi {resp.status}: {raw}")
                return json.loads(raw) if raw.strip() else {}

    async def pack_order(self, package_id: str, line_items: list) -> dict:
        payload = {"lines": line_items}
        async with aiohttp.ClientSession(auth=self._auth()) as session:
            url = f"{self.OMS_URL}/packages/{package_id}/items/pack"
            async with session.post(
                url, json=payload,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status not in (200, 201, 202):
                    raise Exception(f"Paketleme hatasi {resp.status}: {data}")
                return data

    async def get_tracking_status(self, tracking_id: str) -> dict:
        async with aiohttp.ClientSession(auth=self._auth()) as session:
            url = f"{self.PRODUCT_URL}/product/api/products/status/{tracking_id}"
            async with session.get(
                url, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json(content_type=None)
                return {"http_status": resp.status, "data": data}

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
