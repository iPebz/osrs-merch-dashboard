import sqlite3
import logging
from typing import Optional

log = logging.getLogger(__name__)


def upsert_items(conn: sqlite3.Connection, mapping: list[dict]):
    cursor = conn.cursor()
    cursor.executemany(
        """
        INSERT INTO items (id, name, examine, buy_limit, icon_url, members, last_updated)
        VALUES (:id, :name, :examine, :limit, :icon, :members, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            name         = excluded.name,
            examine      = excluded.examine,
            buy_limit    = excluded.buy_limit,
            icon_url     = excluded.icon_url,
            members      = excluded.members,
            last_updated = CURRENT_TIMESTAMP
        """,
        [
            {
                "id":      item.get("id"),
                "name":    item.get("name"),
                "examine": item.get("examine"),
                "limit":   item.get("limit"),
                "icon":    item.get("icon"),
                "members": item.get("members", False),
            }
            for item in mapping
            if item.get("id") and item.get("name")
        ],
    )
    conn.commit()
    log.info("Upserted %d items into items table.", len(mapping))


def save_snapshots(conn: sqlite3.Connection, data: dict, interval: str):
    """
    data: { str(item_id): { high, low, highTime, lowTime,
                             avgHighPrice, avgLowPrice,
                             highPriceVolume, lowPriceVolume,
                             timestamp }, ... }
    Handles both /latest and /5m|/1h|/24h response shapes.
    """
    import time as _time

    rows = []
    now = int(_time.time())
    for item_id_str, v in data.items():
        try:
            item_id = int(item_id_str)
        except ValueError:
            continue

        if interval == "latest":
            high = v.get("high")
            low  = v.get("low")
            ts   = v.get("highTime") or v.get("lowTime") or now
            high_vol = None
            low_vol  = None
        else:
            high     = v.get("avgHighPrice")
            low      = v.get("avgLowPrice")
            high_vol = v.get("highPriceVolume")
            low_vol  = v.get("lowPriceVolume")
            ts       = v.get("timestamp") or now

        rows.append((item_id, ts, high, low, high_vol, low_vol, interval))

    conn.executemany(
        """
        INSERT INTO price_snapshots (item_id, timestamp, high, low, high_vol, low_vol, interval)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    log.debug("Saved %d snapshots (interval=%s).", len(rows), interval)


def get_snapshots(conn: sqlite3.Connection, item_id: int,
                  interval: str = "24h", limit: int = 365) -> list[dict]:
    cursor = conn.execute(
        """
        SELECT timestamp, high, low, high_vol, low_vol
        FROM   price_snapshots
        WHERE  item_id = ? AND interval = ?
        ORDER  BY timestamp DESC
        LIMIT  ?
        """,
        (item_id, interval, limit),
    )
    rows = cursor.fetchall()
    return [
        {
            "timestamp":          r["timestamp"],
            "avgHighPrice":       r["high"],
            "avgLowPrice":        r["low"],
            "highPriceVolume":    r["high_vol"],
            "lowPriceVolume":     r["low_vol"],
        }
        for r in reversed(rows)
    ]


def get_all_items(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute("SELECT id, name, buy_limit, members FROM items ORDER BY name")
    return [dict(r) for r in cursor.fetchall()]


def get_item_icon_urls(conn: sqlite3.Connection) -> dict:
    """Return {item_id: icon_url} for all items that have an icon_url."""
    cursor = conn.execute("SELECT id, icon_url FROM items WHERE icon_url IS NOT NULL")
    return {r["id"]: r["icon_url"] for r in cursor.fetchall()}


def get_item_ids_for_scoring(conn: sqlite3.Connection) -> list[int]:
    cursor = conn.execute(
        """
        SELECT DISTINCT item_id FROM price_snapshots
        WHERE interval = '24h'
        GROUP BY item_id HAVING COUNT(*) >= 2
        """
    )
    return [r[0] for r in cursor.fetchall()]


def get_watchlist(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute(
        """
        SELECT w.item_id, i.name, w.alert_buy_below, w.alert_sell_above, w.notes
        FROM   watchlist w
        JOIN   items i ON i.id = w.item_id
        ORDER  BY i.name
        """
    )
    return [dict(r) for r in cursor.fetchall()]


def add_to_watchlist(conn: sqlite3.Connection, item_id: int,
                     buy_below: Optional[int] = None,
                     sell_above: Optional[int] = None,
                     notes: str = ""):
    conn.execute(
        """
        INSERT INTO watchlist (item_id, alert_buy_below, alert_sell_above, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            alert_buy_below  = excluded.alert_buy_below,
            alert_sell_above = excluded.alert_sell_above,
            notes            = excluded.notes
        """,
        (item_id, buy_below, sell_above, notes),
    )
    conn.commit()


def remove_from_watchlist(conn: sqlite3.Connection, item_id: int):
    conn.execute("DELETE FROM watchlist WHERE item_id = ?", (item_id,))
    conn.commit()


def log_alert(conn: sqlite3.Connection, item_id: int, alert_type: str,
              price: int, threshold: int):
    conn.execute(
        """
        INSERT INTO alerts_log (item_id, alert_type, price, threshold)
        VALUES (?, ?, ?, ?)
        """,
        (item_id, alert_type, price, threshold),
    )
    conn.commit()


def get_recent_alerts(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    cursor = conn.execute(
        """
        SELECT al.fired_at, i.name, al.alert_type, al.price, al.threshold
        FROM   alerts_log al
        JOIN   items i ON i.id = al.item_id
        ORDER  BY al.fired_at DESC
        LIMIT  ?
        """,
        (limit,),
    )
    return [dict(r) for r in cursor.fetchall()]


def alert_recently_fired(conn: sqlite3.Connection, item_id: int,
                         alert_type: str, cooldown_minutes: int) -> bool:
    cursor = conn.execute(
        """
        SELECT 1 FROM alerts_log
        WHERE  item_id = ? AND alert_type = ?
          AND  fired_at >= datetime('now', ? || ' minutes')
        LIMIT  1
        """,
        (item_id, alert_type, f"-{cooldown_minutes}"),
    )
    return cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# News signals
# ---------------------------------------------------------------------------

def replace_news_signals(conn: sqlite3.Connection, signals: list[dict]):
    """Delete all existing signals and insert the fresh batch atomically."""
    conn.execute("DELETE FROM news_signals")
    if signals:
        conn.executemany(
            """
            INSERT INTO news_signals
                (item_id, article_title, article_url, article_date, signal_type)
            VALUES (:item_id, :article_title, :article_url, :article_date, :signal_type)
            """,
            signals,
        )
    conn.commit()
    log.info("Stored %d news signals.", len(signals))


def get_news_signals_for_items(conn: sqlite3.Connection) -> dict:
    """Return {item_id: [signal_dict, ...]} for all stored signals."""
    cursor = conn.execute(
        """
        SELECT item_id, article_title, article_url, article_date, signal_type
        FROM   news_signals
        ORDER  BY article_date DESC
        """
    )
    result: dict = {}
    for row in cursor.fetchall():
        iid = row["item_id"]
        result.setdefault(iid, []).append(dict(row))
    return result


def get_recent_news_signals(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Return latest signals across all items, for the news feed UI."""
    cursor = conn.execute(
        """
        SELECT ns.item_id, i.name, ns.article_title, ns.article_url,
               ns.article_date, ns.signal_type, ns.scraped_at
        FROM   news_signals ns
        JOIN   items i ON i.id = ns.item_id
        ORDER  BY ns.scraped_at DESC, ns.article_date DESC
        LIMIT  ?
        """,
        (limit,),
    )
    return [dict(r) for r in cursor.fetchall()]
