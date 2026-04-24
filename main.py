import sqlite3
import logging
import os
import sys
from database.schema import init_db
from data_service import DataService
from gui.app import App
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("dashboard.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main():
    os.makedirs("data", exist_ok=True)

    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    log.info("Database initialized.")

    service = DataService(conn)

    log.info("Starting initial data load…")
    service.initial_load(progress_callback=lambda msg: log.info(msg))

    service.start_background_refresh(config.REFRESH_INTERVAL_SECONDS)

    app = App(conn, service)
    app.mainloop()

    service.stop()
    conn.close()
    log.info("Dashboard closed.")


if __name__ == "__main__":
    main()
