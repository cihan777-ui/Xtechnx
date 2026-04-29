"""
xtechnx.com admin paneline Selenium ile urun yukler.
Admin oturumu modulun omru boyunca tek bir driver'da tutulur.
"""
import re
import time
import hashlib
import asyncio
import os
import tempfile
from functools import partial

import requests as _req
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from models.product import Product
from config.settings import settings

ADMIN_URL  = settings.xtechnx_admin_url
ADMIN_USER = settings.xtechnx_admin_user
ADMIN_PASS = settings.xtechnx_admin_pass
MARKA      = "Xtechnx"

_driver     = None
_user_token = ""


# ── Driver / Oturum ───────────────────────────────────────────

def _get_driver():
    global _driver
    if _driver is not None:
        try:
            _ = _driver.current_url
            return _driver
        except Exception:
            pass
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    _driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )
    _driver.execute_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    return _driver


def _admin_giris(driver) -> bool:
    global _user_token
    driver.get(ADMIN_URL)
    time.sleep(3)
    wait = WebDriverWait(driver, 15)
    try:
        wait.until(EC.presence_of_element_located((By.ID, "input-username"))).send_keys(ADMIN_USER)
        driver.find_element(By.ID, "input-password").send_keys(ADMIN_PASS)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(3)
        if "login" not in driver.current_url:
            m = re.search(r"user_token=([^&]+)", driver.current_url)
            if not m:
                driver.get(f"{ADMIN_URL}index.php?route=common/dashboard")
                time.sleep(2)
                m = re.search(r"user_token=([^&]+)", driver.current_url)
            _user_token = m.group(1) if m else ""
            return True
        return False
    except Exception as e:
        print(f"[xtechnx] Admin giris hatasi: {e}")
        return False


def _oturum_kontrol(driver) -> bool:
    if not _user_token or "login" in driver.current_url.lower():
        return _admin_giris(driver)
    return True


def _ekle_url():
    return f"{ADMIN_URL}index.php?route=catalog/product/add&user_token={_user_token}"


# ── Form Yardımcıları ─────────────────────────────────────────

def _js_yaz(driver, el, deger):
    driver.execute_script("""
        var el = arguments[0];
        el.removeAttribute('readonly');
        el.removeAttribute('disabled');
        el.style.display = 'block';
        el.style.visibility = 'visible';
        el.value = arguments[1];
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
    """, el, deger)


