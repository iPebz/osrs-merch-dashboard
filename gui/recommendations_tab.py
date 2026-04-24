import tkinter as tk
import customtkinter as ctk
import threading
import logging
from api.icon_cache import get_icon_photo
from analysis.recommendation_engine import (
    group_by_price_range, build_summary, build_detail, PRICE_RANGES,
)
from gui.styles import score_color, FONT_LABEL, FONT_TITLE

log = logging.getLogger(__name__)

BG        = "#1a1a2e"
SECT_BG   = "#0d1b2a"
CARD_BG   = "#16213e"
CARD_HIGH = "#163016"
ICON_SIZE = 40


class RecommendationsTab(ctk.CTkFrame):
    def __init__(self, parent, db_conn):
        super().__init__(parent)
        self.db = db_conn
        self._item_icon_urls: dict[int, str] = {}
        self._icon_photos: dict[int, object] = {}
        self._expanded: dict[str, bool] = {}

        self._build_header()
        self._build_scroll_area()
        self._placeholder()

    # ------------------------------------------------------------------

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=6, pady=(4, 2))
        tk.Label(hdr, text="Recommendations by Price Range",
                 font=FONT_TITLE, fg="#f39c12", bg=BG).pack(side="left", padx=6)
        self._status_lbl = tk.Label(hdr, text="",
                                    font=FONT_LABEL, fg="#555555", bg=BG)
        self._status_lbl.pack(side="right", padx=10)

    def _build_scroll_area(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=6, pady=4)

        self._canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=BG)
        self._win_id = self._canvas.create_window(0, 0, anchor="nw", window=self._inner)

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_inner_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._win_id, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------

    def _placeholder(self):
        for w in self._inner.winfo_children():
            w.destroy()
        tk.Label(self._inner, text='Press "Score All Items" to generate recommendations.',
                 font=FONT_LABEL, fg="#555555", bg=BG).pack(pady=40)

    def update_recommendations(self, scored_items: list[dict],
                                icon_urls: dict[int, str] | None = None):
        """Called from the main thread after scoring completes."""
        if icon_urls:
            self._item_icon_urls = icon_urls
        self._render(scored_items)

    def _render(self, scored_items: list[dict]):
        for w in self._inner.winfo_children():
            w.destroy()
        self._expanded.clear()

        buckets = group_by_price_range(scored_items)
        any_items = any(items for items in buckets.values())

        if not any_items:
            tk.Label(self._inner, text="No scored items yet. Try 'Score All Items'.",
                     font=FONT_LABEL, fg="#555555", bg=BG).pack(pady=40)
            return

        for label, _lo, _hi in PRICE_RANGES:
            items = buckets.get(label, [])
            self._build_section(label, items)

        self._status_lbl.configure(text=f"{len(scored_items)} items scored")
        threading.Thread(target=self._load_icons_bg,
                         args=(scored_items,), daemon=True).start()

    def _build_section(self, label: str, items: list[dict]):
        sect = tk.Frame(self._inner, bg=SECT_BG, relief="flat", bd=1)
        sect.pack(fill="x", padx=4, pady=4)

        hdr = tk.Frame(sect, bg=SECT_BG)
        hdr.pack(fill="x", padx=8, pady=(6, 4))

        tk.Label(hdr, text=label, font=FONT_TITLE,
                 fg="#f39c12", bg=SECT_BG).pack(side="left")

        if not items:
            tk.Label(hdr, text="No items in this range yet",
                     font=FONT_LABEL, fg="#555555", bg=SECT_BG).pack(side="left", padx=12)
            return

        cards_row = tk.Frame(sect, bg=SECT_BG)
        cards_row.pack(fill="x", padx=8, pady=(0, 8))

        for item in items:
            self._build_item_card(cards_row, item, label)

    def _build_item_card(self, parent: tk.Frame, item: dict, section: str):
        has_news = bool(item.get("news_signals"))
        bg = CARD_HIGH if has_news else CARD_BG
        item_id = item.get("item_id", 0)

        card = tk.Frame(parent, bg=bg, relief="solid", bd=1)
        card.pack(side="left", padx=4, pady=2, anchor="nw")

        # Header row: icon + name + score
        top = tk.Frame(card, bg=bg)
        top.pack(fill="x", padx=6, pady=(6, 2))

        icon_lbl = tk.Label(top, bg=bg, width=3)
        icon_lbl.pack(side="left", padx=(0, 6))
        self._icon_photos[item_id] = None  # placeholder; filled by bg thread

        name_col = tk.Frame(top, bg=bg)
        name_col.pack(side="left", fill="x", expand=True)

        name_str = item.get("name", "")[:28]
        score    = item.get("score", 0)
        tk.Label(name_col, text=name_str, font=FONT_TITLE,
                 fg="white", bg=bg, anchor="w").pack(anchor="w")

        score_row = tk.Frame(name_col, bg=bg)
        score_row.pack(anchor="w")
        tk.Label(score_row, text=f"Score: {score:.0f}",
                 font=FONT_LABEL, fg=score_color(score), bg=bg).pack(side="left")
        if has_news:
            tk.Label(score_row, text=" ★ NEWS",
                     font=FONT_LABEL, fg="#2ecc71", bg="#0a3010").pack(side="left", padx=4)

        # Price + summary line
        price = item.get("current_low", 0) or 0
        price_str = _fmt_gp(price)
        tk.Label(card, text=price_str, font=FONT_LABEL,
                 fg="#aaaaaa", bg=bg, anchor="w").pack(padx=6, anchor="w")

        summary = build_summary(item)[:55]
        tk.Label(card, text=summary, font=("Segoe UI", 9),
                 fg="#888888", bg=bg, anchor="w", wraplength=240, justify="left",
                 ).pack(padx=6, pady=(0, 2), anchor="w")

        # Expand/collapse button
        card_key = f"{section}_{item_id}"
        self._expanded[card_key] = False

        detail_frame = tk.Frame(card, bg="#0f2040")

        detail_text_var = tk.StringVar(value=build_detail(item))
        detail_lbl = tk.Label(
            detail_frame,
            textvariable=detail_text_var,
            font=("Courier New", 9),
            fg="#cccccc", bg="#0f2040",
            anchor="nw", justify="left",
            wraplength=320,
            padx=8, pady=6,
        )
        detail_lbl.pack(fill="x")

        toggle_btn = tk.Button(
            card, text="▼ Details", font=("Segoe UI", 8),
            bg="#0d1b2a", fg="#5dade2",
            relief="flat", bd=0, cursor="hand2",
            command=lambda k=card_key, df=detail_frame, btn=None: None,
        )
        toggle_btn.pack(padx=6, pady=(0, 4), anchor="w")

        def _toggle(k=card_key, df=detail_frame, btn=toggle_btn):
            self._expanded[k] = not self._expanded[k]
            if self._expanded[k]:
                df.pack(fill="x", padx=4, pady=(0, 4))
                btn.configure(text="▲ Hide")
            else:
                df.pack_forget()
                btn.configure(text="▼ Details")

        toggle_btn.configure(command=_toggle)

        # Store reference to icon label for later update
        item["_icon_lbl_ref"] = icon_lbl

    # ------------------------------------------------------------------

    def _load_icons_bg(self, scored_items: list[dict]):
        for item in scored_items[:50]:
            item_id  = item.get("item_id", 0)
            icon_url = self._item_icon_urls.get(item_id)
            if not icon_url:
                continue
            photo = get_icon_photo(item_id, icon_url, ICON_SIZE)
            if photo:
                self._icon_photos[item_id] = photo
                lbl_ref = item.get("_icon_lbl_ref")
                if lbl_ref:
                    try:
                        lbl_ref.after(0, lambda l=lbl_ref, p=photo: l.configure(image=p))
                    except Exception:
                        pass


def _fmt_gp(gp: int) -> str:
    if gp >= 1_000_000:
        return f"{gp/1_000_000:.2f}M"
    if gp >= 1_000:
        return f"{gp/1_000:.0f}k"
    return str(gp)
