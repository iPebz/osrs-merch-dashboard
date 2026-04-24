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
