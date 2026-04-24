import customtkinter as ctk
from gui.styles import score_color, trend_color, FONT_LABEL, FONT_TITLE
import config

COLUMNS = [
    ("Rank",        50),
    ("Item",       200),
    ("Score",       60),
    ("Price (low)", 110),
    ("Margin %",    80),
    ("30d",         70),
    ("90d",         70),
    ("RSI",         55),
    ("Volume",      80),
    ("Buy Limit",   80),
    ("Reason",     240),
]


class DashboardTab(ctk.CTkFrame):
    def __init__(self, parent, db_conn, data_service, on_chart_select=None):
        super().__init__(parent)
        self.db = db_conn
        self.data_service = data_service
        self.on_chart_select = on_chart_select
        self._rows: list[dict] = []
        self._sort_col = "Score"
        self._sort_asc = False

        self._build_recommendations()
        self._build_controls()
        self._build_table()

    # ------------------------------------------------------------------
    # Recommendations panel
    # ------------------------------------------------------------------

    def _build_recommendations(self):
        outer = ctk.CTkFrame(self, fg_color="#0d1b2a", corner_radius=8)
        outer.pack(fill="x", padx=6, pady=(6, 2))

        ctk.CTkLabel(
            outer, text="TOP PICKS", font=FONT_TITLE,
            text_color="#f39c12",
        ).pack(side="left", padx=(10, 6), pady=6)

        self._rec_cards_frame = ctk.CTkFrame(outer, fg_color="transparent")
        self._rec_cards_frame.pack(side="left", fill="x", expand=True, pady=4)

        self._rec_placeholder = ctk.CTkLabel(
            self._rec_cards_frame,
            text='Click "Score All Items" to generate recommendations.',
            font=FONT_LABEL, text_color="#555555",
        )
        self._rec_placeholder.pack(side="left", padx=8)

    def _update_recommendations(self, scored_items: list[dict]):
        for w in self._rec_cards_frame.winfo_children():
            w.destroy()

        top = [r for r in scored_items if r.get("score", 0) >= 50][:5]
        if not top:
            ctk.CTkLabel(
                self._rec_cards_frame,
                text="No items above score 50 yet.",
                font=FONT_LABEL, text_color="#555555",
            ).pack(side="left", padx=8)
            return

        for item in top:
            self._add_rec_card(item)

    def _add_rec_card(self, item: dict):
        has_news = bool(item.get("news_signals"))
        card_bg  = "#0f2a0f" if has_news else "#16213e"

        card = ctk.CTkFrame(
            self._rec_cards_frame,
            fg_color=card_bg, corner_radius=8, width=185,
        )
        card.pack(side="left", padx=4, pady=2)
        card.pack_propagate(False)

        # Name row + optional NEWS badge
        name_row = ctk.CTkFrame(card, fg_color="transparent")
        name_row.pack(fill="x", padx=6, pady=(5, 0))

        name = item.get("name", "")
        ctk.CTkLabel(
            name_row, text=name[:20], font=FONT_LABEL,
            text_color="white", anchor="w",
        ).pack(side="left")

        if has_news:
            ctk.CTkLabel(
                name_row, text=" NEWS ", font=FONT_LABEL,
                text_color="#2ecc71", fg_color="#0a2a0a",
                corner_radius=4,
            ).pack(side="right")

        # Score
        score = item.get("score", 0)
        ctk.CTkLabel(
            card, text=f"Score: {score:.0f}",
            font=FONT_TITLE, text_color=score_color(score),
        ).pack(padx=6, anchor="w")

        # Price
        price = item.get("current_low", 0)
        price_str = f"{price/1e6:.2f}M" if price >= 1e6 else f"{price/1e3:.0f}k"
        ctk.CTkLabel(
            card, text=price_str, font=FONT_LABEL, text_color="#aaaaaa",
        ).pack(padx=6, anchor="w")

        # Reason snippet
        reason = item.get("reason", "")
        ctk.CTkLabel(
            card, text=reason[:45], font=FONT_LABEL,
            text_color="#777777", wraplength=170, anchor="w",
        ).pack(padx=6, pady=(0, 5), anchor="w")

        # Make the whole card clickable
        for widget in [card] + card.winfo_children() + \
                       [w for row in card.winfo_children()
                        for w in (row.winfo_children()
                                  if hasattr(row, "winfo_children") else [])]:
            widget.bind("<Button-1>", lambda _, r=item: self._on_row_click(r))

    # ------------------------------------------------------------------
    # Filter controls
    # ------------------------------------------------------------------

    def _build_controls(self):
        ctrl = ctk.CTkFrame(self)
        ctrl.pack(fill="x", padx=6, pady=4)

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
    # Table
    # ------------------------------------------------------------------

    def _build_table(self):
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=6)
        for col, width in COLUMNS:
            ctk.CTkButton(
                header, text=col, width=width, height=26,
                font=FONT_TITLE,
                command=lambda c=col: self._sort_by(c),
            ).pack(side="left", padx=1)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=6, pady=4)

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
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
            "Rank": None, "Item": "name", "Score": "score",
            "Price (low)": "current_low", "Margin %": "margin_pct",
            "30d": "slope_30d", "90d": "slope_90d", "RSI": "rsi",
            "Volume": "avg_daily_vol", "Buy Limit": "buy_limit",
        }
        key = key_map.get(self._sort_col)
        if key:
            out.sort(key=lambda r: r.get(key, 0) or 0, reverse=not self._sort_asc)
        return out

    def _render_rows(self, rows: list[dict]):
        for widget in self._scroll.winfo_children():
            widget.destroy()
        for rank, row in enumerate(rows, 1):
            self._add_row(rank, row)

    def _add_row(self, rank: int, row: dict):
        frame = ctk.CTkFrame(self._scroll, height=28)
        frame.pack(fill="x", pady=1)

        score = row.get("score", 0)
        s30   = row.get("slope_30d", 0) or 0
        s90   = row.get("slope_90d", 0) or 0

        has_news = bool(row.get("news_signals"))
        if has_news:
            frame.configure(fg_color="#0f2a0f")

        def cell(text, width, fg=None):
            lbl = ctk.CTkLabel(frame, text=str(text), width=width,
                               font=FONT_LABEL, text_color=fg or "white",
                               anchor="e")
            lbl.pack(side="left", padx=1)
            return lbl

        cell(rank,                               COLUMNS[0][1])

        name_lbl = ctk.CTkLabel(frame, text=row.get("name", ""),
                                width=COLUMNS[1][1], font=FONT_LABEL, anchor="w")
        name_lbl.pack(side="left", padx=1)
        name_lbl.bind("<Button-1>", lambda _, r=row: self._on_row_click(r))

        cell(f"{score:.0f}",                     COLUMNS[2][1], fg=score_color(score))
        cell(f"{row.get('current_low',0):,.0f}", COLUMNS[3][1])
        cell(f"{row.get('margin_pct',0):.1f}%",  COLUMNS[4][1])
        cell(f"{s30:+.2f}%",                     COLUMNS[5][1], fg=trend_color(s30))
        cell(f"{s90:+.2f}%",                     COLUMNS[6][1], fg=trend_color(s90))
        cell(f"{row.get('rsi',50):.0f}",         COLUMNS[7][1])
        cell(f"{row.get('avg_daily_vol',0):,.0f}", COLUMNS[8][1])
        cell(row.get("buy_limit", "?"),          COLUMNS[9][1])

        reason_text = ("* " if has_news else "") + row.get("reason", "")
        ctk.CTkLabel(
            frame, text=reason_text,
            width=COLUMNS[10][1], font=FONT_LABEL, anchor="w",
            text_color="#2ecc71" if has_news else "#aaaaaa",
        ).pack(side="left", padx=2)

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
