"""
Opportunity scorer — assigns a 0–100 score and classifies trade strategy.

Economic model
--------------
FLIP   High time-averaged margin × volume → profit from buy/sell spread.
       Score emphasises reliable net margin after 1% GE tax and liquidity.
MERCH  Price dipped below long-term average; trend intact; not a falling knife.
       Buy the dip, sell when price recovers to MA90 / resistance.
TREND  Multi-timeframe uptrend + MACD momentum confirmation; RSI not overbought.
       Ride the momentum; exit when RSI > 70 or slope turns negative.
NEWS   Game-update / GE-mover catalyst likely to drive short-term demand.
       Scored by signal quality + technical entry backdrop.

Strategy-first pipeline
-----------------------
1. Compute all metrics (MACD, Bollinger Bands, volume-price divergence, etc.).
2. Classify strategy FIRST (NEWS > FLIP > MERCH > TREND > FLIP fallback).
3. Score with strategy-specific factor pool.
4. Apply universal news boost for non-NEWS items with weak signals.
5. Clamp to [0, 100].
"""

from analysis.trend_analyzer import (
    to_dataframe, price_slope, rsi, detect_dip,
    average_margin, volatility, volume_trend,
    price_vs_ma, support_level, resistance_level,
    multi_timeframe_agreement, liquidity_score,
    estimated_daily_flip_profit, price_momentum,
    moving_average, price_change_pct,
    macd, bollinger_bands, volume_price_divergence,
    falling_knife_risk, average_margin_pct_taxed,
)

GE_TAX_RATE = 0.01
GE_TAX_CAP  = 5_000_000

NEWS_BOOST_GAME_UPDATE = 20
NEWS_BOOST_GE_RISE     = 12
NEWS_BOOST_MENTIONED   = 8

MIN_VOLUME = 50

_LEAGUES_TERMS = frozenset({"league", "leagues"})


