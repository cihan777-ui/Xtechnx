"""
Merter kategori adını N11 alt kategori ID'sine çevirir.
Öncelik: 1) DB manuel mapping  2) Anahtar kelime eşleştirme  3) Varsayılan
"""

# Anahtar kelime → N11 leaf category ID
KEYWORD_MAP = {
    # Adaptör / Şarj / Pil
    "adaptör": 1000544,
    "adaptor": 1000544,
    "şarj": 1000544,
    "pil": 1000542,
    "akü": 1000542,
    "güç kaynağı": 1000544,

    # Televizyon
    "televizyon": 1000558,
    " tv ": 1000558,
    "smart tv": 1000558,
    "led tv": 1000558,
    "tv aksesuarı": 1000565,
    "tv stand": 1000565,
    "projeksiyon": 1246200,

    # Ses
    "hoparlör": 1000557,
    "ses sistemi": 1000557,
    "bluetooth hoparlör": 1165207,
    "müzik sistemi": 1000528,
    "mp3": 1000523,
    "mp4": 1000523,
    "dvd": 1000515,
    "blu-ray": 1000515,
    "uydu alıcı": 1000576,
    "uydu": 1000576,

    # Oto
    "oto ses": 1003054,
    "araç ses": 1003054,
    "oto elektronik": 1003045,
    "araç elektronik": 1003045,
    "navigasyon": 1003042,
    "multimedya": 1003042,

    # Bilgisayar
    "dizüstü": 1000271,
    "laptop": 1000271,
    "notebook": 1000271,
    "tablet": 1000354,
    "yazıcı": 1000333,
    "tarayıcı": 1000333,
    "printer": 1000333,
    "modem": 1000274,
    "router": 1000274,
    "switch": 1000274,
    "ağ ürünü": 1000274,
    "klavye": 1000355,
    "mouse": 1000355,
    "çevre birimi": 1000355,
    "ofis elektroniği": 1000292,
    "bilgisayar bileşeni": 1000257,
    "ram": 1000257,
    "işlemci": 1000257,
    "ekran kartı": 1000257,
    "masaüstü": 1000273,

    # Ev aletleri
    "süpürge": 1000406,
    "ütü": 1000423,
    "mutfak aleti": 1000375,
    "blender": 1000375,
    "tost": 1000375,
    "hava temizleyici": 1278200,
    "nemlendirici": 1278200,
}

DEFAULT_N11_CATEGORY = 1000240  # Bilgisayar → Aksesuar → USB Aksesuarları


def get_n11_category(source_category: str, db_mapping: dict = None) -> int:
    """
    source_category: Merter'den gelen kategori adı
    db_mapping: {source_category: n11_id} şeklinde DB'den gelen manuel mapping
    """
    if db_mapping:
        # 1) Tam eşleşme
        if source_category in db_mapping:
            return db_mapping[source_category]

    lower = source_category.lower()

    # 2) Anahtar kelime eşleştirme
    for keyword, cat_id in KEYWORD_MAP.items():
        if keyword in lower:
            return cat_id

    # 3) Varsayılan
    return DEFAULT_N11_CATEGORY
