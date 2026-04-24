import tkinter as tk
import tkinter.ttk as ttk
import customtkinter as ctk
import threading
from gui.styles import score_color, trend_color, FONT_LABEL, FONT_TITLE
from api.icon_cache import get_icon_photo
import config

TREE_COLS = [
    ("rank",      "Rank",          50, "e"),
    ("name",      "Item",         200, "w"),
    ("strat",     "Strategy",      70, "w"),
    ("score",     "Score",         55, "e"),
    ("price",     "Price (buy)",  110, "e"),
    ("margin",    "Margin%",       70, "e"),
    ("flip_day",  "GP/day",        90, "e"),
    ("slope7",    "7d",            60, "e"),
    ("slope90",   "90d",           60, "e"),
    ("rsi",       "RSI",           50, "e"),
    ("volume",    "Volume",        80, "e"),
    ("reason",    "Reason",       220, "w"),
]

STRAT_COLORS = {
    "FLIP":  "#5dade2",
    "MERCH": "#f39c12",
    "TREND": "#2ecc71",
    "NEWS":  "#e74c3c",
}

CARD_BG      = "#16213e"
CARD_NEWS_BG = "#163016"


def _style_treeview():
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Dashboard.Treeview",
        background="#1a1a2e",
        foreground="white",
        fieldbackground="#1a1a2e",
        rowheight=30,
        font=FONT_LABEL,
        borderwidth=0,
    )
    style.configure("Dashboard.Treeview.Heading",
        background="#0d1b2a",
        foreground="#f39c12",
        font=FONT_TITLE,
        relief="flat",
        borderwidth=1,
    )
    style.map("Dashboard.Treeview",
        background=[("selected", "#0f3460")],
        foreground=[("selected", "white")],
    )
    style.map("Dashboard.Treeview.Heading",
        background=[("active", "#16213e")],
    )
    # Strategy tag colours
    for tag, col in STRAT_COLORS.items():
        pass  # applied per-row via tag_configure after tree creation


