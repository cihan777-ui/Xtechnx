"""
Stok senkronizasyon servisi.
- HB ve N11'den yeni siparişleri çeker
- İşlenmemiş siparişlerde stok_map'ten stok düşer
- Tüm platformlarda stoku günceller
"""
import asyncio
import logging
import aiohttp
import database as db
from config.settings import settings

_log = logging.getLogger(__name__)

_last_sync: dict = {"status": "never", "message": "", "at": ""}


def get_last_sync() -> dict:
    return _last_sync


# ── HB Sipariş Çekme ─────────────────────────────────────────

async def _fetch_hb_orders() -> list:
    """Son 50 HB siparişini çeker. [{order_id, sku, qty}, ...]"""
    from uploaders.hepsiburada import HepsiburadaUploader
    uploader = HepsiburadaUploader()
    orders = []
    try:
        data = await uploader.list_orders(limit=50)
        items = data if isinstance(data, list) else data.get("items", data.get("data", []))
        for order in items:
            order_id = str(order.get("id") or order.get("orderId") or "")
            if not order_id:
                continue
            # HB sipariş detayında line items olabilir
            lines = order.get("orderLines") or order.get("items") or [order]
            for line in lines:
                sku = (line.get("merchantSku") or line.get("sku") or "").strip()
                qty = int(line.get("quantity") or line.get("qty") or 1)
                if sku:
                    orders.append({"order_id": order_id, "sku": sku, "qty": qty})
    except Exception as ex:
        _log.warning("HB sipariş çekme hatası: %s", ex)
    return orders


# ── N11 Sipariş Çekme ────────────────────────────────────────

