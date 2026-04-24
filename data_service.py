import threading
import logging
import time
from api.wiki_api import get_mapping, get_latest, get_bulk, get_timeseries
from api.rate_limiter import wiki_limiter, item_limiter
from analysis.opportunity_scorer import score_item
from analysis.alert_engine import check_alerts
from database.queries import (
    upsert_items, save_snapshots, get_item_ids_for_scoring,
    get_snapshots, get_all_items,
)

log = logging.getLogger(__name__)


class DataService:
    def __init__(self, db_conn):
        self.db        = db_conn
        self._running  = False
        self._thread   = None

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def initial_load(self, progress_callback=None):
        def status(msg):
            log.info(msg)
            if progress_callback:
                progress_callback(msg)

        status("Loading item list…")
        mapping = get_mapping()
        upsert_items(self.db, mapping)

        status("Fetching current prices…")
        wiki_limiter.wait()
        latest = get_latest()
        save_snapshots(self.db, latest, interval="latest")

        status("Fetching 24h market data…")
        wiki_limiter.wait()
        bulk_24h = get_bulk("24h")
        save_snapshots(self.db, bulk_24h, interval="24h")

        status("Ready.")

    # ------------------------------------------------------------------
    # On-demand
    # ------------------------------------------------------------------

    def get_timeseries_for_item(self, item_id: int) -> list[dict]:
        # Try local DB first (saves API calls)
        cached = get_snapshots(self.db, item_id, interval="24h", limit=400)
        if len(cached) >= 30:
            log.debug("Cache hit for item %d (%d rows)", item_id, len(cached))
            return cached

        item_limiter.wait()
        ts = get_timeseries(item_id, timestep="24h")
        if ts:
            save_snapshots(self.db, {str(item_id): {}}, interval="24h")
            # Save via bulk helper by re-keying into expected shape
            _save_timeseries(self.db, item_id, ts)
        return ts

    def score_all_items(self) -> list[dict]:
        item_ids = get_item_ids_for_scoring(self.db)
        all_items = {i["id"]: i for i in get_all_items(self.db)}

        results = []
        for item_id in item_ids:
            item = all_items.get(item_id)
            if not item:
                continue
            ts = get_snapshots(self.db, item_id, interval="24h", limit=365)
            if not ts:
                continue
            score_dict = score_item(ts, buy_limit=item.get("buy_limit") or 0)
            if score_dict.get("score", 0) > 0:
                score_dict["item_id"] = item_id
                score_dict["name"]    = item["name"]
                results.append(score_dict)

        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        log.info("Scored %d items.", len(results))
        return results

    # ------------------------------------------------------------------
    # Background refresh
    # ------------------------------------------------------------------

    def refresh_latest(self):
        wiki_limiter.wait()
        latest = get_latest()
        save_snapshots(self.db, latest, interval="latest")
        check_alerts(self.db, latest)

    def start_background_refresh(self, interval_seconds: int = 90):
        self._running = True
        self._thread  = threading.Thread(
            target=self._refresh_loop,
            args=(interval_seconds,),
            daemon=True,
        )
        self._thread.start()
        log.info("Background refresh started (every %ds).", interval_seconds)

    def stop(self):
        self._running = False

    def _refresh_loop(self, interval_seconds: int):
        while self._running:
            try:
                self.refresh_latest()
                log.debug("Background refresh complete.")
            except Exception as e:
                log.error("Background refresh error: %s", e)
            time.sleep(interval_seconds)


# ------------------------------------------------------------------
# Helper: persist fetched timeseries rows to DB
# ------------------------------------------------------------------

def _save_timeseries(conn, item_id: int, rows: list[dict]):
    import time as _time
    now = int(_time.time())
    db_rows = []
    for r in rows:
        db_rows.append((
            item_id,
            r.get("timestamp") or now,
            r.get("avgHighPrice"),
            r.get("avgLowPrice"),
            r.get("highPriceVolume"),
            r.get("lowPriceVolume"),
            "24h",
        ))
    conn.executemany(
        """
        INSERT OR IGNORE INTO price_snapshots
            (item_id, timestamp, high, low, high_vol, low_vol, interval)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        db_rows,
    )
    conn.commit()
