from analysis.trend_analyzer import (
    to_dataframe, price_slope, rsi, detect_dip,
    average_margin, volatility, volume_trend,
)

BUDGET_MIN_PRICE = 10_000
BUDGET_MAX_PRICE = 50_000_000

# Max score boost from news signals (capped so technicals still matter)
NEWS_BOOST_GAME_UPDATE = 20
NEWS_BOOST_GE_RISE     = 12
NEWS_BOOST_MENTIONED   = 8


def score_item(timeseries: list[dict], buy_limit: int,
               news_signals: list[dict] | None = None) -> dict:
    if not timeseries or len(timeseries) < 14:
        return {"score": 0, "reason": "Insufficient data"}

    df = to_dataframe(timeseries)
    if df.empty:
        return {"score": 0, "reason": "No valid price data"}

    current_low  = float(df["low"].iloc[-1])
    current_high = float(df["high"].iloc[-1])

    if current_low < BUDGET_MIN_PRICE or current_low > BUDGET_MAX_PRICE:
        return {"score": 0, "reason": "Outside budget range"}

    slope_30d     = price_slope(df, days=30)
    slope_90d     = price_slope(df, days=90)
    item_rsi      = rsi(df)
    is_dip        = detect_dip(df)
    margin_pct    = average_margin(df)
    vol_trend     = volume_trend(df)
    item_vol      = volatility(df)
    avg_daily_vol = float(df.tail(30)["total_vol"].mean())

    score = 50.0

    if slope_90d > 0.1:    score += 15
    elif slope_90d > 0:    score += 7
    elif slope_90d < -0.2: score -= 20

    if slope_30d > 0.2:    score += 10
    elif slope_30d < -0.3: score -= 10

    if item_rsi < 30:      score += 20
    elif item_rsi < 45:    score += 10
    elif item_rsi > 70:    score -= 10

    if is_dip:             score += 15

    if margin_pct > 5:     score += 10
    elif margin_pct > 2:   score += 5
    elif margin_pct < 1:   score -= 5

    if avg_daily_vol > 1000:  score += 5
    elif avg_daily_vol < 100: score -= 15

    if vol_trend == "RISING":   score += 5
    elif vol_trend == "FALLING": score -= 5

    # News / market signal boost (take the strongest single signal)
    news_boost = 0
    news_label = ""
    if news_signals:
        for sig in news_signals:
            stype = sig.get("signal_type", "")
            if stype == "game_update" and NEWS_BOOST_GAME_UPDATE > news_boost:
                news_boost = NEWS_BOOST_GAME_UPDATE
                news_label = f"update: {sig['article_title'][:35]}"
            elif stype == "ge_rise" and NEWS_BOOST_GE_RISE > news_boost:
                news_boost = NEWS_BOOST_GE_RISE
                news_label = f"GE rising ({sig['article_title']})"
            elif stype == "mentioned" and NEWS_BOOST_MENTIONED > news_boost:
                news_boost = NEWS_BOOST_MENTIONED
                news_label = f"in news: {sig['article_title'][:35]}"

    score += news_boost
    score = max(0.0, min(100.0, score))

    tech_reason = _build_tech_reason(slope_90d, item_rsi, is_dip, margin_pct)
    reason_parts = [p for p in [tech_reason, news_label] if p and p != "Neutral"]
    reason = "; ".join(reason_parts) if reason_parts else "Neutral"

    return {
        "score":         round(score, 1),
        "current_low":   current_low,
        "current_high":  current_high,
        "margin_pct":    round(margin_pct, 2),
        "slope_30d":     round(slope_30d, 3),
        "slope_90d":     round(slope_90d, 3),
        "rsi":           round(item_rsi, 1),
        "is_dip":        is_dip,
        "vol_trend":     vol_trend,
        "volatility":    round(item_vol, 2),
        "avg_daily_vol": round(avg_daily_vol),
        "buy_limit":     buy_limit,
        "news_signals":  news_signals or [],
        "reason":        reason,
    }


def _build_tech_reason(slope_90d: float, item_rsi: float,
                       is_dip: bool, margin_pct: float) -> str:
    reasons = []
    if slope_90d > 0.1:  reasons.append("90d uptrend")
    if item_rsi < 35:    reasons.append(f"oversold (RSI {item_rsi:.0f})")
    if is_dip:           reasons.append("price dip vs 90d high")
    if margin_pct > 4:   reasons.append(f"{margin_pct:.1f}% margin")
    return ", ".join(reasons) if reasons else "Neutral"
