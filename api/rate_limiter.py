import time
import logging

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, min_interval_seconds: float):
        self.min_interval = min_interval_seconds
        self._last_call = 0.0

    def wait(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            log.debug("Rate limiting: sleeping %.2fs", wait_time)
            time.sleep(wait_time)
        self._last_call = time.time()


wiki_limiter  = RateLimiter(min_interval_seconds=60)
item_limiter  = RateLimiter(min_interval_seconds=2)
jagex_limiter = RateLimiter(min_interval_seconds=3)
