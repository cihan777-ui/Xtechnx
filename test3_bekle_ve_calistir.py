"""
TEST 3: Hepsiburada SIT - Test siparisi olustur, gelince isle.
Calistir: python test3_bekle_ve_calistir.py
"""
import asyncio
import aiohttp
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MERCHANT_ID  = os.getenv("HEPSIBURADA_MERCHANT_ID", "")
USERNAME     = os.getenv("HEPSIBURADA_USERNAME", "")
PASSWORD     = os.getenv("HEPSIBURADA_PASSWORD", "")
DEVELOPER_UA = os.getenv("HEPSIBURADA_DEVELOPER_USERNAME", "")
OMS_BASE     = "https://oms-external-sit.hepsiburada.com"
OMS_STUB     = "https://oms-stub-external-sit.hepsiburada.com"

# Test siparisindeki HepsiburadaSku (Test 1'de yuklenen urun)
HB_SKU = "HBV0000116N2E"

POLL_INTERVAL = 15   # saniye
MAX_WAIT      = 300  # maksimum 5 dakika bekle


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def hdr():
    return {
        "Content-Type": "application/json",
        "User-Agent": DEVELOPER_UA,
    }


async def create_test_order(session) -> str:
    """Stub endpoint ile SIT'e test siparisi olusturur. Olusturulan OrderNumber'i doner."""
    order_number = str(int(time.time()))[-10:]  # uniq 10 haneli numara
    payload = {
        "OrderNumber": order_number,
        "OrderDate": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "Customer": {
            "CustomerId": "dfc8a27f-faae-4cb2-859c-8a7d50ee77be",
            "Name": "Test User"
        },
        "DeliveryAddress": {
            "AddressId": "b12e43e8-3f58-427f-9376-4b4ef40464ef",
            "Name": "Hepsiburada Office",
            "AddressDetail": "MECİDİYEKÖY",
            "Email": "customer@hepsiburada.com.tr",
            "CountryCode": "TR",
            "PhoneNumber": "902822613231",
            "AlternatePhoneNumber": "045321538212",
            "Town": "Gaziosmanpaşa",
            "District": "Gaziosmanpaşa",
            "City": "İstanbul"
        },
        "LineItems": [
            {
                "Sku": HB_SKU,
                "MerchantId": MERCHANT_ID,
                "Quantity": 1,
                "Price": {"Amount": 301.4, "Currency": "TRY"},
                "Vat": 0,
                "TotalPrice": {"Amount": 301.4, "Currency": "TRY"},
                "CargoCompanyId": 89100,
                "DeliveryOptionId": 1
            }
        ]
    }
    url = f"{OMS_STUB}/orders/merchantid/{MERCHANT_ID}"
    log(f"Test siparisi olusturuluyor: OrderNumber={order_number}")
    try:
        async with session.post(
            url, json=payload,
            headers=hdr(), timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            raw = await r.text()
            log(f"Stub HTTP {r.status}: {raw[:300]}")
            if r.status in (200, 201, 202):
                log(f"[OK] Test siparisi olusturuldu: {order_number}")
                return order_number
            else:
                log(f"[!] Siparis olusturma basarisiz: {r.status}")
                return ""
    except Exception as e:
        log(f"create_test_order hata: {e}")
        return ""


async def _fetch_packages(session, base_url: str) -> list:
    url = f"{base_url}/packages/merchantid/{MERCHANT_ID}?limit=10&offset=0"
    try:
        async with session.get(url, headers=hdr(), timeout=aiohttp.ClientTimeout(total=20)) as r:
            raw = await r.text()
            if r.status != 200:
                log(f"  [{base_url.split('//')[1][:20]}] Packages HTTP {r.status}: {raw[:100]}")
                return []
            data = json.loads(raw) if raw.strip() else []
            return data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        log(f"check_packages hata ({base_url}): {e}")
        return []


async def check_packages(session) -> list:
    # Hem normal OMS hem stub URL'de kontrol et
    pkgs = await _fetch_packages(session, OMS_BASE)
    if not pkgs:
        pkgs = await _fetch_packages(session, OMS_STUB)
    return pkgs


async def check_orders(session) -> dict:
    url = f"{OMS_BASE}/orders/merchantid/{MERCHANT_ID}?limit=10&offset=0"
    try:
        async with session.get(url, headers=hdr(), timeout=aiohttp.ClientTimeout(total=20)) as r:
            raw = await r.text()
            data = json.loads(raw) if raw.strip() else {}
            return data
    except Exception as e:
        log(f"check_orders hata: {e}")
        return {}


async def pack_package(session, package_id: str, pkg: dict) -> bool:
    lines = pkg.get("lines", pkg.get("lineItems", pkg.get("items", [])))
    if not lines:
        log(f"[!] Paket {package_id} icin line item bulunamadi. Ham veri: {json.dumps(pkg)[:300]}")
        return False

    line_items = []
    for line in lines:
        li_id = (
            line.get("lineItemId")
            or line.get("id")
            or line.get("orderLineId")
            or ""
        )
        qty = line.get("quantity", line.get("qty", 1))
        if li_id:
            line_items.append({"lineItemId": li_id, "quantity": qty})

    if not line_items:
        log(f"[!] Line item ID'leri alinamamadi. Ham: {json.dumps(lines[:2])}")
        return False

    payload = {"lines": line_items}
    url = f"{OMS_BASE}/packages/{package_id}/items/pack"
    log(f"POST {url}")
    log(f"Payload: {json.dumps(payload)}")
    try:
        async with session.post(
            url, json=payload,
            headers=hdr(), timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            raw = await r.text()
            log(f"HTTP {r.status} - {raw[:400]}")
            if r.status in (200, 201, 202):
                log("[OK] PAKETLEME BASARILI!")
                return True
            else:
                log("[!] Paketleme basarisiz")
                return False
    except Exception as e:
        log(f"pack hatasi: {e}")
        return False


async def main():
    log("=" * 55)
    log("TEST 3: Siparis Olustur + Paketle")
    log(f"Merchant ID  : {MERCHANT_ID}")
    log(f"Poll interval: {POLL_INTERVAL}s, Max bekleme: {MAX_WAIT}s")
    log("=" * 55)

    auth = aiohttp.BasicAuth(USERNAME, PASSWORD)
    elapsed = 0

    async with aiohttp.ClientSession(auth=auth) as session:
        # Stub ile test siparisi olustur
        order_number = await create_test_order(session)
        if not order_number:
            log("[!] Test siparisi olusturulamadi, devam edilemiyor.")
            return

        log(f"\n{POLL_INTERVAL}s bekleniyor (siparis sisteme isleniyor)...")
        await asyncio.sleep(POLL_INTERVAL)

        while elapsed < MAX_WAIT:
            packages = await check_packages(session)
            orders   = await check_orders(session)

            total_orders = orders.get("totalCount", 0)
            pkg_count    = len(packages)

            log(f"Kontrol: {pkg_count} paket, {total_orders} siparis")

            if packages:
                log(f"\n>>> {pkg_count} PAKET BULUNDU!")
                for pkg in packages:
                    pkg_id = pkg.get("packageId", pkg.get("id", "?"))
                    log(f"\nPaket: {pkg_id}")
                    log(f"Ham: {json.dumps(pkg)[:500]}")
                    success = await pack_package(session, pkg_id, pkg)
                    if success:
                        log(f"[OK] Paket {pkg_id} basariyla islendi")

                log("\n=== TEST 3 TAMAMLANDI ===")
                log("Simdi tam test sonuclarini kaydetmek icin:")
                log("  python hepsiburada_sit_test.py")
                break

            log(f"{POLL_INTERVAL}s bekleniliyor...")
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
        else:
            log(f"\n{MAX_WAIT}s icinde paket gorunmedi.")
            log("Stub ile siparis olusturuldu fakat OMS'e yansimadi.")
            log("Hepsiburada destek ekibiyle iletisime gecin.")


if __name__ == "__main__":
    asyncio.run(main())
