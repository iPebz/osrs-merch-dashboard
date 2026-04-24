import tkinter as tk
import tkinter.ttk as ttk
import customtkinter as ctk
from gui.styles import score_color, trend_color, FONT_LABEL, FONT_TITLE
import config

TREE_COLS = [
    ("rank",      "Rank",        50,  "e"),
    ("name",      "Item",       200,  "w"),
    ("score",     "Score",       60,  "e"),
    ("price",     "Price (low)", 110, "e"),
    ("margin",    "Margin %",    80,  "e"),
    ("slope30",   "30d",         70,  "e"),
    ("slope90",   "90d",         70,  "e"),
    ("rsi",       "RSI",         55,  "e"),
    ("volume",    "Volume",      80,  "e"),
    ("buylimit",  "Buy Limit",   80,  "e"),
    ("reason",    "Reason",     240,  "w"),
]

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

        _style_treeview()
        self._build_recommendations()
        self._build_controls()
        self._build_table()

    # ------------------------------------------------------------------
    # TOP PICKS panel (using plain tk widgets for reliable rendering)
    # ------------------------------------------------------------------

    def _build_recommendations(self):
        self._rec_outer = tk.Frame(self, bg="#0d1b2a", relief="flat")
        self._rec_outer.pack(fill="x", padx=6, pady=(6, 2))

        tk.Label(
            self._rec_outer, text="TOP PICKS",
            font=FONT_TITLE, fg="#f39c12", bg="#0d1b2a",
        ).pack(side="left", padx=(10, 6), pady=8)

        self._rec_cards_frame = tk.Frame(self._rec_outer, bg="#0d1b2a")
        self._rec_cards_frame.pack(side="left", fill="x", expand=True, pady=4)

        self._rec_placeholder = tk.Label(
            self._rec_cards_frame,
            text='Press "Score All Items" to generate recommendations.',
            font=FONT_LABEL, fg="#555555", bg="#0d1b2a",
        )
        self._rec_placeholder.pack(side="left", padx=8)

    def _update_recommendations(self, scored_items: list[dict]):
        for w in self._rec_cards_frame.winfo_children():
            w.destroy()

        top = [r for r in scored_items if r.get("score", 0) >= 50][:5]
        if not top:
            tk.Label(
                self._rec_cards_frame,
                text="No items scored above 50 yet.",
                font=FONT_LABEL, fg="#555555", bg="#0d1b2a",
            ).pack(side="left", padx=8)
            return

        for item in top:
            self._add_rec_card(item)

    def _add_rec_card(self, item: dict):
        has_news = bool(item.get("news_signals"))
        bg = CARD_NEWS_BG if has_news else CARD_BG

        card = tk.Frame(
            self._rec_cards_frame, bg=bg,
            relief="solid", bd=1, width=190, height=105,
        )
        card.pack(side="left", padx=4, pady=2)
        card.pack_propagate(False)

        # Name + optional NEWS badge
        top_row = tk.Frame(card, bg=bg)
        top_row.pack(fill="x", padx=6, pady=(5, 0))

        tk.Label(
            top_row, text=item.get("name", "")[:22],
            font=FONT_LABEL, fg="white", bg=bg, anchor="w",
        ).pack(side="left")

        if has_news:
            tk.Label(
                top_row, text=" NEWS ",
                font=FONT_LABEL, fg="#2ecc71", bg="#0a3010",
            ).pack(side="right")

        score = item.get("score", 0)
        tk.Label(
            card, text=f"Score: {score:.0f}",
            font=FONT_TITLE, fg=score_color(score), bg=bg, anchor="w",
        ).pack(padx=6, anchor="w")

        price = item.get("current_low", 0)
        price_str = f"{price/1e6:.2f}M" if price >= 1e6 else f"{price/1e3:.0f}k"
        tk.Label(
            card, text=price_str,
            font=FONT_LABEL, fg="#aaaaaa", bg=bg, anchor="w",
        ).pack(padx=6, anchor="w")

        tk.Label(
            card, text=item.get("reason", "")[:42],
            font=FONT_LABEL, fg="#888888", bg=bg,
            anchor="w", wraplength=175, justify="left",
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
        ctk.CTkSlider(
            ctrl, from_=0, to=100, variable=self._score_var,
            width=150, command=lambda _: self._apply_filters(),
        ).pack(side="left", padx=2)
        self._score_label = ctk.CTkLabel(ctrl, text=str(self._score_var.get()),
                                         width=30, font=FONT_LABEL)
        self._score_label.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(ctrl, text="Search:", font=FONT_LABEL).pack(side="left", padx=(4, 2))
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(ctrl, textvariable=self._search_var, width=160).pack(side="left", padx=2)

        ctk.CTkLabel(ctrl, text="Max Price (M):", font=FONT_LABEL).pack(side="left", padx=(10, 2))
        self._max_price_var = ctk.StringVar(value="50")
        ctk.CTkEntry(ctrl, textvariable=self._max_price_var, width=60).pack(side="left", padx=2)

        ctk.CTkButton(ctrl, text="Apply", width=60,
                      command=self._apply_filters).pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Table (ttk.Treeview — reliable text rendering on all Windows configs)
    # ------------------------------------------------------------------

    def _build_table(self):
        container = tk.Frame(self, bg="#1a1a2e")
        container.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        col_ids = [c[0] for c in TREE_COLS]
        self._tree = ttk.Treeview(
            container,
            columns=col_ids,
            show="headings",
            style="Dashboard.Treeview",
            selectmode="browse",
        )

        for col_id, label, width, anchor in TREE_COLS:
            stretch = (col_id == "reason")
            self._tree.heading(col_id, text=label,
                               command=lambda c=col_id: self._sort_by(c))
            self._tree.column(col_id, width=width, anchor=anchor,
                              minwidth=20, stretch=stretch)

        self._tree.tag_configure("news",
            background="#0f2a10", foreground="#2ecc71")
        self._tree.tag_configure("normal",
            background="#1a1a2e", foreground="white")

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
        min_score = self._score_var.get()
        search    = self._search_var.get().strip().lower()
        try:
            max_price = float(self._max_price_var.get()) * 1_000_000
        except ValueError:
            max_price = config.BUDGET_MAX_GP

        out = [
            r for r in self._rows
            if r.get("score", 0) >= min_score
            and (not search or search in r.get("name", "").lower())
            and r.get("current_low", 0) <= max_price
        ]

        key_map = {
            "rank": None, "name": "name", "score": "score",
            "price": "current_low", "margin": "margin_pct",
            "slope30": "slope_30d", "slope90": "slope_90d",
            "rsi": "rsi", "volume": "avg_daily_vol", "buylimit": "buy_limit",
        }
        key = key_map.get(self._sort_col)
        if key:
            out.sort(key=lambda r: r.get(key, 0) or 0, reverse=not self._sort_asc)
        return out

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_rows(self, rows: list[dict]):
        self._tree.delete(*self._tree.get_children())
        self._row_data.clear()

        for rank, row in enumerate(rows, 1):
            has_news = bool(row.get("news_signals"))
            s30 = row.get("slope_30d", 0) or 0
            s90 = row.get("slope_90d", 0) or 0
            score = row.get("score", 0)

            name_text = ("★ " if has_news else "") + row.get("name", "")
            values = (
                rank,
                name_text,
                f"{score:.0f}",
                f"{row.get('current_low', 0):,.0f}",
                f"{row.get('margin_pct', 0):.1f}%",
                f"{s30:+.2f}%",
                f"{s90:+.2f}%",
                f"{row.get('rsi', 50):.0f}",
                f"{row.get('avg_daily_vol', 0):,.0f}",
                str(row.get("buy_limit", "?")),
                row.get("reason", ""),
            )
            tag = "news" if has_news else "normal"
            iid = self._tree.insert("", "end", values=values, tags=(tag,))
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

    def reload(self):
        self._apply_filters()


def _bind_click(widget, handler):
    widget.bind("<Button-1>", handler)
    for child in widget.winfo_children():
        _bind_click(child, handler)
