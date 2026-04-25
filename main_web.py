"""
Web entry point.
  Local:   python main_web.py  →  http://localhost:8000
  Docker:  binds 0.0.0.0 so Docker can forward the port to the host.
"""
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

if __name__ == "__main__":
    import uvicorn
    # 0.0.0.0 inside a container, 127.0.0.1 for pure-local dev
    host = os.environ.get("BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host=host, port=port, reload=False)
