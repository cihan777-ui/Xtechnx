"""
Barkod Yöneticisi
- Barkodları barcodes/barcodes.json dosyasına kaydeder
- Tekrar okunan barkodları atlar
"""
import json
from datetime import datetime
from pathlib import Path

BARCODE_DIR = Path("barcodes")
BARCODE_FILE = BARCODE_DIR / "barcodes.json"


def _ensure_dir():
    BARCODE_DIR.mkdir(exist_ok=True)


def load_barcodes() -> list:
    _ensure_dir()
    if not BARCODE_FILE.exists():
        return []
    try:
        return json.loads(BARCODE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_barcodes(barcodes: list):
    _ensure_dir()
    BARCODE_FILE.write_text(
        json.dumps(barcodes, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def add_barcode(barcode: str) -> dict:
    barcode = barcode.strip()
    if not barcode:
        return {"status": "error", "message": "Boş barkod"}
    barcodes = load_barcodes()
    if any(b["barcode"] == barcode for b in barcodes):
        return {"status": "duplicate", "message": f"{barcode} zaten kayıtlı", "barcode": barcode}
    entry = {"barcode": barcode, "added_at": datetime.now().isoformat(), "processed": False}
    barcodes.append(entry)
    save_barcodes(barcodes)
    return {"status": "added", "message": f"{barcode} eklendi", "barcode": barcode}


def get_unprocessed() -> list:
    return [b["barcode"] for b in load_barcodes() if not b.get("processed")]


def get_all() -> list:
    return load_barcodes()


def mark_processed(barcode: str):
    barcodes = load_barcodes()
    for b in barcodes:
        if b["barcode"] == barcode:
            b["processed"] = True
    save_barcodes(barcodes)


def clear_barcodes():
    save_barcodes([])


def delete_barcode(barcode: str) -> bool:
    barcodes = load_barcodes()
    new_list = [b for b in barcodes if b["barcode"] != barcode]
    if len(new_list) == len(barcodes):
        return False
    save_barcodes(new_list)
    return True
