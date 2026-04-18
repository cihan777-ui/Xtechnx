"""
Genel amaçlı web scraper.
merterelektronik.com → MerterScraper'a yönlendirir.
"""
import re
import json
import aiohttp
from typing import Optional, List
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from models.product import Product


CATEGORY_MAP = [
    (["telefon", "iphone", "samsung", "smartphone"], "Cep Telefonu", 1081, "CEP_TELEFONU", 1000603),
    (["laptop", "notebook", "bilgisayar", "macbook"], "Laptop & Notebook", 2264, "NOTEBOOK", 1000308),
    (["tablet", "ipad"], "Tablet", 1080, "TABLET", 1000604),
    (["kulaklik", "kulaklık", "airpods", "headphone"], "Kulaklık", 3489, "KULAKLIK", 1001150),
    (["televizyon", "smart tv", "oled", "qled"], "Televizyon", 2057, "TELEVIZYON", 1000251),
    (["kamera", "fotoğraf makinesi", "canon", "nikon"], "Fotoğraf Makinesi", 2072, "FOTOGRAF_MAKINESI", 1000259),
    (["sarj", "şarj", "powerbank", "adaptör", "adaptor", "kablo", "usb"], "Şarj & Kablo", 3302, "SARJ_CIHAZI", 1001066),
    (["playstation", "xbox", "nintendo", "ps4", "ps5"], "Oyun Konsolu", 2076, "OYUN_KONSOLU", 1000325),
    (["uydu", "alici", "alıcı", "receiver", "set top", "settop"], "Uydu Alıcı", 2057, "UYDU_ALICI", 1000251),
    (["modem", "router", "switch", "network", "ağ", "wifi"], "Ağ Ürünleri", 3302, "MODEM", 1001066),
    (["ses sistemi", "hoparlor", "hoparlör", "amfi", "mikrofon", "ses"], "Ses Sistemleri", 3489, "SES_SISTEMI", 1001150),
    (["güneş", "solar", "panel", "inverter", "akü"], "Solar Sistemler", 2062, "SOLAR", 1000503),
    (["hard disk", "harddisk", "ssd", "hdd"], "Depolama", 2264, "HARDDISK", 1000308),
    (["t-shirt", "tisort", "tişört", "gömlek"], "Üst Giyim", 1040, "TISORT", 1000101),
    (["pantolon", "jean", "kot"], "Alt Giyim", 1039, "PANTOLON", 1000102),
    (["ayakkabı", "sneaker", "bot"], "Ayakkabı", 1036, "AYAKKABI", 1000105),
    (["çamaşır", "bulaşık", "buzdolabı", "fırın", "ocak"], "Büyük Ev Aletleri", 2058, "BUYUK_EV_ALETLERI", 1000201),
    (["süpürge", "kahve", "blender", "mikser", "airfryer"], "Küçük Ev Aletleri", 2059, "KUCUK_EV_ALETLERI", 1000202),
    (["kitap", "roman", "dergi"], "Kitap", 2066, "KITAP", 1000801),
    (["oyuncak", "lego", "puzzle"], "Oyuncak", 2067, "OYUNCAK", 1000901),
]

BLOCKED_IMAGE_PATTERNS = [
    r'logo', r'banner', r'icon', r'avatar', r'profile', r'sprite',
    r'placeholder', r'blank', r'spacer', r'pixel', r'tracking',
    r'analytics', r'badge', r'button', r'arrow', r'star', r'rating',
    r'flag', r'favicon', r'\.gif$', r'1x1', r'loading',
    r'default[-_]image', r'no[-_]?image', r'noimage', r'empty',
]
NON_PRODUCT_PATHS = [
    r'/brand/', r'/seller/', r'/category/', r'/cms/', r'/static/',
    r'/assets/', r'/icons/', r'/logos/', r'/banners/', r'/campaigns/',
    r'/sliders/', r'/payment/', r'/cargo/', r'/trust/',
]
MIN_IMAGE_DIMENSION = 100


