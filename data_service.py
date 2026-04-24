import threading
import logging
import time
from api.wiki_api import get_mapping, get_latest, get_bulk, get_timeseries
from api.rate_limiter import wiki_limiter, item_limiter
from analysis.opportunity_scorer import score_item
from analysis.alert_engine import check_alerts
from database.queries import (
    upsert_items, save_snapshots, get_item_ids_for_scoring,
    get_snapshots, get_all_snapshots_batch, get_all_items, get_item_icon_urls,
    replace_news_signals, get_news_signals_for_items,
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
        # No rate-limiter wait here — first API call of the session
        latest = get_latest()
        save_snapshots(self.db, latest, interval="latest")

        status("Ready.")
        # 24h bulk fetch runs in background (avoids blocking startup for 60s)

    # ------------------------------------------------------------------
    # On-demand
    # ------------------------------------------------------------------

    def get_timeseries_for_item(self, item_id: int) -> list[dict]:
        cached = get_snapshots(self.db, item_id, interval="24h", limit=400)
        if len(cached) >= 30:
            log.debug("Cache hit for item %d (%d rows)", item_id, len(cached))
            return cached

        item_limiter.wait()
        ts = get_timeseries(item_id, timestep="24h")
        if ts:
            _save_timeseries(self.db, item_id, ts)
        return ts

    def score_all_items(self) -> list[dict]:
        # Single batch query instead of N individual get_snapshots() calls
        all_items    = {i["id"]: i for i in get_all_items(self.db)}
        news_by_item = get_news_signals_for_items(self.db)
        all_snapshots = get_all_snapshots_batch(self.db)  # 1 query for all items

        results = []
        for item_id, ts in all_snapshots.items():
            item = all_items.get(item_id)
            if not item or len(ts) < 1:
                continue
            item_signals = news_by_item.get(item_id, [])
            score_dict   = score_item(ts,
                                      buy_limit=item.get("buy_limit") or 0,
                                      news_signals=item_signals)
            if score_dict.get("score", 0) > 0:
                score_dict["item_id"] = item_id
                score_dict["name"]    = item["name"]
                results.append(score_dict)

        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        log.info("Scored %d items.", len(results))
        return results

    # ------------------------------------------------------------------
    # News & GE market data
    # ------------------------------------------------------------------

    def fetch_and_store_news(self) -> dict:
        """
        Scrape OSRS news archive and GE market movers, match items,
        store signals. Returns a summary dict.
        """
        from analysis.news_analyzer import fetch_news_signals
        from api.ge_scraper import get_market_movers

        items = get_all_items(self.db)
        item_names = {i["id"]: i["name"] for i in items}

        # --- News signals ---
        log.info("Fetching OSRS news signals…")
        news_signals = fetch_news_signals(item_names, pages=3)

        # --- GE market movers → signals ---
        log.info("Fetching GE market movers…")
        movers = get_market_movers()
        name_to_id = {v.lower(): k for k, v in item_names.items()}
        mover_signals = []

        for entry in movers.get("rises", []):
            item_id = name_to_id.get(entry["name"].lower())
            if item_id:
                mover_signals.append({
                    "item_id":       item_id,
                    "item_name":     entry["name"],
                    "article_title": entry["change"],
                    "article_url":   "",
                    "article_date":  "",
                    "signal_type":   "ge_rise",
                })

        all_signals = news_signals + mover_signals
        replace_news_signals(self.db, all_signals)

        summary = {"news": len(news_signals), "movers": len(mover_signals)}
        log.info("News fetch complete: %s", summary)
        return summary

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
        # Fetch the 24h bulk snapshot in background (respects 60s rate limit)
        threading.Thread(target=self._background_bulk_24h, daemon=True).start()
        log.info("Background refresh started (every %ds).", interval_seconds)

    def get_item_icon_urls(self) -> dict:
        return get_item_icon_urls(self.db)

    def prefetch_top_items_history(self, n: int = 200):
        """Fetch full timeseries for top-N items (by volume), storing in DB."""
        import config as _config
        log.info("Prefetching timeseries for up to %d items…", n)

        all_items = {i["id"]: i for i in get_all_items(self.db)}
        news_by_item = get_news_signals_for_items(self.db)

        # Priority: news items first, then HIGH_VALUE_SEEDS, then all
        news_ids  = list(news_by_item.keys())
        seed_ids  = list(_config.HIGH_VALUE_SEEDS.keys())
        all_ids   = list(all_items.keys())

        priority = []
        seen: set = set()
        for iid in news_ids + seed_ids + all_ids:
            if iid not in seen:
                priority.append(iid)
                seen.add(iid)
        priority = priority[:n]

        fetched = 0
        for item_id in priority:
            cached = get_snapshots(self.db, item_id, interval="24h", limit=10)
            if len(cached) >= 10:
                continue
            try:
                item_limiter.wait()
                ts = get_timeseries(item_id, timestep="24h")
                if ts:
                    _save_timeseries(self.db, item_id, ts)
                    fetched += 1
            except Exception as e:
                log.debug("Prefetch failed for item %d: %s", item_id, e)

        log.info("Prefetch complete — fetched %d items.", fetched)

    def _background_bulk_24h(self):
        try:
            wiki_limiter.wait()
            bulk = get_bulk("24h")
            save_snapshots(self.db, bulk, interval="24h")
            log.info("Background 24h bulk fetch complete (%d items).", len(bulk))
        except Exception as e:
            log.error("Background 24h fetch failed: %s", e)
        threading.Thread(target=self.prefetch_top_items_history,
                         args=(200,), daemon=True).start()

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
    db_rows = [
        (
            item_id,
            r.get("timestamp") or now,
            r.get("avgHighPrice"),
            r.get("avgLowPrice"),
            r.get("highPriceVolume"),
            r.get("lowPriceVolume"),
            "24h",
        )
        for r in rows
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO price_snapshots
            (item_id, timestamp, high, low, high_vol, low_vol, interval)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        db_rows,
    )
    conn.commit()
