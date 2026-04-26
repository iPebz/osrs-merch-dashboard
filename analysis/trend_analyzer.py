import numpy as np
import pandas as pd


def to_dataframe(timeseries: list[dict]) -> pd.DataFrame:
    if not timeseries:
        return pd.DataFrame()
    df = pd.DataFrame(timeseries)
    df.rename(columns={
        "avgHighPrice":      "high",
        "avgLowPrice":       "low",
        "highPriceVolume":   "high_vol",
        "lowPriceVolume":    "low_vol",
    }, inplace=True)
    for col in ("high", "low", "high_vol", "low_vol"):
        if col not in df.columns:
            df[col] = None
    df["mid"]       = (df["high"] + df["low"]) / 2
    df["total_vol"] = df["high_vol"].fillna(0) + df["low_vol"].fillna(0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    df.sort_values("timestamp", inplace=True)
    df.dropna(subset=["high", "low"], inplace=True)
    return df.reset_index(drop=True)


def moving_average(df: pd.DataFrame, window: int, column: str = "mid") -> pd.Series:
    return df[column].rolling(window=window, min_periods=1).mean()


def price_slope(df: pd.DataFrame, days: int = 30) -> float:
    recent = df.tail(days)
    if len(recent) < 3:
        return 0.0
    x = np.arange(len(recent))
    y = recent["mid"].values
    slope, _ = np.polyfit(x, y, 1)
    mean_price = y.mean()
    return (slope / mean_price) * 100 if mean_price > 0 else 0.0


def rsi(df: pd.DataFrame, period: int = 14, column: str = "mid") -> float:
    if len(df) < period + 1:
        return 50.0
    delta = df[column].diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    val = rsi_series.iloc[-1]
    return float(val) if not pd.isna(val) else 50.0


def detect_dip(df: pd.DataFrame, lookback: int = 90,
               dip_threshold: float = 0.15) -> bool:
    if len(df) < 7:
        return False
    recent_high = df.tail(lookback)["high"].max()
    current = df["low"].iloc[-1]
    if pd.isna(recent_high) or pd.isna(current) or recent_high == 0:
        return False
    return current < recent_high * (1 - dip_threshold)


def average_margin(df: pd.DataFrame, days: int = 14) -> float:
    recent = df.tail(days).copy()
    denom = recent["low"].replace(0, np.nan)
    recent["margin_pct"] = (recent["high"] - recent["low"]) / denom * 100
    val = recent["margin_pct"].mean()
    return float(val) if not pd.isna(val) else 0.0


def volatility(df: pd.DataFrame, days: int = 30) -> float:
    recent = df.tail(days)
    pct_changes = recent["mid"].pct_change().dropna()
    return float(pct_changes.std() * 100) if not pct_changes.empty else 0.0


def volume_trend(df: pd.DataFrame, short: int = 7, long: int = 30) -> str:
    if len(df) < long:
        return "STABLE"
    short_avg = df.tail(short)["total_vol"].mean()
    long_avg  = df.tail(long)["total_vol"].mean()
    if long_avg == 0:
        return "STABLE"
    ratio = short_avg / long_avg
    if ratio > 1.2:
        return "RISING"
    if ratio < 0.8:
        return "FALLING"
    return "STABLE"


# ── New indicators ─────────────────────────────────────────────────────────────

def price_vs_ma(df: pd.DataFrame, window: int = 90) -> float:
    """Current mid price % above/below its moving average. Negative = below MA (potential buy zone)."""
    ma_series = moving_average(df, window)
    if ma_series.empty:
        return 0.0
    ma_val = ma_series.iloc[-1]
    if pd.isna(ma_val) or ma_val == 0:
        return 0.0
    current = df["mid"].iloc[-1]
    return float((current - ma_val) / ma_val * 100)


def support_level(df: pd.DataFrame, lookback: int = 90, pct: float = 10) -> float:
    """Price floor: Nth percentile of recent lows over lookback days."""
    recent = df.tail(lookback)["low"].dropna()
    return float(np.percentile(recent, pct)) if len(recent) >= 5 else 0.0


def resistance_level(df: pd.DataFrame, lookback: int = 90, pct: float = 90) -> float:
    """Price ceiling: Nth percentile of recent highs over lookback days."""
    recent = df.tail(lookback)["high"].dropna()
    return float(np.percentile(recent, pct)) if len(recent) >= 5 else 0.0


def multi_timeframe_agreement(df: pd.DataFrame) -> int:
    """
    Count of timeframes (7d/30d/90d) all trending the same direction.
    Returns +3 all up, -3 all down, or partial counts.
    """
    s7  = price_slope(df, 7)
    s30 = price_slope(df, 30)
    s90 = price_slope(df, 90)
    slopes = [s7, s30, s90]
    ups   = sum(1 for s in slopes if s > 0.05)
    downs = sum(1 for s in slopes if s < -0.05)
    if ups == 3:
        return 3
    if downs == 3:
        return -3
    return ups - downs


def liquidity_score(avg_daily_vol: float, buy_limit: int) -> float:
    """
    Ratio of daily volume to buy limit.
    >6  = very liquid (fills multiple times/day)
    1-6 = normal
    <1  = illiquid (may take >4h to fill one cycle)
    """
    if buy_limit <= 0:
        return 0.0
    return avg_daily_vol / buy_limit


def estimated_daily_flip_profit(margin_gp: float, buy_limit: int,
                                avg_daily_vol: float) -> float:
    """
    Estimate how much GP per day from instant-flipping this item.
    Accounts for GE 1% tax (capped at 5M per trade).
    """
    if buy_limit <= 0 or margin_gp <= 0:
        return 0.0
    max_cycles_by_vol  = avg_daily_vol / buy_limit if buy_limit > 0 else 0
    cycles_per_day     = min(6.0, max_cycles_by_vol)  # 4h cooldown → max 6/day
    return margin_gp * buy_limit * cycles_per_day


def price_change_pct(df: pd.DataFrame, days: int = 1) -> float:
    """Actual % price change from `days` candles ago to the most recent candle.
    Unlike price_slope (normalized per-period rate), this returns the raw
    percentage move — e.g. +2.5 means the price rose 2.5% over `days` days.
    """
    if len(df) < days + 1:
        return 0.0
    old = df["mid"].iloc[-(days + 1)]
    new = df["mid"].iloc[-1]
    if pd.isna(old) or pd.isna(new) or old == 0:
        return 0.0
    return float((new - old) / old * 100)


def price_momentum(df: pd.DataFrame, short: int = 7, long: int = 30) -> float:
    """
    Momentum: short-term slope minus long-term slope.
    Positive = accelerating upward (good entry).
    Negative = decelerating / rolling over (caution).
    """
    return price_slope(df, short) - price_slope(df, long)


# ── Advanced indicators ────────────────────────────────────────────────────────

def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9,
         column: str = "mid") -> dict:
    """MACD momentum indicator. Returns line, signal, histogram, and crossover flags."""
    empty = {"macd": 0.0, "signal": 0.0, "histogram": 0.0,
             "histogram_prev": 0.0, "bullish_cross": False, "bearish_cross": False}
    if len(df) < slow + signal:
        return empty
    prices = df[column]
    ema_fast   = prices.ewm(span=fast,   adjust=False).mean()
    ema_slow   = prices.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    sig_line   = macd_line.ewm(span=signal, adjust=False).mean()
    hist       = macd_line - sig_line
    hist_val   = float(hist.iloc[-1])   if not pd.isna(hist.iloc[-1])   else 0.0
    hist_prev  = float(hist.iloc[-2])   if len(hist) >= 2 and not pd.isna(hist.iloc[-2]) else 0.0
    macd_val   = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0.0
    sig_val    = float(sig_line.iloc[-1])  if not pd.isna(sig_line.iloc[-1])  else 0.0
    return {
        "macd":           macd_val,
        "signal":         sig_val,
        "histogram":      hist_val,
        "histogram_prev": hist_prev,
        "bullish_cross":  hist_val > 0 and hist_prev <= 0,
        "bearish_cross":  hist_val < 0 and hist_prev >= 0,
    }


