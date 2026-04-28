"""
Hepsiburada SIT/PROD - Paketlenecek siparisleri bul ve paketle.
Calistir: python hb_paketle.py

Akis:
  1. GET /orders/merchantid/{mid}/pack  -> paketlenecek itemlari al
  2. POST /packages/merchantid/{mid}    -> paket olustur (lineItems ile)
  3. POST /packages/{id}/items/pack     -> paketi onayla
"""
import asyncio
import aiohttp
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MERCHANT_ID  = os.getenv("HEPSIBURADA_MERCHANT_ID", "")
USERNAME     = os.getenv("HEPSIBURADA_USERNAME", "")
PASSWORD     = os.getenv("HEPSIBURADA_PASSWORD", "")
DEVELOPER_UA = os.getenv("HEPSIBURADA_DEVELOPER_USERNAME", "")
OMS_BASE     = "https://oms-external-sit.hepsiburada.com"

LOG = []

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.append(line)

def hdr():
    return {"Content-Type": "application/json", "User-Agent": DEVELOPER_UA}


async def paketlenecekleri_getir(session) -> list:
    """GET /orders/merchantid/{mid}/pack — paketlenmeyi bekleyenler."""
    url = f"{OMS_BASE}/orders/merchantid/{MERCHANT_ID}/pack?limit=50&offset=0"
    log(f"GET {url}")
    async with session.get(url, headers=hdr(), timeout=aiohttp.ClientTimeout(total=30)) as r:
        raw = await r.text()
        log(f"  HTTP {r.status}")
        if r.status != 200:
            log(f"  [!] Hata: {raw[:200]}")
            return []
        data = json.loads(raw) if raw.strip() else {}
        items = data.get("items", []) if isinstance(data, dict) else []
        log(f"  {len(items)} paketlenecek item bulundu")
        return items


async def paket_olustur(session, line_items: list) -> str:
    """POST /packages/merchantid/{mid} — paket olustur, packageId doner."""
    payload = {"lineItems": line_items}
    url = f"{OMS_BASE}/packages/merchantid/{MERCHANT_ID}"
    log(f"POST {url}")
    log(f"  Payload: {json.dumps(payload)}")
    async with session.post(url, json=payload, headers=hdr(), timeout=aiohttp.ClientTimeout(total=30)) as r:
        raw = await r.text()
        log(f"  HTTP {r.status} | {raw[:300]}")
        if r.status not in (200, 201, 202):
            log(f"  [!] Paket olusturulamadi")
            return ""
        try:
            data = json.loads(raw)
            pkg_id = (
                data.get("packageId")
                or data.get("id")
                or data.get("packageNumber")
                or ""
            )
            if pkg_id:
                log(f"  [OK] packageId: {pkg_id}")
            return str(pkg_id)
        except Exception:
            log(f"  [!] Yanit parse edilemedi: {raw[:200]}")
            return ""


async def paketi_onayla(session, package_id: str, line_items: list) -> bool:
    """POST /packages/{packageId}/items/pack — paketi onayla."""
    payload = {"lines": [{"lineItemId": li["id"], "quantity": li["quantity"]} for li in line_items]}
    url = f"{OMS_BASE}/packages/{package_id}/items/pack"
    log(f"POST {url}")
    log(f"  Payload: {json.dumps(payload)}")
    async with session.post(url, json=payload, headers=hdr(), timeout=aiohttp.ClientTimeout(total=30)) as r:
        raw = await r.text()
        log(f"  HTTP {r.status} | {raw[:300]}")
        if r.status in (200, 201, 202):
            log(f"  [OK] Paket {package_id} onaylandi!")
            return True
        log(f"  [!] Paket onay hatasi")
        return False


async def main():
    log("=" * 60)
    log("Hepsiburada - Paketlenecek Siparisleri Isle")
    log(f"Merchant ID : {MERCHANT_ID}")
    log(f"Ortam       : SIT")
    log(f"Tarih       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    auth = aiohttp.BasicAuth(USERNAME, PASSWORD)
    async with aiohttp.ClientSession(auth=auth) as session:

        # 1. Paketlenecekleri al
        items = await paketlenecekleri_getir(session)
        if not items:
            log("\n[!] Paketlenecek siparis yok.")
            log("    Hepsiburada entegrasyon ekibinden gercek test siparisi talep edin.")
        else:
            log(f"\n>>> {len(items)} item isleniyor...\n")

            # Her item ayri paket olarak olusturulacak
            basarili = 0
            for item in items:
                item_id = item.get("id", "")
                qty = item.get("quantity", 1)
                name = item.get("name", "")[:50]
                log(f"\n--- {name} (qty={qty}) ---")

                # 2. Paket olustur
                li = [{"id": item_id, "quantity": qty}]
                pkg_id = await paket_olustur(session, li)

                if pkg_id:
                    # 3. Paketi onayla
                    if await paketi_onayla(session, pkg_id, li):
                        basarili += 1
                else:
                    log(f"  [!] Paket ID alinamadi, onay atlanıyor")

                await asyncio.sleep(1)

            log("\n" + "=" * 60)
            log(f"SONUC: {basarili}/{len(items)} item basariyla paketlendi.")
            if basarili == len(items):
                log("Tum siparisler 'Gonderime hazir' statusune gecmeli.")
            log("=" * 60)

    out = os.path.join(os.path.dirname(__file__), "hb_paketle_sonuc.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))
    print(f"\nSonuclar kaydedildi: {out}")


if __name__ == "__main__":
    asyncio.run(main())
