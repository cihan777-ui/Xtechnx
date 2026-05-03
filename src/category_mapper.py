"""
Merter kategori adını N11 alt kategori ID'sine çevirir.
Öncelik: 1) DB manuel mapping  2) Anahtar kelime eşleştirme  3) Varsayılan
"""
import logging
logger = logging.getLogger(__name__)

# Anahtar kelime → N11 leaf category ID
# ÖNEMLİ: Daha spesifik keyword'ler önce gelir (ilk eşleşme kazanır)
KEYWORD_MAP = {

    # ── TV YEDEK PARÇA ──────────────────────────────────────
    "led bar": 1000569,
    "tv panel": 1000569,
    "t-con board": 1000569,
    "lcd driver": 1000569,
    "lcd power board": 1000569,
    "lcd invertör": 1000569,
    "tv tamir": 1000569,
    "tv yedek": 1000569,
    "panel tamir": 1000569,
    "arçelik tv": 1000569,
    "beko tv": 1000569,
    "vestel tv": 1000569,
    "samsung tv": 1000569,
    "lg tv": 1000569,
    "philips tv": 1000569,

    # ── AYDINLATMA ──────────────────────────────────────────
    "led ampul": 1000616,
    "led floresan": 1000618,
    "led projektör": 1000629,
    "led spot": 1000629,
    "spot lamba": 1000629,
    "spot panel": 1000629,
    "şerit ve dekoratif": 1000623,
    "şerit led": 1000623,
    "neon şerit": 1000623,
    "hortum led": 1000623,
    "dekoratif led": 1000623,
    "solar aydınlatma": 1217206,
    "gece lamb": 1000624,
    "masa lambası": 1000627,
    "tavan lamba": 1149100,
    "avize": 1000621,
    "sarkıt": 1000621,
    "armatür": 1000620,
    "aplik": 1000619,
    "lambader": 1000625,
    "abajur": 1000606,
    "tuz lamba": 1000630,
    "floresan": 1000618,
    "ampul": 1000615,
    "spot": 1000629,
    "el feneri": 1000240,
    "şarjlı lamba": 1000240,
    "cob led": 1000240,
    "aydınlatma": 1000240,

    # ── UYDU & ANTEN ────────────────────────────────────────
    "uydu kumanda": 1000572,
    "alıcı kumanda": 1000572,
    "receiver kumanda": 1000572,
    "uydu alıcı": 1000576,
    "uydu santrali": 1000575,
    "anten santral": 1000575,
    "diseqc": 1000575,
    "çanak anten": 1000575,
    "lnb": 1000575,
    "f konnektör": 1000570,
    "konnektör": 1000570,
    "koaksiyel": 1000570,
    "anten kablo": 1000570,
    "rg6": 1000570,
    "rg59": 1000570,
    "çatı anten": 1000570,
    "uydu ekipman": 1000575,
    "uydu": 1000576,

    # ── TELEVİZYON & SES ────────────────────────────────────
    "smart tv": 1000558,
    "led tv": 1000558,
    "televizyon": 1000558,
    "projeksiyon": 1246200,
    "megafon": 1000240,
    "anons cihaz": 1000240,
    "bluetooth hoparlör": 1165207,
    "gaming hoparlör": 1000370,
    "alçıpan hoparlör": 1000557,
    "trafolu hoparlör": 1000557,
    "seslendirme hoparlör": 1000557,
    "hoparlör": 1000557,
    "soundbar": 1000554,
    "seslendirme amfi": 1000550,
    "amfi ve mixer": 1000550,
    "taşınabilir amfi": 1000550,
    "amfi": 1000550,
    "ses sistem": 1000545,
    "seslendirme": 1000545,
    "cami ses": 1000545,
    "müzik sistemi": 1000528,
    "taşınabilir radyo": 1000534,
    "mp3": 1000523,
    "mp4": 1000523,
    "dvd": 1000515,
    "blu-ray": 1000515,
    "scart": 1000570,
    "hdmi": 1000570,
    "görüntü kablo": 1000570,
    "tv kablo": 1000570,
    "tv kumanda": 1000572,
    "televizyon kumanda": 1000572,
    "akıllı kumanda": 1000572,
    "uzaktan kumanda": 1000572,
    "tv askı": 1000568,
    "tv aksesuarı": 1000565,
    "tv stand": 1000565,

    # ── OTO ─────────────────────────────────────────────────
    "oto amfi": 1003055,
    "oto hoparlör": 1003058,
    "subwoofer": 1003059,
    "oto teyp": 1003056,
    "double teyp": 1003056,
    "fm transmitter": 1003057,
    "oto ses": 1003054,
    "araç ses": 1003054,
    "araç kamera": 1003047,
    "araç kayıt": 1003047,
    "araç tv": 1003052,
    "oto konvertör": 1003045,
    "oto anten": 1003045,
    "oto elektronik": 1003045,
    "araç elektronik": 1003045,
    "motosiklet": 1002993,
    "navigasyon": 1003042,
    "multimedya": 1003042,

    # ── GÜVENLİK & KAMERA ───────────────────────────────────
    "güvenlik kamera": 1000240,
    "ip kamera": 1000240,
    "ahd kamera": 1000240,
    "dome kamera": 1000240,
    "bullet kamera": 1000240,
    "wifi kamera": 1000240,
    "maket kamera": 1000240,
    "fotokapan": 1000240,
    "yılan kamera": 1000240,
    "aksiyon kamera": 1000240,
    "kamera test": 1000240,
    "dvr kayıt": 1000298,
    "nvr kayıt": 1000298,
    "hibrit kayıt": 1000298,
    "ahd kayıt": 1000298,
    "kayıt cihaz": 1000298,
    "alarm kablo": 1000305,
    "kapı zili": 1000305,
    "akıllı kilit": 1000305,
    "güvenlik sistem": 1000305,
    "güvenlik ekipman": 1000305,
    "alarm sistem": 1000305,

    # ── TELEFON & AKSESUARLAR ───────────────────────────────
    "powerbank": 1076100,
    "taşınabilir şarj": 1076100,
    "bluetooth kulaklık": 1000479,
    "kablosuz kulaklık": 1000479,
    "telsiz kulaklık": 1000479,
    "telefon kulaklık": 1000490,
    "kablolu kulaklık": 1000490,
    "hafıza kartı": 1000483,
    "sd kart": 1000483,
    "kart okuyucu": 1000483,
    "ekran koruyucu": 1000482,
    "kırılmaz ekran": 1000482,
    "telefon kılıf": 1000491,
    "araç tutucu": 1000478,
    "telefon tutucu": 1000478,
    "selfie": 1089102,
    "akıllı saat": 1000474,
    "akıllı bileklik": 1071100,
    "data-şarj kablo": 1000486,
    "telefon kablo": 1000486,
    "cep telefonu aksesuarı": 1000477,
    "telefon ve aksesuar": 1000477,
    "telefon aksesuarı": 1000477,

    # ── BİLGİSAYAR ──────────────────────────────────────────
    "all in one": 1000273,
    "masaüstü": 1000273,
    "dizüstü": 1000271,
    "laptop": 1000271,
    "notebook": 1000271,
    "tablet pc": 1000354,
    "tablet": 1000354,
    "gaming monitör": 1000368,
    "monitör": 1000368,
    "webcam": 1000372,
    "web kamera": 1000372,
    "ups güç": 1000371,
    "ups": 1000371,
    "gaming klavye": 1000361,
    "klavye & mouse set": 1000362,
    "klavye": 1000361,
    "gaming mouse": 1000363,
    "mouse pad": 1000369,
    "mouse": 1000363,
    "gaming kulaklık": 1000364,
    "kulaklık": 1000364,
    "mikrofon": 1000366,
    "barkod yazıcı": 1000340,
    "barkod okuyucu": 1000294,
    "barkod": 1000294,
    "yazıcı kablo": 1000333,
    "yazıcı": 1000333,
    "tarayıcı": 1000333,
    "access point": 1000286,
    "ethernet switch": 1000236,
    "kvm switch": 1000236,
    "patch panel": 1000236,
    "fiber optik": 1000236,
    "wireless adaptör": 1000240,
    "network kablo": 1000236,
    "cat5": 1000236,
    "cat6": 1000236,
    "cat7": 1000236,
    "ethernet kablo": 1000236,
    "ethernet": 1000236,
    "lan kablosu": 1000236,
    "modem": 1000240,
    "router": 1000240,
    "ağ ürünü": 1000236,
    "ssd harddisk": 1000264,
    "ssd": 1000264,
    "hard disk": 1000264,
    "harddisk": 1000264,
    "harddisk kutusu": 1000357,
    "taşınabilir disk": 1000352,
    "usb bellek": 1000353,
    "flash bellek": 1000353,
    "bilgisayar bileşen": 1000257,
    "ekran kartı": 1000257,
    "işlemci": 1000257,
    "ram": 1000257,
    "notebook adaptör": 1000231,
    "laptop adaptör": 1000231,
    "notebook power": 1000231,
    "bilgisayar kablo": 1000236,
    "display kablo": 1000236,
    "vga kablo": 1000236,
    "çevre birimi": 1000355,
    "oem ve çevre": 1000355,
    "oyun ekipman": 1000359,
    "gaming aksesuar": 1000359,

    # ── ADAPTÖR / ŞAR / PİL ─────────────────────────────────
    "şarj regülatör": 1000544,
    "akü şarj": 1000544,
    "pil şarj": 1000544,
    "şarj cihazı": 1000495,
    "adaptör": 1000544,
    "adaptor": 1000544,
    "güç kaynağı": 1000544,
    "şarj": 1000544,
    "jel akü": 1000542,
    "lityum akü": 1000542,
    "kuru akü": 1000542,
    "elektrikli bisiklet akü": 1000542,
    "akü": 1000542,
    "pil": 1000542,

    # ── İNVERTÖR / ELEKTRİK ─────────────────────────────────
    "solar için invertör": 1000212,
    "solar enerji": 1000212,
    "invertör": 1000212,
    "konvertör": 1000212,
    "çevirici ve dönüştürücü": 1000212,
    "çevirici dağıtıcı": 1000212,
    "çevirici": 1000212,
    "dönüştürücü": 1000212,
    "regülatör": 1000212,
    "güneş paneli": 1000212,
    "transformatör": 1149101,
    "trafo": 1149101,
    "elektrik aksesuarı": 1149101,
    "akım korumalı": 1149101,
    "priz ve bağlantı": 1149101,
    "priz": 1149101,
    "fişler": 1149101,

    # ── KİŞİSEL BAKIM ───────────────────────────────────────
    "kişisel bakım": 1000430,
    "masaj": 1000430,
    "saç kurutma": 1000430,
    "epilasyon": 1000430,
    "tıraş": 1000430,
    "saç düzleştirici": 1000430,
    "saç şekillendirici": 1000430,

    # ── EV ALETLERİ ─────────────────────────────────────────
    "robot süpürge": 1140100,
    "süpürge": 1000406,
    "ütü": 1000423,
    "tost": 1000402,
    "waffle": 1000403,
    "blender": 1000395,
    "mikser": 1000393,
    "fritöz": 1000386,
    "kahve makine": 1137101,
    "kettle": 1000400,
    "su ısıtıcı": 1000400,
    "küçük ev aleti": 1000375,
    "mutfak aleti": 1000375,
    "hava temizleyici": 1278201,
    "nemlendirici": 1279200,
    "dikiş": 1251200,

    # ── ÖLÇÜ & TAMİR ALETLERİ ───────────────────────────────
    "ölçü aleti": 1000292,
    "termometre": 1000292,
    "wattmetre": 1000292,
    "multimetre": 1000292,
    "pensampermetre": 1000292,
    "mesafe ölçer": 1000292,
    "kablo test": 1000292,
    "kablo bulucu": 1000292,
    "sahte para kontrol": 1000292,
    "hesap makinesi": 1000292,
}

