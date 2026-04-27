# OSRS GE Merching Dashboard

A self-hosted web dashboard for analysing Grand Exchange trading opportunities in Old School RuneScape. Scores every tradeable item 0–100 using a strategy-first pipeline — FLIP, MERCH, TREND, or NEWS — and surfaces the best plays across each category in real time.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-latest-green) ![Docker](https://img.shields.io/badge/Docker-supported-blue)

---

## Features

### Dashboard tab
- Scored item table — every tradeable item ranked by score, with strategy badge (FLIP / MERCH / TREND / NEWS), price, net margin %, estimated GP/day, 1d% change, 30d% change, RSI, and daily volume
- **Top Picks** strip showing the 5 highest-scored items at a glance with icons
- Min score slider, min/max price filters, item search, and strategy dropdown — all live-filter without reloads
- **Info** button on each row opens a score breakdown modal showing every factor that added or subtracted points, starting from the base of 50
- Column header tooltips explaining each metric
- Click any row to open that item's chart

### Charts tab
- **Daily chart** (30d/90d/180d/All): price band (high/low fill) + Mid line + MA30 + MA90 + colour-coded volume bars + RSI panel
- **1d intraday** chart: 5-minute candles from the Wiki API — buy/sell price band with volume for the last ~24 hours
- Volume bars are colour-coded by spike intensity vs the 30-day rolling average:
  - Normal → blue · 1.5× → purple · 2× → orange · 3×+ → red
- **Stats bar** shows: Low/High, spread %, data age, 1d change, 7d/30d/90d slope, RSI (14), Vol Spike (when ≥ 1.5× avg), and avg daily volume
- Item search autocomplete; or click any row in Dashboard / Watchlist / Recommendations to open directly

### Watchlist tab
- Track items with **+ Watch** (no position) or **+ Position** (buy price + quantity)
- Watch-only adds never overwrite existing position data
- **Portfolio summary bar** — total invested, current value, total P&L in gp, P&L %
- P&L is calculated from `current_high × 0.99` (accounting for 1% GE tax) minus cost basis
- Select a row to edit buy price / quantity, remove the item, or open its chart

### Recommendations tab
| Tab | Description |
|-----|-------------|
| **Flips** | Highest time-averaged net margin with sufficient liquidity — reliable spread income |
| **Merch** | Items below their 90d MA with intact long-term trend — buy the dip |
| **Trend** | Multi-timeframe uptrends with MACD momentum and RSI not overbought — ride the momentum |
| **News** | Items with a game-update or GE market-mover signal driving short-term demand |
| **By Price Range** | Top items bucketed: <1M · 1–5M · 10–25M · 25–100M · 100M+ |

Each card shows the item icon, score, price, a one-line summary, and an expandable detail section with trade instructions, technicals, risk notes, and the full score breakdown. Up to 25 items per bucket.

---

## Scoring engine

Each item is classified into a strategy **first**, then scored with a strategy-specific factor pool. This ensures FLIP items aren't penalised by RSI and MERCH items aren't boosted by spread margin.

### Strategy classification (priority order)
1. **NEWS** — game update, GE mover, or 3+ article mentions → overrides all other signals
2. **FLIP** — 14-day time-averaged margin ≥ 2% after tax AND liquidity ≥ 1.5× buy limit/day
3. **TREND (volume spike)** — volume ≥ 2× 30d average AND slope > −0.5 AND not a falling knife → signals large-player / merch-clan accumulation
4. **MERCH** — genuine dip + slope ≥ −0.1 + merch recovery profit ≥ 2M + not a falling knife
5. **TREND** — slope ≥ 0 + multi-timeframe agreement ≥ 1 + RSI < 65
6. **FLIP** — default fallback

### Technical indicators used
| Indicator | Purpose |
|-----------|---------|
| Price slope (7d / 30d / 90d) | Trend direction and strength |
| RSI (14-period) | Overbought / oversold detection |
| MACD (12/26/9) | Momentum and crossover signals |
| Bollinger Bands (20-period) | Volatility and squeeze breakout potential |
| Multi-timeframe agreement | Counts how many of 3 timeframes agree on direction |
| Price vs MA90 | Dip depth below long-term average |
| Support / resistance levels | Recovery upside estimation |
| Volume-price divergence | Confirms or challenges the price move |
| Volume spike ratio | Current vs 30d average daily volume |
| Time-averaged margin (14d) | Manipulation-resistant spread score |
| Falling knife guard | Suppresses MERCH classification when RSI < 35 in a steep downtrend |

### Universal score bonuses (all strategies)
| Condition | Bonus |
|-----------|-------|
| Volume spike 1.5× avg | +5 |
| Volume spike 2× avg | +10 |
| Volume spike 3×+ avg | +15 |

Scores are clamped to **0–100**. The reason string in the Info modal shows every factor applied.

---

## Live price updates

Prices are patched in the background every **60 seconds** without a full rescore:
- `current_low`, `current_high`, `net_margin_gp/pct`, and `daily_flip_profit` update in-place from the latest Wiki API snapshot
- The status bar shows **"prices Xs ago"** so you always know how fresh the data is
- The dashboard table auto-reloads whenever new prices arrive

---

## Data sources

| Source | Used for |
|--------|----------|
| [OSRS Wiki Prices API](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices) | Live prices (`/latest`), timeseries (`/24h`, `/5m`), bulk snapshots |
| OSRS Wiki CDN | Item icons |
| OSRS news archive | Game-update signals (scraped via BeautifulSoup) |
| GE market movers page | Rising-item signals |

---

## Running with Docker (recommended)

```bash
git clone https://github.com/iPebz/osrs-merch-dashboard.git
cd osrs-merch-dashboard
docker compose up -d
```

Open **http://localhost:8000**, then click **Score All Items**.

The SQLite database is stored in the `osrs-data` named volume and survives restarts and rebuilds.

```bash
docker compose down              # stop
docker compose up -d --build     # rebuild after pulling updates
docker compose logs -f           # stream logs
```

---

## Running locally (Python)

```bash
git clone https://github.com/iPebz/osrs-merch-dashboard.git
cd osrs-merch-dashboard

python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # macOS / Linux

pip install -r requirements.txt
python main_web.py
```

Open **http://localhost:8000**.

---

## Project structure

```
├── server.py                     FastAPI app — all HTTP routes
├── main_web.py                   Uvicorn entry point
├── data_service.py               Orchestrates API calls, scoring, background refresh
├── config.py                     Scoring weights, thresholds, seed items
│
├── analysis/
│   ├── opportunity_scorer.py     Strategy-first 0–100 scoring engine
│   ├── trend_analyzer.py         RSI, MACD, Bollinger, slopes, MA, dip, spike detection
│   ├── news_analyzer.py          OSRS news scraper → item signals
│   └── recommendation_engine.py  Groups items into strategy / price buckets
│
├── api/
│   ├── wiki_api.py               OSRS Wiki prices API client
│   ├── ge_scraper.py             GE market movers scraper
│   └── rate_limiter.py           Token-bucket rate limiter
│
├── database/
│   ├── schema.py                 SQLite table definitions + migrations
│   └── queries.py                All DB reads and writes
│
├── static/
│   ├── index.html                Single-page app shell
│   ├── app.js                    Vanilla JS — all tab logic, Plotly charts, watchlist
│   └── style.css                 Dark theme
│
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── requirements.txt
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `REFRESH_INTERVAL_SECONDS` | 60 | Background price patch frequency |
| `MIN_DAILY_VOLUME` | 50 | Items below this daily volume are skipped |
| `DEFAULT_SCORE_THRESHOLD` | 40 | Items below this score are hidden by default |
| `BUDGET_MAX_GP` | 2 000 000 000 | Upper price cap |
| `WEIGHT_TREND/RSI/DIP/MARGIN/VOLUME` | 1.0 | Per-factor scoring multipliers |
| `HIGH_VALUE_SEEDS` | god swords, supplies, etc. | Items prefetched on first startup |

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Status message, running flag, scored-item count, last refresh timestamp |
| POST | `/api/score` | Trigger full rescore in background |
| POST | `/api/refresh` | Patch latest prices in background |
| POST | `/api/news` | Fetch news signals and GE movers |
| GET | `/api/items` | All scored items (filters: `min_score`, `strategy`, `search`, `max_price`) |
| GET | `/api/items/search` | Autocomplete — returns id + name, max 15 results |
| GET | `/api/items/{id}/timeseries` | 24h daily candles for an item |
| GET | `/api/items/{id}/intraday` | 5-minute candles for last ~24 hours |
| GET | `/api/recommendations` | Strategy/price buckets (`view=strategy` or `view=price`) |
| GET | `/api/watchlist` | Watchlist with live scores and P&L |
| POST | `/api/watchlist` | Add item (watch-only or with position) |
| PUT | `/api/watchlist/{id}` | Update buy price / quantity |
| DELETE | `/api/watchlist/{id}` | Remove item |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Data analysis | pandas, numpy |
| Database | SQLite (Python stdlib) |
| Frontend | Vanilla JS, Plotly.js 2.26 |
| Containerisation | Docker, Docker Compose |
| Data | OSRS Wiki Prices API, BeautifulSoup4 |

---

## Notes

- **First startup** performs an initial data load (~30 s), then a background 24h bulk fetch and top-200 item history prefetch (~70 s). Click **Score All Items** after the status bar shows "Ready".
- **Leagues events** — article signals matching "league" / "leagues" are filtered out at both the fetch and scoring stage; Leagues runs on isolated servers and has no effect on main-game GE prices.
- **GE tax** — all margin calculations use 1% sell-side tax, capped at 5 M per transaction.
- Item IDs in `HIGH_VALUE_SEEDS` (config.py) can be verified at [oldschool.runescape.wiki](https://oldschool.runescape.wiki).
