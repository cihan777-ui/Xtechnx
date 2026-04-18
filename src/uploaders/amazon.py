import time
import aiohttp
from datetime import datetime, timezone
from models.product import Product
from config.settings import settings


class AmazonUploader:
    TOKEN_URL = "https://api.amazon.com/auth/o2/token"
    SP_API_URL = "https://sellingpartnerapi-eu.amazon.com"

    def __init__(self):
        self.lwa_app_id = settings.amazon_lwa_app_id
        self.lwa_client_secret = settings.amazon_lwa_client_secret
        self.refresh_token = settings.amazon_refresh_token
        self.seller_id = settings.amazon_seller_id
        self.marketplace_id = settings.amazon_marketplace_id
        self._access_token = None
        self._token_expires = 0

    async def upload(self, product: Product) -> dict:
        token = await self._get_access_token()
        sku = product.sku or f"AMZSKU-{abs(hash(product.title)) % 10**8}"
        payload = self._build_payload(product, sku)
        headers = {
            "x-amz-access-token": token,
            "x-amz-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            url = (f"{self.SP_API_URL}/listings/2021-08-01/items/"
                   f"{self.seller_id}/{sku}?marketplaceIds={self.marketplace_id}")
            async with session.put(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                if resp.status in (200, 201, 202):
                    return {"status": "success", "sku": sku, "message": "Amazon TR'ye yüklendi."}
                raise Exception(f"Amazon API hatası {resp.status}: {data}")

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires:
            return self._access_token
        async with aiohttp.ClientSession() as session:
            async with session.post(self.TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.lwa_app_id,
                "client_secret": self.lwa_client_secret,
            }) as resp:
                data = await resp.json()
                self._access_token = data["access_token"]
                self._token_expires = time.time() + data.get("expires_in", 3600) - 60
                return self._access_token

    def _build_payload(self, p: Product, sku: str) -> dict:
        return {
            "productType": "PRODUCT",
            "attributes": {
                "item_name": [{"value": p.title[:200], "marketplace_id": self.marketplace_id}],
                "product_description": [{"value": p.description[:2000], "marketplace_id": self.marketplace_id}],
                "brand": [{"value": p.brand or "Generic", "marketplace_id": self.marketplace_id}],
                "purchasable_offer": [{
                    "marketplace_id": self.marketplace_id,
                    "currency": p.currency,
                    "our_price": [{"schedule": [{"value_with_tax": p.price}]}],
                }],
                "fulfillment_availability": [{
                    "fulfillment_channel_code": "DEFAULT",
                    "quantity": p.stock,
                    "marketplace_id": self.marketplace_id,
                }],
                "main_offer_image_locator": [
                    {"marketplace_id": self.marketplace_id, "media_location": p.images[0]}
                ] if p.images else [],
            }
        }
