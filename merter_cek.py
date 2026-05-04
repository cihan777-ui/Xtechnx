"""
merterelektronik.com'dan barkodla veya URL ile urun ceker, JSON cikti verir.
xtechnx.com URL'leri Selenium olmadan requests ile islenir.
Kullanim:
  python merter_cek.py <barkod>
  python merter_cek.py --url <urun_url>
"""
import sys, json, re, time, os
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from bs4 import BeautifulSoup
from urllib.parse import quote

_DEFAULT_ARAMA = "https://www.merterelektronik.com/Arama?1&kelime={}"
MERTE_ARAMA = os.environ.get("XTECHNX_SEARCH_URL", _DEFAULT_ARAMA)


def _handle_xtechnx_url(url):
    """xtechnx.com ürün sayfasını requests ile çeker — Selenium gerektirmez."""
    import requests

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9",
    }

    try:
        resp = requests.get(url, headers=hdrs, timeout=30, verify=False)
        resp.raise_for_status()
    except Exception as e:
        sys.stderr.write(f"[xtechnx] GET hatası: {e}\n"); sys.stderr.flush()
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Başlık ───────────────────────────────────────────────────
    baslik = ""
    for sel in ['h1[itemprop="name"]', "h1.product-title", "h1"]:
        el = soup.select_one(sel)
        if el:
            baslik = el.get_text(strip=True)
            break
    if not baslik:
        m = soup.find("meta", {"property": "og:title"})
        if m:
            baslik = m.get("content", "")

    # ── Fiyat: JSON-LD önce, sonra HTML ──────────────────────────
    fiyat = 0.0
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "Product"), None)
            if data and data.get("@type") == "Product":
                if not baslik:
                    baslik = data.get("name", "")
                offers = data.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0]
                p = str(offers.get("price", "0")).replace(",", ".")
                try:
                    fiyat = float(re.sub(r"[^\d.]", "", p))
                    break
                except Exception:
                    pass
        except Exception:
            pass

    if fiyat == 0.0:
        for sel in ["span.price-new", "span[itemprop='price']", ".price-new", "#content .price"]:
            el = soup.select_one(sel)
            if el:
                content = el.get("content") or el.get_text(strip=True)
                val = re.sub(r"[^\d,.]", "", content).replace(".", "").replace(",", ".")
                try:
                    fiyat = float(val)
                    if fiyat > 0:
                        break
                except Exception:
                    pass

    # ── SKU / Barkod ─────────────────────────────────────────────
    stok_kodu = ""
    for li in soup.select("ul.list-unstyled li, #product li, ul.product-meta li"):
        txt = li.get_text(strip=True)
        for prefix in ["ürün kodu:", "model:", "sku:", "stok kodu:"]:
            if txt.lower().startswith(prefix):
                stok_kodu = txt[len(prefix):].strip()
                break
        if stok_kodu:
            break

    if not stok_kodu:
        for sel_attr in ['[itemprop="sku"]', ".product-model", ".sku"]:
            el = soup.select_one(sel_attr)
            if el:
                stok_kodu = el.get_text(strip=True)
                break

    # "Cihan" prefix'i → barcode derive et, transformer için suffix gönder
    barkod = ""
    if stok_kodu.startswith("Cihan"):
        barkod = "Xtechnx" + stok_kodu[5:]
        stok_kodu = stok_kodu[5:]   # transformer "Cihan" + suffix yapacak

    # ── Açıklama ─────────────────────────────────────────────────
    aciklama = ""
    for sel in ["#tab-description", ".product-description", "#product-description",
                'div[id*="description"]', ".desc-container"]:
        el = soup.select_one(sel)
        if el:
            aciklama = el.get_text(separator="\n", strip=True)[:3000]
            break
    if not aciklama:
        for m_attr in [{"name": "description"}, {"property": "og:description"}]:
            m = soup.find("meta", m_attr)
            if m:
                aciklama = m.get("content", "")
                break

    # ── Resimler ─────────────────────────────────────────────────
    resimler = []
    seen = set()

    # OpenCart: thumbnail link'lerinin href'i büyük resim
    for a in soup.select("ul.thumbnails a[href], a.thumbnail[href]"):
        href = a.get("href", "")
        if href and re.search(r'\.(jpg|jpeg|png|webp)', href, re.I) and href not in seen:
            if not href.startswith("http"):
                href = "https://xtechnx.com" + href
            seen.add(href)
            resimler.append(href)

    # img src fallback
    if not resimler:
        for sel in ['img[itemprop="image"]', ".product-image img", "#content img"]:
            for img in soup.select(sel):
                src = img.get("src") or img.get("data-src") or ""
                if src and re.search(r'\.(jpg|jpeg|png|webp)', src, re.I):
                    if not re.search(r'/(logo|banner|icon|sprite)', src, re.I):
                        full = src if src.startswith("http") else "https://xtechnx.com" + src
                        if full not in seen:
                            seen.add(full)
                            resimler.append(full)

    # og:image son çare
    if not resimler:
        for og in soup.find_all("meta", {"property": "og:image"}):
            u = og.get("content", "")
            if u and u not in seen:
                seen.add(u)
                resimler.append(u)

    # ── Kategori ─────────────────────────────────────────────────
    kategori = ""
    bc = soup.select_one("#breadcrumb, nav[aria-label='breadcrumb'], ol.breadcrumb")
    if bc:
        items = [i.get_text(strip=True) for i in bc.find_all(["a", "li", "span"])
                 if len(i.get_text(strip=True)) > 1]
        if len(items) >= 2:
            kategori = items[-2]

    sys.stderr.write(f"[xtechnx] Başlık: {baslik}\n")
    sys.stderr.write(f"[xtechnx] Fiyat: {fiyat} | SKU: {stok_kodu} | Barkod: {barkod}\n")
    sys.stderr.write(f"[xtechnx] Resim: {len(resimler)} | Kategori: {kategori}\n")
    sys.stderr.flush()

    if not baslik:
        sys.stderr.write("[xtechnx] Başlık bulunamadı, ürün parse edilemedi.\n")
        sys.stderr.flush()
        return None

    return {
        "baslik": baslik,
        "fiyat": fiyat,
        "aciklama": aciklama,
        "resimler": resimler[:6],
        "kategori": kategori,
        "barkod": barkod,
        "stok_kodu": stok_kodu,
        "url": url,
    }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"hata": "Barkod verilmedi"}))
        return

    # --url <URL> veya dogrudan URL gecilmisse direkt scraping yap
    direct_url = None
    if sys.argv[1] == "--url" and len(sys.argv) >= 3:
        direct_url = sys.argv[2].strip()
        barkod = "URL-" + direct_url.split("/")[-1][:20].strip("-")
    elif sys.argv[1].startswith("http"):
        direct_url = sys.argv[1].strip()
        barkod = "URL-" + direct_url.split("/")[-1][:20].strip("-")
    else:
        barkod = sys.argv[1].strip()

    # xtechnx.com URL'si → requests ile çek, Selenium gerektirmez
    if direct_url and "xtechnx.com" in direct_url:
        sonuc = _handle_xtechnx_url(direct_url)
        if sonuc:
            print(json.dumps(sonuc, ensure_ascii=False))
        else:
            print(json.dumps({"hata": "xtechnx.com ürün bilgisi alınamadı"}))
        return

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
        _member_no = os.environ.get("XTECHNX_MEMBER_NO", "").strip()
        _site_user = os.environ.get("XTECHNX_SITE_USER", "").strip()
        _site_pass = os.environ.get("XTECHNX_SITE_PASS", "").strip()

        urun_url = direct_url  # None ise arama yapilir

        # Barkod araması her zaman merterelektronik.com — MERTE_ARAMA sadece URL ile eklemede geçerli
        from urllib.parse import urlparse
        _barkod_arama_url_template = _DEFAULT_ARAMA
        _search_parsed = urlparse(_barkod_arama_url_template)
        _search_netloc = _search_parsed.netloc.lower()  # www.merterelektronik.com
        _is_b2bmerter_search = False
        _search_base = f"{_search_parsed.scheme}://{_search_netloc}"

        if not urun_url:
            arama_url = _barkod_arama_url_template.format(quote(barkod))
            sys.stderr.write(f"Arama: {arama_url}\n"); sys.stderr.flush()

            # b2bmerter araması için önce login yap
            if _is_b2bmerter_search and _site_pass:
                _login_url = _search_base + "/Giris"
                sys.stderr.write(f"b2bmerter login öncesi: {_login_url}\n"); sys.stderr.flush()
                driver.get(_login_url)
                time.sleep(3)
                try:
                    from selenium.webdriver.common.keys import Keys as _Keys

                    def _js_fill_pre(el, val):
                        driver.execute_script(
                            "arguments[0].value=arguments[1];"
                            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                            el, val)

                    def _find_input_pre(*selectors):
                        for sel in selectors:
                            els = driver.find_elements(By.CSS_SELECTOR, sel)
                            if els:
                                return els[0]
                        return None

                    if _member_no:
                        el = _find_input_pre("#cBayiKodu","[name='cBayiKodu']","[name='UyeNo']","[name='BayiKodu']")
                        if not el:
                            txt = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                            el = txt[0] if txt else None
                        if el:
                            _js_fill_pre(el, _member_no)
                    if _site_user:
                        el = _find_input_pre("#cKullaniciAdi","[name='cKullaniciAdi']","[name='UserName']","[name='username']")
                        if not el:
                            txt = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                            el = txt[1] if len(txt) >= 2 else None
                        if el:
                            _js_fill_pre(el, _site_user)
                    el_pass = _find_input_pre("#cParola","[name='cParola']","[name='Password']","input[type='password']")
                    if el_pass:
                        _js_fill_pre(el_pass, _site_pass)
                        submit = _find_input_pre("button[type='submit']","input[type='submit']","[name='btnGiris']")
                        if not submit:
                            btns = driver.find_elements(By.CSS_SELECTOR, "button")
                            submit = btns[-1] if btns else None
                        if submit:
                            driver.execute_script("arguments[0].click();", submit)
                        else:
                            el_pass.send_keys(_Keys.RETURN)
                        time.sleep(4)
                        sys.stderr.write(f"Login sonrası URL: {driver.current_url}\n"); sys.stderr.flush()
                except Exception as _le:
                    sys.stderr.write(f"Ön-login hatası: {_le}\n"); sys.stderr.flush()

            driver.get(arama_url)
            time.sleep(3)

            # Arama sonrası login yönlendirmesi varsa tekrar giriş yap
            if _is_b2bmerter_search and _site_pass and driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                sys.stderr.write("Arama sayfasında login formu — giriş yapılıyor\n"); sys.stderr.flush()
                try:
                    from selenium.webdriver.common.keys import Keys as _Keys2
                    def _js_fill2(el, val):
                        driver.execute_script(
                            "arguments[0].value=arguments[1];"
                            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                            el, val)
                    inputs_text = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                    if _member_no and len(inputs_text) >= 1:
                        _js_fill2(inputs_text[0], _member_no)
                    if _site_user and len(inputs_text) >= 2:
                        _js_fill2(inputs_text[1], _site_user)
                    el_pass2 = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
                    if el_pass2:
                        _js_fill2(el_pass2[0], _site_pass)
                        btns2 = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                        if btns2:
                            driver.execute_script("arguments[0].click();", btns2[0])
                        else:
                            el_pass2[0].send_keys(_Keys2.RETURN)
                        time.sleep(4)
                        driver.get(arama_url)
                        time.sleep(3)
                except Exception as _le2:
                    sys.stderr.write(f"Arama-login hatası: {_le2}\n"); sys.stderr.flush()

            SKIP_MERTER = ["hakkimizda","iletisim","arama","kategori","marka","sepet",
                    "giris","uyelik","blog","anasayfa","hesabim","favoriler",
                    "karsilastir","uydu-alici-sistemleri"]
            SKIP_B2B = ["giris","sepet","hesabim","iletisim","hakkimizda","uyelik",
                        "blog","anasayfa","favoriler","karsilastir","arama"]
            SKIP = SKIP_B2B if _is_b2bmerter_search else SKIP_MERTER

            SELECTORS = [
                "div.col-sm-6 a", "div.product-thumb a", ".product-item a",
                ".urun-listesi a", "div[class*='product'] a", "div[class*='urun'] a",
            ]

            def _is_valid_urun_href(href):
                if not href or _search_netloc not in href.lower():
                    return False
                path = href.split(_search_netloc, 1)[-1].strip("/").lower()
                if any(path.startswith(s) for s in SKIP):
                    return False
                if "?" in path:
                    return False
                if _is_b2bmerter_search:
                    # b2bmerter ürün URL'leri: /UrunDetay/12345 veya /urun-adi-12345
                    return len(path) > 5 and not path.startswith("arama")
                else:
                    return path.count("-") >= 3 and len(path) > 20

            for sel in SELECTORS:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in elements:
                        href = el.get_attribute("href") or ""
                        if _is_valid_urun_href(href):
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
                            href = _search_base + href
                        else:
                            continue
                    if not _is_valid_urun_href(href):
                        continue
                    metin = a.get_text(strip=True)
                    if len(metin) > 5:
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

        # Giriş gerekiyorsa: login formu varsa doldur ve gönder
        if _site_pass and driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
            sys.stderr.write("Login formu tespit edildi, giriş yapılıyor...\n"); sys.stderr.flush()
            try:
                from selenium.webdriver.common.keys import Keys

                def _js_fill(el, val):
                    driver.execute_script(
                        "arguments[0].value=arguments[1];"
                        "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                        "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                        el, val)

                def _find_input(*selectors):
                    for sel in selectors:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        if els:
                            return els[0]
                    return None

                # Bayi Kodu / Üye No (cBayiKodu veya ilk text input)
                if _member_no:
                    el = _find_input("#cBayiKodu","[name='cBayiKodu']","[name='UyeNo']","[name='BayiKodu']")
                    if not el:
                        txt = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                        el = txt[0] if txt else None
                    if el:
                        _js_fill(el, _member_no)
                        sys.stderr.write(f"Bayi kodu girildi ({el.get_attribute('name') or el.get_attribute('id')})\n"); sys.stderr.flush()

                # Kullanıcı Adı (cKullaniciAdi veya ikinci text input)
                if _site_user:
                    el = _find_input("#cKullaniciAdi","[name='cKullaniciAdi']","[name='UserName']","[name='username']","[name='KullaniciAdi']")
                    if not el:
                        txt = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                        el = txt[1] if len(txt) >= 2 else (txt[0] if txt and not _member_no else None)
                    if el:
                        _js_fill(el, _site_user)
                        sys.stderr.write(f"Kullanıcı adı girildi ({el.get_attribute('name') or el.get_attribute('id')})\n"); sys.stderr.flush()

                # Şifre (cParola veya ilk password input)
                el_pass = _find_input("#cParola","[name='cParola']","[name='Password']","[name='password']","input[type='password']")
                if el_pass:
                    _js_fill(el_pass, _site_pass)
                    sys.stderr.write("Şifre girildi\n"); sys.stderr.flush()

                    # Submit — önce butona tıkla, yoksa Enter
                    submit = _find_input("button[type='submit']","input[type='submit']","[name='btnGiris']","[id*='Giris']","[id*='Login']","[id*='login']")
                    if not submit:
                        btns = driver.find_elements(By.CSS_SELECTOR, "button")
                        submit = btns[-1] if btns else None
                    if submit:
                        driver.execute_script("arguments[0].click();", submit)
                        sys.stderr.write(f"Submit tıklandı: {submit.get_attribute('id') or submit.text}\n"); sys.stderr.flush()
                    else:
                        el_pass.send_keys(Keys.RETURN)

                    time.sleep(5)
                    sys.stderr.write(f"Giriş sonrası URL: {driver.current_url}\n"); sys.stderr.flush()
                    if driver.current_url.rstrip("/") != urun_url.rstrip("/"):
                        driver.get(urun_url)
                        time.sleep(3)
            except Exception as _e:
                sys.stderr.write(f"Giriş hatası: {_e}\n"); sys.stderr.flush()

        # Login bloğundan sonra her durumda ürün sayfasına git
        if driver.current_url.rstrip("/") != urun_url.rstrip("/"):
            sys.stderr.write(f"Ürün sayfasına dönülüyor: {urun_url}\n"); sys.stderr.flush()
            driver.get(urun_url)
            time.sleep(4)

        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(0.3)
        time.sleep(1)

        # Debug: sayfa kaynağını kaydet
        try:
            import pathlib
            _debug_dir = pathlib.Path(__file__).parent / "logs"
            _debug_dir.mkdir(exist_ok=True)
            (_debug_dir / "debug_page.html").write_text(driver.page_source, encoding="utf-8", errors="replace")
            sys.stderr.write(f"Sayfa kaynağı kaydedildi: logs/debug_page.html (title={driver.title})\n"); sys.stderr.flush()
        except: pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        _site_domain = urun_url.split('/')[2].lower()  # örn: "www.b2bmerter.com"
        _is_b2bmerter = 'b2bmerter' in _site_domain

        # Baslik
        baslik = ""
        if _is_b2bmerter:
            for h2 in soup.find_all("h2"):
                txt = h2.get_text(strip=True)
                if len(txt) > 5 and "sepet" not in txt.lower():
                    # "Özellikleri" ile biten bölümü kes
                    baslik = re.sub(r'\s*Özellikleri.*$', '', txt, flags=re.IGNORECASE).strip()
                    if not baslik:
                        baslik = txt
                    break
            if not baslik:
                baslik = driver.title
        else:
            h1 = soup.find("h1")
            baslik = h1.get_text(strip=True) if h1 else ""
        if not baslik:
            meta = soup.find("meta", {"property": "og:title"})
            baslik = meta.get("content","").strip() if meta else ""

        # Fiyat
        fiyat = 0.0
        if _is_b2bmerter:
            # b2bmerter: KDV Dahil TL fiyatını tablodan al
            for tr in soup.find_all("tr"):
                tds = tr.find_all("td")
                if tds and "kdv" in tds[0].get_text(strip=True).lower():
                    val = re.sub(r"[^\d.,]", "", tds[-1].get_text(strip=True))
                    if val:
                        parts = val.split(".")
                        try:
                            if len(parts) > 1 and len(parts[-1]) == 2:
                                fiyat = float("".join(parts[:-1]) + "." + parts[-1])
                            else:
                                fiyat = float(val.replace(".", "").replace(",", "."))
                            sys.stderr.write(f"Fiyat bulundu (b2bmerter KDV dahil TL): {fiyat}\n"); sys.stderr.flush()
                        except: pass
                    break
        if fiyat == 0.0:
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
        if _is_b2bmerter:
            # b2bmerter: URL'deki ürün ID'sine göre resimleri filtrele
            _urun_id = urun_url.rstrip("/").split("/")[-1]
            for img in soup.select("img"):
                src = img.get("src","")
                if not src.startswith("http"):
                    src = "https://b2bmerter.com" + src if src.startswith("/") else ""
                if "B2BDosyalar/UrunResimleri" in src and f"/{_urun_id}-" in src and src not in resimler:
                    resimler.append(src)
            # Fallback: og:image
            if not resimler:
                for og in soup.find_all("meta", {"property":"og:image"}):
                    u = og.get("content","")
                    if u and u not in resimler:
                        resimler.append(u)
        else:
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
            if _is_b2bmerter:
                # b2bmerter: <ul class="breadcrumbs"> içinde sadece <a> tagları — son item marka, bir önceki kategori
                parcalar = [a.get_text(strip=True) for a in bc.find_all("a") if len(a.get_text(strip=True)) > 1]
            else:
                parcalar = [i.get_text(strip=True) for i in bc.find_all(["a","span","li"]) if len(i.get_text(strip=True))>1]
            if len(parcalar) >= 2:
                kategori = parcalar[-2]
        sys.stderr.write(f"Kategori: {kategori}\n"); sys.stderr.flush()

        # Stok kodu
        stok_kodu = ""
        for sel in ['[itemprop="sku"]', ".product-code span", ".stok-kodu",
                    '[itemprop="mpn"]', ".product-sku", ".urun-kodu", ".sku"]:
            tag = soup.select_one(sel)
            if tag:
                val = (tag.get("content") or tag.get_text(strip=True) or "").strip()
                if val and len(val) >= 2:
                    stok_kodu = val
                    break
        if not stok_kodu:
            m = re.search(r'-([A-Z0-9]{4,20})\.html', urun_url, re.I)
            if m:
                stok_kodu = m.group(1).upper()

        sys.stderr.write(f"Baslik: {baslik}\n"); sys.stderr.flush()
        sys.stderr.write(f"Fiyat: {fiyat}\n"); sys.stderr.flush()
        sys.stderr.write(f"Resimler: {len(resimler)}\n"); sys.stderr.flush()
        sys.stderr.write(f"Stok kodu: {stok_kodu}\n"); sys.stderr.flush()

        # Doğrulama: sayfa JS'indeki gerçek barkod ile aranan barkod karşılaştırılır
        # merterelektronik.com her ürün sayfasında "barkod":"XXXXXXXXX" JSON'u gömer
        if not direct_url:
            _page_barkod = None
            for _script in soup.find_all("script"):
                _stxt = _script.string or ""
                _m = re.search(r'"barkod"\s*:\s*"(\d{8,14})"', _stxt)
                if _m:
                    _page_barkod = _m.group(1)
                    break
            sys.stderr.write(f"Sayfa barkodu: {_page_barkod}\n"); sys.stderr.flush()
            if _page_barkod and _page_barkod != barkod:
                sys.stderr.write(
                    f"UYARI: Aranan '{barkod}' != sayfa barkodu '{_page_barkod}'. Yanlis urun.\n"
                ); sys.stderr.flush()
                print(json.dumps({"hata": f"Yanlis urun eslesmesi: aranan '{barkod}', sayfadaki '{_page_barkod}' ({baslik[:50]}). Urunu URL ile ekleyin."}))
                return
            # _page_barkod None ise barkod sayfada gizli — devam et

        sonuc = {
            "baslik": baslik,
            "fiyat": fiyat,
            "aciklama": aciklama,
            "resimler": resimler[:6],
            "kategori": kategori,
            "barkod": barkod,
            "stok_kodu": stok_kodu,
            "url": urun_url,
        }
        print(json.dumps(sonuc, ensure_ascii=False))

    finally:
        try: driver.quit()
        except: pass

if __name__ == "__main__":
    main()
