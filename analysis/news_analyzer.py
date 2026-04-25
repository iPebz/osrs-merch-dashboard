import re
import requests
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

NEWS_BASE = "https://secure.runescape.com/m=news"
HEADERS = {"User-Agent": "osrs-merch-dashboard - personal project"}

NEWS_LOOKBACK_DAYS = 30
# Only fetch full article body for these categories (heavier scraping)
FULL_BODY_CATEGORIES = {"Game Updates"}
# Minimum item name length to attempt matching (avoids common short words)
MIN_NAME_LEN = 5
# Leagues is a temporary seasonal game mode — its updates affect a separate
# economy and should not influence main-game GE scoring.
_LEAGUES_SKIP_WORDS = {"league", "leagues"}


def fetch_news_signals(item_names: dict, pages: int = 3) -> list[dict]:
    """
    Scrape recent OSRS news and return signals for items mentioned.

    item_names: {item_id: name}
    Returns list of dicts:
        {item_id, item_name, article_title, article_url, article_date, signal_type}
    signal_type: "game_update" | "mentioned"
    """
    articles = _fetch_article_list(pages)
    if not articles:
        log.warning("No news articles fetched.")
        return []

    # Build {lowercase_name: item_id}, sorted longest-first so "Dragon scimitar"
    # matches before "Dragon" when scanning text.
    name_to_id = {name.lower(): iid
                  for iid, name in item_names.items()
                  if len(name) >= MIN_NAME_LEN}

    cutoff = datetime.utcnow() - timedelta(days=NEWS_LOOKBACK_DAYS)
    signals = []

    for article in articles:
        date_parsed = article.get("date_parsed")
        if date_parsed and date_parsed < cutoff:
            continue

        title_lower = article.get("title", "").lower()
        if any(w in title_lower for w in _LEAGUES_SKIP_WORDS):
            continue

        category = article.get("category", "")
        is_game_update = category in FULL_BODY_CATEGORIES

        text = article.get("summary", "")
        if is_game_update and article.get("url"):
            full = _fetch_article_body(article["url"])
            if full:
                text = full

        combined = (article.get("title", "") + " " + text).lower()
        signal_type = "game_update" if is_game_update else "mentioned"

        matched_ids = set()
        for name_lower, item_id in name_to_id.items():
            if item_id in matched_ids:
                continue
            if len(name_lower) < 8:
                # Short names require word boundaries to reduce false positives
                if re.search(r'\b' + re.escape(name_lower) + r'\b', combined):
                    matched_ids.add(item_id)
            else:
                if name_lower in combined:
                    matched_ids.add(item_id)

        for item_id in matched_ids:
            signals.append({
                "item_id":       item_id,
                "item_name":     item_names[item_id],
                "article_title": article.get("title", ""),
                "article_url":   article.get("url", ""),
                "article_date":  article.get("date", ""),
                "signal_type":   signal_type,
            })

    log.info("News analyzer: %d signals from %d articles", len(signals), len(articles))
    return signals


def _fetch_article_list(pages: int = 3) -> list[dict]:
    articles = []
    url = f"{NEWS_BASE}/archive?oldschool=1"

    for page_num in range(pages):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for art in soup.find_all("article", class_="news-list-article"):
                title_a = art.find("a", class_="news-list-article__title-link")
                time_el = art.find("time", class_="news-list-article__date")
                cat_el  = art.find("span", class_="news-list-article__category")
                summ_el = art.find("p", class_="news-list-article__summary")

                if not title_a:
                    continue

                raw_date = (time_el.get("datetime", "") if time_el else "")
                try:
                    date_parsed = datetime.fromisoformat(
                        raw_date.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except (ValueError, AttributeError):
                    date_parsed = None

                href = title_a.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://secure.runescape.com" + href

                articles.append({
                    "title":       title_a.get_text(strip=True),
                    "url":         href,
                    "date":        time_el.get_text(strip=True) if time_el else "",
                    "date_parsed": date_parsed,
                    "category":    cat_el.get_text(strip=True) if cat_el else "",
                    "summary":     summ_el.get_text(strip=True) if summ_el else "",
                })

            next_link = soup.find("a", class_="news-archive-next")
            if not next_link:
                break
            next_href = next_link.get("href", "")
            if not next_href.startswith("http"):
                next_href = "https://secure.runescape.com" + next_href
            url = next_href

        except Exception as e:
            log.warning("Failed to fetch news page %d: %s", page_num + 1, e)
            break

    return articles


def _fetch_article_body(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        body = soup.find("div", class_="news-article-content")
        return body.get_text(separator=" ", strip=True) if body else ""
    except Exception as e:
        log.warning("Failed to fetch article body %s: %s", url, e)
        return ""
