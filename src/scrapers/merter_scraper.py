"""
merterelektronik.com - Özel Scraper
Platform: IdeaSoft tabanlı Türk e-ticaret altyapısı
Resimler: /Data/Products/ CDN yolunda
"""
import re
import json
import asyncio
import aiohttp
from typing import Optional, List
from bs4 import BeautifulSoup
from models.product import Product


BASE_URL = "https://www.merterelektronik.com"

MERTER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.merterelektronik.com/",
    "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

# merterelektronik.com ürün OLMAYAN CDN yolları
MERTER_BLOCKED = re.compile(
    r'/(logo|banner|slider|kampanya|brand|marka|kategori|footer|'
    r'header|icon|sprite|payment|cargo|guven|trust|sosyal|social|'
    r'uyelik|login|kargo|bayilik)',
    re.IGNORECASE
)

# Ürün CDN yolu işareti
MERTER_PRODUCT_IMG = re.compile(
    r'/Data/Products?/|/Uploads?/Product|/urun[-_]?resim|/productimage',
    re.IGNORECASE
)

# Küçük thumbnail sürümleri
THUMB_RE = re.compile(r'[_-](thumb|kucuk|small|mini|list|\d{2,3}x\d{2,3})', re.I)


class MerterScraper:
    """merterelektronik.com için özel scraper. IdeaSoft sitelerinde de çalışır."""

    async def scrape(self, url: str) -> Product:
        html = await self._fetch(url)
        try:
            import lxml  # noqa
            parser = "lxml"
        except ImportError:
            parser = "html.parser"
        soup = BeautifulSoup(html, parser)

        product = self._parse_jsonld(soup, url) or self._parse_html(soup, url)
        if not product:
            raise ValueError(f"merterelektronik.com ürün bilgisi alınamadı: {url}")

        product.images = self._filter_images(product.images)
        return product

    # ── HTTP ────────────────────────────────────────────────────────────────

    async def _fetch(self, url: str) -> str:
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(headers=MERTER_HEADERS, connector=connector) as session:
            # Önce anasayfayı ziyaret et (session çerezi için)
            try:
                await session.get(BASE_URL, timeout=aiohttp.ClientTimeout(total=10))
                await asyncio.sleep(0.8)
            except Exception:
                pass
            async with session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                return await resp.text(encoding="utf-8", errors="replace")

    # ── JSON-LD Parse ────────────────────────────────────────────────────────

    def _parse_jsonld(self, soup: BeautifulSoup, url: str) -> Optional[Product]:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = next((d for d in data if d.get("@type") == "Product"), None)
                if not data or data.get("@type") != "Product":
                    continue

                offers = data.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0]

                price = self._parse_price(str(offers.get("price", "0")))

                images = data.get("image", [])
                if isinstance(images, str):
                    images = [images]
                elif isinstance(images, dict):
                    images = [images.get("url", "")]

                brand = data.get("brand", {})
                brand_name = brand.get("name") if isinstance(brand, dict) else str(brand or "")

                return Product(
                    title=data.get("name", "").strip(),
                    description=self._clean(data.get("description", "")),
                    price=price,
                    currency=offers.get("priceCurrency", "TRY"),
                    stock=10 if "InStock" in offers.get("availability", "") else 0,
                    brand=brand_name or None,
                    barcode=data.get("gtin13") or data.get("gtin8") or data.get("gtin"),
                    sku=data.get("sku") or data.get("mpn"),
                    category=self._get_breadcrumb(soup),
                    images=[i for i in images if i and i.startswith("http")],
                    source_url=url,
                )
            except Exception:
                continue
        return None

    # ── HTML Parse ───────────────────────────────────────────────────────────

    def _parse_html(self, soup: BeautifulSoup, url: str) -> Optional[Product]:
        """
        IdeaSoft / merterelektronik.com HTML yapısı:
        - Başlık:     h1[itemprop="name"]  /  h1.product-name
        - Fiyat:      [itemprop="price"]  /  span.price
        - SKU:        [itemprop="sku"]  /  .product-code
        - Marka:      [itemprop="brand"]
        - Açıklama:   #productDescription  /  .product-description
        - Resimler:   #productImages img  /  [data-zoom-image]
        - Breadcrumb: .breadcrumb li
        """
        title = (
            self._text(soup, 'h1[itemprop="name"]') or
            self._text(soup, "h1.product-name") or
            self._text(soup, ".urun-adi h1") or
            self._text(soup, "h1")
        )
        if not title:
            return None

        price_raw = (
            self._attr(soup, '[itemprop="price"]', "content") or
            self._text(soup, "span.price") or
            self._text(soup, ".fiyat span") or
            self._text(soup, ".product-price") or
            self._find_price_text(soup) or "0"
        )

        sku = (
            self._attr(soup, '[itemprop="sku"]', "content") or
            self._text(soup, ".product-code span") or
            self._text(soup, ".stok-kodu") or
            self._sku_from_url(url)
        )

        brand = (
            self._attr(soup, '[itemprop="brand"]', "content") or
            self._text(soup, '[itemprop="brand"] span') or
            self._text(soup, ".product-brand a") or
            self._text(soup, ".marka a")
        )

        desc = (
            self._text(soup, '[itemprop="description"]') or
            self._text(soup, "#productDescription") or
            self._text(soup, ".product-description") or
            self._text(soup, ".urun-aciklama") or ""
        )

        stock_text = self._text(soup, '[itemprop="availability"]') or ""
        stock = 0 if any(k in stock_text.lower() for k in ["tükendi", "stokta yok", "OutOfStock"]) else 10

        return Product(
            title=title.strip(),
            description=self._clean(desc),
            price=self._parse_price(price_raw),
            currency="TRY",
            stock=stock,
            brand=brand,
            barcode=self._attr(soup, '[itemprop="gtin13"]', "content"),
            sku=sku,
            category=self._get_breadcrumb(soup),
            images=self._collect_images(soup),
            source_url=url,
        )

    # ── Resim Toplama ────────────────────────────────────────────────────────

    def _collect_images(self, soup: BeautifulSoup) -> List[str]:
        seen, imgs = set(), []

        # 1. Ürün galeri alanı — zoom versiyonunu tercih et
        for sel in [
            "#productImages img", "#urunGaleri img",
            ".product-images img", ".product-gallery img",
            ".product-image-wrapper img", ".owl-carousel img",
        ]:
            for tag in soup.select(sel):
                src = (
                    tag.get("data-zoom-image") or
                    tag.get("data-large") or
                    tag.get("data-src") or
                    tag.get("src") or ""
                )
                src = self._normalize(src)
                if src and src not in seen:
                    seen.add(src)
                    imgs.append(src)

        # 2. /Data/Products/ CDN yolundaki tüm img'ler
        if not imgs:
            for tag in soup.find_all("img"):
                src = self._normalize(tag.get("data-src") or tag.get("src") or "")
                if src and MERTER_PRODUCT_IMG.search(src) and src not in seen:
                    seen.add(src)
                    imgs.append(src)

        # 3. og:image fallback
        if not imgs:
            for meta in soup.find_all("meta", property="og:image"):
                src = meta.get("content", "")
                if src and src not in seen:
                    seen.add(src)
                    imgs.append(src)

        return imgs

    def _filter_images(self, images: List[str]) -> List[str]:
        result, seen = [], set()
        for url in images:
            if not url:
                continue
            url = self._normalize(url)
            clean = url.split("?")[0]
            if clean in seen:
                continue
            seen.add(clean)
            # merterelektronik.com'a özel engellenen yollar
            if MERTER_BLOCKED.search(clean):
                continue
            # Resim uzantısı zorunlu
            if not re.search(r'\.(jpg|jpeg|png|webp)', clean, re.I):
                continue
            # Thumbnail ise büyük sürüme geç
            if THUMB_RE.search(clean):
                big = THUMB_RE.sub("", clean)
                if big != clean:
                    url = big
            result.append(url)
            if len(result) >= 8:
                break
        return result

    # ── Breadcrumb ───────────────────────────────────────────────────────────

    def _get_breadcrumb(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in [
            ".breadcrumb li:nth-last-child(2)",
            ".breadcrumb li:last-child",
            '[typeof="BreadcrumbList"] [property="name"]:last-of-type',
        ]:
            text = self._text(soup, sel)
            if text and len(text) > 1:
                return text.strip()

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = next((d for d in data if d.get("@type") == "BreadcrumbList"), None)
                if data and data.get("@type") == "BreadcrumbList":
                    items = data.get("itemListElement", [])
                    if len(items) >= 2:
                        return items[-2].get("name")
                    elif items:
                        return items[-1].get("name")
            except Exception:
                continue
        return None

    # ── Yardımcılar ──────────────────────────────────────────────────────────

    def _text(self, soup, sel) -> Optional[str]:
        el = soup.select_one(sel)
        return el.get_text(strip=True) if el else None

    def _attr(self, soup, sel, attr) -> Optional[str]:
        el = soup.select_one(sel)
        return el.get(attr, "").strip() if el else None

    def _normalize(self, src: str) -> str:
        if not src:
            return ""
        src = src.strip()
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            return BASE_URL + src
        if not src.startswith("http"):
            return BASE_URL + "/" + src
        return src

    def _sku_from_url(self, url: str) -> Optional[str]:
        m = re.search(r'-([A-Z0-9]{4,20})\.html', url, re.I)
        return m.group(1).upper() if m else None

    def _find_price_text(self, soup: BeautifulSoup) -> Optional[str]:
        for pat in [r'\d{1,6}[.,]\d{2}\s*(?:TL|₺)', r'(?:₺|TL)\s*\d{1,6}[.,]\d{2}']:
            m = re.search(pat, soup.get_text())
            if m:
                return m.group(0)
        return None

    def _parse_price(self, raw: str) -> float:
        if not raw:
            return 0.0
        cleaned = re.sub(r"[^\d,.]", "", raw).strip()
        if "," in cleaned and "." in cleaned:
            if cleaned.rindex(",") > cleaned.rindex("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()[:5000]