class ProductScraper:

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }

    async def scrape(self, url: str) -> Product:
        # merterelektronik.com → özel scraper
        if "merterelektronik.com" in url:
            from scrapers.merter_scraper import MerterScraper
            scraper = MerterScraper()
            product = await scraper.scrape(url)
            if not product.category:
                product.category = self._guess_category(product.title, product.description)
            return product

        async with aiohttp.ClientSession(headers=self.HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                html = await resp.text()

        try:
            import lxml  # noqa
            parser = "lxml"
        except ImportError:
            parser = "html.parser"

        soup = BeautifulSoup(html, parser)
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        product = (
            self._try_jsonld(soup, url, base_url) or
            self._try_opengraph(soup, url, base_url) or
            self._try_site_specific(soup, url, base_url)
        )

        if not product:
            raise ValueError(f"Ürün bilgileri çekilemedi: {url}")

        product.images = self._filter_images(product.images, base_url)

        if not product.category:
            product.category = self._guess_category(product.title, product.description)

        return product

    def _try_jsonld(self, soup, url, base_url):
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
                price = float(str(offers.get("price", 0)).replace(",", "."))
                images = data.get("image", [])
                if isinstance(images, str):
                    images = [images]
                elif isinstance(images, dict):
                    images = [images.get("url", "")]
                category = self._extract_breadcrumb(soup)
                brand = data.get("brand", {})
                return Product(
                    title=data.get("name", "").strip(),
                    description=self._clean(data.get("description", "")),
                    price=price,
                    currency=offers.get("priceCurrency", "TRY"),
                    stock=10 if "InStock" in offers.get("availability", "") else 0,
                    brand=brand.get("name") if isinstance(brand, dict) else brand,
                    barcode=data.get("gtin13") or data.get("gtin"),
                    sku=data.get("sku"),
                    category=category,
                    images=[i for i in images if i],
                    source_url=url,
                )
            except Exception:
                continue
        return None

    def _try_opengraph(self, soup, url, base_url):
        def og(prop):
            tag = soup.find("meta", property=f"og:{prop}")
            return tag["content"] if tag and tag.get("content") else None
        title = og("title") or (soup.title.string if soup.title else None)
        if not title:
            return None
        price_str = None
        for tag in soup.find_all("meta"):
            if tag.get("property") in ("product:price:amount", "og:price:amount"):
                price_str = tag.get("content")
        if not price_str:
            price_str = self._find_price(soup)
        images = [t["content"] for t in soup.find_all("meta", property="og:image") if t.get("content")]
        return Product(
            title=title.strip(),
            description=self._clean(og("description") or ""),
            price=self._parse_price(price_str or "0"),
            images=images,
            category=self._extract_breadcrumb(soup),
            source_url=url,
        )

    def _try_site_specific(self, soup, url, base_url):
        if "trendyol.com" in url:
            title = self._text(soup, "h1.pr-new-br span") or self._text(soup, "h1")
            price = self._parse_price(self._text(soup, ".prc-dsc") or "0")
            imgs = self._collect_images(soup, [".base-product-image img"], base_url)
            return Product(title=title or "", description=self._text(soup, ".product-description-text") or "",
                           price=price, brand=self._text(soup, ".pr-new-br a"),
                           category=self._text(soup, ".breadcrumb-item:last-child"),
                           images=imgs, source_url=url)
        elif "hepsiburada.com" in url:
            title = self._text(soup, "h1.product-name") or self._text(soup, "h1")
            price = self._parse_price(self._text(soup, "span[data-bind*='salesPrice']") or self._text(soup, ".price-value") or "0")
            img_selectors = [
                "#product-detail-app img[src*='/productimages/']",
                ".product-detail-slider img",
                "[class*='product-image'] img",
            ]
            imgs = self._collect_images(soup, img_selectors, base_url)
            if not imgs:
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "")
                        if isinstance(data, list):
                            data = next((d for d in data if d.get("@type") == "Product"), None)
                        if data and data.get("@type") == "Product":
                            raw = data.get("image", [])
                            imgs = [raw] if isinstance(raw, str) else [i for i in raw if i]
                            break
                    except Exception:
                        continue
            return Product(title=title or "", description=self._text(soup, "#productDescriptionContent") or "",
                           price=price, brand=self._text(soup, ".brand-name a"),
                           category=self._extract_breadcrumb(soup), images=imgs, source_url=url)
        elif "n11.com" in url:
            title = self._text(soup, ".proName h1") or self._text(soup, "h1")
            price = self._parse_price(self._text(soup, ".newPrice ins") or "0")
            imgs = self._collect_images(soup, [".bigImage", ".prd-img img"], base_url)
            return Product(title=title or "", description=self._text(soup, "#productDetail") or "",
                           price=price, category=self._extract_breadcrumb(soup), images=imgs, source_url=url)
        elif "amazon.com.tr" in url:
            title = self._text(soup, "#productTitle") or self._text(soup, "h1")
            price = self._parse_price(self._text(soup, ".a-price .a-offscreen") or "0")
            main_img = soup.select_one("#imgBlkFront, #landingImage")
            imgs = [main_img["src"]] if main_img and main_img.get("src") else []
            return Product(title=title or "", description=self._text(soup, "#productDescription") or "",
                           price=price, category=self._extract_breadcrumb(soup), images=imgs, source_url=url)
        return self._scrape_generic(soup, url, base_url)

    def _scrape_generic(self, soup, url, base_url):
        title = (self._text(soup, "h1") or "").strip()
        imgs = self._collect_images(soup, ["img"], base_url)
        desc = self._text(soup, "article") or self._text(soup, ".description") or ""
        return Product(title=title, description=self._clean(desc),
                       price=self._parse_price(self._find_price(soup) or "0"),
                       category=self._extract_breadcrumb(soup), images=imgs, source_url=url)

    def _collect_images(self, soup, selectors, base_url):
        seen, imgs = set(), []
        for sel in selectors:
            for tag in soup.select(sel):
                src = (tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src") or tag.get("data-original") or "")
                if src and src not in seen:
                    seen.add(src)
                    imgs.append(src)
        return imgs

    def _filter_images(self, images, base_url):
        blocked_re = re.compile("|".join(BLOCKED_IMAGE_PATTERNS), re.IGNORECASE)
        non_product_re = re.compile("|".join(NON_PRODUCT_PATHS), re.IGNORECASE)
        small_re = re.compile(r'[_\-x](\d+)x(\d+)', re.IGNORECASE)
        seen, result = set(), []
        for url in images:
            if not url or not isinstance(url, str):
                continue
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = base_url + url
            if not url.startswith("http"):
                continue
            clean = url.split("?")[0]
            if clean in seen:
                continue
            seen.add(clean)
            if blocked_re.search(clean) or non_product_re.search(clean):
                continue
            m = small_re.search(clean)
            if m and (int(m.group(1)) < MIN_IMAGE_DIMENSION or int(m.group(2)) < MIN_IMAGE_DIMENSION):
                continue
            if not re.search(r'\.(jpg|jpeg|png|webp)', clean, re.I) and \
               not re.search(r'/(image|img|media|photo|product|productimages)', clean, re.I):
                continue
            result.append(url)
            if len(result) >= 8:
                break
        return result

    def _extract_breadcrumb(self, soup):
        for sel in [
            "nav.breadcrumb li:last-child", ".breadcrumb-item:last-child",
            "[aria-label='breadcrumb'] li:last-child", ".breadcrumbs span:last-child",
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
                    if items:
                        return items[-1].get("name")
            except Exception:
                continue
        return None

    def _guess_category(self, title, description):
        text = (title + " " + description).lower()
        for keywords, category_name, *_ in CATEGORY_MAP:
            for kw in keywords:
                if kw in text:
                    return category_name
        return "Elektronik"

    def get_platform_category_ids(self, category_name):
        for _, name, trendyol_id, hb_id, n11_id in CATEGORY_MAP:
            if name == category_name:
                return {"trendyol": trendyol_id, "hepsiburada": hb_id, "n11": n11_id}
        return {"trendyol": 3302, "hepsiburada": "SARJ_CIHAZI", "n11": 1001066}

    def _text(self, soup, selector):
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else None

    def _clean(self, text):
        return re.sub(r"\s+", " ", text).strip()[:5000]

    def _find_price(self, soup):
        for pat in [r'\d{1,6}[.,]\d{2}\s*(?:TL|₺|TRY)', r'(?:TL|₺)\s*\d{1,6}[.,]\d{2}']:
            m = re.search(pat, soup.get_text())
            if m:
                return m.group(0)
        return None

    def _parse_price(self, raw):
        if not raw:
            return 0.0
        cleaned = re.sub(r"[^\d,.]", "", raw).replace(",", ".")
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
