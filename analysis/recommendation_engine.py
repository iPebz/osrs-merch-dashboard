"""
Groups scored items into price-range buckets and strategy categories,
and generates detailed human-readable analysis text.
"""

PRICE_RANGES = [
    ("<1M",      0,              1_000_000),
    ("1–5M",     1_000_000,      5_000_000),
    ("10–25M",   10_000_000,    25_000_000),
    ("25–100M",  25_000_000,   100_000_000),
    ("100M+",   100_000_000,   float("inf")),
]

STRATEGIES = ["FLIP", "MERCH", "TREND", "NEWS"]

STRATEGY_LABELS = {
    "FLIP":  "Best Flips",
    "MERCH": "Dip Buys (Merch)",
    "TREND": "Trend Rides",
    "NEWS":  "News Plays",
}

STRATEGY_DESC = {
    "FLIP":  "High margin after GE tax — buy and sell for quick profit",
    "MERCH": "Price is below long-term average — buy the dip, sell the recovery",
    "TREND": "Multi-timeframe uptrend with room to run — ride the momentum",
    "NEWS":  "Game update or market signal detected — demand catalyst present",
}

TOP_N_PRICE  = 3
TOP_N_STRAT  = 5


def group_by_price_range(scored_items: list[dict]) -> dict[str, list[dict]]:
    """Return {range_label: top-N items sorted by score}."""
    buckets: dict[str, list[dict]] = {label: [] for label, *_ in PRICE_RANGES}
    for item in scored_items:
        price = item.get("current_low", 0) or 0
        for label, lo, hi in PRICE_RANGES:
            if lo <= price < hi:
                buckets[label].append(item)
                break
    for label in buckets:
        buckets[label].sort(key=lambda r: r.get("score", 0), reverse=True)
        buckets[label] = buckets[label][:TOP_N_PRICE]
    return buckets


def group_by_strategy(scored_items: list[dict]) -> dict[str, list[dict]]:
    """Return {strategy: top-N items for that strategy sorted by score}."""
    buckets: dict[str, list[dict]] = {s: [] for s in STRATEGIES}
    for item in scored_items:
        strat = item.get("strategy", "FLIP")
        if strat in buckets:
            buckets[strat].append(item)

    # Secondary sort keys per strategy
    sort_keys = {
        "FLIP":  lambda r: r.get("daily_flip_profit", 0) or 0,
        "MERCH": lambda r: r.get("merch_profit", 0) or 0,
        "TREND": lambda r: r.get("score", 0) or 0,
        "NEWS":  lambda r: r.get("score", 0) or 0,
    }
    for strat in buckets:
        buckets[strat].sort(key=sort_keys[strat], reverse=True)
        buckets[strat] = buckets[strat][:TOP_N_STRAT]
    return buckets


def build_summary(item: dict) -> str:
    """One-line card summary."""
    strat  = item.get("strategy", "")
    parts  = []

    if strat == "FLIP":
        nm = item.get("net_margin_pct", 0) or 0
        dp = item.get("daily_flip_profit", 0) or 0
        parts.append(f"{nm:.1f}% net margin")
        if dp > 0:
            parts.append(f"~{_fmt_gp(int(dp))}/day")
    elif strat == "MERCH":
        ma = item.get("ma_deviation", 0) or 0
        mp = item.get("merch_profit", 0) or 0
        parts.append(f"{abs(ma):.0f}% below MA90")
        if mp > 0:
            parts.append(f"~{_fmt_gp(int(mp))} potential")
    elif strat == "TREND":
        s90 = item.get("slope_90d", 0) or 0
        mtf = item.get("mtf_score", 0) or 0
        parts.append(f"90d slope {s90:+.1f}%")
        if mtf >= 2:
            parts.append("all TFs aligned")
    elif strat == "NEWS":
        sigs = item.get("news_signals", [])
        if sigs:
            parts.append(sigs[0].get("article_title", "")[:40])

    if not parts:
        parts.append(item.get("reason", "")[:55])
    return "; ".join(parts)


