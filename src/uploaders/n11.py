import aiohttp
from models.product import Product
from config.settings import settings
from category_mapper import get_n11_category

CREATE_URL      = "https://api.n11.com/ms/product/tasks/product-create"
TASK_QUERY_URL  = "https://api.n11.com/ms/product/task-details/page-query"
PRODUCT_QUERY_URL = "https://api.n11.com/ms/product/page-query"


def _resolve_category(p: Product) -> int:
    manual = p.attributes.get("_category_ids", {}).get("n11", 0)
    if manual and manual != 0:
        return manual
    try:
        import database as db
        db_mappings = {
            m["source_category"]: m["n11_id"]
            for m in db.get_category_mappings()
            if m.get("n11_id")
        }
    except Exception:
        db_mappings = {}
    # Kategori boşsa başlıktan tahmin et
    cat = p.category or p.title or ""
    return get_n11_category(cat, db_mappings)


def _extract_brand(p: Product) -> str:
    return "Xtechnx"


def _ean13(base: str) -> str:
    """12 haneli sayıdan geçerli EAN-13 üretir (check digit ekler)."""
    digits = base[:12].zfill(12)
    toplam = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    check = (10 - (toplam % 10)) % 10
    return digits + str(check)


def _numeric_barcode(p: Product) -> str:
    """Ürüne özgü geçerli EAN-13 barkod üretir.
    GS1 dahili kullanım aralığı (2xx) — N11 kataloğundaki gerçek ürünlerle çakışmaz."""
    raw = p.barcode or ""
    digits = "".join(c for c in raw if c.isdigit())
    # "2" + 11 hane → 12 hane base, her zaman "2" ile başlar
    if len(digits) >= 11:
        base12 = "2" + digits[:11]
    else:
        base12 = "2" + digits.zfill(11)
    return _ean13(base12)


def _build_payload(p: Product) -> dict:
    cat_id = _resolve_category(p)
    images = [{"url": img, "order": i + 1} for i, img in enumerate(p.images[:8]) if img]
    brand = _extract_brand(p)
    barcode = _numeric_barcode(p)
    tmpl = getattr(settings, "n11_shipment_template", "") or "Aras Kargo"
    return {
        "payload": {
            "integrator": "Xtechnx",
            "skus": [{
                "title": p.title[:255],
                "description": p.description[:30000],
                "categoryId": cat_id,
                "currencyType": "TL",
                "productMainId": p.sku or f"XTECH-{abs(hash(p.title)) % 10**8}",
                "preparingDay": 1,
                "shipmentTemplate": tmpl,
                "stockCode": p.sku or f"XTECH-{abs(hash(p.title)) % 10**8}",
                "barcode": barcode,
                "quantity": p.stock,
                "images": images,
                "attributes": [{"id": 1, "customValue": brand, "valueId": None}],
                "salePrice": round(p.price, 2),
                "listPrice": round(p.price * 1.1, 2),
                "vatRate": 20,
            }]
        }
    }


