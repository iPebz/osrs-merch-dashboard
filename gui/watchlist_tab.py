import customtkinter as ctk
import logging
from database.queries import (
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    get_recent_alerts, get_all_items,
)
from gui.styles import FONT_LABEL, FONT_TITLE

log = logging.getLogger(__name__)


class WatchlistTab(ctk.CTkFrame):
    def __init__(self, parent, db_conn, data_service):
        super().__init__(parent)
        self.db = db_conn
        self.data_service = data_service

        self._build_add_section()
        self._build_watchlist_section()
        self._build_alerts_log()

    # ------------------------------------------------------------------
    # Add item section
    # ------------------------------------------------------------------

    def _build_add_section(self):
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=6, pady=4)

        ctk.CTkLabel(frame, text="Add to Watchlist", font=FONT_TITLE).pack(anchor="w", padx=6)

        row = ctk.CTkFrame(frame)
        row.pack(fill="x", padx=4, pady=4)

        ctk.CTkLabel(row, text="Item name:", font=FONT_LABEL).pack(side="left", padx=4)
        self._add_search = ctk.CTkEntry(row, width=200, placeholder_text="e.g. Abyssal whip")
        self._add_search.pack(side="left", padx=4)

        ctk.CTkLabel(row, text="Buy below:", font=FONT_LABEL).pack(side="left", padx=4)
        self._buy_below = ctk.CTkEntry(row, width=100, placeholder_text="gp")
        self._buy_below.pack(side="left", padx=4)

        ctk.CTkLabel(row, text="Sell above:", font=FONT_LABEL).pack(side="left", padx=4)
        self._sell_above = ctk.CTkEntry(row, width=100, placeholder_text="gp")
        self._sell_above.pack(side="left", padx=4)

        ctk.CTkButton(row, text="Add", width=60,
                      command=self._add_item).pack(side="left", padx=6)
        self._add_status = ctk.CTkLabel(row, text="", font=FONT_LABEL,
                                        text_color="#aaa")
        self._add_status.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Watchlist table
    # ------------------------------------------------------------------

    def _build_watchlist_section(self):
        ctk.CTkLabel(self, text="Watched Items", font=FONT_TITLE).pack(
            anchor="w", padx=10, pady=(8, 0))

        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=6)
        for text, width in [("Item", 200), ("Buy Below", 110), ("Sell Above", 110),
                             ("Notes", 200), ("", 80)]:
            ctk.CTkLabel(header, text=text, width=width, font=FONT_TITLE,
                         anchor="w").pack(side="left", padx=2)

        self._wl_scroll = ctk.CTkScrollableFrame(self, height=180)
        self._wl_scroll.pack(fill="x", padx=6, pady=2)

    # ------------------------------------------------------------------
    # Alerts log
    # ------------------------------------------------------------------

    def _build_alerts_log(self):
        ctk.CTkLabel(self, text="Recent Alerts", font=FONT_TITLE).pack(
            anchor="w", padx=10, pady=(8, 0))

        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=6)
        for text, width in [("Time", 150), ("Item", 200), ("Type", 60),
                             ("Price", 110), ("Threshold", 110)]:
            ctk.CTkLabel(header, text=text, width=width, font=FONT_TITLE,
                         anchor="w").pack(side="left", padx=2)

        self._alerts_scroll = ctk.CTkScrollableFrame(self, height=160)
        self._alerts_scroll.pack(fill="both", expand=True, padx=6, pady=4)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_item(self):
        name = self._add_search.get().strip()
        if not name:
            self._add_status.configure(text="Enter item name.")
            return

        items = get_all_items(self.db)
        match = next((i for i in items if i["name"].lower() == name.lower()), None)
        if not match:
            # fuzzy first match
            match = next((i for i in items if name.lower() in i["name"].lower()), None)
        if not match:
            self._add_status.configure(text=f"Item '{name}' not found in DB.")
            return

        def _parse_gp(entry: ctk.CTkEntry):
            val = entry.get().strip().replace(",", "").replace("k", "000").replace("m", "000000")
            return int(val) if val.isdigit() or (val.lstrip("-").isdigit()) else None

        buy_below  = _parse_gp(self._buy_below)
        sell_above = _parse_gp(self._sell_above)

        add_to_watchlist(self.db, match["id"], buy_below, sell_above)
        self._add_status.configure(text=f"Added: {match['name']}")
        self._add_search.delete(0, "end")
        self._buy_below.delete(0, "end")
        self._sell_above.delete(0, "end")
        self._render_watchlist()

    def _remove_item(self, item_id: int):
        remove_from_watchlist(self.db, item_id)
        self._render_watchlist()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_watchlist(self):
        for w in self._wl_scroll.winfo_children():
            w.destroy()

        for item in get_watchlist(self.db):
            row = ctk.CTkFrame(self._wl_scroll)
            row.pack(fill="x", pady=1)

            def cell(text, width, anchor="w"):
                ctk.CTkLabel(row, text=str(text), width=width,
                             font=FONT_LABEL, anchor=anchor).pack(side="left", padx=2)

            cell(item["name"],                           200)
            cell(f"{item['alert_buy_below'] or '—':,}" if item['alert_buy_below']
                 else "—",                               110, anchor="e")
            cell(f"{item['alert_sell_above'] or '—':,}" if item['alert_sell_above']
                 else "—",                               110, anchor="e")
            cell(item["notes"] or "",                    200)
            ctk.CTkButton(
                row, text="Remove", width=76,
                command=lambda iid=item["item_id"]: self._remove_item(iid),
            ).pack(side="left", padx=4)

    def _render_alerts(self):
        for w in self._alerts_scroll.winfo_children():
            w.destroy()

        for alert in get_recent_alerts(self.db, limit=50):
            row = ctk.CTkFrame(self._alerts_scroll)
            row.pack(fill="x", pady=1)
            color = "#2ecc71" if alert["alert_type"] == "BUY" else "#e74c3c"

            for text, width in [
                (str(alert["fired_at"])[:16], 150),
                (alert["name"],               200),
            ]:
                ctk.CTkLabel(row, text=text, width=width,
                             font=FONT_LABEL, anchor="w").pack(side="left", padx=2)

            ctk.CTkLabel(row, text=alert["alert_type"], width=60,
                         font=FONT_LABEL, text_color=color).pack(side="left", padx=2)

            for text, width in [
                (f"{alert['price']:,}",     110),
                (f"{alert['threshold']:,}", 110),
            ]:
                ctk.CTkLabel(row, text=text, width=width,
                             font=FONT_LABEL, anchor="e").pack(side="left", padx=2)

    def reload(self):
        self._render_watchlist()
        self._render_alerts()
