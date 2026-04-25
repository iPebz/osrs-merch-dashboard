CREATE_ITEMS = """
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    examine      TEXT,
    buy_limit    INTEGER,
    icon_url     TEXT,
    members      BOOLEAN,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PRICE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS price_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    high      INTEGER,
    low       INTEGER,
    high_vol  INTEGER,
    low_vol   INTEGER,
    interval  TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id)
);
"""

CREATE_WATCHLIST = """
CREATE TABLE IF NOT EXISTS watchlist (
    item_id          INTEGER PRIMARY KEY,
    alert_buy_below  INTEGER,
    alert_sell_above INTEGER,
    notes            TEXT,
    added_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id)
);
"""

CREATE_ALERTS_LOG = """
CREATE TABLE IF NOT EXISTS alerts_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL,
    alert_type TEXT NOT NULL,
    price      INTEGER NOT NULL,
    threshold  INTEGER NOT NULL,
    fired_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_NEWS_SIGNALS = """
CREATE TABLE IF NOT EXISTS news_signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       INTEGER NOT NULL,
    article_title TEXT NOT NULL,
    article_url   TEXT NOT NULL,
    article_date  TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    scraped_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id)
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_snapshots_item_time
    ON price_snapshots (item_id, timestamp, interval);
CREATE INDEX IF NOT EXISTS idx_news_item
    ON news_signals (item_id, scraped_at);
"""


def init_db(conn):
    cursor = conn.cursor()
    for stmt in [CREATE_ITEMS, CREATE_PRICE_SNAPSHOTS,
                 CREATE_WATCHLIST, CREATE_ALERTS_LOG,
                 CREATE_NEWS_SIGNALS, CREATE_INDEXES]:
        cursor.executescript(stmt)
    _migrate(conn)
    conn.commit()


def _migrate(conn):
    """Idempotent migrations applied to existing databases."""
    # Migration 1: deduplicate snapshots and add unique index to prevent future dupes
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_snapshots_unique'"
    ).fetchone()
    if not exists:
        # Remove duplicate rows, keeping the most-recently inserted one per (item, ts, interval)
        conn.execute("""
            DELETE FROM price_snapshots
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM   price_snapshots
                GROUP  BY item_id, timestamp, interval
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX idx_snapshots_unique
                ON price_snapshots (item_id, timestamp, interval)
        """)
        conn.commit()

    # Migration 2: add position tracking columns to watchlist
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(watchlist)").fetchall()}
    if "buy_price" not in existing_cols:
        conn.execute("ALTER TABLE watchlist ADD COLUMN buy_price INTEGER")
        conn.execute("ALTER TABLE watchlist ADD COLUMN quantity  INTEGER")
        conn.commit()
