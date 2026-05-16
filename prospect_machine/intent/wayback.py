from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

logger = logging.getLogger(__name__)

_CDX_URL = "http://web.archive.org/cdx/search/cdx"
_TIMEOUT = 12


def fetch_wayback_quarters(
    domain: str,
    num_quarters: int = 8,
    timeout: int = _TIMEOUT,
    _session: requests.Session | None = None,
) -> list[int]:
    """Return snapshot counts per quarter, oldest first, over the last num_quarters quarters.

    Uses the Wayback CDX API with output=json&fl=timestamp&collapse=digest.
    Returns an empty list on any network/parse error.
    """
    today = date.today()
    # Build quarter boundaries going back num_quarters quarters from today.
    boundaries = _quarter_boundaries(today, num_quarters)

    counts: list[int] = []
    sess = _session or requests.Session()
    for start, end in boundaries:
        count = _count_snapshots(domain, start, end, sess, timeout)
        counts.append(count)
    return counts


def compute_wayback_score(quarters: list[int], min_snapshots: int = 1) -> tuple[float, float]:
    """Return (trend_slope, normalised_score).

    trend_slope: linear regression slope normalised to [-1, 1] over the quarter counts.
    score: 1.0 when fully declining, 0.0 when stable/growing.
    Returns (0.0, 0.0) on empty/insufficient data.
    """
    if len(quarters) < 2:
        return 0.0, 0.0
    slope = _linear_slope(quarters)
    # Normalise by the range of the series so the score is scale-independent.
    q_range = max(quarters) - min(quarters)
    if q_range == 0:
        return slope, 0.0
    # slope magnitude relative to range; clamped to [0, 1]; positive when declining.
    score = float(min(1.0, max(0.0, -slope / (q_range / len(quarters)))))
    return slope, score


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _quarter_boundaries(today: date, num_quarters: int) -> list[tuple[date, date]]:
    """Return list of (start, end) date pairs for the last num_quarters calendar quarters."""
    # Snap today to start of current quarter.
    q_month = ((today.month - 1) // 3) * 3 + 1
    current_q_start = date(today.year, q_month, 1)
    boundaries: list[tuple[date, date]] = []
    end = current_q_start
    for _ in range(num_quarters):
        # Go back one quarter.
        m = end.month - 3
        y = end.year
        if m <= 0:
            m += 12
            y -= 1
        start = date(y, m, 1)
        boundaries.append((start, end - timedelta(days=1)))
        end = start
    boundaries.reverse()
    return boundaries


def _count_snapshots(
    domain: str,
    start: date,
    end: date,
    sess: requests.Session,
    timeout: int,
) -> int:
    params = {
        "url": f"*.{domain}",
        "output": "json",
        "fl": "timestamp",
        "collapse": "digest",
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "limit": "500",
    }
    try:
        resp = sess.get(_CDX_URL, params=params, timeout=timeout)
        if not resp.ok:
            return 0
        data = resp.json()
        # First row is the header ["timestamp"], remaining rows are results.
        return max(0, len(data) - 1)
    except Exception as exc:
        logger.debug("wayback CDX error domain=%s: %s", domain, exc)
        return 0


def _linear_slope(values: list[int]) -> float:
    """Least-squares slope of the series."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    return num / den if den else 0.0
