"""
Hepsiburada SIT (Test Ortami) Entegrasyon Testi
Calistir: python hepsiburada_sit_test.py
Sonuclar: hepsiburada_sit_sonuclar.txt
"""

import asyncio
import aiohttp
import json
import sys
import os
import io
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MERCHANT_ID    = os.getenv("HEPSIBURADA_MERCHANT_ID", "")
USERNAME       = os.getenv("HEPSIBURADA_USERNAME", "")
PASSWORD       = os.getenv("HEPSIBURADA_PASSWORD", "")
DEVELOPER_USER = os.getenv("HEPSIBURADA_DEVELOPER_USERNAME", "")

MPOP_BASE  = "https://mpop-sit.hepsiburada.com"
LIST_BASE  = "https://listing-external-sit.hepsiburada.com"
OMS_BASE   = "https://oms-external-sit.hepsiburada.com"

LOG = []


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.append(line)


def auth():
    return aiohttp.BasicAuth(USERNAME, PASSWORD)


def json_headers():
    return {
        "Content-Type": "application/json",
        "User-Agent": DEVELOPER_USER,
    }


def base_headers():
    return {"User-Agent": DEVELOPER_USER}


# -------------------------------------------------------
# TEST 1: Katalog - Urun Gonderi (multipart/form-data)
# -------------------------------------------------------
async def test1_urun_gonder(session: aiohttp.ClientSession) -> str:
    log("=" * 55)
    log("TEST 1: Katalog - Urun Gonderi")
    log("=" * 55)

    product_data = [
        {
            "categoryId": 60003862,
            "merchant": MERCHANT_ID,
            "attributes": {
                "merchantSku":       "XTECHNX-SIT-TEST-001",
                "UrunAdi":           "Xtechnx Entegrasyon Test Urunu",
                "UrunAciklamasi":    "Hepsiburada SIT entegrasyon testi icin gonderilen ornek urun.",
                "Barcode":           "XTECHNXTEST001",
                "Marka":             "Xtechnx",
                "GarantiSuresi":     "24",
                "tax_vat_rate":      "1",
                "kg":                "1",
                "Image1":            "https://via.placeholder.com/600x600.jpg",
                "price":             "399,90",
                "stock":             "5",
            }
        }
    ]

    json_bytes = json.dumps(product_data, ensure_ascii=False).encode("utf-8")
    url = f"{MPOP_BASE}/product/api/products/import"
    log(f"POST {url}  (multipart/form-data)")

    try:
        form = aiohttp.FormData()
        form.add_field("file", io.BytesIO(json_bytes),
                       filename="products.json", content_type="application/json")

        async with session.post(
            url, data=form,
            headers=base_headers(),
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status}")
            log(f"Yanit: {raw[:500]}")
            try:
                data = json.loads(raw)
            except Exception:
                data = {}

            tracking_id = (
                data.get("trackingId")
                or data.get("data", {}).get("trackingId", "")
            )
            if tracking_id:
                log(f"[OK] trackingId: {tracking_id}")
            else:
                log("[!] trackingId alinamadi - yaniti kontrol edin")
            return tracking_id
    except Exception as e:
        log(f"[HATA] {e}")
        return ""


async def test1_tracking_sorgula(session: aiohttp.ClientSession, tracking_id: str):
    if not tracking_id:
        return
    log(f"\nTrackingId durumu sorgulanıyor: {tracking_id}")
    url = f"{MPOP_BASE}/product/api/products/status/{tracking_id}"
    try:
        async with session.get(
            url, headers=json_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status} - {raw[:300]}")
    except Exception as e:
        log(f"Sorgulama hatasi: {e}")


# -------------------------------------------------------
# TEST 2: Listeleme - Stok ve Fiyat Gonderimi
# -------------------------------------------------------
async def test2_mevcut_listeler(session: aiohttp.ClientSession) -> list:
    log("\n" + "=" * 55)
    log("TEST 2: Listeleme - Mevcut Urunler")
    log("=" * 55)

    url = f"{LIST_BASE}/listings/merchantid/{MERCHANT_ID}?limit=20&offset=0"
    log(f"GET {url}")
    try:
        async with session.get(
            url, headers=json_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status}")
            data = json.loads(raw)
            items = data.get("listings", data) if isinstance(data, dict) else data
            log(f"Mevcut urun sayisi: {len(items)}")
            for item in items[:5]:
                hb  = item.get("hepsiburadaSku", "")
                msk = item.get("merchantSku", "")
                stk = item.get("availableStock", "?")
                log(f"  merchantSku={msk}  hbSku={hb}  stok={stk}")
            return items
    except Exception as e:
        log(f"[HATA] {e}")
        return []