async def _fetch_n11_orders() -> list:
    """Son 50 N11 siparişini çeker. [{order_id, sku, qty}, ...]"""
    headers = {
        "Content-Type": "application/json",
        "appkey":    settings.n11_app_key,
        "appsecret": settings.n11_app_secret,
    }
    orders = []
    try:
        # N11 sipariş listesi endpoint
        url = "https://api.n11.com/ms/order/page-query"
        payload = {"page": 0, "size": 50, "status": "Approved"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    _log.warning("N11 sipariş API HTTP %d", r.status)
                    return []
                import json as _j
                data = _j.loads(await r.text())
                items = (data.get("orderList") or data.get("content")
                         or data.get("data") or data.get("orders") or [])
                for order in items:
                    order_id = str(order.get("id") or order.get("orderId") or "")
                    if not order_id:
                        continue
                    lines = order.get("orderItemList") or order.get("items") or [order]
                    for line in lines:
                        sku = (line.get("productStockCode") or line.get("stockCode")
                               or line.get("merchantSku") or "").strip()
                        qty = int(line.get("quantity") or 1)
                        if sku:
                            orders.append({"order_id": order_id, "sku": sku, "qty": qty})
    except Exception as ex:
        _log.warning("N11 sipariş çekme hatası: %s", ex)
    return orders


# ── HB Stok Güncelleme ───────────────────────────────────────

async def _push_stock_hb(hb_sku: str, merchant_sku: str, new_stock: int):
    from uploaders.hepsiburada import HepsiburadaUploader
    uploader = HepsiburadaUploader()
    auth = uploader._auth()
    payload = [{"hepsiburadaSku": hb_sku, "merchantSku": merchant_sku,
                "availableStock": max(0, new_stock)}]
    try:
        async with aiohttp.ClientSession(auth=auth) as session:
            url = (f"{uploader.BASE_URL}/listings/merchantid/"
                   f"{uploader.merchant_id}/stock-uploads")
            async with session.post(url, json=payload, headers=uploader._headers(),
                                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status in (200, 201, 202):
                    _log.info("HB stok güncellendi: %s → %d", merchant_sku, new_stock)
                else:
                    _log.warning("HB stok güncelleme hatası %d: %s", r.status, await r.text())
    except Exception as ex:
        _log.warning("HB stok push hatası: %s", ex)


# ── N11 Stok Güncelleme ──────────────────────────────────────

async def _push_stock_n11(stock_code: str, new_stock: int):
    headers = {
        "Content-Type": "application/json",
        "appkey":    settings.n11_app_key,
        "appsecret": settings.n11_app_secret,
    }
    payload = {"payload": {"skus": [{"stockCode": stock_code, "quantity": max(0, new_stock)}]}}
    try:
        url = "https://api.n11.com/ms/product/tasks/sku-update"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status in (200, 201, 202):
                    _log.info("N11 stok güncellendi: %s → %d", stock_code, new_stock)
                else:
                    _log.warning("N11 stok güncelleme hatası %d: %s", r.status, await r.text())
    except Exception as ex:
        _log.warning("N11 stok push hatası: %s", ex)


# ── Ana Sync Fonksiyonu ──────────────────────────────────────

async def sync_stock() -> dict:
    """
    Tüm platformlardan siparişleri çeker, stok düşer, platformları günceller.
    Sonuç dict döner.
    """
    from datetime import datetime
    _log.info("Stok senkronizasyonu başladı")
    processed_count = 0
    skipped_count   = 0
    errors          = []

    # Siparişleri çek (HB + N11 paralel)
    hb_orders, n11_orders = await asyncio.gather(
        _fetch_hb_orders(),
        _fetch_n11_orders(),
        return_exceptions=True,
    )
    if isinstance(hb_orders, Exception):
        errors.append(f"HB sipariş hatası: {hb_orders}")
        hb_orders = []
    if isinstance(n11_orders, Exception):
        errors.append(f"N11 sipariş hatası: {n11_orders}")
        n11_orders = []

    all_orders = (
        [{"platform": "hepsiburada", **o} for o in hb_orders] +
        [{"platform": "n11",         **o} for o in n11_orders]
    )

    _log.info("Toplam sipariş: %d (HB:%d N11:%d)",
              len(all_orders), len(hb_orders), len(n11_orders))

    for order in all_orders:
        platform = order["platform"]
        order_id = order["order_id"]
        sku      = order["sku"]
        qty      = order["qty"]

        # Daha önce işlendiyse atla
        if db.is_order_processed(order_id, platform):
            skipped_count += 1
            continue

        # stock_map'te bu SKU var mı?
        stock_row = db.get_stock_by_sku(sku)
        if not stock_row:
            _log.info("SKU stock_map'te yok: %s (sipariş: %s)", sku, order_id)
            db.mark_order_processed(order_id, platform, sku, qty)
            skipped_count += 1
            continue

        # Stok düş
        new_stock = max(0, stock_row["current_stock"] - qty)
        db.update_stock(sku, new_stock)
        db.mark_order_processed(order_id, platform, sku, qty)
        _log.info("Stok düşüldü: %s %d → %d (%s sipariş:%s)",
                  sku, stock_row["current_stock"], new_stock, platform, order_id)
        processed_count += 1

        # Tüm platformlarda stoku güncelle
        push_tasks = []
        if stock_row.get("hb_sku"):
            push_tasks.append(_push_stock_hb(stock_row["hb_sku"], sku, new_stock))
        if stock_row.get("n11_stock_code"):
            push_tasks.append(_push_stock_n11(stock_row["n11_stock_code"], new_stock))
        if push_tasks:
            await asyncio.gather(*push_tasks, return_exceptions=True)

    result = {
        "status":    "ok",
        "processed": processed_count,
        "skipped":   skipped_count,
        "errors":    errors,
        "message":   (f"{processed_count} sipariş işlendi, "
                      f"{skipped_count} atlandı (zaten işlenmiş/bilinmiyor)"),
        "at":        datetime.now().isoformat(),
    }
    _last_sync.update(result)
    _log.info("Stok sync tamamlandı: %s", result["message"])
    return result
