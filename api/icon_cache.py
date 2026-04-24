import logging
from pathlib import Path

try:
    import requests as _requests
    from PIL import Image, ImageTk
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

log = logging.getLogger(__name__)

ICON_DIR = Path("data/icons")
CDN_BASE = "https://oldschool.runescape.wiki/images"
HEADERS  = {"User-Agent": "osrs-merch-dashboard - personal project"}

_photo_cache: dict[int, object] = {}  # item_id → PhotoImage; kept to prevent GC


def get_icon_photo(item_id: int, icon_filename: str | None, size: int = 32):
    """Return a PIL PhotoImage for the given item, or None if unavailable."""
    if not _AVAILABLE or not icon_filename:
        return None
    if item_id in _photo_cache:
        return _photo_cache[item_id]

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    path = ICON_DIR / f"{item_id}.png"

    if not path.exists():
        fname = icon_filename.replace(" ", "_")
        url   = f"{CDN_BASE}/{fname}"
        try:
            r = _requests.get(url, headers=HEADERS, timeout=5)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception as e:
            log.debug("Icon download failed item %d: %s", item_id, e)
            return None

    try:
        img   = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        _photo_cache[item_id] = photo
        return photo
    except Exception as e:
        log.debug("Icon load failed item %d: %s", item_id, e)
        return None


def prefetch_icons(items: list[dict], size: int = 32):
    """Download and cache icons for a list of {id, icon_url} dicts."""
    for item in items:
        get_icon_photo(item.get("id") or item.get("item_id"),
                       item.get("icon_url"), size)