class N11Uploader:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "appkey": settings.n11_app_key,
            "appsecret": settings.n11_app_secret,
        }

    async def _poll_task(self, session: aiohttp.ClientSession, task_id: str) -> dict | None:
        """Task sonucunu N11'den sorgular. Henüz bitmemişse None döner."""
        import asyncio, logging, json as _json
        from datetime import datetime
        _log = logging.getLogger(__name__)
        for attempt in range(24):  # 24 × 10s = 4 dakika
            await asyncio.sleep(10)
            try:
                payload = {"taskId": task_id, "page": 0, "size": 10}
                async with session.post(TASK_QUERY_URL, json=payload, headers=self.headers,
                                        timeout=aiohttp.ClientTimeout(total=15)) as r:
                    raw = await r.text()
                    _log.info(f"N11 task poll [{attempt+1}] HTTP {r.status} body={raw[:500]!r}")
                    if not raw.strip():
                        continue
                    try:
                        d = _json.loads(raw)
                    except Exception:
                        continue
                    # Eski task tespiti: createdDate > 5 dakika geçmişte ve IN_QUEUE → stuck
                    if attempt == 0:
                        try:
                            cdate_str = d.get("createdDate", "")
                            cdate = datetime.strptime(cdate_str, "%d-%m-%Y %H:%M:%S")
                            age_minutes = (datetime.utcnow() - cdate).total_seconds() / 60
                            if age_minutes > 5 and (d.get("status") or "").upper() == "IN_QUEUE":
                                _log.info(f"N11 task [{task_id}] ESKİ TASK ({age_minutes:.0f} dk) — ürün zaten N11 kuyruğunda")
                                return {"status": "error", "task_id": task_id,
                                        "message": "N11_STUCK_TASK: ürün N11 kuyruğunda takılı kalmış, varyant denemesi yapılıyor"}
                        except Exception:
                            pass
                    # Cevap yapısı: {"taskId":..., "skus":{"content":[{"status":"SUCCESS"/"REJECT",...}]}}
                    skus = d.get("skus") or {}
                    items = skus.get("content") or d.get("content") or d.get("data") or []
                    task_level = (d.get("status") or "").upper()
                    if isinstance(items, list) and items:
                        sku_status = (items[0].get("status") or "").upper()
                        n11_id = (items[0].get("sku") or {}).get("n11ProductId") or items[0].get("n11ProductId")
                    else:
                        sku_status = task_level
                        n11_id = None
                    _log.info(f"N11 task [{task_id}] task:{task_level} sku:{sku_status} n11ProductId:{n11_id}")
                    # Task tamamlandıysa (PROCESSED/COMPLETED/DONE) kesin sonuç var
                    if task_level in ("PROCESSED", "COMPLETED", "DONE"):
                        if sku_status in ("SUCCESS", "DONE", "COMPLETED"):
                            # groupId'yi DB'ye kaydet (varyant yüklemeleri için)
                            try:
                                import database as _db
                                gid = (items[0].get("sku") or {}).get("groupId") or items[0].get("groupId")
                                sc  = (items[0].get("sku") or {}).get("stockCode") or items[0].get("itemCode")
                                if gid and sc:
                                    _db.save_n11_group(sc, int(gid))
                            except Exception:
                                pass
                            return {"status": "success", "task_id": task_id, "n11_product_id": n11_id,
                                    "message": f"N11 onayladı. TaskID: {task_id}, N11 ürün ID: {n11_id}"}
                        else:
                            errors = (items[0].get("failedReasons") or items[0].get("reasons")
                                      or items[0].get("errorMessage")
                                      or d.get("message") or d) if items else d
                            return {"status": "error", "task_id": task_id,
                                    "message": f"N11 reddetti ({sku_status}): {errors}"}
                    # SKU düzeyinde açık red
                    if sku_status in ("REJECT", "REJECTED", "FAILED", "ERROR"):
                        errors = (items[0].get("failedReasons") or items[0].get("reasons")
                                  or items[0].get("errorMessage")
                                  or d.get("message") or d) if items else d
                        return {"status": "error", "task_id": task_id,
                                "message": f"N11 reddetti: {errors}"}
                    # IN_QUEUE / IN_PROGRESS / FAIL (N11 başlangıç değeri) → tekrar dene
            except Exception as ex:
                _log.info(f"N11 task poll [{attempt+1}] hata: {ex}")

    async def _get_group_id(self, session: aiohttp.ClientSession, stock_code: str) -> int | None:
        """Verilen stockCode'a sahip N11 ürününün groupId'sini döner. Önce DB'ye, sonra N11 API'ye bakar."""
        # 1) Yerel DB
        try:
            import database as _db
            gid = _db.get_n11_group(stock_code)
            if gid:
                _log.info(f"N11 groupId DB'den bulundu: {gid} ({stock_code})")
                return gid
        except Exception:
            pass

        # 2) N11 product page-query API
        _log.info(f"N11 groupId DB'de yok ({stock_code}) — N11 API sorgulanıyor")
        try:
            import json as _json
            url = f"{PRODUCT_QUERY_URL}?stockCode={stock_code}&page=0&size=1"
            async with session.get(url, headers=self.headers,
                                   timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    raw = await r.text()
                    d = _json.loads(raw) if raw else {}
                    content = (d.get("content") or
                               (d.get("skus") or {}).get("content") or
                               d.get("data") or [])
                    for item in content:
                        sku = item.get("sku") or item
                        gid = sku.get("groupId") or item.get("groupId")
                        if gid:
                            gid = int(gid)
                            _log.info(f"N11 groupId API'den bulundu: {gid} ({stock_code})")
                            try:
                                _db.save_n11_group(stock_code, gid)
                            except Exception:
                                pass
                            return gid
                _log.info(f"N11 groupId API yanıtı: HTTP {r.status}, bulunamadı ({stock_code})")
        except Exception as ex:
            _log.info(f"N11 groupId API hatası: {ex}")
        return None

    async def upload(self, product: Product) -> dict:
        import re, json as _json
        payload = _build_payload(product)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CREATE_URL, json=payload, headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                raw_resp = await resp.text()
                if resp.status not in (200, 201, 202):
                    raise Exception(f"N11 REST {resp.status}: {raw_resp[:500]}")
                try:
                    data = _json.loads(raw_resp)
                except Exception:
                    data = {}

                task_id = data.get("taskId") or data.get("id") or str(data)

            # Task sonucunu bekle
            result = await self._poll_task(session, task_id)

            # Varyant hatası: aynı katalog ID farklı stockCode ile zaten listede,
            # ya da task eski/takılı kaldı → mevcut ürünün groupId'sini bul, varyant olarak gönder
            if result and result.get("status") == "error":
                err_msg = result.get("message", "")
                # "...katalog id Cihan682364 mağaza ürün kodu ve Cihan682364 seller stock kodu..."
                # → conflicting ürünün stockCode'unu çek
                mc = re.search(r'(\w+)\s+seller stock kodu', err_msg)
                existing_stock_code = mc.group(1) if mc else None
                # STUCK_TASK: task takılı kaldı, kendi SKU'muz zaten N11'de olabilir
                if not existing_stock_code and "N11_STUCK_TASK" in err_msg:
                    existing_stock_code = payload["payload"]["skus"][0].get("stockCode", "")
                    _log.info(f"N11 STUCK_TASK: kendi SKU'su ile varyant aranıyor ({existing_stock_code})")
                if existing_stock_code:
                    group_id = await self._get_group_id(session, existing_stock_code)
                    if group_id:
                        import logging
                        logging.getLogger(__name__).info(
                            f"N11 varyant denemesi: groupId={group_id}, stockCode={existing_stock_code}"
                        )
                        # groupId ekleyerek yeniden gönder
                        payload["payload"]["skus"][0]["groupId"] = group_id
                        async with session.post(
                            CREATE_URL, json=payload, headers=self.headers,
                            timeout=aiohttp.ClientTimeout(total=60)
                        ) as resp2:
                            raw2 = await resp2.text()
                            if resp2.status not in (200, 201, 202):
                                return result  # varyant denemesi de başarısız
                            try:
                                data2 = _json.loads(raw2)
                            except Exception:
                                data2 = {}
                            task_id2 = data2.get("taskId") or data2.get("id") or str(data2)
                        result2 = await self._poll_task(session, task_id2)
                        if result2:
                            return result2
                        return {
                            "status": "success_unconfirmed",
                            "task_id": task_id2,
                            "message": f"N11'e varyant olarak gönderildi (groupId:{group_id}). TaskID: {task_id2}",
                        }

            if result:
                return result
            # Zaman aşımı — N11 henüz işlemedi
            return {
                "status": "success_unconfirmed",
                "task_id": task_id,
                "message": f"N11'e gönderildi, onay bekleniyor. TaskID: {task_id}",
            }