DEFAULT_N11_CATEGORY = 1000240  # Bilgisayar → Aksesuar → USB Aksesuarları

# Hepsiburada kategori ID'leri (Elektronik ağırlıklı)
HB_KEYWORD_MAP = {
    # ── TV & GÖRÜNTÜ ────────────────────────────────────────
    "led tv": "60000072",
    "smart tv": "60000072",
    "televizyon": "60000072",
    "tv panel": "60000075",
    "tv yedek": "60000075",
    "led bar": "60000075",
    "projeksiyon": "60000074",
    "tv kumanda": "60001094",
    "uzaktan kumanda": "60001094",
    "tv askı": "60001094",
    "tv aksesuarı": "60001094",

    # ── SES SİSTEMLERİ ───────────────────────────────────────
    "soundbar": "60000084",
    "hoparlör": "60000082",
    "bluetooth hoparlör": "60000082",
    "amfi": "60000081",
    "ses sistem": "60000081",
    "kulaklık": "60000086",
    "bluetooth kulaklık": "60000086",
    "kablosuz kulaklık": "60000086",
    "gaming kulaklık": "60000086",
    "mikrofon": "60000088",

    # ── AYDINLATMA ───────────────────────────────────────────
    "led ampul": "60002048",
    "ampul": "60002048",
    "floresan": "60002048",
    "led floresan": "60002048",
    "avize": "60002042",
    "sarkıt": "60002042",
    "tavan lamba": "60002044",
    "aplik": "60002043",
    "masa lambası": "60002046",
    "lambader": "60002045",
    "led spot": "60002049",
    "spot lamba": "60002049",
    "led projektör": "60002049",
    "şerit led": "60002050",
    "neon şerit": "60002050",
    "dekoratif led": "60002050",
    "solar aydınlatma": "60002051",
    "el feneri": "60002051",
    "aydınlatma": "60002041",

    # ── UYDU & ANTEN ────────────────────────────────────────
    "uydu kumanda": "60001094",
    "alıcı kumanda": "60001094",
    "receiver kumanda": "60001094",
    "uydu alıcı": "60000078",
    "uydu": "60000078",
    "çanak anten": "60000079",
    "lnb": "60000079",
    "anten": "60000079",
    "koaksiyel": "60001094",
    "hdmi": "60001094",
    "görüntü kablo": "60001094",

    # ── GÜVENLİK & KAMERA ───────────────────────────────────
    "güvenlik kamera": "60000477",
    "ip kamera": "60000477",
    "ahd kamera": "60000477",
    "wifi kamera": "60000477",
    "dvr kayıt": "60000478",
    "nvr kayıt": "60000478",
    "kayıt cihaz": "60000478",
    "alarm sistem": "60000479",
    "güvenlik sistem": "60000479",

    # ── TELEFON & AKSESUARLAR ───────────────────────────────
    "powerbank": "60001184",
    "taşınabilir şarj": "60001184",
    "hafıza kartı": "60001185",
    "sd kart": "60001185",
    "kart okuyucu": "60001185",
    "ekran koruyucu": "60001186",
    "kırılmaz ekran": "60001186",
    "telefon kılıf": "60001187",
    "araç tutucu": "60001188",
    "telefon tutucu": "60001188",
    "akıllı saat": "60001189",
    "telefon kablo": "60001190",
    "şarj kablosu": "60001190",
    "data kablo": "60001190",
    "telefon aksesuarı": "60001183",

    # ── BİLGİSAYAR ──────────────────────────────────────────
    "laptop": "60000138",
    "dizüstü": "60000138",
    "notebook": "60000138",
    "masaüstü": "60000139",
    "all in one": "60000139",
    "tablet": "60000141",
    "monitör": "60000143",
    "gaming monitör": "60000143",
    "klavye": "60000147",
    "mouse": "60000148",
    "webcam": "60000150",
    "ups": "60000151",
    "ssd": "60000156",
    "hard disk": "60000156",
    "harddisk": "60000156",
    "usb bellek": "60000157",
    "flash bellek": "60000157",
    "yazıcı": "60000159",
    "barkod okuyucu": "60000160",
    "barkod yazıcı": "60000160",
    "modem": "60001671",
    "router": "60001671",
    "ethernet switch": "60001671",
    "ethernet kablo": "60001671",
    "ethernet": "60001671",
    "lan kablosu": "60001671",
    "ağ kablosu": "60001671",
    "access point": "60001671",
    "network kablo": "60001671",
    "cat5": "60001671",
    "cat6": "60001671",
    "bilgisayar soğutma": "60001094",
    "pc fan": "60001094",
    "dc fan": "60001094",
    "vantilatör": "60001094",
    "kasa fanı": "60001094",
    "soğutucu fan": "60001094",
    "bilgisayar": "60001094",

    # ── OTO ELEKTRONİK ──────────────────────────────────────
    "oto teyp": "60001068",
    "double teyp": "60001068",
    "oto hoparlör": "60001069",
    "oto amfi": "60001070",
    "subwoofer": "60001070",
    "fm transmitter": "60001071",
    "araç kamera": "60001072",
    "navigasyon": "60001073",
    "oto elektronik": "60001067",
    "araç elektronik": "60001067",

    # ── ADAPTÖR / ŞARJ / PİL ────────────────────────────────
    "akü şarj": "60002060",
    "pil şarj": "60002060",
    "şarj cihazı": "60002060",
    "adaptör": "60002060",
    "güç kaynağı": "60002060",
    "akü": "60002061",
    "pil": "60002061",
    "invertör": "60002062",
    "konvertör": "60002062",
    "solar enerji": "60002062",
    "güneş paneli": "60002062",
    "regülatör": "60002063",
    "transformatör": "60002063",
    "trafo": "60002063",
    "priz": "60002063",
    "elektrik aksesuarı": "60002063",

    # ── KİŞİSEL BAKIM ───────────────────────────────────────
    "saç kurutma": "60000424",
    "epilasyon": "60000425",
    "tıraş": "60000426",
    "masaj": "60000427",
    "kişisel bakım": "60000423",

    # ── EV ALETLERİ ─────────────────────────────────────────
    "robot süpürge": "60000390",
    "süpürge": "60000391",
    "blender": "60000380",
    "kahve makine": "60000381",
    "kettle": "60000382",
    "su ısıtıcı": "60000382",
    "ütü": "60000383",
    "küçük ev aleti": "60000375",
    "mutfak aleti": "60000375",
}

