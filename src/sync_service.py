"""
Fiyat & Stok Senkronizasyon Modülü
- merterelektronik.com'daki fiyat/stok değişikliklerini tespit eder
- Değişiklik varsa platformlara otomatik yansıtır
"""
import asyncio
import logging
from datetime import datetime
import database as db
from scrapers.product_scraper import ProductScraper

logger = logging.getLogger(__name__)


async def check_and_sync(item: dict, uploaders: dict) -> dict:
    """
    Tek bir kayıtlı ürünü kontrol eder.
    item: upload_history kaydı
    """
    result = {
        "barcode_orig": item["barcode_orig"],
        "title": item["title_orig"],
        "platform": item["platform"],
        "status": "no_change",
        "changes": {}
    }

    try:
        # Önbellekten veya siteden ürünü çek
        cached = db.get_cached_product(item["barcode_orig"] or "")
        if cached:
            product_dict = cached["product"]
            url = cached["url"]
        else:
            scraper = ProductScraper()
            url = await _find_url(item["barcode_orig"], scraper)
            if not url:
                result["status"] = "not_found"
                return result
            product = await scraper.scrape(url)
            product_dict = product.model_dump()
            db.cache_product(item["barcode_orig"], url, product_dict)

        current_price = product_dict.get("price", 0)
        current_stock = product_dict.get("stock", 0)

        # Orijinal fiyatla karşılaştır
        new_sale_price = round(current_price * 2, 2)
        price_changed = abs(new_sale_price - (item["price_new"] or 0)) > 0.01
        stock_changed = current_stock != (item.get("stock") or 10)

        if not price_changed and not stock_changed:
            return result

        result["changes"] = {}
        if price_changed:
            result["changes"]["price"] = {
                "old": item["price_new"],
                "new": new_sale_price
            }
        if stock_changed:
            result["changes"]["stock"] = {
                "old": item.get("stock", 10),
                "new": current_stock
            }

        # Platformda güncelle
        platform = item["platform"]
        if platform in uploaders and (price_changed or stock_changed):
            from models.product import Product
            updated_product = Product(**{**product_dict,
                "title": item["title_new"],
                "price": new_sale_price,
                "barcode": item["barcode_new"],
                "sku": item["sku_new"],
                "stock": current_stock,
            })
            await uploaders[platform].update_price_stock(updated_product)
            result["status"] = "updated"
            logger.info(f"Güncellendi: {item['title_orig']} → {platform}")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"Sync hatası {item.get('barcode_orig')}: {e}")

    return result


async def sync_all(uploaders: dict, limit: int = 100) -> list:
    """Son yüklenen ürünleri kontrol eder ve değişiklikleri senkronize eder."""
    history = db.get_history(limit=limit, status="success")

    # Benzersiz barkodları al (her platform için bir kere kontrol)
    seen_barcodes = set()
    unique_items = []
    for item in history:
        if item["barcode_orig"] not in seen_barcodes:
            seen_barcodes.add(item["barcode_orig"])
            unique_items.append(item)

    # Paralel kontrol (max 5 eş zamanlı)
    semaphore = asyncio.Semaphore(5)

    async def _limited(item):
        async with semaphore:
            return await check_and_sync(item, uploaders)

    results = await asyncio.gather(*[_limited(item) for item in unique_items])
    return list(results)


async def _find_url(barcode: str, scraper) -> str:
    """Önbellekten veya siteden URL bul."""
    cached = db.get_cached_product(barcode)
    if cached:
        return cached["url"]

    import aiohttp
    from bs4 import BeautifulSoup

    search_url = f"https://www.merterelektronik.com/arama?q={barcode}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
        "Referer": "https://www.merterelektronik.com/",
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
        try:
            import lxml; parser = "lxml"
        except ImportError:
            parser = "html.parser"
        soup = BeautifulSoup(html, parser)
        for sel in [".product-item a", ".urun-liste a", "a[href*='.html']"]:
            link = soup.select_one(sel)
            if link and link.get("href") and ".html" in link["href"]:
                href = link["href"]
                if not href.startswith("http"):
                    href = "https://www.merterelektronik.com" + href
                return href
    except Exception:
        pass
    return None