class DashboardTab(ctk.CTkFrame):
    def __init__(self, parent, db_conn, data_service, on_chart_select=None):
        super().__init__(parent)
        self.db = db_conn
        self.data_service = data_service
        self.on_chart_select = on_chart_select
        self._rows: list[dict] = []
        self._row_data: dict[str, dict] = {}
        self._sort_col = "score"
        self._sort_asc = False
        self._icon_urls: dict[int, str] = {}
        self._icon_photos: dict[int, object] = {}  # GC guard

        _style_treeview()
        self._build_recommendations()
        self._build_controls()
        self._build_table()

    # ------------------------------------------------------------------
    # TOP PICKS panel
    # ------------------------------------------------------------------

    def _build_recommendations(self):
        self._rec_outer = tk.Frame(self, bg="#0d1b2a", relief="flat")
        self._rec_outer.pack(fill="x", padx=6, pady=(6, 2))

        tk.Label(self._rec_outer, text="TOP PICKS",
                 font=FONT_TITLE, fg="#f39c12", bg="#0d1b2a",
                 ).pack(side="left", padx=(10, 6), pady=8)

        self._rec_cards_frame = tk.Frame(self._rec_outer, bg="#0d1b2a")
        self._rec_cards_frame.pack(side="left", fill="x", expand=True, pady=4)

        tk.Label(self._rec_cards_frame,
                 text='Press "Score All Items" to generate recommendations.',
                 font=FONT_LABEL, fg="#555555", bg="#0d1b2a",
                 ).pack(side="left", padx=8)

    def _update_recommendations(self, scored_items: list[dict]):
        for w in self._rec_cards_frame.winfo_children():
            w.destroy()

        top = [r for r in scored_items if r.get("score", 0) >= 50][:5]
        if not top:
            tk.Label(self._rec_cards_frame,
                     text="No items scored above 50 yet.",
                     font=FONT_LABEL, fg="#555555", bg="#0d1b2a",
                     ).pack(side="left", padx=8)
            return
        for item in top:
            self._add_rec_card(item)

    def _add_rec_card(self, item: dict):
        has_news = bool(item.get("news_signals"))
        strat    = item.get("strategy", "FLIP")
        bg = CARD_NEWS_BG if has_news else CARD_BG

        card = tk.Frame(self._rec_cards_frame, bg=bg,
                        relief="solid", bd=1, width=200, height=110)
        card.pack(side="left", padx=4, pady=2)
        card.pack_propagate(False)

        top_row = tk.Frame(card, bg=bg)
        top_row.pack(fill="x", padx=6, pady=(5, 0))

        strat_color = STRAT_COLORS.get(strat, "#aaaaaa")
        tk.Label(top_row, text=f"[{strat}]", font=("Segoe UI", 8, "bold"),
                 fg=strat_color, bg=bg).pack(side="left")
        tk.Label(top_row, text=item.get("name", "")[:20],
                 font=FONT_LABEL, fg="white", bg=bg, anchor="w",
                 ).pack(side="left", padx=(4, 0))

        if has_news:
            tk.Label(top_row, text=" ★ ", font=FONT_LABEL,
                     fg="#2ecc71", bg="#0a3010").pack(side="right")

        score = item.get("score", 0)
        tk.Label(card, text=f"Score: {score:.0f}",
                 font=FONT_TITLE, fg=score_color(score), bg=bg, anchor="w",
                 ).pack(padx=6, anchor="w")

        price = item.get("current_low", 0)
        price_str = _fmt_gp(price)
        dfp = item.get("daily_flip_profit", 0) or 0
        detail = f"{price_str}  •  {_fmt_gp(int(dfp))}/day" if dfp > 0 else price_str
        tk.Label(card, text=detail, font=FONT_LABEL,
                 fg="#aaaaaa", bg=bg, anchor="w").pack(padx=6, anchor="w")

        tk.Label(card, text=item.get("reason", "")[:45],
                 font=("Segoe UI", 9), fg="#888888", bg=bg,
                 anchor="w", wraplength=185, justify="left",
                 ).pack(padx=6, pady=(0, 4), anchor="w")

        _bind_click(card, lambda _, r=item: self._on_row_click(r))

    # ------------------------------------------------------------------
    # Filter controls
    # ------------------------------------------------------------------

    def _build_controls(self):
        ctrl = ctk.CTkFrame(self)
        ctrl.pack(fill="x", padx=6, pady=(4, 2))

        ctk.CTkLabel(ctrl, text="Min Score:", font=FONT_LABEL).pack(side="left", padx=(4, 2))
        self._score_var = ctk.IntVar(value=config.DEFAULT_SCORE_THRESHOLD)
        ctk.CTkSlider(ctrl, from_=0, to=100, variable=self._score_var,
                      width=140, command=lambda _: self._apply_filters(),
                      ).pack(side="left", padx=2)
        self._score_label = ctk.CTkLabel(ctrl, text=str(self._score_var.get()),
                                         width=28, font=FONT_LABEL)
        self._score_label.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(ctrl, text="Search:", font=FONT_LABEL).pack(side="left", padx=(4, 2))
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(ctrl, textvariable=self._search_var, width=150).pack(side="left", padx=2)

        ctk.CTkLabel(ctrl, text="Max Price:", font=FONT_LABEL).pack(side="left", padx=(8, 2))
        self._max_price_var = ctk.StringVar(value="2000M")
        ctk.CTkEntry(ctrl, textvariable=self._max_price_var, width=80).pack(side="left", padx=2)

        ctk.CTkLabel(ctrl, text="Strategy:", font=FONT_LABEL).pack(side="left", padx=(8, 2))
        self._strat_var = ctk.StringVar(value="All")
        strat_menu = ctk.CTkOptionMenu(ctrl, variable=self._strat_var,
                                        values=["All", "FLIP", "MERCH", "TREND", "NEWS"],
                                        width=90, command=lambda _: self._apply_filters())
        strat_menu.pack(side="left", padx=2)

        ctk.CTkButton(ctrl, text="Apply", width=55,
                      command=self._apply_filters).pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _build_table(self):
        container = tk.Frame(self, bg="#1a1a2e")
        container.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        col_ids = [c[0] for c in TREE_COLS]
        self._tree = ttk.Treeview(container, columns=col_ids,
                                   show="tree headings",
                                   style="Dashboard.Treeview",
                                   selectmode="browse")

        self._tree.heading("#0", text="")
        self._tree.column("#0", width=36, minwidth=36, stretch=False, anchor="center")

        for col_id, label, width, anchor in TREE_COLS:
            stretch = (col_id == "reason")
            self._tree.heading(col_id, text=label,
                               command=lambda c=col_id: self._sort_by(c))
            self._tree.column(col_id, width=width, anchor=anchor,
                              minwidth=20, stretch=stretch)

        self._tree.tag_configure("news",   background="#0f2a10", foreground="#2ecc71")
        self._tree.tag_configure("normal", background="#1a1a2e", foreground="white")

        scrollbar = ttk.Scrollbar(container, orient="vertical",
                                  command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)

    # ------------------------------------------------------------------
    # Sorting / filtering
    # ------------------------------------------------------------------

    def _sort_by(self, col_id: str):
        if self._sort_col == col_id:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_id
            self._sort_asc = False
        self._render_rows(self._filtered_rows())

    def _apply_filters(self):
        self._score_label.configure(text=str(self._score_var.get()))
        self._render_rows(self._filtered_rows())

    def _filtered_rows(self) -> list[dict]:
        min_score  = self._score_var.get()
        search     = self._search_var.get().strip().lower()
        strat_filt = self._strat_var.get()
        max_price  = _parse_price(self._max_price_var.get(), config.BUDGET_MAX_GP)

        out = [
            r for r in self._rows
            if r.get("score", 0) >= min_score
            and (not search or search in r.get("name", "").lower())
            and r.get("current_low", 0) <= max_price
            and (strat_filt == "All" or r.get("strategy") == strat_filt)
        ]

        key_map = {
            "rank": None, "name": "name", "score": "score",
            "price": "current_low", "margin": "net_margin_pct",
            "flip_day": "daily_flip_profit",
            "slope7": "slope_7d", "slope90": "slope_90d",
            "rsi": "rsi", "volume": "avg_daily_vol",
            "strat": "strategy",
        }
        key = key_map.get(self._sort_col)
        if key:
            out.sort(key=lambda r: r.get(key, 0) or 0, reverse=not self._sort_asc)
        return out

    # ------------------------------------------------------------------
    # Rendering — NO HTTP calls here; icons only from memory cache
    # ------------------------------------------------------------------

    def _render_rows(self, rows: list[dict]):
        self._tree.delete(*self._tree.get_children())
        self._row_data.clear()

        for rank, row in enumerate(rows, 1):
            has_news = bool(row.get("news_signals"))
            item_id  = row.get("item_id", 0)
            score    = row.get("score", 0)
            s7       = row.get("slope_7d", 0) or 0
            s90      = row.get("slope_90d", 0) or 0
            strat    = row.get("strategy", "")
            dfp      = row.get("daily_flip_profit", 0) or 0
            nm_pct   = row.get("net_margin_pct", 0) or 0

            # Only use already-cached icons — never download in the render thread
            photo = self._icon_photos.get(item_id, "")

            name_text = ("★ " if has_news else "") + row.get("name", "")
            values = (
                rank,
                name_text,
                strat,
                f"{score:.0f}",
                f"{row.get('current_low', 0):,.0f}",
                f"{nm_pct:.1f}%",
                _fmt_gp(int(dfp)) if dfp > 0 else "",
                f"{s7:+.1f}%",
                f"{s90:+.1f}%",
                f"{row.get('rsi', 50):.0f}",
                f"{row.get('avg_daily_vol', 0):,.0f}",
                row.get("reason", ""),
            )
            tag = "news" if has_news else "normal"
            iid = self._tree.insert("", "end", image=photo,
                                    values=values, tags=(tag,))
            self._row_data[iid] = row

    def _on_tree_click(self, event):
        iid = self._tree.identify_row(event.y)
        if iid and iid in self._row_data:
            self._on_row_click(self._row_data[iid])

    def _on_row_click(self, row: dict):
        if self.on_chart_select:
            self.on_chart_select(row.get("item_id"), row.get("name", ""))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_scores(self, scored_items: list[dict]):
        self._rows = scored_items
        self._update_recommendations(scored_items)
        self._apply_filters()
        # Load icons in background after render — non-blocking
        threading.Thread(target=self._load_icons_bg,
                         args=(scored_items[:100],), daemon=True).start()

    def reload(self):
        self._apply_filters()

    def set_icon_urls(self, icon_urls: dict[int, str]):
        self._icon_urls = icon_urls

    def _load_icons_bg(self, items: list[dict]):
        """Download icons in background; re-render once a batch is ready."""
        loaded = 0
        for item in items:
            item_id  = item.get("item_id", 0)
            if item_id in self._icon_photos:
                continue
            icon_url = self._icon_urls.get(item_id)
            if not icon_url:
                continue
            photo = get_icon_photo(item_id, icon_url, 24)
            if photo:
                self._icon_photos[item_id] = photo
                loaded += 1
            if loaded > 0 and loaded % 20 == 0:
                # Re-render every 20 icons so user sees them appear gradually
                self.after(0, lambda: self._render_rows(self._filtered_rows()))
        if loaded > 0:
            self.after(0, lambda: self._render_rows(self._filtered_rows()))


# ------------------------------------------------------------------

def _bind_click(widget, handler):
    widget.bind("<Button-1>", handler)
    for child in widget.winfo_children():
        _bind_click(child, handler)


def _fmt_gp(gp: int) -> str:
    if gp >= 1_000_000_000:
        return f"{gp/1_000_000_000:.2f}B"
    if gp >= 1_000_000:
        return f"{gp/1_000_000:.1f}M"
    if gp >= 1_000:
        return f"{gp/1_000:.0f}k"
    return str(gp)


def _parse_price(text: str, default: int) -> int:
    """Parse price strings like '50M', '1.5B', '500k', '50'."""
    t = text.strip().upper()
    try:
        if t.endswith("B"):
            return int(float(t[:-1]) * 1_000_000_000)
        if t.endswith("M"):
            return int(float(t[:-1]) * 1_000_000)
        if t.endswith("K"):
            return int(float(t[:-1]) * 1_000)
        return int(float(t) * 1_000_000)  # bare number assumed millions
    except (ValueError, IndexError):
        return default