DEFAULT_HB_CATEGORY = "60001671"  # Bilgisayar > Ağ Ürünleri (güvenilir fallback)


def get_hepsiburada_category(source_category: str, db_mapping: dict = None) -> str:
    if db_mapping:
        normalized = source_category.strip().lower()
        for db_key, db_id in db_mapping.items():
            if db_key.strip().lower() == normalized and db_id:
                logger.info("HB Kategori DB mapping: '%s' → %s", source_category, db_id)
                return str(db_id)

    lower = source_category.strip().lower()
    for keyword, cat_id in HB_KEYWORD_MAP.items():
        if keyword in lower:
            logger.info("HB Kategori keyword eşleşti: '%s' → ID %s", source_category, cat_id)
            return cat_id

    logger.warning(
        "HB KATEGORİ EŞLEŞMEDİ: '%s' → varsayılan ID %s. "
        "Doğru ID için /hepsiburada-categories endpoint'ini kullanın.",
        source_category, DEFAULT_HB_CATEGORY
    )
    return DEFAULT_HB_CATEGORY


def get_n11_category(source_category: str, db_mapping: dict = None) -> int:
    """
    source_category: Merter'den gelen kategori adı
    db_mapping: {source_category: n11_id} şeklinde DB'den gelen manuel mapping
    """
    if db_mapping:
        normalized = source_category.strip().lower()
        for db_key, db_id in db_mapping.items():
            if db_key.strip().lower() == normalized:
                logger.info("Kategori DB mapping: '%s' → %s", source_category, db_id)
                return db_id

    lower = source_category.strip().lower()

    for keyword, cat_id in KEYWORD_MAP.items():
        if keyword in lower:
            logger.info("Kategori keyword eşleşti: '%s' içinde '%s' → ID %s", source_category, keyword, cat_id)
            return cat_id

    logger.warning(
        "KATEGORİ EŞLEŞMEDİ: '%s' → varsayılan ID %s (USB Aksesuarları). "
        "Doğru ID için /categories endpoint'ini kullanın.",
        source_category, DEFAULT_N11_CATEGORY
    )
    return DEFAULT_N11_CATEGORY
