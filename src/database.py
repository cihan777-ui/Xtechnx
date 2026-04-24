"""
SQLite veritabanı katmanı.
Tablolar:
  - upload_history   : Yüklenen ürünlerin kaydı
  - product_cache    : merterelektronik.com ürün önbelleği
  - category_mapping : Kullanıcı tanımlı kategori eşleştirmeleri
  - barcode_registry : Üretilen Xtechnx barkodları (duplicate koruması)
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/xtechnx.db")


def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Tabloları oluşturur (idempotent)."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS upload_history (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode_orig  TEXT,
        barcode_new   TEXT,
        sku_new       TEXT,
        title_orig    TEXT,
        title_new     TEXT,
        price_orig    REAL,
        price_new     REAL,
        platform      TEXT,
        status        TEXT,
        error_msg     TEXT,
        uploaded_at   TEXT
    );

    CREATE TABLE IF NOT EXISTS product_cache (
        barcode       TEXT PRIMARY KEY,
        url           TEXT,
        product_json  TEXT,
        cached_at     TEXT
    );

    CREATE TABLE IF NOT EXISTS category_mapping (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        source_category TEXT UNIQUE,
        trendyol_id     INTEGER DEFAULT 0,
        hepsiburada_id  TEXT DEFAULT '',
        n11_id          INTEGER DEFAULT 0,
        updated_at      TEXT
    );

    CREATE TABLE IF NOT EXISTS barcode_registry (
        barcode_new   TEXT PRIMARY KEY,
        barcode_orig  TEXT,
        created_at    TEXT
    );
    """)

    conn.commit()
    conn.close()


# ── Upload History ───────────────────────────────────────────

def record_upload(barcode_orig, barcode_new, sku_new, title_orig, title_new,
                  price_orig, price_new, platform, status, error_msg=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO upload_history
        (barcode_orig, barcode_new, sku_new, title_orig, title_new,
         price_orig, price_new, platform, status, error_msg, uploaded_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (barcode_orig, barcode_new, sku_new, title_orig, title_new,
          price_orig, price_new, platform, status, error_msg,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_history(limit=200, platform=None, status=None):
    conn = get_conn()
    query = "SELECT * FROM upload_history"
    params = []
    filters = []
    if platform:
        filters.append("platform = ?"); params.append(platform)
    if status:
        filters.append("status = ?"); params.append(status)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY uploaded_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history_stats():
    conn = get_conn()
    stats = {}
    for platform in ['trendyol', 'hepsiburada', 'n11', 'amazon']:
        row = conn.execute("""
            SELECT
              COUNT(*) as total,
              SUM(CASE WHEN status IN ('success','success_unconfirmed') THEN 1 ELSE 0 END) as success,
              SUM(CASE WHEN status='success_unconfirmed' THEN 1 ELSE 0 END) as unconfirmed,
              SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as error
            FROM upload_history WHERE platform=?
        """, (platform,)).fetchone()
        stats[platform] = dict(row)
    stats['total'] = conn.execute("SELECT COUNT(*) as n FROM upload_history").fetchone()['n']
    stats['today'] = conn.execute(
        "SELECT COUNT(*) as n FROM upload_history WHERE uploaded_at LIKE ?",
        (datetime.now().strftime('%Y-%m-%d') + '%',)
    ).fetchone()['n']
    conn.close()
    return stats


# ── Product Cache ────────────────────────────────────────────

def cache_product(barcode, url, product_dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO product_cache (barcode, url, product_json, cached_at)
        VALUES (?, ?, ?, ?)
    """, (barcode, url, json.dumps(product_dict, ensure_ascii=False),
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_cached_product(barcode):
    """Önbellekteki ürünü döner. 24 saatten eski ise None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM product_cache WHERE barcode=?", (barcode,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    # 24 saat kontrolü
    cached_at = datetime.fromisoformat(row['cached_at'])
    if (datetime.now() - cached_at).total_seconds() > 86400:
        return None
    return {'url': row['url'], 'product': json.loads(row['product_json'])}


def clear_cache():
    conn = get_conn()
    conn.execute("DELETE FROM product_cache")
    conn.commit()
    conn.close()


# ── Category Mapping ─────────────────────────────────────────

def get_category_mappings():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM category_mapping ORDER BY source_category").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_category_mapping(source_category, trendyol_id, hepsiburada_id, n11_id):
    conn = get_conn()
    conn.execute("""
        INSERT INTO category_mapping (source_category, trendyol_id, hepsiburada_id, n11_id, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_category) DO UPDATE SET
          trendyol_id=excluded.trendyol_id,
          hepsiburada_id=excluded.hepsiburada_id,
          n11_id=excluded.n11_id,
          updated_at=excluded.updated_at
    """, (source_category, trendyol_id, hepsiburada_id, n11_id,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_category_ids(source_category):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM category_mapping WHERE source_category=?",
        (source_category,)
    ).fetchone()
    conn.close()
    if row:
        return {'trendyol': row['trendyol_id'],
                'hepsiburada': row['hepsiburada_id'],
                'n11': row['n11_id']}
    return None


# ── Barcode Registry ─────────────────────────────────────────

def register_barcode(barcode_new, barcode_orig):
    """Yeni barkodu kaydeder. Zaten varsa False döner (duplicate)."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO barcode_registry (barcode_new, barcode_orig, created_at)
            VALUES (?, ?, ?)
        """, (barcode_new, barcode_orig, datetime.now().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def barcode_exists(barcode_new):
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM barcode_registry WHERE barcode_new=?", (barcode_new,)
    ).fetchone()
    conn.close()
    return row is not None


def get_barcode_by_orig(barcode_orig):
    """Orijinal barkoda karşılık gelen Xtechnx barkodunu döner, yoksa None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT barcode_new FROM barcode_registry WHERE barcode_orig=?", (barcode_orig,)
    ).fetchone()
    conn.close()
    return row[0] if row else None
