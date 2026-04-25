from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, ORJSONResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn, logging, uuid, asyncio, subprocess, sys, os, aiohttp
from pathlib import Path

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/app.log", encoding="utf-8")]
)
logger = logging.getLogger(__name__)

import database as db
import barcode_manager as bm
from config.settings import settings
from transformer import transform, preview
from app_config import get_config, set_config_value
from uploaders.trendyol import TrendyolUploader
from uploaders.hepsiburada import HepsiburadaUploader
from uploaders.n11 import N11Uploader
from uploaders.amazon import AmazonUploader

db.init_db()

app = FastAPI(title="Xtechnx Product Sync", version="4.0.0", default_response_class=ORJSONResponse)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

jobs: dict = {}
pending_approval: dict = {}
PARALLEL_LIMIT = 3


def _get_uploaders():
    return {
        "trendyol":    TrendyolUploader(),
        "hepsiburada": HepsiburadaUploader(),
        "n11":         N11Uploader(),
        "amazon":      AmazonUploader(),
    }


@app.get("/", response_class=HTMLResponse)
async def ui():
    candidates = [
        Path("src") / "ui.html",
        Path("ui.html"),
        Path(getattr(sys, "_MEIPASS", "")) / "src" / "ui.html",
    ]
    for f in candidates:
        if f.exists():
            return HTMLResponse(f.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>API çalışıyor → /docs</h1>")


# ── APP CONFIG ──────────────────────────────────────────────
@app.get("/settings/app-config")
async def get_app_config():
    return get_config()

class AppConfigIn(BaseModel):
    price_multiplier: Optional[float] = None
    source_site_selected: Optional[str] = None
    source_site_name: Optional[str] = None
    source_site_search_url: Optional[str] = None
    source_site_login_url: Optional[str] = None
    source_site_member_no: Optional[str] = None
    source_site_username: Optional[str] = None
    source_site_password: Optional[str] = None

@app.post("/settings/app-config")
async def update_app_config(body: AppConfigIn):
    if body.price_multiplier is not None:
        if body.price_multiplier <= 0:
            raise HTTPException(400, "Çarpan 0'dan büyük olmalı")
        set_config_value("price_multiplier", body.price_multiplier)
    if body.source_site_selected is not None:
        set_config_value("source_site_selected", body.source_site_selected)
    if body.source_site_name is not None:
        set_config_value("source_site_name", body.source_site_name)
    if body.source_site_search_url is not None:
        set_config_value("source_site_search_url", body.source_site_search_url)
    if body.source_site_login_url is not None:
        set_config_value("source_site_login_url", body.source_site_login_url)
    if body.source_site_member_no is not None:
        set_config_value("source_site_member_no", body.source_site_member_no)
    if body.source_site_username is not None:
        set_config_value("source_site_username", body.source_site_username)
    if body.source_site_password is not None:
        set_config_value("source_site_password", body.source_site_password)
    cfg = get_config()
    cfg.pop("source_site_password", None)  # şifreyi response'ta gösterme
    return {"status": "saved", "config": cfg}


# ── BARKOD ──────────────────────────────────────────────────
class BarcodeIn(BaseModel):
    barcode: str

@app.post("/barcodes/add")
async def add_barcode(body: BarcodeIn):
    return bm.add_barcode(body.barcode)

@app.get("/barcodes")
async def list_barcodes():
    all_bc = bm.get_all()
    return {"total": len(all_bc), "unprocessed": sum(1 for b in all_bc if not b["processed"]), "barcodes": all_bc}

@app.delete("/barcodes/{barcode}")
async def delete_barcode(barcode: str):
    if not bm.delete_barcode(barcode): raise HTTPException(404, "Barkod bulunamadı")
    return {"status": "deleted"}

@app.delete("/barcodes")
async def clear_barcodes():
    bm.clear_barcodes()
    return {"status": "cleared"}


# ── ÜRÜN ÇEKME ──────────────────────────────────────────────
@app.post("/process")
async def process_barcodes(background_tasks: BackgroundTasks):
    unprocessed = bm.get_unprocessed()
    if not unprocessed:
        return {"status": "nothing_to_do", "message": "İşlenecek barkod yok"}
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "total": len(unprocessed), "done": 0, "results": [], "errors": []}
    background_tasks.add_task(_process_job, job_id, unprocessed)
    return {"status": "started", "job_id": job_id, "message": f"{len(unprocessed)} barkod işleniyor."}


