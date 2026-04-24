import customtkinter as ctk
import threading
import logging
from gui.dashboard_tab import DashboardTab
from gui.chart_tab import ChartTab
from gui.watchlist_tab import WatchlistTab
from gui.recommendations_tab import RecommendationsTab
from gui.styles import FONT_LABEL

log = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

AUTO_RESCORE_REFRESHES = 5


class App(ctk.CTk):
    def __init__(self, db_conn, data_service):
        super().__init__()
        self.title("OSRS GE Merching Dashboard")
        self.geometry("1380x860")
        self.minsize(1024, 600)

        self.db           = db_conn
        self.data_service = data_service
        self._refresh_count = 0

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        self.tabs.add("Dashboard")
        self.tabs.add("Charts")
        self.tabs.add("Watchlist")
        self.tabs.add("Recommendations")

        self.dashboard = DashboardTab(
            self.tabs.tab("Dashboard"), db_conn, data_service,
            on_chart_select=self._open_chart,
        )
        self.dashboard.pack(fill="both", expand=True)

        self.charts = ChartTab(self.tabs.tab("Charts"), db_conn)
        self.charts.pack(fill="both", expand=True)

        self.watchlist = WatchlistTab(
            self.tabs.tab("Watchlist"), db_conn, data_service)
        self.watchlist.pack(fill="both", expand=True)

        self.recommendations = RecommendationsTab(
            self.tabs.tab("Recommendations"), db_conn)
        self.recommendations.pack(fill="both", expand=True)

        # Bottom bar
        bottom = ctk.CTkFrame(self, height=36)
        bottom.pack(fill="x", padx=10, pady=4)

        self._status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(bottom, textvariable=self._status_var,
                     font=FONT_LABEL, anchor="w").pack(side="left", padx=8)

        ctk.CTkButton(bottom, text="Refresh Prices", width=130,
                      command=self._refresh).pack(side="right", padx=8)
        ctk.CTkButton(bottom, text="Score All Items", width=130,
                      command=self._score_all).pack(side="right", padx=4)
        ctk.CTkButton(bottom, text="Fetch News", width=110,
                      fg_color="#1a4a1a", hover_color="#2a6a2a",
                      command=self._fetch_news).pack(side="right", padx=4)

        # Load icon URLs once so dashboard & recommendations can use them
        self.after(200, self._load_icon_urls)
        # Auto-score on startup once the window is ready
        self.after(500, self._score_all)

    # ------------------------------------------------------------------

    def _load_icon_urls(self):
        threading.Thread(target=self._do_load_icon_urls, daemon=True).start()

    def _do_load_icon_urls(self):
        try:
            urls = self.data_service.get_item_icon_urls()
            self.after(0, lambda: self.dashboard.set_icon_urls(urls))
            self.after(0, lambda: setattr(self.recommendations, "_item_icon_urls", urls))
        except Exception as e:
            log.error("Icon URL load failed: %s", e)

    def _refresh(self):
        self._status_var.set("Fetching latest prices…")
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            self.data_service.refresh_latest()
            self._refresh_count += 1
            self.after(0, lambda: self._status_var.set("Prices updated."))
            self.after(0, self.watchlist.reload)
            if self._refresh_count % AUTO_RESCORE_REFRESHES == 0:
                log.info("Auto re-score triggered after %d refreshes.", self._refresh_count)
                self.after(0, self._score_all)
        except Exception as e:
            log.error("Refresh failed: %s", e)
            self.after(0, lambda: self._status_var.set(f"Refresh failed: {e}"))

    def _score_all(self):
        self._status_var.set("Scoring items… (this may take a moment)")
        threading.Thread(target=self._do_score_all, daemon=True).start()

    def _do_score_all(self):
        try:
            results = self.data_service.score_all_items()
            icon_urls = self.data_service.get_item_icon_urls()
            self.after(0, lambda: self.dashboard.load_scores(results))
            self.after(0, lambda: self.recommendations.update_recommendations(
                results, icon_urls))
            self.after(0, lambda: self._status_var.set(
                f"Scored {len(results)} items. Showing top results."))
        except Exception as e:
            log.error("Scoring failed: %s", e)
            self.after(0, lambda: self._status_var.set(f"Scoring failed: {e}"))

    def _fetch_news(self):
        self._status_var.set("Fetching OSRS news and GE market data…")
        threading.Thread(target=self._do_fetch_news, daemon=True).start()

    def _do_fetch_news(self):
        try:
            summary = self.data_service.fetch_and_store_news()
            msg = (f"News: {summary['news']} item signals, "
                   f"{summary['movers']} GE movers. "
                   f"Re-score to apply.")
            self.after(0, lambda: self._status_var.set(msg))
        except Exception as e:
            log.error("News fetch failed: %s", e)
            self.after(0, lambda: self._status_var.set(f"News fetch failed: {e}"))

    def _open_chart(self, item_id: int, item_name: str):
        self._status_var.set(f"Loading chart for {item_name}…")
        self.tabs.set("Charts")
        threading.Thread(
            target=self._do_load_chart,
            args=(item_id, item_name),
            daemon=True,
        ).start()

    def _do_load_chart(self, item_id: int, item_name: str):
        try:
            ts = self.data_service.get_timeseries_for_item(item_id)
            self.after(0, lambda: self.charts.load_item(item_id, item_name, ts))
            self.after(0, lambda: self._status_var.set(f"Chart loaded: {item_name}"))
        except Exception as e:
            log.error("Chart load failed: %s", e)
            self.after(0, lambda: self._status_var.set(f"Chart failed: {e}"))
