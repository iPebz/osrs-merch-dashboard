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


def price_momentum(df: pd.DataFrame, short: int = 7, long: int = 30) -> float:
    """
    Momentum: short-term slope minus long-term slope.
    Positive = accelerating upward (good entry).
    Negative = decelerating / rolling over (caution).
    """
    return price_slope(df, short) - price_slope(df, long)