def bollinger_bands(df: pd.DataFrame, window: int = 20, num_std: float = 2.0,
                    column: str = "mid") -> dict:
    """Bollinger Bands. percent_b: 0 = at lower band, 1 = at upper band."""
    empty = {"upper": 0.0, "middle": 0.0, "lower": 0.0,
             "percent_b": 0.5, "bandwidth": 0.0, "squeeze": False}
    if len(df) < window:
        return empty
    prices  = df[column]
    middle  = prices.rolling(window=window, min_periods=window).mean()
    std     = prices.rolling(window=window, min_periods=window).std()
    upper   = middle + num_std * std
    lower   = middle - num_std * std
    mid_val = float(middle.iloc[-1]) if not pd.isna(middle.iloc[-1]) else 0.0
    up_val  = float(upper.iloc[-1])  if not pd.isna(upper.iloc[-1])  else 0.0
    lo_val  = float(lower.iloc[-1])  if not pd.isna(lower.iloc[-1])  else 0.0
    cur     = float(prices.iloc[-1])
    band_w  = up_val - lo_val
    pct_b   = (cur - lo_val) / band_w if band_w > 0 else 0.5
    bw      = band_w / mid_val        if mid_val > 0 else 0.0
    return {
        "upper":     up_val,
        "middle":    mid_val,
        "lower":     lo_val,
        "percent_b": round(pct_b, 4),
        "bandwidth": round(bw,    4),
        "squeeze":   bw < 0.05,
    }


