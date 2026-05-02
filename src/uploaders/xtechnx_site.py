"""
xtechnx.com admin paneline Selenium ile urun yukler.
Admin oturumu modulun omru boyunca tek bir driver'da tutulur.
"""
import re
import time
import hashlib
import asyncio
import os
import logging
from functools import partial

log = logging.getLogger(__name__)

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
        log.info("[xtechnx] Admin giris hatasi: {e}")
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
    # data-toggle="tab" — Bootstrap tab linkleri, başka nav linklerine karışmaz
    tum_sekmeler = driver.find_elements(By.CSS_SELECTOR, "a[data-toggle='tab']")
    for isim in isimler:
        for a in tum_sekmeler:
            metin = a.text.strip()
            if metin.lower() == isim.lower() or isim.lower() in metin.lower():
                driver.execute_script("arguments[0].click();", a)
                time.sleep(0.8)
                return True
        try:
            el = driver.find_element(By.CSS_SELECTOR, f"a[href='#{isim}'][data-toggle='tab']")
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
    return False


def _resim_yukle(driver, resim_url, sira):
    """v2.py bypc_ile_yukle — resmi Desktop'a indir, label#byPc ile yukle."""
    try:
        resp = _req.get(resim_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200 or len(resp.content) < 5000:
            log.info(f"[xtechnx] Resim {sira}: indirilemedi ({resp.status_code}, {len(resp.content)} byte)")
            return False

        dosya_yolu = os.path.join(os.path.expanduser("~"), "Desktop", f"r{sira}_{int(time.time())}.jpg")
        with open(dosya_yolu, "wb") as f:
            f.write(resp.content)
        log.info(f"[xtechnx] Resim {sira}: indirildi ({len(resp.content)} byte) -> {dosya_yolu}")

        try:
            # Önce #file-input direkt dene, sonra label#byPc yolu
            file_input = None
            for sel in ["#file-input", "label#byPc", "#drop-files input[type='file']"]:
                try:
                    if sel == "label#byPc":
                        label = driver.find_element(By.CSS_SELECTOR, sel)
                        for_id = label.get_attribute("for") or ""
                        file_input = driver.find_element(By.ID, for_id) if for_id else None
                    else:
                        file_input = driver.find_element(By.CSS_SELECTOR, sel)
                    if file_input:
                        log.info(f"[xtechnx] Resim {sira}: file input bulundu ({sel})")
                        break
                except Exception:
                    pass

            if not file_input:
                log.info(f"[xtechnx] Resim {sira}: file input bulunamadi")
                try: os.unlink(dosya_yolu)
                except: pass
                return False

            driver.execute_script("arguments[0].style.display='block';arguments[0].style.visibility='visible';", file_input)
            file_input.send_keys(dosya_yolu)
            log.info(f"[xtechnx] Resim {sira}: dosya gonderildi")
            time.sleep(3)
        except Exception as e:
            log.info(f"[xtechnx] Resim {sira}: upload hatasi: {e}")
            try: os.unlink(dosya_yolu)
            except: pass
            return False

        try:
            alert = driver.switch_to.alert
            alert_txt = alert.text.strip()[:60]
            alert.accept()
            log.info(f"[xtechnx] Resim {sira}: alert: {alert_txt}")
            time.sleep(0.5)
            if "error" in alert_txt.lower() or "undefined" in alert_txt.lower():
                try: os.unlink(dosya_yolu)
                except: pass
                return False
        except Exception:
            pass

        try: os.unlink(dosya_yolu)
        except: pass
        return True

    except Exception as e:
        log.info(f"[xtechnx] Resim {sira}: genel hata: {e}")
        return False


# ── Ana Yükleme Fonksiyonu ────────────────────────────────────

def _urun_ekle_sync(p: Product) -> dict:
    global _driver
    driver = _get_driver()
    if not _oturum_kontrol(driver):
        return {"status": "error", "message": "Admin girisi basarisiz"}

    driver.get(_ekle_url())
    time.sleep(3)
    try:
        sc_path = os.path.join(os.path.expanduser("~"), "Desktop", "product-sync", "logs", "xtechnx_form_yuklendi.png")
        driver.save_screenshot(sc_path)
        html_path = os.path.join(os.path.expanduser("~"), "Desktop", "product-sync", "logs", "xtechnx_form.html")
        with open(html_path, "w", encoding="utf-8") as _f:
            _f.write(driver.page_source)
        log.info(f"[xtechnx] Screenshot ve HTML kaydedildi")
    except Exception as _e:
        log.info(f"[xtechnx] Screenshot hatasi: {_e}")

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
        # jQuery Bootstrap tab API ile aktive et
        driver.execute_script("""
            var $tab = (typeof jQuery !== 'undefined') && jQuery('a[href="#tab-image"]');
            if ($tab && $tab.length) { $tab.tab('show'); }
            else {
                var a = document.querySelector('a[href="#tab-image"]');
                if (a) a.click();
            }
        """)
        time.sleep(2)

        # DOM'da ne var logla
        check = driver.execute_script("""
            return {
                byPc: !!document.querySelector('label#byPc'),
                fileInput: !!document.querySelector('#file-input'),
                tabActive: !!(document.querySelector('#tab-image.active') || document.querySelector('#tab-image.in')),
                tabPaneDisplay: (document.querySelector('#tab-image') || {}).style && (document.querySelector('#tab-image')).offsetParent !== null
            };
        """)
        log.info(f"[xtechnx] DOM check: {check}")

        sc_path = os.path.join(os.path.expanduser("~"), "Desktop", "product-sync", "logs", "xtechnx_resim_tab.png")
        try:
            driver.save_screenshot(sc_path)
        except Exception:
            pass

        if p.images:
            log.info(f"[xtechnx] Resimler yukleniyor ({len(p.images[:5])} adet)...")
            for i, resim_url in enumerate(p.images[:5], 1):
                basarili = _resim_yukle(driver, resim_url, i)
                log.info(f"[xtechnx] Resim {i}: {'OK' if basarili else 'BASARISIZ'}")
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
