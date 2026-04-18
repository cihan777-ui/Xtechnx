import aiohttp
from models.product import Product
from config.settings import settings


class N11Uploader:
    BASE_URL = "https://api.n11.com"

    def __init__(self):
        self.app_key = settings.n11_app_key
        self.app_secret = settings.n11_app_secret
        self.headers = {
            "Content-Type": "application/json",
            "appKey": self.app_key,
            "appSecret": self.app_secret,
        }

    async def upload(self, product: Product) -> dict:
        create_result = await self._create_product(product)
        return {
            "status": "success",
            "product_id": create_result.get("productId"),
            "message": "N11'e yüklendi.",
        }

    async def _create_product(self, p: Product) -> dict:
        cat_id = p.attributes.get("_category_ids", {}).get("n11", 0)
        payload = {
            "productSellerCode": p.sku or f"N11-{abs(hash(p.title)) % 10**8}",
            "title": p.title[:255],
            "description": p.description[:30000],
            "category": {"id": cat_id},
            "price": p.price,
            "currencyType": 1,
            "images": {"image": [{"url": img, "order": i+1} for i, img in enumerate(p.images[:8])]},
            "approvalStatus": 1,
            "attributes": {"attribute": []},
            "productCondition": 1,
            "preparingDay": 3,
            "discount": {"startDate": "", "endDate": "", "type": 1, "value": 0},
            "shipmentTemplate": {"name": "Standart"},
            "unitInfo": {"unitType": 0, "unitWeight": p.weight_kg or 0},
            "stockItems": {
                "stockItem": [{
                    "quantity": p.stock,
                    "sellerStockCode": p.barcode or f"BAR{abs(hash(p.title)) % 10**12}",
                    "optionPrice": p.price,
                    "attributes": {"attribute": []},
                }]
            }
        }
        async with aiohttp.ClientSession() as session:
            url = f"{self.BASE_URL}/v2/products"
            async with session.post(url, json=payload, headers=self.headers) as resp:
                data = await resp.json()
                if data.get("status") == "success" or resp.status in (200, 201):
                    return data
                raise Exception(f"N11 hatası: {data}")
