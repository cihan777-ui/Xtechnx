"""
merterelektronik.com'dan barkodla urun ceker, JSON cikti verir.
Kullanim: python merter_cek.py <barkod>
"""
import sys, json, re, time
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from bs4 import BeautifulSoup
from urllib.parse import quote

MERTE_ARAMA = "https://www.merterelektronik.com/Arama?1&kelime={}"

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"hata": "Barkod verilmedi"}))
        return

    barkod = sys.argv[1].strip()

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")

    try:
        service = Service(ChromeDriverManager().install())
    except:
        service = Service()

    driver = webdriver.Chrome(service=service, options=options)

    try:
        arama_url = MERTE_ARAMA.format(quote(barkod))
        sys.stderr.write(f"Arama: {arama_url}\n"); sys.stderr.flush()
        driver.get(arama_url)
        time.sleep(3)

        urun_url = None
        SKIP = ["hakkimizda","iletisim","arama","kategori","marka","sepet",
                "giris","uyelik","blog","anasayfa","hesabim","favoriler",
                "karsilastir","uydu-alici-sistemleri"]

        SELECTORS = [
            "div.col-sm-6 a", "div.product-thumb a", ".product-item a",
            ".urun-listesi a", "div[class*='product'] a", "div[class*='urun'] a",
        ]

        for sel in SELECTORS:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    href = el.get_attribute("href") or ""
                    if "merterelektronik.com" not in href:
                        continue
                    path = href.replace("https://www.merterelektronik.com","").strip("/").lower()
                    if any(path.startswith(s) for s in SKIP):
                        continue
                    if path.count("-") >= 3 and len(path) > 20 and "?" not in path:
                        urun_url = href
                        break
            except:
                pass
            if urun_url:
                break

        # Fallback: BeautifulSoup ile tüm linkleri tara
        if not urun_url:
            soup = BeautifulSoup(driver.page_source, "html.parser")
            kandidatlar = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href.startswith("http"):
                    if href.startswith("/"):
                        href = "https://www.merterelektronik.com" + href
                    else:
                        continue
                if "merterelektronik.com" not in href:
                    continue
                path = href.replace("https://www.merterelektronik.com","").strip("/").lower()
                if any(path.startswith(s) for s in SKIP):
                    continue
                if path.count("-") >= 3 and len(path) > 20 and "?" not in path:
                    metin = a.get_text(strip=True)
                    if len(metin) > 10:
                        kandidatlar.append((len(metin), href))

            if kandidatlar:
                kandidatlar.sort(reverse=True)
                urun_url = kandidatlar[0][1]

        if not urun_url:
            print(json.dumps({"hata": f"Urun bulunamadi: {barkod}"}))
            return

        sys.stderr.write(f"Urun URL: {urun_url}\n"); sys.stderr.flush()

        driver.get(urun_url)
        time.sleep(3)
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(0.3)
        time.sleep(1)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Baslik
        h1 = soup.find("h1")
        baslik = h1.get_text(strip=True) if h1 else ""
        if not baslik:
            meta = soup.find("meta", {"property": "og:title"})
            baslik = meta.get("content","").strip() if meta else ""

        # Fiyat
        fiyat = 0.0
        # merterelektronik.com'a özel seçiciler
        for sel in ["span#fiyat2", "span.spanFiyat", "span.indirimliFiyat",
                    "#divIndirimsizFiyat span", "meta[itemprop='price']",
                    ".fiyat", ".price", "[itemprop='price']"]:
            try:
                if sel.startswith("meta"):
                    tag = soup.find("meta", {"itemprop": "price"})
                    val = tag.get("content","") if tag else ""
                else:
                    tag = soup.select_one(sel)
                    val = tag.get_text(strip=True) if tag else ""
                if val:
                    val_clean = re.sub(r"[^\d,.]", "", val).replace(".","").replace(",",".")
                    nums = re.findall(r"[\d]+\.?[\d]*", val_clean)
                    if nums:
                        fiyat = float(nums[0])
                        if fiyat > 0:
                            sys.stderr.write(f"Fiyat bulundu ({sel}): {fiyat}\n")
                            sys.stderr.flush()
                            break
            except: pass

        # Aciklama - tum olasi bolumlerden topla
        aciklama_parcalar = []
        for id_val in ["divTabOzellikler","divTabAciklama","divUrunAciklama",
                       "divDescription","divUrunDetay","divOzellikler",
                       "divTeknikOzellik","product-description","product-detail"]:
            tag = soup.find(id=id_val)
            if tag:
                metin = tag.get_text(separator="\n", strip=True)
                if metin and metin not in aciklama_parcalar:
                    aciklama_parcalar.append(metin)
        # CSS class ile de dene
        for cls in ["product-description","urun-aciklama","product-detail","ozellikler"]:
            tag = soup.find(class_=cls)
            if tag:
                metin = tag.get_text(separator="\n", strip=True)
                if metin and metin not in aciklama_parcalar:
                    aciklama_parcalar.append(metin)
        aciklama = "\n\n".join(aciklama_parcalar)
        if not aciklama:
            meta_d = soup.find("meta", {"name":"description"}) or soup.find("meta", {"property":"og:description"})
            aciklama = meta_d.get("content","") if meta_d else ""

        # Resimler
        resimler = []
        for img in driver.find_elements(By.CSS_SELECTOR, "img.cloudzoom-gallery, #divThumbList img"):
            try:
                cz = img.get_attribute("data-cloudzoom") or ""
                if cz:
                    d = json.loads(cz)
                    url = d.get("zoomImage") or d.get("image","")
                    url = re.sub(r'/cdn-cgi/image/[^/]+/', '/', url).split("?")[0]
                    if url and url not in resimler:
                        resimler.append(url)
            except: pass

        if not resimler:
            for og in soup.find_all("meta", {"property":"og:image"}):
                u = og.get("content","")
                if u and u not in resimler:
                    resimler.append(u)

        # Kategori
        kategori = ""
        bc = soup.find(class_=re.compile(r"breadcrumb",re.I))
        if bc:
            parcalar = [i.get_text(strip=True) for i in bc.find_all(["a","span","li"]) if len(i.get_text(strip=True))>1]
            if len(parcalar) >= 2:
                kategori = parcalar[-2]

        sys.stderr.write(f"Baslik: {baslik}\n"); sys.stderr.flush()
        sys.stderr.write(f"Fiyat: {fiyat}\n"); sys.stderr.flush()
        sys.stderr.write(f"Resimler: {len(resimler)}\n"); sys.stderr.flush()

        sonuc = {
            "baslik": baslik,
            "fiyat": fiyat,
            "aciklama": aciklama,
            "resimler": resimler[:6],
            "kategori": kategori,
            "barkod": barkod,
            "url": urun_url,
        }
        print(json.dumps(sonuc, ensure_ascii=False))

    finally:
        try: driver.quit()
        except: pass

if __name__ == "__main__":
    main()
