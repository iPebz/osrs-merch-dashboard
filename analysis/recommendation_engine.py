"""
Groups scored items into price-range buckets and builds detailed analysis text.
"""

PRICE_RANGES = [
    ("<1M",      0,            1_000_000),
    ("1–5M",     1_000_000,    5_000_000),
    ("10–20M",   10_000_000,  20_000_000),
    ("25–50M",   25_000_000,  50_000_000),
    ("50–100M",  50_000_000, 100_000_000),
    ("100M+",   100_000_000,  float("inf")),
]

TOP_N = 3


def group_by_price_range(scored_items: list[dict]) -> dict[str, list[dict]]:
    """Return {range_label: [top-N items sorted by score]}."""
    buckets: dict[str, list[dict]] = {label: [] for label, *_ in PRICE_RANGES}
    for item in scored_items:
        price = item.get("current_low", 0) or 0
        for label, lo, hi in PRICE_RANGES:
            if lo <= price < hi:
                buckets[label].append(item)
                break
    for label in buckets:
        buckets[label].sort(key=lambda r: r.get("score", 0), reverse=True)
        buckets[label] = buckets[label][:TOP_N]
    return buckets


def build_summary(item: dict) -> str:
    """One-line summary for a card header."""
    parts = []
    score = item.get("score", 0)
    rsi   = item.get("rsi", 50)
    s90   = item.get("slope_90d", 0) or 0
    is_dip = item.get("is_dip", False)
    margin = item.get("margin_pct", 0) or 0

    if is_dip:
        parts.append("price dip vs 90d high")
    if rsi < 35:
        parts.append(f"oversold RSI {rsi:.0f}")
    elif rsi < 45:
        parts.append(f"low RSI {rsi:.0f}")
    if s90 > 0.1:
        parts.append("90d uptrend")
    elif s90 < -0.1:
        parts.append("90d downtrend")
    if margin > 4:
        parts.append(f"{margin:.1f}% margin")
    if item.get("news_signals"):
        parts.append("news signal")
    return "; ".join(parts) if parts else item.get("reason", "Neutral")


def build_detail(item: dict) -> str:
    """Multi-line detailed analysis for the expanded card view."""
    name   = item.get("name", "")
    score  = item.get("score", 0)
    price  = item.get("current_low", 0) or 0
    high   = item.get("current_high", 0) or 0
    margin = item.get("margin_pct", 0) or 0
    s30    = item.get("slope_30d", 0) or 0
    s90    = item.get("slope_90d", 0) or 0
    rsi    = item.get("rsi", 50)
    is_dip = item.get("is_dip", False)
    vol_t  = item.get("vol_trend", "STABLE")
    vol    = item.get("avg_daily_vol", 0) or 0
    buy_lim = item.get("buy_limit", 0) or 0
    volat  = item.get("volatility", 0) or 0

    price_str = _fmt_gp(price)
    high_str  = _fmt_gp(high)

    lines = [
        f"Score: {score:.0f}/100",
        f"Buy price: {price_str}  |  Sell price: {high_str}  |  Margin: {margin:.1f}%",
        "",
        "TREND",
        f"  30d slope: {s30:+.2f}%  |  90d slope: {s90:+.2f}%",
    ]

    if is_dip:
        lines.append("  Currently in a price dip vs 90-day high — potential bounce opportunity")
    if s90 > 0.1:
        lines.append("  Long-term uptrend supports entry here")
    elif s90 < -0.15:
        lines.append("  Caution: long-term downtrend — higher risk play")

    lines += [
        "",
        "MOMENTUM",
        f"  RSI: {rsi:.0f}  {'(oversold — historically good entry)' if rsi < 35 else '(neutral)' if rsi < 55 else '(overbought — watch for pullback)'}",
        f"  Volume trend: {vol_t}  |  Avg daily: {vol:,.0f}",
    ]

    lines += [
        "",
        "TRADE SETUP",
        f"  Buy limit: {buy_lim:,} / 4h",
        f"  Suggested buy: ≤ {price_str}   Target sell: ≥ {high_str}",
    ]

    if margin >= 2 and buy_lim > 0:
        profit = price * buy_lim * (margin / 100)
        lines.append(f"  Est. profit per fill: {_fmt_gp(int(profit))} (at {margin:.1f}% margin × {buy_lim:,} items)")

    news = item.get("news_signals", [])
    if news:
        lines += ["", "NEWS / MARKET SIGNALS"]
        seen = set()
        for sig in news[:3]:
            title = sig.get("article_title", "")[:60]
            stype = sig.get("signal_type", "")
            if title not in seen:
                seen.add(title)
                badge = {"game_update": "[UPDATE]", "ge_rise": "[GE RISE]",
                         "mentioned": "[MENTIONED]"}.get(stype, "[SIGNAL]")
                lines.append(f"  {badge} {title}")

    lines += [
        "",
        "RISK",
    ]
    if volat > 5:
        lines.append(f"  High volatility ({volat:.1f}%) — price can swing quickly")
    elif volat > 2:
        lines.append(f"  Moderate volatility ({volat:.1f}%)")
    else:
        lines.append(f"  Low volatility ({volat:.1f}%) — stable price action")
    if s90 < -0.1:
        lines.append("  Long-term trend is down — set a stop-loss")

    return "\n".join(lines)


def _fmt_gp(gp: int) -> str:
    if gp >= 1_000_000:
        return f"{gp/1_000_000:.2f}M"
    if gp >= 1_000:
        return f"{gp/1_000:.0f}k"
    return str(gp)
