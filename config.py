BUDGET_MIN_GP = 1              # no lower cap — let volume filter remove junk
BUDGET_MAX_GP = 2_000_000_000  # 2B cap covers all tradeable OSRS items

WEIGHT_TREND  = 1.0
WEIGHT_RSI    = 1.0
WEIGHT_DIP    = 1.0
WEIGHT_MARGIN = 0.8
WEIGHT_VOLUME = 0.7

DEFAULT_SCORE_THRESHOLD    = 40
REFRESH_INTERVAL_SECONDS   = 60
MIN_DAILY_VOLUME           = 100  # minimum avg daily volume to appear in results
ALERT_COOLDOWN_MINUTES     = 60

DB_PATH = "data/ge_prices.db"

HIGH_VALUE_SEEDS = {
    4151:  "Abyssal whip",
    11802: "Saradomin godsword",
    11804: "Armadyl godsword",
    11806: "Bandos godsword",
    11808: "Zamorak godsword",
    4587:  "Dragon scimitar",
    1215:  "Dragon dagger",
    3204:  "Dragon halberd",
    11838: "Armadyl crossbow",
    12006: "Armadyl helmet",
    12008: "Armadyl chestplate",
    12010: "Armadyl chainskirt",
    11832: "Bandos chestplate",
    11834: "Bandos tassets",
    11836: "Bandos boots",
    13576: "Toxic blowpipe",
    12899: "Twisted bow",
    2577:  "Rangers' tunic",
    6570:  "Fire cape",
    453:   "Coal",
    440:   "Iron ore",
    444:   "Gold ore",
    447:   "Mithril ore",
    449:   "Adamantite ore",
    451:   "Runite ore",
    1519:  "Magic logs",
    1515:  "Yew logs",
    207:   "Grimy ranarr weed",
    213:   "Grimy snapdragon",
}