def score_item(timeseries: list[dict], buy_limit: int,
               news_signals: list[dict] | None = None) -> dict:

    if news_signals:
        news_signals = [
            s for s in news_signals
            if not any(t in s.get("article_title", "").lower() for t in _LEAGUES_TERMS)
        ]

    if not timeseries or len(timeseries) < 2:
        return {"score": 0, "reason": "Insufficient data"}

    df = to_dataframe(timeseries)
    if df.empty or len(df) < 2:
        return {"score": 0, "reason": "No valid price data"}

    current_low  = float(df["low"].iloc[-1])
    current_high = float(df["high"].iloc[-1])

    if current_low <= 0 or current_high <= 0:
        return {"score": 0, "reason": "Invalid price data"}

    # ── Core metrics ─────────────────────────────────────────────────────
    slope_7d      = price_slope(df, 7)
    slope_30d     = price_slope(df, 30)
    slope_90d     = price_slope(df, 90)
    item_rsi      = rsi(df)
    is_dip        = detect_dip(df)
    margin_pct    = average_margin(df)
    vol_t         = volume_trend(df)
    item_vol      = volatility(df)
    avg_daily_vol = float(df.tail(30)["total_vol"].mean())

    # ── Extended metrics ──────────────────────────────────────────────────
    ma_deviation  = price_vs_ma(df, 90)
    sup           = support_level(df)
    res           = resistance_level(df)
    mtf_score     = multi_timeframe_agreement(df)
    liq           = liquidity_score(avg_daily_vol, buy_limit)
    momentum      = price_momentum(df)

    upside_to_res = ((res - current_low) / current_low * 100
                     if current_low > 0 and res > current_low else 0.0)

    # ── GE-tax-adjusted flip metrics ─────────────────────────────────────
    raw_margin_gp     = max(0.0, current_high - current_low)
    tax               = min(current_high * GE_TAX_RATE, GE_TAX_CAP)
    net_margin_gp     = max(0.0, raw_margin_gp - tax)
    net_margin_pct    = (net_margin_gp / current_low * 100) if current_low > 0 else 0.0
    daily_flip_profit = estimated_daily_flip_profit(net_margin_gp, buy_limit, avg_daily_vol)

    # ── New advanced metrics ──────────────────────────────────────────────
    avg_margin_taxed = average_margin_pct_taxed(df, 14)
    macd_data        = macd(df)
    bb               = bollinger_bands(df)
    vpd              = volume_price_divergence(df)
    knife_risk       = falling_knife_risk(df)

    # ── Merch potential ───────────────────────────────────────────────────
    ma90_val     = float(moving_average(df, 90).iloc[-1])
    merch_target = max(res, ma90_val)
    merch_profit = max(0.0, (merch_target - current_low) * buy_limit) if buy_limit > 0 else 0.0

    # ── Guards ────────────────────────────────────────────────────────────
    if avg_daily_vol < MIN_VOLUME:
        return {"score": 0, "reason": "Volume too low"}

    if ma_deviation < -70:
        return {"score": 0, "reason": "Extreme price collapse — likely stale data"}

    # ── Strategy classification (FIRST) ──────────────────────────────────
    strategy = _classify_strategy(
        df, slope_90d, item_rsi, is_dip, avg_margin_taxed,
        liq, mtf_score, news_signals,
        current_low=current_low, merch_profit=merch_profit, knife_risk=knife_risk,
    )

    # ── Strategy-specific scoring ─────────────────────────────────────────
    reason_parts: list[str] = []
    score = 50.0

    if strategy == "FLIP":
        score = _score_flip(
            score, reason_parts,
            avg_margin_taxed, liq, vol_t, vpd, bb, net_margin_pct, daily_flip_profit,
        )
    elif strategy == "MERCH":
        score = _score_merch(
            score, reason_parts,
            ma_deviation, item_rsi, slope_90d, upside_to_res, bb, vpd, merch_profit, knife_risk,
        )
    elif strategy == "TREND":
        score = _score_trend(
            score, reason_parts,
            mtf_score, macd_data, item_rsi, slope_90d, momentum, vpd, bb,
        )
    elif strategy == "NEWS":
        score = _score_news(
            score, reason_parts,
            news_signals, ma_deviation, item_rsi, vol_t, mtf_score, liq,
        )

    # ── Universal news boost for non-NEWS items with weak signals ─────────
    if strategy != "NEWS":
        news_boost, news_label = _calc_news_boost(news_signals)
        if news_boost > 0:
            score += news_boost
            reason_parts.insert(0, f"★ {news_label} (+{news_boost})")

    score = max(0.0, min(100.0, score))
    reason = " · ".join(reason_parts) if reason_parts else "Neutral signals"

    return {
        "score":             round(score, 1),
        "current_low":       current_low,
        "current_high":      current_high,
        "margin_pct":        round(margin_pct, 2),
        "net_margin_pct":    round(net_margin_pct, 2),
        "net_margin_gp":     round(net_margin_gp),
        "avg_margin_taxed":  round(avg_margin_taxed, 2),
        "change_1d":         round(price_change_pct(df, 1), 2),
        "change_7d":         round(price_change_pct(df, 7), 2),
        "change_30d":        round(price_change_pct(df, 30), 2),
        "slope_7d":          round(slope_7d, 3),
        "slope_30d":         round(slope_30d, 3),
        "slope_90d":         round(slope_90d, 3),
        "rsi":               round(item_rsi, 1),
        "is_dip":            is_dip,
        "ma_deviation":      round(ma_deviation, 1),
        "support":           round(sup),
        "resistance":        round(res),
        "upside_pct":        round(upside_to_res, 1),
        "mtf_score":         mtf_score,
        "liquidity":         round(liq, 2),
        "vol_trend":         vol_t,
        "volatility":        round(item_vol, 2),
        "avg_daily_vol":     round(avg_daily_vol),
        "buy_limit":         buy_limit,
        "daily_flip_profit": round(daily_flip_profit),
        "merch_profit":      round(merch_profit),
        "strategy":          strategy,
        "news_signals":      news_signals or [],
        "reason":            reason,
    }


# ── Strategy-specific scoring pools ──────────────────────────────────────────

