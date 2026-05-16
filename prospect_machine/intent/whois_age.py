from __future__ import annotations

import logging
from datetime import date, datetime

import whois  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def fetch_whois_age(domain: str) -> float | None:
    """Return domain age in fractional years, or None on failure."""
    try:
        w = whois.whois(domain)
    except Exception as exc:
        logger.debug("whois error domain=%s: %s", domain, exc)
        return None

    creation = w.get("creation_date") if isinstance(w, dict) else getattr(w, "creation_date", None)
    if creation is None:
        return None

    # python-whois may return a list (multiple registrars).
    if isinstance(creation, list):
        creation = creation[0]

    if isinstance(creation, datetime):
        creation = creation.date()
    elif not isinstance(creation, date):
        return None

    age_days = (date.today() - creation).days
    return max(0.0, age_days / 365.25)


def compute_whois_score(
    domain_age_years: float | None,
    last_post_age_days: int | None,
    stagnation_threshold: float = 0.5,
) -> tuple[float | None, float]:
    """Return (stagnation_ratio, normalised_score).

    ratio = domain_age_years / (last_post_age_days / 365)
    A high ratio means the domain is old but content hasn't been updated recently.
    Score is clamped to [0, 1].
    """
    if domain_age_years is None or last_post_age_days is None or last_post_age_days <= 0:
        return None, 0.0
    content_age_years = last_post_age_days / 365.25
    if content_age_years <= 0:
        return None, 0.0
    ratio = domain_age_years / content_age_years
    # Only penalise when the domain is old AND the content is stale.
    # content_age_years < 1 means content was updated recently → low score regardless of domain age.
    content_staleness = min(1.0, content_age_years / 2.0)  # 0 → fresh, 1 → ≥ 2 years stale
    # Ratio contribution: how much older is the domain than its last update.
    ratio_contrib = min(1.0, ratio / max(stagnation_threshold * 4, 1.0))
    score = content_staleness * ratio_contrib
    return ratio, score
