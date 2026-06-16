"""Shared scraping helpers: logging, rate limiting, retries, User-Agent
rotation, name normalization and thin wrappers over scrapling fetchers."""
from __future__ import annotations

import logging
import random
import time
import unicodedata
from functools import wraps
from typing import Callable, Optional

from backend.config import settings, LOG_DIR

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
_LOG_FILE = LOG_DIR / "scraping.log"


def get_logger(name: str = "scraper") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


log = get_logger()

# --------------------------------------------------------------------------- #
# User agents / rate limiting
# --------------------------------------------------------------------------- #
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def random_ua() -> str:
    return random.choice(USER_AGENTS)


def polite_sleep() -> None:
    time.sleep(random.uniform(settings.SCRAPER_RATE_LIMIT_MIN, settings.SCRAPER_RATE_LIMIT_MAX))


def with_retry(max_attempts: Optional[int] = None, base_delay: float = 1.0) -> Callable:
    """Exponential-backoff retry decorator. Returns None on final failure rather
    than raising, so callers can degrade gracefully."""
    attempts = max_attempts or settings.SCRAPER_MAX_RETRIES

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - intentional broad catch
                    last_exc = exc
                    delay = base_delay * (2 ** i) + random.uniform(0, 0.5)
                    log.warning("%s failed (attempt %d/%d): %s; retrying in %.1fs",
                                fn.__name__, i + 1, attempts, exc, delay)
                    time.sleep(delay)
            log.error("%s failed after %d attempts: %s", fn.__name__, attempts, last_exc)
            return None
        return wrapper
    return deco


# --------------------------------------------------------------------------- #
# Name normalization
# --------------------------------------------------------------------------- #
_ALIASES = {
    "man city": "manchester city",
    "man utd": "manchester united",
    "man united": "manchester united",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "newcastle": "newcastle united",
    "west ham": "west ham united",
    "brighton": "brighton & hove albion",
    "atletico": "atletico madrid",
    "atletico de madrid": "atletico madrid",
    "barca": "barcelona",
    "fc barcelona": "barcelona",
    "real": "real madrid",
    "inter": "inter milan",
    "internazionale": "inter milan",
    "psg": "paris saint-germain",
    "bayern": "bayern munich",
    "bayern munchen": "bayern munich",
    "dortmund": "borussia dortmund",
    "juve": "juventus",
}


def normalize_team_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.strip().lower()
    for suffix in (" fc", " cf", " afc", " sc"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = s.strip()
    return _ALIASES.get(s, s)


def teams_match(a: Optional[str], b: Optional[str]) -> bool:
    na, nb = normalize_team_name(a), normalize_team_name(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


# --------------------------------------------------------------------------- #
# Fetch wrappers
# --------------------------------------------------------------------------- #
def fetch_json(url: str, headers: Optional[dict] = None, params: Optional[dict] = None,
               timeout: int = 25):
    """Lightweight JSON GET via curl_cffi impersonation. Returns parsed JSON or None."""
    from scrapling.fetchers import Fetcher
    h = {"User-Agent": random_ua(), "Accept": "application/json"}
    if headers:
        h.update(headers)
    try:
        r = Fetcher.get(url, headers=h, params=params or {}, impersonate="chrome", timeout=timeout)
        if r.status == 200:
            try:
                return r.json()
            except Exception:
                import json
                return json.loads(str(r.body, "utf-8") if isinstance(r.body, bytes) else r.body)
        log.warning("fetch_json %s -> HTTP %s", url, r.status)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("fetch_json %s error: %s", url, exc)
        return None


def fetch_browser(url: str, *, solve_cloudflare: bool = False, network_idle: bool = True,
                  timeout: int = 90000, page_setup=None, page_action=None, wait: int = 0,
                  wait_selector: Optional[str] = None):
    """Render a page with the stealth browser. Returns a scrapling Response or None.

    ``wait_selector`` makes the fetch block until that CSS selector is attached,
    which is essential for feed-driven pages (e.g. FlashScore) that inject rows
    asynchronously after the initial render."""
    from scrapling.fetchers import StealthyFetcher
    kwargs = dict(
        headless=settings.SCRAPER_HEADLESS,
        solve_cloudflare=solve_cloudflare,
        network_idle=network_idle,
        timeout=timeout,
        page_setup=page_setup,
        page_action=page_action,
        wait=wait,
    )
    if wait_selector:
        kwargs["wait_selector"] = wait_selector
    try:
        return StealthyFetcher.fetch(url, **kwargs)
    except Exception as exc:  # noqa: BLE001
        log.warning("fetch_browser %s error: %s", url, exc)
        return None