def _score_flip(score, parts, avg_margin_taxed, liq, vol_t, vpd, bb,
                net_margin_pct, daily_flip_profit):
    # Primary: time-averaged net margin (resistant to single-candle manipulation)
    if avg_margin_taxed > 8:
        score += 18; parts.append(f"avg margin {avg_margin_taxed:.1f}% (+18)")
    elif avg_margin_taxed > 5:
        score += 12; parts.append(f"avg margin {avg_margin_taxed:.1f}% (+12)")
    elif avg_margin_taxed > 3:
        score +=  7; parts.append(f"avg margin {avg_margin_taxed:.1f}% (+7)")
    elif avg_margin_taxed > 1.5:
        score +=  3; parts.append(f"avg margin {avg_margin_taxed:.1f}% (+3)")
    elif avg_margin_taxed < 0:
        score -= 10; parts.append("negative avg margin (−10)")

    # Primary: liquidity — can we fill orders reliably?
    if liq > 10:
        score += 10; parts.append(f"high liquidity {liq:.1f}× buy-limit/day (+10)")
    elif liq > 3:
        score +=  6; parts.append(f"good liquidity {liq:.1f}× buy-limit/day (+6)")
    elif liq > 1.5:
        score +=  3; parts.append(f"liquidity {liq:.1f}× buy-limit/day (+3)")
    elif liq < 0.2:
        score -= 20; parts.append(f"very low liquidity {liq:.2f}× (−20)")
    elif liq < 0.5:
        score -= 12; parts.append(f"low liquidity {liq:.2f}× (−12)")

    # Volume trend
    if vol_t == "RISING":
        score += 3; parts.append("volume rising (+3)")
    elif vol_t == "FALLING":
        score -= 4; parts.append("volume falling (−4)")

    # Volume-price divergence
    if vpd == "BULLISH_CONFIRM":
        score += 5; parts.append("volume confirms price (+5)")
    elif vpd == "BEARISH_CONFIRM":
        score -= 5; parts.append("distribution — volume rising as price falls (−5)")
    elif vpd == "BEARISH_DIVERGE":
        score -= 3; parts.append("weak rally — volume not confirming (−3)")

    # Bollinger position — buy near lower band for best flip entry
    pct_b = bb.get("percent_b", 0.5)
    if pct_b < 0.15:
        score += 8; parts.append("near lower Bollinger band (+8)")
    elif pct_b < 0.30:
        score += 4; parts.append("below Bollinger midband (+4)")
    elif pct_b > 0.85:
        score -= 6; parts.append("near upper Bollinger band — extended (−6)")

    # Spot margin tiebreaker (current spread also healthy)
    if net_margin_pct > 5:
        score += 5; parts.append(f"current spread {net_margin_pct:.1f}% (+5)")

    # Absolute GP floor — small-margin items waste GE slots
    if daily_flip_profit < 25_000:
        score -= 25; parts.append(f"daily profit ~{_fmt_gp(int(daily_flip_profit))} too low (−25)")
    elif daily_flip_profit < 100_000:
        score -= 12; parts.append(f"daily profit ~{_fmt_gp(int(daily_flip_profit))} below target (−12)")
    elif daily_flip_profit < 250_000:
        score -= 4;  parts.append(f"daily profit ~{_fmt_gp(int(daily_flip_profit))} moderate (−4)")

    return score


def _score_merch(score, parts, ma_deviation, item_rsi, slope_90d, upside_to_res,
                 bb, vpd, merch_profit, knife_risk):
    # Primary: dip depth below MA90
    if ma_deviation < -25:
        score += 20; parts.append(f"{abs(ma_deviation):.0f}% below MA90 — very deep dip (+20)")
    elif ma_deviation < -15:
        score += 13; parts.append(f"{abs(ma_deviation):.0f}% below MA90 — dip (+13)")
    elif ma_deviation < -8:
        score +=  7; parts.append(f"{abs(ma_deviation):.0f}% below MA90 — mild dip (+7)")
    elif ma_deviation < -3:
        score +=  4; parts.append(f"{abs(ma_deviation):.0f}% below MA90 (+4)")
    else:
        score -=  5; parts.append("not clearly below MA90 (−5)")

    # Primary: RSI with falling knife guard
    if knife_risk:
        score -= 8; parts.append("falling knife — oversold in strong downtrend (−8)")
    else:
        if item_rsi < 25:
            score += 18; parts.append(f"RSI {item_rsi:.0f} deeply oversold (+18)")
        elif item_rsi < 35:
            score += 12; parts.append(f"RSI {item_rsi:.0f} oversold (+12)")
        elif item_rsi < 45:
            score +=  6; parts.append(f"RSI {item_rsi:.0f} approaching oversold (+6)")
        elif item_rsi > 70:
            score -= 10; parts.append(f"RSI {item_rsi:.0f} overbought (−10)")

    # 90d slope — long-term trend intact?
    if slope_90d > 0.2:
        score +=  8; parts.append("strong 90d uptrend (+8)")
    elif slope_90d > 0:
        score +=  4; parts.append("90d uptrend intact (+4)")
    elif slope_90d < -0.3:
        score -= 10; parts.append("90d downtrend (−10)")
    elif slope_90d < -0.1:
        score -=  5; parts.append("90d slope weakening (−5)")

    # Recovery potential
    if upside_to_res > 25:
        score += 10; parts.append(f"{upside_to_res:.0f}% upside to resistance (+10)")
    elif upside_to_res > 15:
        score +=  6; parts.append(f"{upside_to_res:.0f}% upside to resistance (+6)")
    elif upside_to_res > 5:
        score +=  3; parts.append(f"{upside_to_res:.0f}% upside to resistance (+3)")

    # Bollinger position — extreme lower band = high-conviction dip entry
    pct_b = bb.get("percent_b", 0.5)
    if pct_b < 0.10:
        score += 8; parts.append("extreme lower Bollinger band (+8)")
    elif pct_b < 0.20:
        score += 4; parts.append("near lower Bollinger band (+4)")

    # Volume-price divergence — weak selloff is a bullish sign for MERCH
    if vpd == "BULLISH_DIVERGE":
        score += 8; parts.append("price dip on falling volume — weak selloff (+8)")
    elif vpd == "BULLISH_CONFIRM":
        score += 3; parts.append("price/volume both rising (+3)")
    elif vpd == "BEARISH_CONFIRM":
        score -= 6; parts.append("heavy distribution — price down on rising volume (−6)")

    # Merch profit floor
    if merch_profit < 2_000_000:
        score -= 15; parts.append(f"recovery profit ~{_fmt_gp(int(merch_profit))} too low (−15)")
    elif merch_profit < 5_000_000:
        score -=  4; parts.append(f"modest recovery target ~{_fmt_gp(int(merch_profit))} (−4)")

    return score


