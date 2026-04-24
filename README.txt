OSRS GE Merching Dashboard
==========================

A local Python desktop application for Old School RuneScape Grand Exchange merchants.
Monitors live item prices, analyzes market trends, and surfaces long-term hold
opportunities within a 10M-100M GP budget.


FEATURES
--------
- Live price data pulled from the OSRS Wiki API (updates every ~60 seconds)
- Technical analysis: RSI, price slope, dip detection, margin, volume trends
- Opportunity scorer ranks all items 0-100 for merch potential
- Interactive price charts with 30/90-day moving averages and RSI subplot
- Watchlist with configurable buy/sell price alerts and desktop notifications
- All data stored locally in SQLite (works offline after first load)


REQUIREMENTS
------------
- Python 3.10 or higher
- See requirements.txt for all dependencies


INSTALLATION
------------
1. Clone the repository:
   git clone https://github.com/iPebz/osrs-merch-dashboard.git
   cd osrs-merch-dashboard

2. Create and activate a virtual environment:
   python -m venv venv
   venv\Scripts\activate        (Windows)
   source venv/bin/activate     (Mac/Linux)

3. Install dependencies:
   pip install -r requirements.txt

4. Run the app:
   python main.py


PROJECT STRUCTURE
-----------------
osrs-merch-dashboard/
  main.py               Entry point - launches GUI
  config.py             User settings, budget limits, scoring weights
  data_service.py       Orchestrates API calls, DB writes, background refresh
  requirements.txt      Python dependencies

  api/
    wiki_api.py         OSRS Wiki prices API wrapper
    jagex_api.py        Jagex official GE API wrapper (180-day history)
    rate_limiter.py     Polite rate limiting for all API requests

  analysis/
    trend_analyzer.py   Price trend detection (slope, MA, RSI, dip, volatility)
    opportunity_scorer.py  Scores items for merch potential (0-100)
    alert_engine.py     Threshold checking and desktop notifications

  database/
    schema.py           SQLite table definitions
    queries.py          All DB read/write operations

  gui/
    app.py              Main application window (3 tabs)
    dashboard_tab.py    Sortable opportunity table with filters
    chart_tab.py        Interactive price chart per item
    watchlist_tab.py    Watched items and alert configuration
    styles.py           Colors, fonts, theme constants

  data/
    ge_prices.db        Local SQLite database (gitignored)


CONFIGURATION
-------------
Edit config.py to tune the dashboard:

  BUDGET_MIN_GP             Minimum item price to consider (default: 10,000)
  BUDGET_MAX_GP             Maximum item price to consider (default: 50,000,000)
  DEFAULT_SCORE_THRESHOLD   Minimum score shown in dashboard (default: 55)
  REFRESH_INTERVAL_SECONDS  How often to poll for new prices (default: 90)
  ALERT_COOLDOWN_MINUTES    Minimum time between repeat alerts (default: 60)

  Scoring weights (all default 1.0, lower = less influence):
    WEIGHT_TREND, WEIGHT_RSI, WEIGHT_DIP, WEIGHT_MARGIN, WEIGHT_VOLUME

  HIGH_VALUE_SEEDS          Dict of item IDs to pre-populate the watchlist
                            (god swords, skilling supplies, high-value armour)


DATA SOURCES
------------
  OSRS Wiki Real-Time Prices API   https://prices.runescape.wiki/api/v1/osrs
  Jagex Official GE API            https://secure.runescape.com/m=itemdb_oldschool

Both APIs are free and require no authentication.
A descriptive User-Agent header is sent on every request per Wiki API policy.


TABS
----
Dashboard
  Shows all scored items above the minimum score threshold.
  Columns: Rank, Item Name, Score, Price, Margin%, 30d Trend, 90d Trend,
           RSI, Volume Trend, Buy Limit.
  Filters: min score slider, price range, item name search.
  Click any row to load that item's chart.

Charts
  Displays a 3-panel chart for the selected item:
    - Price band (high/low) with 30-day and 90-day moving averages
    - Daily volume bars
    - RSI with overbought (70) and oversold (30) threshold lines
  Time range buttons: 30d / 90d / 180d / All

Watchlist
  Add items manually or from the Dashboard.
  Set buy-below and sell-above price thresholds per item.
  Desktop notifications fire when a threshold is crossed.
  Alert history shows the last 50 fired alerts.


NOTES
-----
- The database (data/ge_prices.db) is gitignored and built locally on first run.
- First startup performs an initial data load (~60 seconds due to API rate limiting).
- Item IDs in config.py HIGH_VALUE_SEEDS should be verified against
  https://oldschool.runescape.wiki as IDs can change with game updates.
- Logs are written to dashboard.log in the project root.
