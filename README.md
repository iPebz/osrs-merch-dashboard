# OSRS GE Merching Dashboard

A self-hosted web dashboard for analysing Grand Exchange trading opportunities in Old School RuneScape. Scores every tradeable item against price trends, RSI, margin, volume, and news signals, then surfaces the best flips, dip-buys, trend rides, and news plays.

![Dashboard](https://img.shields.io/badge/Python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-latest-green) ![Docker](https://img.shields.io/badge/Docker-supported-blue)

---

## Features

### Dashboard tab
- Scored item table — every tradeable item ranked 0–100 with colour-coded score, strategy badge, price, margin %, GP/day, 7d/90d slope, RSI, and daily volume
- **Min Score** slider and **Min / Max Price** text filters, plus a live search and strategy dropdown — all live-filter without page reloads
- **Top Picks** strip at the top showing the 5 highest-scored items at a glance
- **Info button** on each row opens a modal with a full colour-coded score breakdown (which factors added or subtracted points, and by how much)
- Hover any column header for a tooltip explaining what that metric means
- Click any row to jump straight to the Charts tab for that item

### Charts tab
- Interactive Plotly chart with price band (high/low fill), Mid line, MA30, MA90, RSI pane, and Volume pane
- Range buttons: **1d · 30d · 90d · 180d · All**
- **1d (intraday)** mode fetches 5-minute candles from the wiki API and draws a buy/sell price band with volume — shows the last ~24 hours of trading
- **Stat bar** below the range buttons shows: Low/High prices, spread %, data age, and (for daily charts) 7d/30d/90d slope, RSI, and avg daily volume
- Item search autocomplete, or click any row in Dashboard/Watchlist/Recommendations to chart it directly

### Watchlist tab
- Track items with `+ Watch` (no position data) or `+ Position` (enter buy price and quantity)
- Adding an item as Watch never overwrites existing position data
- **Portfolio summary bar** — when you have positions, shows total invested, current value, total P&L in gp, and P&L %
- P&L is calculated client-side from `current_high × 0.99` (accounting for 1 % GE tax) minus your buy price × quantity
- Select a row to reveal an action bar: edit buy price / qty, remove the item, or open its chart

### Recommendations tab
Four strategy tabs plus a price range view:

| Tab | What it shows |
|-----|---------------|
| **Flips** | Items with the highest net margin after GE tax and sufficient liquidity to fill orders |
| **Merch** | Items trading below their 90-day moving average with intact long-term trend — buy the dip |
| **Trend** | Multi-timeframe uptrends with RSI not yet overbought — ride the momentum |
| **News** | Items with a recent game-update or GE market-mover signal |
| **By Price Range** | Top items bucketed by price: <1M · 1–5M · 10–25M · 25–100M · 100M+ |

Each strategy card shows the item icon, score, price, a one-line summary, and an expandable detail section with trade instructions, technicals, risk notes, and the full score breakdown.

Up to **25 items per bucket** are shown.

---

## Scoring engine

Each item starts at a base score of **50** and factors are added or subtracted:

| Factor | Range |
|--------|-------|
| Multi-timeframe trend agreement (3 timeframes) | −20 to +18 |
| RSI (14-period) — oversold/overbought | −14 to +22 |
| Price dip vs 90-day MA | 0 to +20 |
| Net margin after GE tax | −8 to +15 |
| Liquidity (volume vs buy limit) | −20 to +8 |
| 90-day slope | −8 to +6 |
| Volume trend (rising/falling) | −6 to +5 |
| Upside to resistance | 0 to +8 |
| Short-term momentum | −5 to +5 |
| News/GE-rise boost | 0 to +20 |
| Daily GP floor penalty | −25 to 0 |

Leagues game-mode articles are filtered out at both the fetch stage and the scoring stage — Leagues runs on separate servers with an independent economy and has no bearing on main-game GE prices.

---

## Data sources

- **Prices & timeseries** — [OSRS Wiki Prices API](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices) (`/latest`, `/timeseries`, `/5m`, `/24h`)
- **Item icons** — OSRS Wiki CDN
- **News signals** — OSRS news archive + GE market movers page (scraped via BeautifulSoup)

Prices refresh every **90 seconds** in the background. A 24-hour bulk snapshot and top-200 item history are pre-fetched on startup.

---

## Running with Docker (recommended)

```bash
# Clone and start
git clone https://github.com/iPebz/osrs-merch-dashboard.git
cd osrs-merch-dashboard
docker compose up -d
```

Open **http://localhost:8000** in your browser, then click **Score All Items**.

The SQLite database is stored in a named Docker volume (`osrs-data`) and survives container restarts and image rebuilds.

```bash
# Stop
docker compose down

# Rebuild after pulling updates
docker compose up -d --build

# View logs
docker compose logs -f
```

---

## Running locally (Python)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements-web.txt
python main_web.py
```

Open **http://localhost:8000**.

---

## Project structure

```
├── server.py                  # FastAPI app — all HTTP routes
├── main_web.py                # Uvicorn entrypoint
├── data_service.py            # Orchestrates API calls, scoring, background refresh
├── config.py                  # Thresholds, refresh interval, seed items
├── analysis/
│   ├── opportunity_scorer.py  # 0–100 scoring engine
│   ├── trend_analyzer.py      # RSI, slopes, MA, dip detection
│   ├── news_analyzer.py       # OSRS news scraper → item signals
│   └── recommendation_engine.py  # Groups items into strategy/price buckets
├── api/
│   ├── wiki_api.py            # OSRS wiki prices API client
│   ├── ge_scraper.py          # GE market movers scraper
│   └── rate_limiter.py        # Token-bucket rate limiter
├── database/
│   ├── schema.py              # SQLite schema + migrations
│   └── queries.py             # All DB reads and writes
├── static/
│   ├── index.html             # Single-page app shell
│   ├── app.js                 # Vanilla JS — all tab logic, charts, watchlist
│   └── style.css              # Dark theme styles
├── Dockerfile
├── docker-compose.yml
└── requirements-web.txt
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Current status message and scored-item count |
| POST | `/api/score` | Trigger a full rescore in the background |
| POST | `/api/refresh` | Refresh latest prices |
| POST | `/api/news` | Fetch news signals and GE movers |
| GET | `/api/items` | Scored items (supports `min_score`, `strategy`, `search`, `max_price`) |
| GET | `/api/items/search` | Autocomplete search (returns id + name, max 15) |
| GET | `/api/items/{id}/timeseries` | 24h timeseries for an item |
| GET | `/api/items/{id}/intraday` | 5-minute intraday timeseries for an item |
| GET | `/api/recommendations` | Grouped recommendations (`view=strategy` or `view=price`) |
| GET | `/api/watchlist` | Watchlist items enriched with live score data and P&L |
| POST | `/api/watchlist` | Add item to watchlist (watch-only or with position) |
| PUT | `/api/watchlist/{id}` | Update buy price / quantity for a watchlist item |
| DELETE | `/api/watchlist/{id}` | Remove item from watchlist |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Data analysis | pandas, numpy |
| Database | SQLite (via Python stdlib) |
| Frontend | Vanilla JS (no framework), Plotly.js for charts |
| Containerisation | Docker, Docker Compose |
| Data | OSRS Wiki Prices API, BeautifulSoup4 |