def _score_trend(score, parts, mtf_score, macd_data, item_rsi, slope_90d,
                 momentum, vpd, bb):
    # Primary: multi-timeframe agreement
    if mtf_score == 3:
        score += 25; parts.append("all 3 timeframes bullish (+25)")
    elif mtf_score == 2:
        score += 15; parts.append("2/3 timeframes bullish (+15)")
    elif mtf_score == 1:
        score +=  7; parts.append("1/3 timeframes bullish (+7)")
    elif mtf_score == -1:
        score -=  8; parts.append("1 timeframe bearish (−8)")
    elif mtf_score == -2:
        score -= 15; parts.append("2 timeframes bearish (−15)")
    elif mtf_score == -3:
        score -= 25; parts.append("all 3 timeframes bearish (−25)")

    # Primary: MACD momentum confirmation
    if macd_data.get("bullish_cross"):
        score += 12; parts.append("MACD bullish crossover (+12)")
    elif macd_data.get("histogram", 0) > 0:
        score +=  6; parts.append("MACD positive (+6)")
    elif macd_data.get("bearish_cross"):
        score -= 12; parts.append("MACD bearish crossover (−12)")
    elif macd_data.get("histogram", 0) < 0:
        score -=  6; parts.append("MACD negative (−6)")

    # RSI — ride the trend, not the top
    if item_rsi < 50:
        score += 5; parts.append(f"RSI {item_rsi:.0f} neutral-bullish (+5)")
    elif item_rsi < 65:
        score += 3; parts.append(f"RSI {item_rsi:.0f} rising (+3)")
    elif item_rsi > 75:
        score -= 12; parts.append(f"RSI {item_rsi:.0f} overbought (−12)")
    elif item_rsi > 65:
        score -=  6; parts.append(f"RSI {item_rsi:.0f} elevated (−6)")

    # Slope magnitude
    if slope_90d > 0.4:
        score += 8; parts.append("strong 90d slope (+8)")
    elif slope_90d > 0.2:
        score += 5; parts.append("solid 90d slope (+5)")
    elif slope_90d > 0:
        score += 2; parts.append("positive 90d slope (+2)")

    # Momentum (short-term acceleration)
    if momentum > 0.3:
        score += 5; parts.append("accelerating momentum (+5)")
    elif momentum < -0.3:
        score -= 5; parts.append("decelerating momentum (−5)")

    # Volume-price divergence — healthy trend needs volume confirmation
    if vpd == "BULLISH_CONFIRM":
        score += 6; parts.append("volume confirms uptrend (+6)")
    elif vpd == "BEARISH_CONFIRM":
        score -= 6; parts.append("distribution — volume rising against price (−6)")

    # Bollinger squeeze — low volatility before a breakout
    if bb.get("squeeze"):
        score += 8; parts.append("Bollinger squeeze — breakout potential (+8)")
    elif bb.get("percent_b", 0.5) > 0.85:
        score -= 5; parts.append("near upper Bollinger band — extended (−5)")

    return score


