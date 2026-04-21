"""
N11 SOAP API - ilgili kategorilerin tum alt agacini ceker.
Kullanim: venv\Scripts\python n11_kategoriler.py
"""
import requests, time
from pathlib import Path
from xml.etree import ElementTree as ET

env = {}
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

APP_KEY    = env.get("N11_APP_KEY", "")
APP_SECRET = env.get("N11_APP_SECRET", "")
HEADERS = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

def get_subs(parent_id):
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:cat="http://www.n11.com/ws/schemas">
  <soapenv:Header/>
  <soapenv:Body>
    <cat:GetSubCategoriesRequest>
      <auth><appKey>{APP_KEY}</appKey><appSecret>{APP_SECRET}</appSecret></auth>
      <categoryId>{parent_id}</categoryId>
    </cat:GetSubCategoriesRequest>
  </soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post("https://api.n11.com/ws/CategoryService",
                      data=body.encode("utf-8"), headers=HEADERS, timeout=30)
    root = ET.fromstring(r.text)
    cats = []
    for sc in root.iter("subCategory"):
        cid = sc.findtext("id")
        name = sc.findtext("name")
        if cid and name:
            cats.append((cid, name))
    return cats

def fetch_tree(parent_id, parent_name, depth=0, lines=None):
    if lines is None:
        lines = []
    indent = "  " * depth
    subs = get_subs(parent_id)
    for cid, name in subs:
        line = f"{indent}{cid}  {name}"
        print(line)
        lines.append(line)
        if depth < 2:  # max 3 seviye
            time.sleep(0.2)
            fetch_tree(cid, name, depth + 1, lines)
    return lines

# Ilgili ust kategoriler
HEDEF = [
    ("1000605", "Aydinlatma"),
    ("1000472", "Telefon & Aksesuarlari"),
    ("1000373", "Elektrikli Ev Aletleri"),
    ("1000514", "Televizyon & Ses Sistemleri"),
    ("1003041", "Ses Sistemleri & Navigasyon"),
    ("1000210", "Bilgisayar"),
]

tum_satirlar = []
for cat_id, cat_name in HEDEF:
    print(f"\n{'='*50}")
    print(f"{cat_id}  {cat_name}")
    print('='*50)
    tum_satirlar.append(f"\n{'='*50}")
    tum_satirlar.append(f"{cat_id}  {cat_name}")
    satirlar = fetch_tree(cat_id, cat_name)
    tum_satirlar.extend(satirlar)
    time.sleep(0.3)

Path("n11_alt_kategoriler.txt").write_text(
    "\n".join(tum_satirlar), encoding="utf-8"
)
print("\n\nTamamlandi! n11_alt_kategoriler.txt dosyasina kaydedildi.")
