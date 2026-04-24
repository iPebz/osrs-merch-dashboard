import tkinter as tk
import customtkinter as ctk
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import pandas as pd
import logging
from analysis.trend_analyzer import to_dataframe, moving_average, rsi as calc_rsi
from gui.styles import FONT_LABEL, FONT_TITLE

log = logging.getLogger(__name__)

RANGE_DAYS = {"30d": 30, "90d": 90, "180d": 180, "All": None}

BG        = "#1a1a2e"
PLOT_BG   = "#0f3460"
SPINE_COL = "#444444"


class ChartTab(ctk.CTkFrame):
    def __init__(self, parent, db_conn):
        super().__init__(parent)
        self.db = db_conn
        self._item_id: int | None = None
        self._item_name: str = ""
        self._timeseries: list[dict] = []
        self._range = "90d"

        self._build_controls()
        self._build_canvas()

    def _build_controls(self):
        ctrl = ctk.CTkFrame(self)
        ctrl.pack(fill="x", padx=6, pady=4)

        self._title_var = ctk.StringVar(value="Select an item from the Dashboard")
        ctk.CTkLabel(ctrl, textvariable=self._title_var,
                     font=FONT_TITLE).pack(side="left", padx=6)

        for label in RANGE_DAYS:
            ctk.CTkButton(
                ctrl, text=label, width=55,
                command=lambda l=label: self._set_range(l),
            ).pack(side="right", padx=2)

    def _build_canvas(self):
        # Use a plain tk.Frame — avoids CTK canvas-in-canvas layering issues on Windows
        self._canvas_host = tk.Frame(self, bg=BG)
        self._canvas_host.pack(fill="both", expand=True, padx=6, pady=4)

        self._fig = Figure(facecolor=BG)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self._canvas_host)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvas.get_tk_widget().configure(bg=BG)

        # Show placeholder until an item is selected
        self._show_placeholder("Select an item from the Dashboard to view its chart.")

    def _set_range(self, label: str):
        self._range = label
        if self._timeseries:
            self._draw_chart()

    def load_item(self, item_id: int, item_name: str, timeseries: list[dict]):
        self._item_id    = item_id
        self._item_name  = item_name
        self._timeseries = timeseries
        self._title_var.set(item_name)
        self._draw_chart()

    # ------------------------------------------------------------------

    def _show_placeholder(self, message: str):
        self._fig.clear()
        self._fig.patch.set_facecolor(BG)
        ax = self._fig.add_subplot(111)
        ax.set_facecolor(BG)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.text(0.5, 0.5, message, ha="center", va="center",
                color="#555555", fontsize=12, transform=ax.transAxes)
        self._canvas.draw()

    def _draw_chart(self):
        self._fig.clear()
        self._fig.patch.set_facecolor(BG)

        try:
            df = to_dataframe(self._timeseries)
        except Exception as e:
            log.error("to_dataframe failed: %s", e)
            self._show_placeholder(f"Data error: {e}")
            return

        if df.empty or len(df) < 2:
            self._show_placeholder(
                f"Not enough price history for {self._item_name}.\n"
                "Try clicking it from the Charts tab after Fetch News or refreshing."
            )
            return

        days = RANGE_DAYS[self._range]
        if days:
            df = df.tail(days).reset_index(drop=True)

        dates = df["timestamp"]

        try:
            gs = self._fig.add_gridspec(3, 1, height_ratios=[4, 1, 1], hspace=0.05)
            ax_price = self._fig.add_subplot(gs[0])
            ax_vol   = self._fig.add_subplot(gs[1], sharex=ax_price)
            ax_rsi   = self._fig.add_subplot(gs[2], sharex=ax_price)

            for ax in (ax_price, ax_vol, ax_rsi):
                ax.set_facecolor(PLOT_BG)
                ax.tick_params(colors="white", labelsize=8)
                for spine in ax.spines.values():
                    spine.set_edgecolor(SPINE_COL)

            # Price band + moving averages
            ax_price.fill_between(dates, df["low"], df["high"],
                                  alpha=0.3, color="#5dade2", label="High/Low")
            ax_price.plot(dates, df["mid"], color="#5dade2", linewidth=1, label="Mid")

            ma30 = moving_average(df, 30)
            ma90 = moving_average(df, 90)
            ax_price.plot(dates, ma30, color="#f39c12", linewidth=1.2,
                          linestyle="--", label="MA30")
            ax_price.plot(dates, ma90, color="#e74c3c", linewidth=1.2,
                          linestyle="--", label="MA90")

            ax_price.set_ylabel("Price (gp)", color="white", fontsize=9)
            ax_price.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6
                                  else f"{x/1e3:.0f}k"))
            ax_price.legend(fontsize=7, loc="upper left",
                            facecolor="#1a1a2e", labelcolor="white")
            ax_price.set_title(self._item_name, color="white", fontsize=11)

            # Volume
            ax_vol.bar(dates, df["total_vol"], color="#5dade2", alpha=0.6, width=0.8)
            ax_vol.set_ylabel("Volume", color="white", fontsize=8)
            ax_vol.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, _: f"{x/1e3:.0f}k"))

            # RSI (computed incrementally so all points are visible)
            rsi_vals = pd.Series(index=df.index, dtype=float)
            for i in range(len(df)):
                rsi_vals.iloc[i] = calc_rsi(df.iloc[:i + 1])
            ax_rsi.plot(dates, rsi_vals, color="#e67e22", linewidth=1)
            ax_rsi.axhline(70, color="#e74c3c", linewidth=0.8, linestyle="--")
            ax_rsi.axhline(30, color="#2ecc71", linewidth=0.8, linestyle="--")
            ax_rsi.set_ylim(0, 100)
            ax_rsi.set_ylabel("RSI", color="white", fontsize=8)

            ax_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_rsi.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax_price.get_xticklabels(), visible=False)
            plt.setp(ax_vol.get_xticklabels(), visible=False)

            self._fig.tight_layout(pad=0.5)
            self._canvas.draw()

        except Exception as e:
            log.error("Chart render error for %s: %s", self._item_name, e, exc_info=True)
            self._show_placeholder(f"Chart render error: {e}")
