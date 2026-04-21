import urllib.request
import json

key = 'f4e48bee-666c-4f1b-8182-2cddad031b1d'
secret = 'I70eoqICiJRqZwHi'

req = urllib.request.Request(
    'https://api.n11.com/ms/product/categories',
    headers={'appkey': key, 'appsecret': secret}
)

print("N11 API'ye baglaniliyor...")
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
        data = json.loads(raw)
    print("Baglandı! Kategoriler aranıyor...\n")
except Exception as e:
    print("HATA:", e)
    input("Enter'a basin...")
    exit()

def search(cats, path=''):
    for c in cats:
        name = c.get('name', '')
        cid  = c.get('id', '')
        full = (path + ' > ' + name).lstrip(' > ')
        if any(k in full.lower() for k in ['sulama', 'bahce', 'bahçe', 'yapi', 'yapı']):
            print(str(cid).ljust(12), full)
        sub = c.get('subCategories') or c.get('children') or []
        search(sub, full)

cats = data if isinstance(data, list) else data.get('categories', data.get('data', []))
search(cats)

print("\nTamam!")
input("Enter'a basin...")
