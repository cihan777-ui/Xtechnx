"""
ADIM 1: Sadece login yap, cookie'leri kaydet.
Calistirin, CAPTCHA cozerek giris yapin, Enter'a basin.
"""
import time, json, sys
from selenium import webdriver
from selenium.webdriver.common.by import By
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
wait = WebDriverWait(driver, 20)

print("Login sayfasi aciliyor...")
driver.get("https://merchant.hepsiburada.com/v2/login")
wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys("orhancihan17@hotmail.com")
wait.until(EC.presence_of_element_located((By.ID, "password"))).send_keys("Hb12345!")
wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.login-button"))).click()

print("\n>>> CAPTCHA gorununce cozerek giris yapin.")
print("    Giris sonrasi bu terminale gelin ve ENTER'a basin.")
print()

for i in range(120):
    time.sleep(1)
    url = driver.current_url
    if "merchant.hepsiburada.com" in url and "/login" not in url:
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