def _sekme_ac(driver, *isimler):
    sekmeler = driver.find_elements(By.CSS_SELECTOR, "ul.nav-tabs a, .nav-tabs li a")
    for isim in isimler:
        for a in sekmeler:
            metin = a.text.strip().lower()
            if metin == isim.lower() or isim.lower() in metin:
                driver.execute_script("arguments[0].click();", a)
                time.sleep(0.8)
                return True
        for sel in [f"a[href='#{isim}']", f"a[href*='{isim}']"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script("arguments[0].click();", el)
                time.sleep(0.8)
                return True
            except Exception:
                pass
    return False


def _autocomplete_sec(driver, el, deger):
    el.clear()
    for harf in deger[:5]:
        el.send_keys(harf)
        time.sleep(0.3)
    time.sleep(2)
    for sel in ["ul.dropdown-menu li a", ".dropdown-menu li a",
                "ul.typeahead li a", ".autocomplete li a"]:
        try:
            dd = WebDriverWait(driver, 2).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
            driver.execute_script("arguments[0].click();", dd)
            return True
        except Exception:
            pass
    el.send_keys(Keys.RETURN)
    time.sleep(0.5)
    return False


def _resim_yukle(driver, resim_url, sira):
    try:
        resp = _req.get(resim_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200 or len(resp.content) < 5000:
            return False
        tmp = os.path.join(tempfile.gettempdir(), f"xtechnx_r{sira}_{int(time.time())}.jpg")
        with open(tmp, "wb") as f:
            f.write(resp.content)
        try:
            label = driver.find_element(By.CSS_SELECTOR, "label#byPc")
            for_id = label.get_attribute("for") or ""
            if for_id:
                file_input = driver.find_element(By.ID, for_id)
            else:
                file_input = driver.find_element(
                    By.CSS_SELECTOR, "#drop-files input[type='file'], #frm input[type='file']")
            file_input.send_keys(tmp)
            time.sleep(2)
        except Exception as e:
            print(f"[xtechnx] Resim input hatasi ({sira}): {e}")
            return False
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass
        for _ in range(3):
            try:
                alert = driver.switch_to.alert
                alert.accept()
                time.sleep(0.5)
            except Exception:
                break
        return True
    except Exception as e:
        print(f"[xtechnx] Resim yukle hatasi ({sira}): {e}")
        return False


# ── Ana Yükleme Fonksiyonu ────────────────────────────────────

def _urun_ekle_sync(p: Product) -> dict:
    global _driver
    driver = _get_driver()
    if not _oturum_kontrol(driver):
        return {"status": "error", "message": "Admin girisi basarisiz"}

    driver.get(_ekle_url())
    time.sleep(3)

    baslik  = p.title[:200]
    fiyat   = str(round(p.price, 2))
    aciklama_html = (p.description or "").replace("\n", "<br>")[:5000]
    sku     = p.sku or ("XTX-" + hashlib.md5(p.title.encode()).hexdigest()[:8].upper())
    barkod  = p.barcode or ""
    kategori = p.category or ""

    try:
        # ── Sekme 1: Genel ──────────────────────────────────────
        _sekme_ac(driver, "tab-general", "tab-description", "genel", "general")

        ad = None
        for sel in ["input[name='product_description[1][name]']",
                    "input[name='product_description[2][name]']",
                    "input[id^='input-name']", "#input-name1", "#input-name"]:
            try:
                ad = WebDriverWait(driver, 4).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                break
            except Exception:
                pass
        if not ad:
            for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='text']"):
                if inp.is_displayed() and inp.is_enabled():
                    ad = inp
                    break
        if not ad:
            return {"status": "error", "message": "Urun adi alani bulunamadi"}
        _js_yaz(driver, ad, baslik)

        # Açıklama
        try:
            sonuc = driver.execute_script("""
                if(typeof tinymce !== 'undefined' && tinymce.editors.length > 0) {
                    tinymce.editors[0].setContent(arguments[0]);
                    return tinymce.editors[0].getContent().length;
                }
                return 0;
            """, aciklama_html)
            if not sonuc:
                iframeler = driver.find_elements(By.CSS_SELECTOR, "iframe")
                for iframe in iframeler:
                    try:
                        driver.switch_to.frame(iframe)
                        body = driver.find_element(By.CSS_SELECTOR, "body")
                        driver.execute_script(
                            "arguments[0].innerHTML = arguments[1];", body, aciklama_html)
                        driver.switch_to.default_content()
                        break
                    except Exception:
                        driver.switch_to.default_content()
        except Exception:
            pass

        # ── Sekme 2: Detay ──────────────────────────────────────
        _sekme_ac(driver, "tab-data", "tab-detay", "detay", "data")

        for sel in ["input[name='model']", "#input-model"]:
            try:
                _js_yaz(driver, driver.find_element(By.CSS_SELECTOR, sel), sku)
                break
            except Exception:
                pass

        for sel in ["input[name='price']", "#input-price"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    _js_yaz(driver, el, fiyat)
                    break
            except Exception:
                pass

        # %20 KDV
        for sel in ["select[name='tax_class_id']", "#input-tax-class"]:
            try:
                s = driver.find_element(By.CSS_SELECTOR, sel)
                if s.is_displayed():
                    secim = Select(s)
                    for opt in secim.options:
                        if "20" in opt.text:
                            secim.select_by_value(opt.get_attribute("value"))
                            break
                    break
            except Exception:
                pass

        for sel in ["input[name='quantity']", "#input-quantity"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    _js_yaz(driver, el, str(p.stock or 1))
                    break
            except Exception:
                pass

        if barkod:
            for sel in ["input[name='ean']", "#input-ean",
                        "input[name='upc']", "#input-upc"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        _js_yaz(driver, el, barkod)
                        break
                except Exception:
                    pass

        for sel in ["select[name='status']", "#input-status"]:
            try:
                Select(driver.find_element(By.CSS_SELECTOR, sel)).select_by_value("1")
                break
            except Exception:
                pass

        # ── Sekme 3: Bağlantılar ────────────────────────────────
        _sekme_ac(driver, "tab-links", "tab-baglantilar", "baglantilar", "links")
        time.sleep(1)

        for sel in ["#input-manufacturer", "input[name='manufacturer']"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    _autocomplete_sec(driver, el, MARKA)
                    break
            except Exception:
                pass

        if kategori:
            aranan = kategori.lower().strip()
            checkboxlar = driver.find_elements(By.CSS_SELECTOR, "input[name='product_category[]']")
            for cb in checkboxlar:
                try:
                    etiket = ""
                    for xpath in ["following-sibling::label", "..", "../.."]:
                        try:
                            etiket = cb.find_element(By.XPATH, xpath).text.strip().lower()
                            if etiket:
                                break
                        except Exception:
                            pass
                    if aranan in etiket or etiket in aranan:
                        if not cb.is_selected():
                            driver.execute_script("arguments[0].click();", cb)
                        break
                except Exception:
                    pass

        # ── Sekme 4: Resim ──────────────────────────────────────
        _sekme_ac(driver, "tab-image", "tab-resim", "resim", "image")
        time.sleep(1)

        for i, resim_url in enumerate(p.images[:5], 1):
            _resim_yukle(driver, resim_url, i)
            time.sleep(1)

        # ── Kaydet ──────────────────────────────────────────────
        if "login" in driver.current_url.lower():
            _admin_giris(driver)
            driver.get(_ekle_url())
            time.sleep(2)

        kaydet = None
        for sel in ["button[data-original-title='Kaydet']", "button[data-original-title='Save']",
                    "#button-save"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    kaydet = el
                    break
            except Exception:
                pass
        if not kaydet:
            for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                d = (btn.get_attribute("data-original-title") or "").lower()
                t = btn.text.lower()
                if ("kaydet" in t or "save" in t or "kaydet" in d) and btn.is_displayed():
                    kaydet = btn
                    break

        if kaydet:
            driver.execute_script("arguments[0].click();", kaydet)
        else:
            driver.execute_script("document.querySelector('form').submit();")

        time.sleep(4)
        for _ in range(3):
            try:
                driver.switch_to.alert.accept()
                time.sleep(0.5)
            except Exception:
                break

        src = driver.page_source
        if 'alert-success' in src:
            return {"status": "success", "message": f"xtechnx.com'a yuklendi: {baslik[:50]}"}
        if 'alert-danger' in src or 'alert-error' in src:
            return {"status": "error", "message": "Admin panel kaydetme hatasi"}
        return {"status": "success", "message": f"xtechnx.com'a yuklendi (kontrol edin): {baslik[:50]}"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


class XtechnxSiteUploader:

    async def upload(self, product: Product) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(_urun_ekle_sync, product))
