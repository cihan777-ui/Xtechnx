# Xtechnx Product Sync — Kurulum & Kullanım

## EXE ile Kullanım (Önerilen)

### İlk Kurulum
1. `dist/` klasörünü istediğiniz bir yere kopyalayın
2. `XtechnxProductSync.exe` dosyasını çalıştırın
3. Tarayıcı otomatik açılır → `http://localhost:8000`
4. **Ayarlar** sekmesinden API anahtarlarınızı girin

### Klasör Yapısı (EXE yanında oluşur)
```
XtechnxProductSync.exe
.env                  ← API anahtarları (otomatik oluşur)
barcodes/             ← Okutulan barkodlar
data/                 ← SQLite veritabanı
logs/                 ← Uygulama logları
reports/              ← Excel raporlar
```

### Sistem Gereksinimleri
- Windows 10 / 11 (64-bit)
- .NET Framework 4.x (genellikle yüklü gelir)
- İnternet bağlantısı (merterelektronik.com erişimi için)

---

## Geliştirici Kurulumu (kaynak kod)

```bat
kur.bat          ← Bağımlılıkları yükler
calistir.bat     ← Sunucuyu başlatır
exe_yap.bat      ← .exe üretir
```

---

## API Endpoint'leri

| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/` | Web arayüzü |
| POST | `/barcodes/add` | Barkod ekle |
| GET | `/barcodes` | Barkod listesi |
| POST | `/process` | Ürünleri çek & dönüştür |
| GET | `/pending` | Onay bekleyenler |
| POST | `/approve/{id}` | Onayla & platforma gönder |
| GET | `/history` | Yükleme geçmişi |
| GET | `/stats` | İstatistikler |
| POST | `/report` | Excel rapor oluştur |
| POST | `/sync/prices` | Fiyat senkronizasyonu |
| GET | `/categories` | Kategori eşleştirmeleri |
| GET | `/docs` | Swagger API dokümantasyonu |

---

## Dönüşüm Kuralları

| Alan | Kural | Örnek |
|------|-------|-------|
| Başlık | `Xtechnx ` + orijinal | `Xtechnx Samsung TV 55"` |
| Fiyat | Orijinal × 2 | `15.000 → 30.000 TL` |
| Barkod | `Xtechnx` + 6 rastgele rakam | `Xtechnx047291` |
| Stok Kodu | `Cihan` + aynı 6 rakam | `Cihan047291` |
