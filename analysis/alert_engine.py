import logging
from database.queries import get_watchlist, log_alert, alert_recently_fired
import config

log = logging.getLogger(__name__)

try:
    from plyer import notification
    _PLYER_AVAILABLE = True
except Exception:
    _PLYER_AVAILABLE = False

APP_NAME = "OSRS Merch Dashboard"


def check_alerts(conn, latest_prices: dict):
    watchlist = get_watchlist(conn)

    for item in watchlist:
        item_id    = item["item_id"]
        item_name  = item["name"]
        buy_below  = item["alert_buy_below"]
        sell_above = item["alert_sell_above"]

        price_data = latest_prices.get(str(item_id))
        if not price_data:
            continue

        current_low  = price_data.get("low")
        current_high = price_data.get("high")

        if buy_below and current_low and current_low <= buy_below:
            if not alert_recently_fired(conn, item_id, "BUY", config.ALERT_COOLDOWN_MINUTES):
                msg = (f"{item_name}: LOW {current_low:,} gp "
                       f"≤ buy target {buy_below:,} gp")
                _fire_alert(conn, item_id, "BUY", current_low, buy_below, msg)

        if sell_above and current_high and current_high >= sell_above:
            if not alert_recently_fired(conn, item_id, "SELL", config.ALERT_COOLDOWN_MINUTES):
                msg = (f"{item_name}: HIGH {current_high:,} gp "
                       f"≥ sell target {sell_above:,} gp")
                _fire_alert(conn, item_id, "SELL", current_high, sell_above, msg)


def _fire_alert(conn, item_id: int, alert_type: str,
                price: int, threshold: int, message: str):
    log.info("ALERT [%s] %s", alert_type, message)

    if _PLYER_AVAILABLE:
        try:
            notification.notify(
                title=f"OSRS {alert_type} Alert",
                message=message,
                app_name=APP_NAME,
                timeout=10,
            )
        except Exception as e:
            log.warning("Desktop notification failed: %s", e)

    log_alert(conn, item_id, alert_type, price, threshold)
