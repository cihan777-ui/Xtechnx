"""
Hepsiburada - Paketlenecek siparisleri bul ve paketle.

Auth: hb_cookies.json (Selenium ile kaydedilmis portal session)
      Cookie suresi dolunca: python hb_step1_login.py ile yenile

Calistir: python hb_paketle.py
"""
import requests, json, os, sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

# Ortama gore URL
ENV      = os.getenv("HEPSIBURADA_ENV", "test").lower()
if ENV == "production":
    BASE = "https://merchant.hepsiburada.com/fulfilment"
else:
    BASE = "https://merchant-sit.hepsiburada.com/fulfilment"

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "hb_cookies.json")
LOG = []

def log(msg):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.append(line)


def load_session():
    if not os.path.exists(COOKIES_FILE):
        log(f"[!] {COOKIES_FILE} bulunamadi.")
        log("    Once 'python hb_step1_login.py' calistirin.")
        sys.exit(1)
    with open(COOKIES_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    s = requests.Session()
    for c in saved:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    s.headers.update({"Content-Type": "application/json"})
    return s


def paketlenecekleri_getir(session) -> list:
    """GET /api/v3/orderlines/tobepacked -> paketlenecek satirlari dondur."""
    url = f"{BASE}/api/v3/orderlines/tobepacked?offset=0&limit=100"
    log(f"GET {url}")
    r = session.get(url, timeout=30)
    log(f"  HTTP {r.status_code}")
    if r.status_code == 401:
        log("  [!] Session suresi dolmus. 'python hb_step1_login.py' ile yenileyin.")
        sys.exit(1)
    if r.status_code != 200:
        log(f"  [!] Hata: {r.text[:200]}")
        return []
    data = r.json()
    items = []
    for order in data.get("Data", []):
        for line in order.get("OrderLines", []):
            items.append({
                "orderNumber": order.get("OrderNumber"),
                "lineId":      line["Id"],
                "qty":         line["Quantity"],
                "name":        line.get("Sku", "")[:50],
            })
    log(f"  {len(items)} paketlenecek item bulundu")
    return items


def paket_olustur(session, line_id: str, qty: int) -> dict:
    """POST /api/v1/deliveries -> paket olustur."""
    payload = {
        "CarrierId":      0,
        "Lines":          [{"OrderLineId": line_id, "Quantity": qty, "SerialNumbers": []}],
        "ParcelQuantity": 1,
        "Deci":           None,
    }
    url = f"{BASE}/api/v1/deliveries"
    log(f"POST {url}")
    log(f"  Payload: {json.dumps(payload)}")
    r = session.post(url, json=payload, timeout=30)
    log(f"  HTTP {r.status_code}")
    if r.status_code in (200, 201):
        try:
            data = r.json()
            pkg_id   = data.get("Id", "")
            pkg_code = data.get("Code", "")
            log(f"  [OK] Paket olusturuldu — Id={pkg_id}  Code={pkg_code}")
            return {"id": pkg_id, "code": pkg_code, "ok": True}
        except Exception as e:
            log(f"  [!] Yanit parse hatasi: {e}")
    else:
        log(f"  [!] Hata: {r.text[:300]}")
    return {"ok": False}


def main():
    log("=" * 60)
    log("Hepsiburada - Paketlenecek Siparisleri Isle")
    log(f"Ortam : {ENV.upper()} | Base: {BASE}")
    log(f"Tarih : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    session = load_session()

    # 1. Paketlenecekleri al
    items = paketlenecekleri_getir(session)
    if not items:
        log("\n[!] Paketlenecek siparis yok.")
        log("    Yeni siparis geldikten sonra tekrar calistirin.")
    else:
        log(f"\n>>> {len(items)} item isleniyor...\n")
        basarili = 0
        for item in items:
            log(f"\n--- {item['orderNumber']} | {item['name']} (qty={item['qty']}) ---")
            result = paket_olustur(session, item["lineId"], item["qty"])
            if result["ok"]:
                basarili += 1

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
    main()
