import customtkinter as ctk
from gui.styles import score_color, trend_color, FONT_LABEL, FONT_TITLE
import config


COLUMNS = [
    ("Rank",       50),
    ("Item",       200),
    ("Score",      60),
    ("Price (low)", 110),
    ("Margin %",   80),
    ("30d",        70),
    ("90d",        70),
    ("RSI",        55),
    ("Volume",     80),
    ("Buy Limit",  80),
    ("Reason",     200),
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

        self._build_controls()
        self._build_table()

    def _build_controls(self):
        ctrl = ctk.CTkFrame(self)
        ctrl.pack(fill="x", padx=6, pady=4)

        ctk.CTkLabel(ctrl, text="Min Score:", font=FONT_LABEL).pack(side="left", padx=(4, 2))
        self._score_var = ctk.IntVar(value=config.DEFAULT_SCORE_THRESHOLD)
        self._score_slider = ctk.CTkSlider(
            ctrl, from_=0, to=100, variable=self._score_var,
            width=150, command=lambda _: self._apply_filters(),
        )
        self._score_slider.pack(side="left", padx=2)
        self._score_label = ctk.CTkLabel(ctrl, text=str(self._score_var.get()), width=30,
                                         font=FONT_LABEL)
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

    def _build_table(self):
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=6)
        for col, width in COLUMNS:
            btn = ctk.CTkButton(
                header, text=col, width=width, height=26,
                font=FONT_TITLE,
                command=lambda c=col: self._sort_by(c),
            )
            btn.pack(side="left", padx=1)

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

        score   = row.get("score", 0)
        s30     = row.get("slope_30d", 0) or 0
        s90     = row.get("slope_90d", 0) or 0

        def cell(text, width, fg=None):
            lbl = ctk.CTkLabel(frame, text=str(text), width=width,
                               font=FONT_LABEL, text_color=fg or "white",
                               anchor="e")
            lbl.pack(side="left", padx=1)
            return lbl

        cell(rank,                        COLUMNS[0][1])
        name_lbl = ctk.CTkLabel(frame, text=row.get("name", ""),
                                width=COLUMNS[1][1], font=FONT_LABEL, anchor="w")
        name_lbl.pack(side="left", padx=1)
        name_lbl.bind("<Button-1>", lambda _, r=row: self._on_row_click(r))

        cell(f"{score:.0f}",              COLUMNS[2][1], fg=score_color(score))
        cell(f"{row.get('current_low',0):,.0f}", COLUMNS[3][1])
        cell(f"{row.get('margin_pct',0):.1f}%",  COLUMNS[4][1])
        cell(f"{s30:+.2f}%",              COLUMNS[5][1], fg=trend_color(s30))
        cell(f"{s90:+.2f}%",              COLUMNS[6][1], fg=trend_color(s90))
        cell(f"{row.get('rsi',50):.0f}",  COLUMNS[7][1])
        cell(f"{row.get('avg_daily_vol',0):,.0f}", COLUMNS[8][1])
        cell(row.get("buy_limit", "?"),   COLUMNS[9][1])
        reason_lbl = ctk.CTkLabel(frame, text=row.get("reason", ""),
                                  width=COLUMNS[10][1], font=FONT_LABEL,
                                  anchor="w", text_color="#aaaaaa")
        reason_lbl.pack(side="left", padx=2)

    def _on_row_click(self, row: dict):
        if self.on_chart_select:
            self.on_chart_select(row.get("item_id"), row.get("name", ""))

    def load_scores(self, scored_items: list[dict]):
        self._rows = scored_items
        self._apply_filters()

    def reload(self):
        self._apply_filters()
