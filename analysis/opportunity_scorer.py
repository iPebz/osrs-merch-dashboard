"""
Opportunity scorer — assigns a 0–100 score to each item and classifies
the trade strategy (FLIP / MERCH / TREND / NEWS).

Economic model
--------------
FLIP   High margin × volume → profit from buy/sell spread immediately.
       Score emphasises net margin after 1% GE tax, buy-limit fill rate.
MERCH  Price has dipped below long-term average but trend is intact.
       Buy the dip, sell when price recovers to MA90 / resistance.
TREND  Multi-timeframe uptrend with RSI not yet overbought.
       Ride the momentum; exit when RSI > 70 or slope turns negative.
NEWS   Game-update / GE-mover signal likely to drive short-term demand.
       Priority override over technical signals.
"""

from analysis.trend_analyzer import (
    to_dataframe, price_slope, rsi, detect_dip,
    average_margin, volatility, volume_trend,
    price_vs_ma, support_level, resistance_level,
    multi_timeframe_agreement, liquidity_score,
    estimated_daily_flip_profit, price_momentum,
    moving_average,
)

GE_TAX_RATE = 0.01        # 1 % on sell price
GE_TAX_CAP  = 5_000_000   # capped at 5 M per transaction

NEWS_BOOST_GAME_UPDATE = 20
NEWS_BOOST_GE_RISE     = 12
NEWS_BOOST_MENTIONED   = 8

MIN_VOLUME = 50  # items trading fewer than this per day are unscoreable


