import requests
import logging

log = logging.getLogger(__name__)

BASE_URL = "https://secure.runescape.com/m=itemdb_oldschool"
HEADERS = {"User-Agent": "osrs-merch-dashboard - personal project"}


def get_item_detail(item_id: int) -> dict:
    resp = requests.get(
        f"{BASE_URL}/api/catalogue/detail.json",
        headers=HEADERS,
        params={"item": item_id},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_price_graph(item_id: int) -> dict:
    resp = requests.get(
        f"{BASE_URL}/api/graph/{item_id}.json",
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