def _score_news(score, parts, news_signals, ma_deviation, item_rsi, vol_t,
                mtf_score, liq):
    # Primary: signal type and quality
    game_update_title = None
    ge_rise_title     = None
    mentioned_count   = 0
    for sig in (news_signals or []):
        st = sig.get("signal_type", "")
        if st == "game_update" and game_update_title is None:
            game_update_title = sig.get("article_title", "")[:35]
        elif st == "ge_rise" and ge_rise_title is None:
            ge_rise_title = sig.get("article_title", "")[:20]
        elif st == "mentioned":
            mentioned_count += 1

    if game_update_title:
        score += 30; parts.append(f"★ game update: {game_update_title} (+30)")
    elif ge_rise_title:
        score += 20; parts.append(f"★ GE mover: {ge_rise_title} (+20)")
    elif mentioned_count >= 3:
        score += 15; parts.append(f"★ mentioned {mentioned_count}× in news (+15)")
    elif mentioned_count == 2:
        score +=  8; parts.append("★ mentioned 2× in news (+8)")
    elif mentioned_count == 1:
        score +=  4; parts.append("★ mentioned in news (+4)")

    # Technical entry: news catalyst at a dip = better risk/reward
    if ma_deviation < -15:
        score += 10; parts.append("catalyst at MA90 dip (+10)")
    elif ma_deviation < -5:
        score +=  6; parts.append("below MA90 (+6)")
    elif ma_deviation > 15:
        score -=  5; parts.append("extended above MA90 (−5)")

    # RSI — clean entry?
    if item_rsi < 45:
        score += 8; parts.append(f"RSI {item_rsi:.0f} — clean entry (+8)")
    elif item_rsi < 60:
        score += 4; parts.append(f"RSI {item_rsi:.0f} neutral (+4)")
    elif item_rsi > 75:
        score -= 8; parts.append(f"RSI {item_rsi:.0f} overbought (−8)")

    # Volume trend — is the news being absorbed?
    if vol_t == "RISING":
        score += 6; parts.append("rising volume (+6)")
    elif vol_t == "FALLING":
        score -= 3; parts.append("falling volume (−3)")

    # MTF backdrop — catalyst into a rising market is ideal
    if mtf_score >= 2:
        score += 6; parts.append("strong technical backdrop (+6)")
    elif mtf_score >= 1:
        score += 3; parts.append("positive technical backdrop (+3)")
    elif mtf_score <= -2:
        score -= 8; parts.append("weak technical backdrop (−8)")

    # Liquidity — can we exit when the news premium fades?
    if liq > 3:
        score += 5; parts.append(f"good liquidity {liq:.1f}× (+5)")
    elif liq < 0.3:
        score -= 10; parts.append(f"poor liquidity {liq:.2f}× (−10)")

    return score


# ── Classification ────────────────────────────────────────────────────────────

def _classify_strategy(df, slope_90d, rsi_val, is_dip, avg_margin_taxed,
                        liq, mtf_score, news_signals,
                        current_low=0, merch_profit=0, knife_risk=False):
    # NEWS: strong catalyst overrides all technical classifications.
    # Single "mentioned" is too weak; require game_update, ge_rise, or 3+ mentions.
    if news_signals:
        has_update   = any(s.get("signal_type") == "game_update" for s in news_signals)
        has_ge_rise  = any(s.get("signal_type") == "ge_rise"     for s in news_signals)
        n_mentioned  = sum(1 for s in news_signals if s.get("signal_type") == "mentioned")
        if has_update or has_ge_rise or n_mentioned >= 3:
            return "NEWS"

    # FLIP: time-averaged margin is reliable (2%+ after tax) with enough liquidity.
    # Using avg_margin_taxed prevents single-candle manipulation from triggering FLIP.
    if avg_margin_taxed >= 2.0 and liq >= 1.5 and liq > 0 and slope_90d > -1.0:
        return "FLIP"

    # MERCH: genuine dip, intact long-term trend, not a falling knife.
    # Minimum price and profit thresholds exclude micro-price noise.
    if (is_dip and slope_90d >= -0.1 and current_low >= 1_000
            and merch_profit >= 2_000_000 and not knife_risk):
        return "MERCH"

    # TREND: multi-timeframe uptrend with RSI still below overbought.
    if slope_90d >= 0.0 and mtf_score >= 1 and rsi_val < 65:
        return "TREND"

    return "FLIP"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calc_news_boost(signals):
    """Small boost applied to non-NEWS items that have weak news signals (1-2 mentions)."""
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


def _fmt_gp(gp: int) -> str:
    if gp >= 1_000_000_000:
        return f"{gp/1_000_000_000:.2f}B"
    if gp >= 1_000_000:
        return f"{gp/1_000_000:.1f}M"
    if gp >= 1_000:
        return f"{gp/1_000:.0f}k"
    return f"{gp:,}"
