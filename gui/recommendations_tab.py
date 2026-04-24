"""
Recommendations tab — two views:
  1. Strategy sections (FLIP / MERCH / TREND / NEWS) — top 5 each
  2. Price-range sections (<1M … 100M+) — top 3 each
"""
import tkinter as tk
import customtkinter as ctk
import threading
import logging
from api.icon_cache import get_icon_photo
from analysis.recommendation_engine import (
    group_by_price_range, group_by_strategy,
    build_summary, build_detail,
    PRICE_RANGES, STRATEGIES, STRATEGY_LABELS, STRATEGY_DESC,
)
from gui.styles import score_color, FONT_LABEL, FONT_TITLE

log = logging.getLogger(__name__)

BG       = "#1a1a2e"
SECT_BG  = "#0d1b2a"
CARD_BG  = "#16213e"
CARD_HI  = "#163016"
ICON_SZ  = 40

STRAT_COLORS = {
    "FLIP":  "#5dade2",
    "MERCH": "#f39c12",
    "TREND": "#2ecc71",
    "NEWS":  "#e74c3c",
}


class RecommendationsTab(ctk.CTkFrame):
    def __init__(self, parent, db_conn):
        super().__init__(parent)
        self.db = db_conn
        self._item_icon_urls: dict[int, str] = {}
        self._icon_photos:    dict[int, object] = {}
        self._expanded:       dict[str, bool] = {}
        self._view = "strategy"   # "strategy" | "price"

        self._build_header()
        self._build_scroll_area()
        self._show_placeholder()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=6, pady=(4, 0))

        tk.Label(hdr, text="Recommendations", font=FONT_TITLE,
                 fg="#f39c12", bg=BG).pack(side="left", padx=6)

        btn_frame = tk.Frame(hdr, bg=BG)
        btn_frame.pack(side="left", padx=12)

        self._strat_btn = tk.Button(
            btn_frame, text="By Strategy", font=FONT_LABEL,
            bg="#0f3460", fg="white", relief="flat", cursor="hand2",
            command=lambda: self._switch_view("strategy"))
        self._strat_btn.pack(side="left", padx=2)

        self._price_btn = tk.Button(
            btn_frame, text="By Price Range", font=FONT_LABEL,
            bg="#1a1a2e", fg="#aaaaaa", relief="flat", cursor="hand2",
            command=lambda: self._switch_view("price"))
        self._price_btn.pack(side="left", padx=2)

        self._status_lbl = tk.Label(hdr, text="", font=FONT_LABEL,
                                    fg="#555555", bg=BG)
        self._status_lbl.pack(side="right", padx=10)

    def _switch_view(self, view: str):
        self._view = view
        if view == "strategy":
            self._strat_btn.configure(bg="#0f3460", fg="white")
            self._price_btn.configure(bg="#1a1a2e", fg="#aaaaaa")
        else:
            self._price_btn.configure(bg="#0f3460", fg="white")
            self._strat_btn.configure(bg="#1a1a2e", fg="#aaaaaa")
        if hasattr(self, "_last_scored_items"):
            self._render(self._last_scored_items)

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

        self._inner.bind("<Configure>",  self._on_inner_cfg)
        self._canvas.bind("<Configure>", self._on_canvas_cfg)
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _on_inner_cfg(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_cfg(self, event):
        self._canvas.itemconfigure(self._win_id, width=event.width)

    def _on_wheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_recommendations(self, scored_items: list[dict],
                                icon_urls: dict[int, str] | None = None):
        if icon_urls:
            self._item_icon_urls = icon_urls
        self._last_scored_items = scored_items
        self._render(scored_items)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _show_placeholder(self):
        for w in self._inner.winfo_children():
            w.destroy()
        tk.Label(self._inner,
                 text='Press "Score All Items" to generate recommendations.',
                 font=FONT_LABEL, fg="#555555", bg=BG).pack(pady=60)

    def _render(self, scored_items: list[dict]):
        for w in self._inner.winfo_children():
            w.destroy()
        self._expanded.clear()

        if not scored_items:
            tk.Label(self._inner,
                     text="No scored items yet. Try 'Score All Items'.",
                     font=FONT_LABEL, fg="#555555", bg=BG).pack(pady=60)
            return

        if self._view == "strategy":
            self._render_strategy_view(scored_items)
        else:
            self._render_price_view(scored_items)

        self._status_lbl.configure(text=f"{len(scored_items)} items scored")
        threading.Thread(target=self._load_icons_bg,
                         args=(scored_items[:60],), daemon=True).start()

    def _render_strategy_view(self, scored_items: list[dict]):
        buckets = group_by_strategy(scored_items)
        for strat in STRATEGIES:
            items = buckets.get(strat, [])
            color = STRAT_COLORS.get(strat, "#aaaaaa")
            self._build_section(
                STRATEGY_LABELS[strat],
                STRATEGY_DESC[strat],
                items, strat, color,
            )

    def _render_price_view(self, scored_items: list[dict]):
        buckets = group_by_price_range(scored_items)
        for label, _lo, _hi in PRICE_RANGES:
            items = buckets.get(label, [])
            self._build_section(label, "", items, label, "#f39c12")

    def _build_section(self, title: str, subtitle: str,
                        items: list[dict], section_key: str, accent: str):
        sect = tk.Frame(self._inner, bg=SECT_BG)
        sect.pack(fill="x", padx=4, pady=4)

        hdr = tk.Frame(sect, bg=SECT_BG)
        hdr.pack(fill="x", padx=10, pady=(8, 2))

        tk.Label(hdr, text=title, font=FONT_TITLE,
                 fg=accent, bg=SECT_BG).pack(side="left")
        if subtitle:
            tk.Label(hdr, text=f"  — {subtitle}", font=("Segoe UI", 9),
                     fg="#666666", bg=SECT_BG).pack(side="left")

        if not items:
            tk.Label(sect, text="No items in this category yet.",
                     font=FONT_LABEL, fg="#555555", bg=SECT_BG).pack(
                     padx=12, pady=(0, 8), anchor="w")
            return

        cards_row = tk.Frame(sect, bg=SECT_BG)
        cards_row.pack(fill="x", padx=8, pady=(2, 10))

        for idx, item in enumerate(items):
            card_key = f"{section_key}_{item.get('item_id', idx)}"
            self._build_card(cards_row, item, card_key)

    def _build_card(self, parent: tk.Frame, item: dict, card_key: str):
        has_news = bool(item.get("news_signals"))
        strat    = item.get("strategy", "")
        bg = CARD_HI if has_news else CARD_BG
        acc = STRAT_COLORS.get(strat, "#aaaaaa")

        card = tk.Frame(parent, bg=bg, relief="solid", bd=1)
        card.pack(side="left", padx=4, pady=2, anchor="nw")

        # ── Top row: icon + name + strategy badge ──────────────────────
        top = tk.Frame(card, bg=bg)
        top.pack(fill="x", padx=6, pady=(6, 2))

        icon_lbl = tk.Label(top, bg=bg, width=3)
        icon_lbl.pack(side="left", padx=(0, 6))
        item["_icon_lbl_ref"] = icon_lbl

        name_col = tk.Frame(top, bg=bg)
        name_col.pack(side="left", fill="x", expand=True)

        name_row = tk.Frame(name_col, bg=bg)
        name_row.pack(anchor="w")
        tk.Label(name_row, text=item.get("name", "")[:26],
                 font=FONT_TITLE, fg="white", bg=bg).pack(side="left")
        if strat:
            tk.Label(name_row, text=f" [{strat}]", font=("Segoe UI", 8, "bold"),
                     fg=acc, bg=bg).pack(side="left", padx=2)

        # ── Score row ──────────────────────────────────────────────────
        score = item.get("score", 0)
        score_row = tk.Frame(name_col, bg=bg)
        score_row.pack(anchor="w")
        tk.Label(score_row, text=f"Score: {score:.0f}",
                 font=FONT_LABEL, fg=score_color(score), bg=bg).pack(side="left")
        if has_news:
            tk.Label(score_row, text=" ★ NEWS",
                     font=("Segoe UI", 8), fg="#2ecc71", bg="#0a3010").pack(side="left", padx=3)

        # ── Price ──────────────────────────────────────────────────────
        price = item.get("current_low", 0) or 0
        tk.Label(card, text=_fmt_gp(price), font=FONT_LABEL,
                 fg="#aaaaaa", bg=bg, anchor="w").pack(padx=6, anchor="w")

        # ── Summary ────────────────────────────────────────────────────
        summary = build_summary(item)[:62]
        tk.Label(card, text=summary, font=("Segoe UI", 9),
                 fg="#888888", bg=bg, anchor="w",
                 wraplength=260, justify="left").pack(padx=6, pady=(0, 2), anchor="w")

        # ── Expandable detail ─────────────────────────────────────────
        self._expanded[card_key] = False
        detail_frame = tk.Frame(card, bg="#0a1428")
        tk.Label(detail_frame,
                 text=build_detail(item),
                 font=("Courier New", 8),
                 fg="#cccccc", bg="#0a1428",
                 anchor="nw", justify="left",
                 wraplength=340, padx=8, pady=6).pack(fill="x")

        toggle_btn = tk.Button(
            card, text="▼ Details", font=("Segoe UI", 8),
            bg="#0d1b2a", fg="#5dade2", relief="flat", bd=0, cursor="hand2",
        )
        toggle_btn.pack(padx=6, pady=(0, 5), anchor="w")

        def _toggle(k=card_key, df=detail_frame, btn=toggle_btn):
            self._expanded[k] = not self._expanded[k]
            if self._expanded[k]:
                df.pack(fill="x", padx=4, pady=(0, 4))
                btn.configure(text="▲ Hide")
            else:
                df.pack_forget()
                btn.configure(text="▼ Details")

        toggle_btn.configure(command=_toggle)

    # ------------------------------------------------------------------
    # Background icon loading
    # ------------------------------------------------------------------

    def _load_icons_bg(self, scored_items: list[dict]):
        for item in scored_items:
            item_id  = item.get("item_id", 0)
            icon_url = self._item_icon_urls.get(item_id)
            if not icon_url:
                continue
            photo = get_icon_photo(item_id, icon_url, ICON_SZ)
            if photo:
                self._icon_photos[item_id] = photo
                lbl = item.get("_icon_lbl_ref")
                if lbl:
                    try:
                        lbl.after(0, lambda l=lbl, p=photo: l.configure(image=p))
                    except Exception:
                        pass


# ------------------------------------------------------------------

def _fmt_gp(gp: int) -> str:
    if gp >= 1_000_000_000:
        return f"{gp/1_000_000_000:.2f}B"
    if gp >= 1_000_000:
        return f"{gp/1_000_000:.2f}M"
    if gp >= 1_000:
        return f"{gp/1_000:.0f}k"
    return f"{gp:,}"