async def _process_job(job_id: str, barcodes: list):
    job = jobs[job_id]
    semaphore = asyncio.Semaphore(PARALLEL_LIMIT)

    async def _process_one(barcode):
        async with semaphore:
            try:
                cached = db.get_cached_product(barcode)
                if cached:
                    from models.product import Product
                    product = Product(**cached["product"])
                else:
                    loop = asyncio.get_event_loop()
                    urun_dict = await loop.run_in_executor(None, _cek_selenium, barcode)
                    if not urun_dict:
                        job["errors"].append({"barcode": barcode, "error": "Sitede bulunamadı"})
                        return
                    from models.product import Product
                    product = Product(
                        title=urun_dict["baslik"],
                        price=urun_dict["fiyat"],
                        description=urun_dict["aciklama"],
                        images=urun_dict["resimler"],
                        category=urun_dict["kategori"],
                        barcode=urun_dict["barkod"],
                        sku=urun_dict.get("stok_kodu", ""),
                        stock=1,
                        source_url=urun_dict["url"],
                    )
                    db.cache_product(barcode, urun_dict["url"], product.model_dump())

                transformed = transform(product)
                pv = preview(product)
                item_id = str(uuid.uuid4())
                pending_approval[item_id] = {
                    "item_id": item_id,
                    "original_barcode": barcode,
                    "original": product,
                    "transformed": transformed,
                    "preview": pv,
                }
                job["results"].append({
                    "barcode": barcode, "item_id": item_id,
                    "title": transformed.title, "price": transformed.price,
                    "status": "pending_approval"
                })
                bm.mark_processed(barcode)
                logger.info(f"✓ {barcode} → {transformed.title}")
            except Exception as e:
                job["errors"].append({"barcode": barcode, "error": str(e)})
                logger.error(f"✗ {barcode}: {e}")
            finally:
                job["done"] += 1

    await asyncio.gather(*[_process_one(bc) for bc in barcodes])
    job["status"] = "completed"
    job["message"] = f"{job['done']} işlendi, {len(job['results'])} onay bekliyor"


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs: raise HTTPException(404, "Job bulunamadı")
    return {"job_id": job_id, **jobs[job_id]}


# ── ONAY ────────────────────────────────────────────────────
@app.get("/pending")
async def get_pending():
    items = []
    for item_id, item in pending_approval.items():
        items.append({
            "item_id": item_id,
            "barcode": item["original_barcode"],
            "preview": item["preview"],
            "images": item["transformed"].images[:3],
            "category": item["original"].category,
        })
    return {"count": len(items), "items": items}


class ApproveRequest(BaseModel):
    platforms: List[str]

@app.post("/approve/{item_id}")
async def approve_item(item_id: str, body: ApproveRequest, background_tasks: BackgroundTasks):
    if item_id not in pending_approval: raise HTTPException(404, "Ürün bulunamadı")
    item = pending_approval[item_id]
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "results": {}, "errors": []}
    background_tasks.add_task(_upload_job, job_id, item, body.platforms)
    return {"status": "uploading", "job_id": job_id}

@app.delete("/pending/{item_id}")
async def reject_item(item_id: str):
    if item_id not in pending_approval: raise HTTPException(404, "Bulunamadı")
    del pending_approval[item_id]
    return {"status": "rejected"}


