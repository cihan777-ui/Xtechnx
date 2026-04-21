"""
merterelektronik.com sitesindeki tum kategorileri ceker.
Kullanim: venv\Scripts\python merter_kategoriler.py
"""
import requests, re
from bs4 import BeautifulSoup
from pathlib import Path

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
}

resp = requests.get("https://www.merterelektronik.com", headers=HEADERS, timeout=30, verify=False)
soup = BeautifulSoup(resp.text, "html.parser")

kategoriler = set()

# Nav menüsündeki tüm linkleri tara
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if not text or len(text) < 2 or len(text) > 60:
        continue
    # Kategori linki olabilecekler
    if any(x in href for x in ["/kategori", "/category", "/c/", "?CategoryId", "?kategori"]):
        kategoriler.add(text)
    # Nav/menu class'larına bak
    parent = a.find_parent(class_=re.compile(r"nav|menu|kategori|category", re.I))
    if parent and text:
        kategoriler.add(text)

# Tüm li > a yapısındaki menü öğeleri
for nav in soup.find_all(["nav", "ul"], class_=re.compile(r"nav|menu|kategori", re.I)):
    for a in nav.find_all("a"):
        text = a.get_text(strip=True)
        if text and 2 < len(text) < 60:
            kategoriler.add(text)

# Filtrele - gereksizleri at
SKIP = {"anasayfa", "home", "iletişim", "hakkımızda", "blog", "sepet",
        "giriş", "üyelik", "hesabım", "favoriler", "ara", "search",
        "kampanya", "fırsat", "indirim", "yeni", "çok satan"}

sonuc = sorted([k for k in kategoriler
                if k.lower() not in SKIP and not k.isdigit() and len(k) > 2])

Path("merter_kategoriler.txt").write_text(
    "\n".join(sonuc), encoding="utf-8"
)
print(f"{len(sonuc)} kategori bulundu → merter_kategoriler.txt")
for k in sonuc:
    print(" ", k)
