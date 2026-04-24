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
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id  INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    high     INTEGER,
    low      INTEGER,
    high_vol INTEGER,
    low_vol  INTEGER,
    interval TEXT NOT NULL,
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

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_snapshots_item_time
    ON price_snapshots (item_id, timestamp, interval);
"""


def init_db(conn):
    cursor = conn.cursor()
    for stmt in [CREATE_ITEMS, CREATE_PRICE_SNAPSHOTS,
                 CREATE_WATCHLIST, CREATE_ALERTS_LOG, CREATE_INDEXES]:
        cursor.executescript(stmt)
    conn.commit()