async def _upload_job(job_id: str, item: dict, platforms: list):
    job = jobs[job_id]
    job["status"] = "uploading"
    product = item["transformed"]
    uploaders = _get_uploaders()
    for platform in platforms:
        if platform not in uploaders:
            continue
        try:
            if platform == "n11":
                import json as _j
                from uploaders.n11 import _build_payload
                logger.info(f"N11 payload: {_j.dumps(_build_payload(product), ensure_ascii=False)[:3000]}")
            result = await uploaders[platform].upload(product)
            logger.info(f"[{platform}] create cevap / sonuç: {result}")
            job["results"][platform] = result
            upload_status = result.get("status", "success")
            if upload_status not in ("success", "success_unconfirmed", "error"):
                upload_status = "success_unconfirmed"
            db.record_upload(
                item["original_barcode"], product.barcode, product.sku,
                item["original"].title, product.title,
                item["original"].price, product.price, platform, upload_status
            )
        except Exception as e:
            job["results"][platform] = {"status": "error", "message": str(e)}
            db.record_upload(
                item["original_barcode"], product.barcode, product.sku,
                item["original"].title, product.title,
                item["original"].price, product.price, platform, "error", str(e)
            )
    if item["item_id"] in pending_approval:
        del pending_approval[item["item_id"]]
    job["status"] = "completed"


# ── GEÇMİŞ ──────────────────────────────────────────────────
@app.get("/history")
async def get_history(platform: str = None, status: str = None, limit: int = 100):
    return {"records": db.get_history(limit=limit, platform=platform, status=status)}

@app.get("/stats")
async def get_stats():
    return db.get_history_stats()

