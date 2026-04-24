import requests
import logging
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

GE_BASE = "https://secure.runescape.com/m=itemdb_oldschool"
HEADERS = {"User-Agent": "osrs-merch-dashboard - personal project"}


def get_market_movers() -> dict:
    """
    Scrape the GE main page for trending items.
    Returns:
        {
          "rises":    [{"name": str, "change": str}, ...],
          "falls":    [...],
          "traded":   [...],
          "valuable": [...],
        }
    """
    try:
        resp = requests.get(GE_BASE + "/", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        result = {}
        for section_class in ("rises", "falls", "traded", "valuable"):
            section = soup.find("section", class_=section_class)
            items = []
            if section:
                # First <a> is the section header link — skip it
                for a in section.find_all("a")[1:]:
                    name = a.get_text(strip=True)
                    change_span = a.find_next_sibling("span")
                    change = change_span.get_text(strip=True) if change_span else ""
                    if name:
                        items.append({"name": name, "change": change})
            result[section_class] = items

        log.info("GE market movers fetched: %s",
                 {k: len(v) for k, v in result.items()})
        return result

    except Exception as e:
        log.warning("GE scraper failed: %s", e)
        return {"rises": [], "falls": [], "traded": [], "valuable": []}