def score_item(timeseries: list[dict], buy_limit: int,
               news_signals: list[dict] | None = None) -> dict:

    if not timeseries or len(timeseries) < 2:
        return {"score": 0, "reason": "Insufficient data"}

    df = to_dataframe(timeseries)
    if df.empty or len(df) < 2:
        return {"score": 0, "reason": "No valid price data"}

    current_low  = float(df["low"].iloc[-1])
    current_high = float(df["high"].iloc[-1])

    if current_low <= 0 or current_high <= 0:
        return {"score": 0, "reason": "Invalid price data"}

    # ── Core metrics ───────────────────────────────────────────────────
    slope_7d  = price_slope(df, 7)
    slope_30d = price_slope(df, 30)
    slope_90d = price_slope(df, 90)
    item_rsi  = rsi(df)
    is_dip    = detect_dip(df)
    margin_pct  = average_margin(df)   # raw %, pre-tax
    vol_t       = volume_trend(df)
    item_vol    = volatility(df)
    avg_daily_vol = float(df.tail(30)["total_vol"].mean())

    # ── Extended metrics ───────────────────────────────────────────────
    ma_deviation  = price_vs_ma(df, 90)   # % below MA90 → negative = cheap
    sup           = support_level(df)
    res           = resistance_level(df)
    mtf_score     = multi_timeframe_agreement(df)
    liq           = liquidity_score(avg_daily_vol, buy_limit)
    momentum      = price_momentum(df)

    upside_to_res = ((res - current_low) / current_low * 100
                     if current_low > 0 and res > current_low else 0.0)

    # ── GE-tax-adjusted flip metrics ──────────────────────────────────
    raw_margin_gp  = max(0.0, current_high - current_low)
    tax            = min(current_high * GE_TAX_RATE, GE_TAX_CAP)
    net_margin_gp  = max(0.0, raw_margin_gp - tax)
    net_margin_pct = (net_margin_gp / current_low * 100) if current_low > 0 else 0.0
    daily_flip_profit = estimated_daily_flip_profit(net_margin_gp, buy_limit, avg_daily_vol)

    # Merch profit: difference between current price and MA90 × buy_limit
    ma90_val     = float(moving_average(df, 90).iloc[-1])
    merch_target = max(res, ma90_val)
    merch_profit = max(0.0, (merch_target - current_low) * buy_limit) if buy_limit > 0 else 0.0

    # ── Guard: near-zero volume is untradeable ────────────────────────
    if avg_daily_vol < MIN_VOLUME:
        return {"score": 0, "reason": "Volume too low"}

    # ── Guard: extreme MA deviation is almost always stale/corrupted data ─
    # A legitimate dip rarely exceeds 70%; beyond that, the item has likely
    # collapsed permanently and the "resistance" level is meaningless.
    if ma_deviation < -70:
        return {"score": 0, "reason": "Extreme price collapse — likely stale data"}

    # ── Score (base 50) ────────────────────────────────────────────────
    score = 50.0

    # Multi-timeframe agreement (strongest signal)
    if mtf_score == 3:    score += 18   # all 3 timeframes bullish
    elif mtf_score == 2:  score += 10
    elif mtf_score == 1:  score += 4
    elif mtf_score == -2: score -= 12
    elif mtf_score == -3: score -= 20

    # Slope refinement (90d is most reliable for merching)
    if slope_90d > 0.2:   score += 6
    elif slope_90d < -0.3: score -= 8

    # RSI — oversold gives the best entries
    if item_rsi < 25:     score += 22
    elif item_rsi < 35:   score += 14
    elif item_rsi < 45:   score += 7
    elif item_rsi > 75:   score -= 14
    elif item_rsi > 65:   score -= 6

    # Price dip relative to MA90 (deeper dip = bigger opportunity)
    if is_dip:
        if ma_deviation < -25:  score += 20   # very deep dip
        elif ma_deviation < -15: score += 13
        elif ma_deviation < -8:  score += 7
        else:                    score += 4

    # GE-tax-adjusted margin quality
    if net_margin_pct > 8:    score += 15
    elif net_margin_pct > 5:  score += 10
    elif net_margin_pct > 3:  score += 6
    elif net_margin_pct > 1:  score += 2
    elif net_margin_pct < 0:  score -= 8

    # Liquidity — can we actually fill a buy order?
    if liq > 10:   score += 8
    elif liq > 3:  score += 4
    elif liq < 0.5: score -= 10
    elif liq < 0.2: score -= 20

    # Volume trend
    if vol_t == "RISING":    score += 5
    elif vol_t == "FALLING": score -= 6

    # Upside to resistance (merch potential)
    if upside_to_res > 20:  score += 8
    elif upside_to_res > 10: score += 4

    # Momentum (short-term acceleration)
    if momentum > 0.3:    score += 5
    elif momentum < -0.3:  score -= 5

    # ── News / market signal boost ─────────────────────────────────────
    news_boost, news_label = _calc_news_boost(news_signals)
    score += news_boost

    # ── Practical profit floor ─────────────────────────────────────────
    # Penalise items where the absolute GP reward is too small to bother,
    # regardless of how good the % metrics look.
    if daily_flip_profit < 25_000:    score -= 25
    elif daily_flip_profit < 100_000: score -= 12
    elif daily_flip_profit < 250_000: score -= 4

    score = max(0.0, min(100.0, score))

    # ── Strategy classification ────────────────────────────────────────
    strategy = _classify_strategy(
        slope_90d, item_rsi, is_dip, net_margin_pct,
        avg_daily_vol, buy_limit, liq, news_signals,
        current_low=current_low, merch_profit=merch_profit,
    )

    # ── Reason string ──────────────────────────────────────────────────
    reason = _build_reason(strategy, slope_90d, item_rsi, is_dip,
                            net_margin_pct, ma_deviation, news_label, mtf_score)

    return {
        "score":            round(score, 1),
        "current_low":      current_low,
        "current_high":     current_high,
        "margin_pct":       round(margin_pct, 2),       # raw pre-tax
        "net_margin_pct":   round(net_margin_pct, 2),   # post GE-tax
        "net_margin_gp":    round(net_margin_gp),
        "slope_7d":         round(slope_7d, 3),
        "slope_30d":        round(slope_30d, 3),
        "slope_90d":        round(slope_90d, 3),
        "rsi":              round(item_rsi, 1),
        "is_dip":           is_dip,
        "ma_deviation":     round(ma_deviation, 1),
        "support":          round(sup),
        "resistance":       round(res),
        "upside_pct":       round(upside_to_res, 1),
        "mtf_score":        mtf_score,
        "liquidity":        round(liq, 2),
        "vol_trend":        vol_t,
        "volatility":       round(item_vol, 2),
        "avg_daily_vol":    round(avg_daily_vol),
        "buy_limit":        buy_limit,
        "daily_flip_profit": round(daily_flip_profit),
        "merch_profit":     round(merch_profit),
        "strategy":         strategy,
        "news_signals":     news_signals or [],
        "reason":           reason,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _calc_news_boost(signals):
    boost = 0
    label = ""
    if not signals:
        return boost, label
    for sig in signals:
        stype = sig.get("signal_type", "")
        if stype == "game_update" and NEWS_BOOST_GAME_UPDATE > boost:
            boost = NEWS_BOOST_GAME_UPDATE
            label = f"update: {sig['article_title'][:35]}"
        elif stype == "ge_rise" and NEWS_BOOST_GE_RISE > boost:
            boost = NEWS_BOOST_GE_RISE
            label = f"GE rising ({sig['article_title']})"
        elif stype == "mentioned" and NEWS_BOOST_MENTIONED > boost:
            boost = NEWS_BOOST_MENTIONED
            label = f"in news: {sig['article_title'][:35]}"
    return boost, label


def _classify_strategy(slope_90d, rsi_val, is_dip, net_margin_pct,
                        avg_daily_vol, buy_limit, liq, news_signals,
                        current_low=0, merch_profit=0):
    if news_signals:
        return "NEWS"
    # FLIP: meaningful margin with enough volume to actually fill orders
    if net_margin_pct >= 3 and liq >= 1 and buy_limit > 0:
        return "FLIP"
    # MERCH: genuine dip with a meaningful recovery profit potential.
    # Require both a minimum per-item price and 2M total potential to exclude
    # micro-price artifacts with inflated historical resistance levels.
    if is_dip and slope_90d >= -0.1 and current_low >= 1_000 and merch_profit >= 2_000_000:
        return "MERCH"
    # TREND: consistent multi-timeframe upward momentum
    if slope_90d > 0.05 and rsi_val < 65:
        return "TREND"
    return "FLIP"


def _build_reason(strategy, slope_90d, rsi_val, is_dip,
                   net_margin_pct, ma_deviation, news_label, mtf_score):
    parts = []
    if strategy == "NEWS" and news_label:
        parts.append(news_label)
    if strategy == "FLIP":
        parts.append(f"{net_margin_pct:.1f}% net margin")
    if is_dip:
        parts.append(f"{abs(ma_deviation):.0f}% below MA90")
    if mtf_score >= 2:
        parts.append("multi-TF uptrend")
    elif mtf_score <= -2:
        parts.append("multi-TF downtrend")
    if rsi_val < 35:
        parts.append(f"oversold RSI {rsi_val:.0f}")
    elif rsi_val > 70:
        parts.append(f"overbought RSI {rsi_val:.0f}")
    if not parts:
        parts.append("Neutral")
    return "; ".join(parts)
