from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_UA_PATTERN = re.compile(r"\bUA-\d{4,}-\d+\b")
_GA4_PATTERN = re.compile(r"\bG-[A-Z0-9]{6,}\b")

_TIMEOUT = 10
_MAX_BYTES = 150_000
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_ga_signals(
    domain: str,
    timeout: int = _TIMEOUT,
    _session: requests.Session | None = None,
) -> tuple[bool, bool]:
    """Scrape the domain home page and return (has_ua_tag, has_ga4_tag).

    Returns (False, False) on any network error.
    """
    sess = _session or requests.Session()
    url = f"https://{domain}"
    try:
        resp = sess.get(url, headers=_HEADERS, timeout=timeout, stream=True)
        if not resp.ok:
            return False, False
        raw = b""
        for chunk in resp.iter_content(chunk_size=8192):
            raw += chunk
            if len(raw) >= _MAX_BYTES:
                break
        html = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug("ga_detect fetch error domain=%s: %s", domain, exc)
        return False, False

    return detect_ga_tags(html)


def detect_ga_tags(html: str) -> tuple[bool, bool]:
    """Parse HTML and return (has_ua_tag, has_ga4_tag)."""
    # Search raw HTML for tag patterns (covers inline scripts and data attributes).
    has_ua = bool(_UA_PATTERN.search(html))
    has_ga4 = bool(_GA4_PATTERN.search(html))
    return has_ua, has_ga4


def compute_ga_obsolete_score(has_ua: bool, has_ga4: bool) -> float:
    """Return 1.0 when UA tag present without GA4 (obsolete setup), else 0.0."""
    if has_ua and not has_ga4:
        return 1.0
    return 0.0