async def test2_fiyat_stok_gonder(session: aiohttp.ClientSession,
                                   hb_sku: str, merchant_sku: str):
    log(f"\nFiyat guncelleniyor: {merchant_sku}")
    price_payload = [{
        "hepsiburadaSku": hb_sku,
        "merchantSku":    merchant_sku,
        "price":          399.90,
    }]
    url_price = f"{LIST_BASE}/listings/merchantid/{MERCHANT_ID}/price-uploads"
    log(f"POST {url_price}")
    try:
        async with session.post(
            url_price, json=price_payload,
            headers=json_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status} - {raw[:200]}")
            if resp.status == 200:
                data = json.loads(raw)
                log(f"[OK] price-upload id: {data.get('id', '')}")
    except Exception as e:
        log(f"[HATA] fiyat: {e}")

    log(f"\nStok guncelleniyor: {merchant_sku}")
    stock_payload = [{
        "hepsiburadaSku":  hb_sku,
        "merchantSku":     merchant_sku,
        "availableStock":  10,
    }]
    url_stock = f"{LIST_BASE}/listings/merchantid/{MERCHANT_ID}/stock-uploads"
    log(f"POST {url_stock}")
    try:
        async with session.post(
            url_stock, json=stock_payload,
            headers=json_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status} - {raw[:200]}")
            if resp.status == 200:
                data = json.loads(raw)
                log(f"[OK] stock-upload id: {data.get('id', '')}")
    except Exception as e:
        log(f"[HATA] stok: {e}")


# -------------------------------------------------------
# TEST 3: Siparis - Listeleme ve Paketleme
# -------------------------------------------------------
async def test3_siparis_listele(session: aiohttp.ClientSession) -> list:
    log("\n" + "=" * 55)
    log("TEST 3: Siparis - Listeleme (OMS)")
    log("=" * 55)

    paketler = []
    url = f"{OMS_BASE}/packages/merchantid/{MERCHANT_ID}?limit=10&offset=0"
    log(f"GET {url}")
    try:
        async with session.get(
            url, headers=json_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status}")
            data = json.loads(raw) if raw.strip() else []
            items = data if isinstance(data, list) else data.get("data", data.get("packages", []))
            log(f"Paket sayisi: {len(items)}")
            for pkg in items[:3]:
                pkg_id = pkg.get("packageId", pkg.get("id", "?"))
                log(f"  packageId={pkg_id}")
                paketler.append(pkg)
    except Exception as e:
        log(f"[HATA] packages: {e}")

    url2 = f"{OMS_BASE}/orders/merchantid/{MERCHANT_ID}?limit=10&offset=0"
    log(f"\nGET {url2}")
    try:
        async with session.get(
            url2, headers=json_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status}")
            data = json.loads(raw)
            total = data.get("totalCount", len(data) if isinstance(data, list) else 0)
            log(f"Siparis sayisi: {total}")
    except Exception as e:
        log(f"[HATA] orders: {e}")

    return paketler


async def test3_paketle(session: aiohttp.ClientSession, package_id: str, line_items: list):
    log(f"\nPaketleme: {package_id}")
    payload = {"lines": line_items}
    url = f"{OMS_BASE}/packages/{package_id}/items/pack"
    log(f"POST {url}")
    try:
        async with session.post(
            url, json=payload,
            headers=json_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            raw = await resp.text()
            log(f"HTTP {resp.status} - {raw[:300]}")
            if resp.status in (200, 201, 202):
                log("[OK] Paketleme basarili")
    except Exception as e:
        log(f"[HATA] paketle: {e}")


# -------------------------------------------------------
# ANA AKIS
# -------------------------------------------------------
async def main():
    log("Hepsiburada SIT Entegrasyon Testi")
    log(f"Merchant ID : {MERCHANT_ID}")
    log(f"Username    : {USERNAME}")
    log(f"User-Agent  : {DEVELOPER_USER}")
    log(f"Ortam       : SIT (Test)")
    log(f"Tarih       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    async with aiohttp.ClientSession(auth=auth()) as session:

        # TEST 1
        tracking_id = await test1_urun_gonder(session)
        await asyncio.sleep(2)
        await test1_tracking_sorgula(session, tracking_id)

        # TEST 2
        mevcut = await test2_mevcut_listeler(session)
        if mevcut:
            item = mevcut[0]
            hb_sku  = item.get("hepsiburadaSku", "")
            msk     = item.get("merchantSku", "")
            await test2_fiyat_stok_gonder(session, hb_sku, msk)
        else:
            log("[!] Listeleme icin urun bulunamadi")

        # TEST 3
        paketler = await test3_siparis_listele(session)
        if paketler:
            pkg = paketler[0]
            pkg_id = pkg.get("packageId", pkg.get("id", ""))
            lines = pkg.get("lines", pkg.get("lineItems", []))
            if lines:
                line_items = [{
                    "lineItemId": l.get("id", l.get("lineItemId", "")),
                    "quantity": l.get("quantity", 1)
                } for l in lines]
                await test3_paketle(session, pkg_id, line_items)
            else:
                log("[!] Paket line item bulunamadi")
        else:
            log("\n[!] Sistemde siparis/paket yok.")
            log("    --> Test portalindan (merchant-sit.hepsiburada.com) bir test")
            log("        siparisi olusturun, sonra bu scripti tekrar calistirin.")

    log("\n" + "=" * 55)
    log("TESTLER TAMAMLANDI")
    log("=" * 55)
    if tracking_id:
        log(f"Hepsiburada'ya iletilecek TrackingId: {tracking_id}")

    out_file = os.path.join(os.path.dirname(__file__), "hepsiburada_sit_sonuclar.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))
    log(f"\nSonuclar kaydedildi: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
