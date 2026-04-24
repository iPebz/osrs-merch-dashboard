SCORE_HIGH  = "#2ecc71"   # green  — score >= 70
SCORE_MID   = "#f39c12"   # amber  — score 50–69
SCORE_LOW   = "#e74c3c"   # red    — score < 50

TREND_UP    = "#2ecc71"
TREND_DOWN  = "#e74c3c"
TREND_FLAT  = "#95a5a6"

TABLE_HEADER_BG = "#1a1a2e"
TABLE_ROW_ALT   = "#16213e"
TABLE_ROW_NORM  = "#0f3460"

FONT_MONO   = ("Courier New", 11)
FONT_LABEL  = ("Segoe UI", 11)
FONT_TITLE  = ("Segoe UI", 13, "bold")


def score_color(score: float) -> str:
    if score >= 70:
        return SCORE_HIGH
    if score >= 50:
        return SCORE_MID
    return SCORE_LOW


def trend_color(slope: float) -> str:
    if slope > 0.05:
        return TREND_UP
    if slope < -0.05:
        return TREND_DOWN
    return TREND_FLAT
