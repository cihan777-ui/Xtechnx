"""
ADIM 1: Sadece login yap, cookie'leri kaydet.
"""
import time, json, sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

opts = Options()
opts.add_argument("--window-size=1400,900")
opts.add_argument("--start-maximized")
opts.add_argument("--disable-blink-features=AutomationControlled")
opts.add_experimental_option("excludeSwitches", ["enable-automation"])
opts.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
wait   = WebDriverWait(driver, 30)

print("Login sayfasi aciliyor...")
driver.get("https://merchant.hepsiburada.com/v2/login")

# Email doldur
print("Email giriliyor...")
email_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
email_field.send_keys("orhancihan17@hotmail.com")

# "Giris yap" butonuna tikla (orange buton)
print("Giris yap butonuna tiklaniyor...")
email_field.send_keys(Keys.RETURN)

# Sifre alani bekle (farkli ID olabilir, type=password ile bul)
print("Sifre alani bekleniyor...")
time.sleep(2)
pwd_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
print("Sifre alani bulundu, dolduruluyor...")
pwd_field.send_keys("emrchnCAN.18")
pwd_field.send_keys(Keys.RETURN)

print("\n>>> CAPTCHA gorununce cozerek giris yapin.")
print("    Giris otomatik algilanacak (120 saniye bekleniyor)...")

for i in range(120):
    time.sleep(1)
    url = driver.current_url
    if "merchant.hepsiburada.com" in url and "/login" not in url and "/v2/login" not in url:
        print(f"Otomatik algilama - Giris OK: {url}")
        break
    if i % 15 == 0 and i > 0:
        print(f"  {i}s... (hala login sayfasinda)")

# Cookie'leri kaydet
cookies = driver.get_cookies()
with open("hb_cookies.json", "w", encoding="utf-8") as f:
    json.dump(cookies, f, ensure_ascii=False, indent=2)
print(f"\n{len(cookies)} cookie kaydedildi -> hb_cookies.json")
print(f"Mevcut URL: {driver.current_url}")

driver.quit()
print("Hazir. Cookie yenilendi. Simdi hb_paketle.py calistirabilirsiniz.")