def volume_price_divergence(df: pd.DataFrame, lookback: int = 14) -> str:
    """
    Compare price direction vs volume direction over lookback days.
    BULLISH_CONFIRM  — price up, volume up   (healthy uptrend)
    BEARISH_DIVERGE  — price up, volume down (weak rally, suspect)
    BULLISH_DIVERGE  — price down, volume down (weak selloff, potential reversal)
    BEARISH_CONFIRM  — price down, volume up  (distribution / capitulation)
    """
    if len(df) < lookback + 1:
        return "NEUTRAL"
    recent    = df.tail(lookback)
    price_up  = recent["mid"].iloc[-1]       > recent["mid"].iloc[0]
    vol_up    = recent["total_vol"].iloc[-1]  > recent["total_vol"].iloc[0]
    if price_up and vol_up:
        return "BULLISH_CONFIRM"
    if price_up and not vol_up:
        return "BEARISH_DIVERGE"
    if not price_up and not vol_up:
        return "BULLISH_DIVERGE"
    return "BEARISH_CONFIRM"


def falling_knife_risk(df: pd.DataFrame, slope_threshold: float = -0.5,
                       rsi_ceiling: float = 35.0) -> bool:
    """
    True when slope_90d < threshold AND RSI < ceiling.
    An oversold RSI in a steep downtrend is NOT a buy signal — it is a falling knife.
    Suppresses RSI bonus in MERCH scoring and blocks MERCH classification.
    """
    return price_slope(df, 90) < slope_threshold and rsi(df) < rsi_ceiling


def average_margin_pct_taxed(df: pd.DataFrame, days: int = 14,
                              tax_rate: float = 0.01,
                              tax_cap: float = 5_000_000) -> float:
    """
    Average daily net margin % after GE tax over the last N candles.
    More robust than spot margin — resistant to single-candle manipulation.
    """
    recent = df.tail(days).copy()
    if recent.empty:
        return 0.0
    low  = recent["low"].replace(0, np.nan)
    tax  = (recent["high"] * tax_rate).clip(upper=tax_cap)
    pct  = (recent["high"] - recent["low"] - tax) / low * 100
    val  = pct.mean()
    return float(val) if not pd.isna(val) else 0.0
