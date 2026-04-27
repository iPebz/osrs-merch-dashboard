"""
FastAPI backend — replaces the tkinter GUI.
All analysis/DB/API modules are reused unchanged.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from analysis.recommendation_engine import (
    PRICE_RANGES, STRATEGIES, STRATEGY_LABELS, STRATEGY_DESC,
    group_by_strategy, group_by_price_range, build_summary, build_detail,
)
from database.queries import (
    add_to_watchlist, get_all_items, get_item_icon_urls,
    get_watchlist, remove_from_watchlist,
)
from database.schema import init_db
from data_service import DataService
import numpy as np
import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Numpy → Python type sanitizer
# FastAPI's JSON encoder can't handle numpy.bool_, numpy.int64, etc.
# Also replaces float nan/inf (not valid JSON) with None.
# ---------------------------------------------------------------------------
import math as _math

def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return None if not _math.isfinite(v) else v
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, float):
        return None if not _math.isfinite(obj) else obj
    return obj

# ---------------------------------------------------------------------------
# Shared state (written by background threads, read by request handlers)
# ---------------------------------------------------------------------------
_db:     sqlite3.Connection | None = None
_svc:    DataService        | None = None
_cache:  list[dict] = []          # scored items
_status: dict = {"message": "Starting…", "running": False, "count": 0, "refreshed_at": 0}
_lock = threading.Lock()


def _set(msg: str, running: bool = False, count: int | None = None):
    with _lock:
        _status["message"] = msg
        _status["running"] = running
        if count is not None:
            _status["count"] = count


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

_WIKI_CDN = "https://oldschool.runescape.wiki/images/"


def _do_score():
    global _cache
    _set("Scoring items…", running=True)
    try:
        results = _svc.score_all_items()
        _cache = [_sanitize(r) for r in results]
        # Merge icon URLs from DB into cached items
        icon_map = get_item_icon_urls(_db)
        for item in _cache:
            fname = icon_map.get(item.get("item_id"))
            if fname:
                item["icon_url"] = _WIKI_CDN + fname.replace(" ", "_")
        _patch_cache_prices()
        _set(f"Ready — {len(results)} items scored", count=len(results))
    except Exception as e:
        log.error("Scoring failed: %s", e)
        _set(f"Scoring error: {e}")


def _do_refresh():
    _set("Refreshing prices…", running=True)
    try:
        _svc.refresh_latest()
        _patch_cache_prices()
        _set("Prices refreshed.")
    except Exception as e:
        _set(f"Refresh error: {e}")


def _patch_cache_prices():
    """
    Fast price patch: update current_low/high and derived margin fields in
    _cache from the latest DB snapshot without running a full rescore.
    Called after every background refresh (~60 s) so the table stays live.
    """
    import time as _time
    if not _cache or _db is None:
        return
    from database.queries import get_latest_snapshots_batch
    latest = get_latest_snapshots_batch(_db)
    if not latest:
        return
    for item in _cache:
        iid = item.get("item_id")
        lp  = latest.get(iid)
        if not lp:
            continue
        lo, hi = lp.get("low") or 0, lp.get("high") or 0
        if lo <= 0 or hi <= 0:
            continue
        item["current_low"]  = lo
        item["current_high"] = hi
        tax     = min(hi * 0.01, 5_000_000)
        net_gp  = max(0.0, hi - lo - tax)
        item["net_margin_gp"]  = round(net_gp)
        item["net_margin_pct"] = round(net_gp / lo * 100, 2) if lo > 0 else 0
        # Recompute daily flip profit with updated margin
        liq = item.get("liquidity", 0)
        bl  = item.get("buy_limit", 0)
        adv = item.get("avg_daily_vol", 0)
        if bl > 0 and adv > 0:
            cycles = min(6.0, adv / bl)
            item["daily_flip_profit"] = round(net_gp * bl * cycles)
    with _lock:
        _status["refreshed_at"] = int(_time.time())


def _do_news():
    _set("Fetching news…", running=True)
    try:
        s = _svc.fetch_and_store_news()
        _set(f"News: {s['news']} signals, {s['movers']} GE movers. Re-score to apply.")
    except Exception as e:
        _set(f"News error: {e}")


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _svc
    os.makedirs("data", exist_ok=True)

    _db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    init_db(_db)

    _svc = DataService(_db)
    _set("Loading item list and prices…", running=True)
    _svc.initial_load()
    _svc.start_background_refresh(config.REFRESH_INTERVAL_SECONDS)

    # Initial scoring
    threading.Thread(target=_do_score, daemon=True).start()

    # Re-score after 24h bulk fetch completes (~70 s)
    def _delayed():
        import time; time.sleep(70)
        threading.Thread(target=_do_score, daemon=True).start()
    threading.Thread(target=_delayed, daemon=True).start()

    yield

    _svc.stop()
    _db.close()


app = FastAPI(title="OSRS GE Dashboard", lifespan=lifespan)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    with _lock:
        return dict(_status)


@app.post("/api/score")
def api_score(bg: BackgroundTasks):
    if not _status["running"]:
        bg.add_task(_do_score)
    return {"queued": True}


@app.post("/api/refresh")
def api_refresh(bg: BackgroundTasks):
    bg.add_task(_do_refresh)
    return {"queued": True}


@app.post("/api/news")
def api_news(bg: BackgroundTasks):
    bg.add_task(_do_news)
    return {"queued": True}


@app.get("/api/history/status")
def api_history_status():
    """How many items have ≥30 daily candles (i.e. enough for 30d% / full charts)."""
    from database.queries import get_all_items as _get_items, get_snapshots as _get_snaps
    if _db is None:
        return {"ready": 0, "total": 0}
    all_items = _get_items(_db)
    total = len(all_items)
    ready = sum(
        1 for i in all_items
        if len(_get_snaps(_db, i["id"], interval="24h", limit=30)) >= 30
    )
    return {"ready": ready, "total": total, "pct": round(ready / total * 100, 1) if total else 0}


@app.post("/api/history/fetch")
def api_history_fetch(bg: BackgroundTasks):
    """Manually trigger a background history prefetch for all items."""
    if _svc is None:
        return {"queued": False}
    bg.add_task(_svc.prefetch_all_history)
    return {"queued": True}


@app.get("/api/items")
def api_items(
    min_score: float = Query(0),
    strategy:  str   = Query(""),
    search:    str   = Query(""),
    max_price: int   = Query(2_000_000_000),
):
    items = _cache
    if min_score > 0:
        items = [i for i in items if (i.get("score") or 0) >= min_score]
    if strategy:
        items = [i for i in items if i.get("strategy") == strategy]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i.get("name") or "").lower()]
    if max_price < 2_000_000_000:
        items = [i for i in items if (i.get("current_low") or 0) <= max_price]
    return items


@app.get("/api/items/search")
def api_items_search(q: str = Query("")):
    """Autocomplete — returns id + name only, max 15."""
    if len(q) < 2:
        return []
    return [
        {"id": i["id"], "name": i["name"]}
        for i in get_all_items(_db)
        if q.lower() in i["name"].lower()
    ][:15]


@app.get("/api/items/{item_id}/timeseries")
def api_timeseries(item_id: int):
    return _svc.get_timeseries_for_item(item_id)


@app.get("/api/items/{item_id}/intraday")
def api_intraday(item_id: int):
    try:
        return _svc.get_intraday_for_item(item_id)
    except Exception as e:
        log.error("Intraday fetch failed for %d: %s", item_id, e)
        return {"timeseries": [], "latest": {}}


@app.get("/api/recommendations")
def api_recommendations(view: str = Query("strategy")):
    if not _cache:
        return {"sections": []}

    if view == "strategy":
        buckets = group_by_strategy(_cache)
        sections = [
            {
                "key":      s,
                "title":    STRATEGY_LABELS[s],
                "subtitle": STRATEGY_DESC[s],
                "color":    _STRAT_COLORS[s],
                "items":    [_enrich_card(i) for i in buckets.get(s, [])],
            }
            for s in STRATEGIES
        ]
    else:
        buckets = group_by_price_range(_cache)
        sections = [
            {
                "key":      label,
                "title":    label,
                "subtitle": "",
                "color":    "#f39c12",
                "items":    [_enrich_card(i) for i in buckets.get(label, [])],
            }
            for label, _lo, _hi in PRICE_RANGES
        ]

    return {"sections": sections}


def _enrich_card(item: dict) -> dict:
    return {**item, "summary": build_summary(item), "detail": build_detail(item)}


# Watchlist -------------------------------------------------------------------

class _WLBody(BaseModel):
    item_id:   int
    buy_price: Optional[int] = None
    quantity:  Optional[int] = None
    notes:     str = ""


@app.get("/api/watchlist")
def api_wl_get():
    score_by_id = {r["item_id"]: r for r in _cache}
    result = []
    for w in get_watchlist(_db):
        item_id = w["item_id"]
        sd = score_by_id.get(item_id, {})
        row = {**dict(w), **{k: v for k, v in sd.items() if k not in dict(w)}}
        bp = w.get("buy_price")
        qty = w.get("quantity")
        if bp and qty and bp > 0:
            cur_high = sd.get("current_high") or 0
            if cur_high > 0:
                net_sell = cur_high * 0.99
                row["pnl_gp"]  = int((net_sell - bp) * qty)
                row["pnl_pct"] = round((net_sell - bp) / bp * 100, 2)
        result.append(row)
    return result


@app.post("/api/watchlist")
def api_wl_add(body: _WLBody):
    if body.buy_price is None and body.quantity is None:
        # Watch-only: add if new, but never wipe an existing position's buy/qty
        _db.execute(
            "INSERT OR IGNORE INTO watchlist (item_id, notes) VALUES (?, ?)",
            (body.item_id, body.notes or ""),
        )
        _db.commit()
    else:
        add_to_watchlist(_db, body.item_id,
                         buy_price=body.buy_price,
                         quantity=body.quantity,
                         notes=body.notes)
    return {"ok": True}


@app.put("/api/watchlist/{item_id}")
def api_wl_update(item_id: int, body: _WLBody):
    add_to_watchlist(_db, item_id,
                     buy_price=body.buy_price,
                     quantity=body.quantity,
                     notes=body.notes)
    return {"ok": True}


@app.delete("/api/watchlist/{item_id}")
def api_wl_delete(item_id: int):
    remove_from_watchlist(_db, item_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Static files + SPA fallback
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


# ---------------------------------------------------------------------------

_STRAT_COLORS = {
    "FLIP":  "#5dade2",
    "MERCH": "#f39c12",
    "TREND": "#2ecc71",
    "NEWS":  "#e74c3c",
}
