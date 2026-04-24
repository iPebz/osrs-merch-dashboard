import requests
import logging
from typing import Optional

log = logging.getLogger(__name__)

BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"
HEADERS = {"User-Agent": "osrs-merch-dashboard - personal project"}


def get_mapping() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/mapping", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_latest(item_id: Optional[int] = None) -> dict:
    params = {"id": item_id} if item_id else {}
    resp = requests.get(f"{BASE_URL}/latest", headers=HEADERS,
                        params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", {})


def get_timeseries(item_id: int, timestep: str = "24h") -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/timeseries",
        headers=HEADERS,
        params={"id": item_id, "timestep": timestep},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_bulk(interval: str = "24h") -> dict:
    resp = requests.get(f"{BASE_URL}/{interval}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", {})