@app.post("/report")
async def generate_report(platform: str = None, status: str = None):
    try:
        from report import generate_history_report
        path = generate_history_report(platform=platform, status=status)
        return {"status": "ok", "download": f"/download/{Path(path).name}"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/download/{filename}")
async def download_file(filename: str):
    for folder in ["reports", "exports"]:
        path = Path(folder) / filename
        if path.exists():
            return FileResponse(str(path),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=filename)
    raise HTTPException(404, "Dosya bulunamadı")


# ── KATEGORİ ────────────────────────────────────────────────
class CategoryMapping(BaseModel):
    source_category: str
    trendyol_id: int = 0
    hepsiburada_id: str = ""
    n11_id: int = 0

@app.get("/categories")
async def get_categories():
    return {"mappings": db.get_category_mappings()}

@app.post("/categories")
async def save_category(body: CategoryMapping):
    db.upsert_category_mapping(body.source_category, body.trendyol_id, body.hepsiburada_id, body.n11_id)
    return {"status": "saved"}

@app.get("/hepsiburada-categories")
async def hepsiburada_categories(search: str = ""):
    """Hepsiburada MPOP kategori ağacını çeker. ?search=televizyon ile filtrele."""
    from category_mapper import HB_KEYWORD_MAP
    cats = [{"id": v, "name": k} for k, v in HB_KEYWORD_MAP.items()]
    try:
        auth = aiohttp.BasicAuth(settings.hepsiburada_username, settings.hepsiburada_password)
        async with aiohttp.ClientSession(auth=auth) as session:
            _mpop = "https://mpop-sit.hepsiburada.com" if settings.hepsiburada_env == "test" else "https://mpop.hepsiburada.com"
            async with session.get(
                f"{_mpop}/product/api/categories/get-all-categories",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    api_cats = data if isinstance(data, list) else data.get("categories", data.get("data", []))
                    def _flatten(items, path=""):
                        result = []
                        for c in items:
                            name = c.get("name", c.get("displayName", ""))
                            cid = str(c.get("id", c.get("categoryId", "")))
                            full = f"{path} > {name}".lstrip(" > ")
                            result.append({"id": cid, "name": full})
                            result += _flatten(c.get("subCategories", c.get("children", [])), full)
                        return result
                    cats = _flatten(api_cats)
    except Exception:
        pass  # API erişimi yoksa yerel listeyle devam et
    if search:
        low = search.lower()
        cats = [c for c in cats if low in c["name"].lower()]
    return {"categories": cats, "total": len(cats)}


@app.get("/n11-categories")
async def n11_categories(search: str = ""):
    """N11 kategori ağacını çeker. ?search=sulama ile filtrele."""
    import aiohttp as _aiohttp
    headers = {"appkey": settings.n11_app_key, "appsecret": settings.n11_app_secret}

    def _flatten(cats, path=""):
        results = []
        for c in cats:
            name = c.get("name", "")
            cid  = c.get("id", "")
            full = f"{path} > {name}".lstrip(" > ")
            results.append({"id": cid, "name": full})
            results += _flatten(c.get("subCategories", c.get("children", [])), full)
        return results

    try:
        async with _aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.n11.com/ms/product/categories",
                headers=headers, timeout=_aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json(content_type=None)
        cats = data if isinstance(data, list) else data.get("categories", data.get("data", []))
        flat = _flatten(cats)
        if search:
            low = search.lower()
            flat = [c for c in flat if low in c["name"].lower()]
        return {"categories": flat, "total": len(flat)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"N11 API hatası: {e}")


# ── CREDENTIALS ─────────────────────────────────────────────
class CredentialIn(BaseModel):
    platform: str
    field: str
    value: str

@app.post("/credentials")
async def save_credential(body: CredentialIn):
    from credentials import set_credential
    set_credential(body.platform, body.field, body.value)
    return {"status": "saved"}

@app.get("/credentials/{platform}")
async def get_credential_status(platform: str):
    from credentials import check_credentials
    return check_credentials(platform)

@app.delete("/cache")
async def clear_cache():
    db.clear_cache()
    return {"status": "cleared"}

@app.get("/health/hepsiburada")
async def hepsiburada_health():
    """Hepsiburada API bağlantısını test eder."""
    if not settings.hepsiburada_username or not settings.hepsiburada_merchant_id:
        return {"status": "not_configured", "message": "Kimlik bilgileri eksik"}
    try:
        auth = aiohttp.BasicAuth(settings.hepsiburada_username, settings.hepsiburada_password)
        hb_headers = {"User-Agent": settings.hepsiburada_developer_username}
        mpop_base = "https://mpop-sit.hepsiburada.com" if settings.hepsiburada_env == "test" else "https://mpop.hepsiburada.com"
        url = f"{mpop_base}/product/api/products?merchantId={settings.hepsiburada_merchant_id}&size=1"
        async with aiohttp.ClientSession(auth=auth, headers=hb_headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return {"status": "ok", "message": "Hepsiburada MPOP bağlantısı başarılı"}
                if resp.status == 403:
                    return {"status": "auth_ok_no_permission", "message": "Kimlik doğrulandı ancak hesap aktivasyonu bekleniyor (403)"}
                text = await resp.text()
                return {"status": "error", "http_status": resp.status, "message": text[:200]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/debug/n11-task/{task_id}")
async def check_n11_task(task_id: str):
    """N11 task sonucunu POST task-details/page-query ile sorgular."""
    import aiohttp as _aio, json as _j
    headers = {"appkey": settings.n11_app_key, "appsecret": settings.n11_app_secret,
               "Content-Type": "application/json"}
    url = "https://api.n11.com/ms/product/task-details/page-query"
    try:
        async with _aio.ClientSession() as session:
            payload = {"taskId": int(task_id), "page": 0, "size": 10}
            async with session.post(url, json=payload, headers=headers,
                                    timeout=_aio.ClientTimeout(total=15)) as r:
                raw = await r.text()
                logger.info(f"N11 task {task_id} → HTTP {r.status}: {raw[:1000]}")
                try:
                    return {"http_status": r.status, "body": _j.loads(raw)}
                except Exception:
                    return {"http_status": r.status, "raw": raw[:500]}
    except Exception as e:
        return {"error": str(e)}


@app.get("/debug/n11-category/{cat_id}")
async def check_n11_category(cat_id: int):
    """N11 kategori attribute'larını farklı URL'lerle sorgular."""
    import aiohttp as _aio, json as _j
    headers = {"appkey": settings.n11_app_key, "appsecret": settings.n11_app_secret}
    base = "https://api.n11.com"
    urls = [
        f"{base}/ms/product/categories/{cat_id}/attributes",
        f"{base}/ms/product/attributes/categories/{cat_id}",
        f"{base}/ms/product/categories/{cat_id}",
        f"{base}/ms/product/categories",
    ]
    results = {}
    try:
        async with _aio.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, headers=headers, timeout=_aio.ClientTimeout(total=10)) as r:
                        raw = await r.text()
                        logger.info(f"N11 [{r.status}] {url} → {raw[:300]}")
                        try:
                            results[url] = {"status": r.status, "body": _j.loads(raw)}
                        except Exception:
                            results[url] = {"status": r.status, "raw": raw[:300]}
                except Exception as ex:
                    results[url] = {"error": str(ex)}
        return results
    except Exception as e:
        return {"error": str(e)}


@app.get("/health")
async def health():
    stats = db.get_history_stats()
    return {"status": "ok", "version": "4.0.0",
            "uploads_total": stats.get("total", 0), "uploads_today": stats.get("today", 0)}


# ── URL İLE ÜRÜN EKLEME ─────────────────────────────────────
class UrlIn(BaseModel):
    url: str

@app.post("/products/add-by-url")
async def add_product_by_url(body: UrlIn, background_tasks: BackgroundTasks):
    url = body.url.strip()
    if not url.startswith("http"):
        raise HTTPException(400, "Geçerli bir URL girin")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "total": 1, "done": 0, "results": [], "errors": []}
    background_tasks.add_task(_process_url_job, job_id, url)
    return {"status": "started", "job_id": job_id, "message": "URL işleniyor..."}


async def _process_url_job(job_id: str, url: str):
    job = jobs[job_id]
    try:
        loop = asyncio.get_event_loop()
        urun_dict = await loop.run_in_executor(None, _cek_selenium_url, url)
        if not urun_dict:
            job["errors"].append({"url": url, "error": "Ürün bilgisi alınamadı"})
        else:
            from models.product import Product
            product = Product(
                title=urun_dict["baslik"],
                price=urun_dict["fiyat"],
                description=urun_dict["aciklama"],
                images=urun_dict["resimler"],
                category=urun_dict["kategori"],
                barcode=urun_dict.get("barkod", ""),
                sku=urun_dict.get("stok_kodu", ""),
                stock=1,
                source_url=urun_dict["url"],
            )
            transformed = transform(product)
            pv = preview(product)
            item_id = str(uuid.uuid4())
            pending_approval[item_id] = {
                "item_id": item_id,
                "original_barcode": urun_dict.get("barkod", "URL"),
                "original": product,
                "transformed": transformed,
                "preview": pv,
            }
            job["results"].append({"url": url, "item_id": item_id, "title": transformed.title, "status": "pending_approval"})
            logger.info(f"✓ URL → {transformed.title}")
    except Exception as e:
        job["errors"].append({"url": url, "error": str(e)})
        logger.error(f"✗ URL hatası: {e}")
    finally:
        job["done"] = 1
        job["status"] = "completed"
        job["message"] = "1 ürün onay bekliyor" if job["results"] else "Ürün alınamadı"


# ── SELENIUM SCRAPER ─────────────────────────────────────────
def _cek_selenium(barcode: str) -> Optional[dict]:
    import json as _json

    # merter_cek.py yi bul
    aday_klasorler = [
        Path(sys.executable).parent,
        Path(sys.executable).parent.parent,
        Path(__file__).parent.parent,
        Path(__file__).parent,
        Path("."),
    ]
    cek_script = None
    for klasor in aday_klasorler:
        yol = klasor / "merter_cek.py"
        if yol.exists():
            cek_script = str(yol)
            break

    if not cek_script:
        logger.error("merter_cek.py bulunamadi!")
        return None

    # Gerçek Python'u bul
    python_exe = sys.executable
    if getattr(sys, "frozen", False):
        import shutil as _sh
        python_exe = _sh.which("python") or _sh.which("python3") or "python"

    logger.info(f"Scraper: {cek_script}")
    try:
        cfg = get_config()
        scraper_env = {
            **os.environ,
            "XTECHNX_SEARCH_URL":  cfg.get("source_site_search_url", ""),
            "XTECHNX_LOGIN_URL":   cfg.get("source_site_login_url", ""),
            "XTECHNX_MEMBER_NO":   cfg.get("source_site_member_no", ""),
            "XTECHNX_SITE_USER":   cfg.get("source_site_username", ""),
            "XTECHNX_SITE_PASS":   cfg.get("source_site_password", ""),
        }
        result = subprocess.run(
            [python_exe, "-u", cek_script, barcode],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
            env=scraper_env,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                logger.info(f"  [cek] {line}")

        stdout = result.stdout.strip()
        if not stdout:
            logger.error("Scraper cikti vermedi")
            return None

        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    d = _json.loads(line)
                    if "hata" in d:
                        logger.error(f"Scraper hatasi: {d['hata']}")
                        return None
                    logger.info(f"Urun bulundu: {d.get('baslik','')[:60]}")
                    return d
                except:
                    pass

        logger.error(f"JSON parse hatasi. Cikti: {stdout[:200]}")
        return None

    except subprocess.TimeoutExpired:
        logger.error("Scraper timeout")
        return None
    except Exception as e:
        logger.error(f"Scraper hatasi: {e}")
        return None


def _cek_selenium_url(url: str) -> Optional[dict]:
    """Direkt URL ile ürün çeker — barkod araması yapmaz."""
    import json as _json

    aday_klasorler = [
        Path(sys.executable).parent,
        Path(sys.executable).parent.parent,
        Path(__file__).parent.parent,
        Path(__file__).parent,
        Path("."),
    ]
    cek_script = None
    for klasor in aday_klasorler:
        yol = klasor / "merter_cek.py"
        if yol.exists():
            cek_script = str(yol)
            break

    if not cek_script:
        logger.error("merter_cek.py bulunamadi!")
        return None

    python_exe = sys.executable
    if getattr(sys, "frozen", False):
        import shutil as _sh
        python_exe = _sh.which("python") or _sh.which("python3") or "python"

    cfg = get_config()
    env = {
        **os.environ,
        "XTECHNX_SEARCH_URL":  cfg.get("source_site_search_url", ""),
        "XTECHNX_LOGIN_URL":   cfg.get("source_site_login_url", ""),
        "XTECHNX_MEMBER_NO":   cfg.get("source_site_member_no", ""),
        "XTECHNX_SITE_USER":   cfg.get("source_site_username", ""),
        "XTECHNX_SITE_PASS":   cfg.get("source_site_password", ""),
    }

    logger.info(f"URL Scraper: {url}")
    try:
        result = subprocess.run(
            [python_exe, "-u", cek_script, "--url", url],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
            env=env,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                logger.info(f"  [cek-url] {line}")

        stdout = result.stdout.strip()
        if not stdout:
            logger.error("URL Scraper çıktı vermedi")
            return None

        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    d = _json.loads(line)
                    if "hata" in d:
                        logger.error(f"URL Scraper hatası: {d['hata']}")
                        return None
                    logger.info(f"URL ürün bulundu: {d.get('baslik','')[:60]}")
                    return d
                except:
                    pass

        logger.error(f"URL JSON parse hatası. Çıktı: {stdout[:200]}")
        return None

    except subprocess.TimeoutExpired:
        logger.error("URL Scraper timeout")
        return None
    except Exception as e:
        logger.error(f"URL Scraper hatası: {e}")
        return None


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
