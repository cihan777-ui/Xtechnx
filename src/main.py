from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, ORJSONResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn, logging, uuid, asyncio, subprocess, sys, os
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
from transformer import transform, preview
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
        Path("ui.html"),
        Path("src") / "ui.html",
        Path(getattr(sys, "_MEIPASS", "")) / "src" / "ui.html",
    ]
    for f in candidates:
        if f.exists():
            return HTMLResponse(f.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>API çalışıyor → /docs</h1>")


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
                        sku="",
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
            result = await uploaders[platform].upload(product)
            job["results"][platform] = result
            db.record_upload(
                item["original_barcode"], product.barcode, product.sku,
                item["original"].title, product.title,
                item["original"].price, product.price, platform, "success"
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

@app.get("/health")
async def health():
    stats = db.get_history_stats()
    return {"status": "ok", "version": "4.0.0",
            "uploads_total": stats.get("total", 0), "uploads_today": stats.get("today", 0)}


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
        result = subprocess.run(
            [python_exe, "-u", cek_script, barcode],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