def build_detail(item: dict) -> str:
    """Multi-line detailed analysis for the expandable card view."""
    strat  = item.get("strategy", "FLIP")
    name   = item.get("name", "")
    score  = item.get("score", 0)
    price  = item.get("current_low", 0) or 0
    high   = item.get("current_high", 0) or 0
    nm_pct = item.get("net_margin_pct", 0) or 0
    nm_gp  = item.get("net_margin_gp", 0) or 0
    s7     = item.get("slope_7d", 0) or 0
    s30    = item.get("slope_30d", 0) or 0
    s90    = item.get("slope_90d", 0) or 0
    rsi_v  = item.get("rsi", 50)
    is_dip = item.get("is_dip", False)
    ma_dev = item.get("ma_deviation", 0) or 0
    sup    = item.get("support", 0) or 0
    res    = item.get("resistance", 0) or 0
    upside = item.get("upside_pct", 0) or 0
    mtf    = item.get("mtf_score", 0) or 0
    liq    = item.get("liquidity", 0) or 0
    vol    = item.get("avg_daily_vol", 0) or 0
    vol_t  = item.get("vol_trend", "STABLE")
    buy_lim= item.get("buy_limit", 0) or 0
    volat  = item.get("volatility", 0) or 0
    dfp    = item.get("daily_flip_profit", 0) or 0
    mp     = item.get("merch_profit", 0) or 0

    lines = [
        f"[{strat}] Score: {score:.0f}/100",
        f"Buy: {_fmt_gp(price)}  Sell: {_fmt_gp(high)}  Net margin: {nm_pct:.1f}% ({_fmt_gp(int(nm_gp))} after GE tax)",
        "",
    ]

    # Strategy-specific guidance
    if strat == "FLIP":
        lines += [
            "HOW TO FLIP",
            f"  1. Offer to buy at {_fmt_gp(price)} (or check buy price with 1-item offer)",
            f"  2. Sell at {_fmt_gp(high)} (or +1 gp above current sell)",
            f"  Buy limit: {buy_lim:,} every 4h",
        ]
        if dfp > 0:
            lines.append(f"  Est. daily profit: ~{_fmt_gp(int(dfp))} ({_fmt_gp(int(dfp/6))} per 4h cycle)")
        if liq < 1:
            lines.append(f"  WARNING: Low liquidity ({liq:.1f}x) — may take >4h to fill")
        elif liq > 6:
            lines.append(f"  Good liquidity ({liq:.1f}x buy limit trades daily)")

    elif strat == "MERCH":
        lines += [
            "HOW TO MERCH",
            f"  1. Buy at or below {_fmt_gp(price)}",
            f"  2. Target sell: {_fmt_gp(int(res))} (resistance) or {_fmt_gp(int(max(res, price * 1.15)))} (+15%)",
            f"  Est. profit if target hit: ~{_fmt_gp(int(mp))} (× {buy_lim:,} buy limit)",
        ]
        if ma_dev < -15:
            lines.append(f"  Price is {abs(ma_dev):.0f}% below its 90d average — historically strong entry")
        if sup > 0:
            lines.append(f"  Support floor: ~{_fmt_gp(int(sup))} — set stop-loss just below this")

    elif strat == "TREND":
        lines += [
            "HOW TO TRADE",
            f"  Buy in on a pullback toward {_fmt_gp(int(sup))} (support)",
            f"  Ride to {_fmt_gp(int(res))} ({upside:.0f}% upside to resistance)",
            f"  Exit if RSI breaks above 70 or price closes below MA30",
        ]

    elif strat == "NEWS":
        lines += ["NEWS CATALYST"]
        seen = set()
        for sig in (item.get("news_signals") or [])[:3]:
            t = sig.get("article_title", "")[:60]
            if t not in seen:
                seen.add(t)
                badge = {"game_update": "[UPDATE]", "ge_rise": "[GE RISE]",
                         "mentioned": "[MENTION]"}.get(sig.get("signal_type",""), "[SIG]")
                lines.append(f"  {badge} {t}")
        lines += [
            "",
            "  Strategy: buy before market fully prices in the news,",
            f"  target {_fmt_gp(int(res))} or +20% within 1–3 days",
        ]

    lines += [
        "",
        "TECHNICALS",
        f"  7d: {s7:+.2f}%  30d: {s30:+.2f}%  90d: {s90:+.2f}%",
        f"  RSI: {rsi_v:.0f}  {'(oversold)' if rsi_v < 35 else '(neutral)' if rsi_v < 60 else '(overbought)'}",
        f"  Multi-TF agreement: {mtf:+d}/3",
        f"  Daily volume: {vol:,.0f}  Trend: {vol_t}",
        f"  Volatility (30d): {volat:.1f}%",
        f"  Support: {_fmt_gp(int(sup))}  Resistance: {_fmt_gp(int(res))}",
        "",
        "RISK",
    ]

    if volat > 8:
        lines.append(f"  HIGH volatility ({volat:.1f}%) — price can move 8%+ in a day")
    elif volat > 4:
        lines.append(f"  Moderate volatility ({volat:.1f}%) — normal for this item class")
    else:
        lines.append(f"  Low volatility ({volat:.1f}%) — stable, predictable price action")

    if s90 < -0.2:
        lines.append("  Long-term downtrend still intact — higher risk, tighter stop")
    if liq < 0.5:
        lines.append("  Illiquid — hard to buy/sell quickly; avoid large positions")

    return "\n".join(lines)


def _fmt_gp(gp: int) -> str:
    if gp >= 1_000_000_000:
        return f"{gp/1_000_000_000:.2f}B"
    if gp >= 1_000_000:
        return f"{gp/1_000_000:.2f}M"
    if gp >= 1_000:
        return f"{gp/1_000:.0f}k"
    return f"{gp:,}"
