from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

from .ga_detect import compute_ga_obsolete_score, fetch_ga_signals
from .post_age import compute_post_age_score
from .signals import IntentSignals
from .wayback import compute_wayback_score, fetch_wayback_quarters
from .whois_age import compute_whois_score, fetch_whois_age

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path("config/intent_scoring.yaml")


def load_config(path: Path = _DEFAULT_CONFIG) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)  # type: ignore[no-any-return]


def compute_intent_signals(
    domain: str,
    last_post_date_str: str,
    config: dict[str, Any],
) -> IntentSignals:
    """Compute all 4 intent signals and final weighted score for one domain."""
    sig = IntentSignals(domain=domain)
    weights: dict[str, float] = config.get("weights", {})
    inactive_days: int = int(config.get("post_age_inactive_days", 180))
    n_quarters: int = int(config.get("wayback_quarters", 8))
    min_snap: int = int(config.get("wayback_min_snapshots", 1))
    stagnation_threshold: float = float(config.get("whois_stagnation_ratio", 0.5))

    # --- Signal 1: post age ---
    age_days, post_age_score = compute_post_age_score(last_post_date_str, inactive_days)
    sig.last_post_age_days = age_days
    sig.post_age_score = post_age_score

    # --- Signal 2: Wayback ---
    try:
        quarters = fetch_wayback_quarters(domain, num_quarters=n_quarters)
        sig.wayback_quarters = quarters
        slope, wb_score = compute_wayback_score(quarters, min_snapshots=min_snap)
        sig.wayback_trend = slope
        sig.wayback_score = wb_score
    except Exception as exc:
        logger.warning("wayback error domain=%s: %s", domain, exc)

    # --- Signal 3: WHOIS ---
    try:
        age_years = fetch_whois_age(domain)
        sig.whois_domain_age_years = age_years
        ratio, whois_score = compute_whois_score(age_years, age_days, stagnation_threshold)
        sig.whois_stagnation_ratio = ratio
        sig.whois_score = whois_score
    except Exception as exc:
        logger.warning("whois error domain=%s: %s", domain, exc)

    # --- Signal 4: GA tags ---
    try:
        has_ua, has_ga4 = fetch_ga_signals(domain)
        sig.ga_has_ua_tag = has_ua
        sig.ga_has_ga4_tag = has_ga4
        sig.ga_obsolete_score = compute_ga_obsolete_score(has_ua, has_ga4)
    except Exception as exc:
        logger.warning("ga_detect error domain=%s: %s", domain, exc)

    # --- Weighted sum ---
    sig.intent_score = round(
        weights.get("post_age", 0.35) * sig.post_age_score
        + weights.get("wayback", 0.30) * sig.wayback_score
        + weights.get("whois", 0.20) * sig.whois_score
        + weights.get("ga_obsolete", 0.15) * sig.ga_obsolete_score,
        4,
    )
    return sig


def run_intent_scoring(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    concurrency: int = 5,
) -> list[IntentSignals]:
    """Score all domains concurrently using a thread pool (I/O-bound calls).

    Uses threads (not async) because python-whois and requests are blocking.
    """
    results: list[IntentSignals | None] = [None] * len(rows)

    def _score(idx: int, row: dict[str, Any]) -> tuple[int, IntentSignals]:
        domain = row.get("domain", "")
        last_post = row.get("last_post_date", "")
        try:
            return idx, compute_intent_signals(domain, last_post, config)
        except Exception as exc:
            logger.error("intent scoring crashed domain=%s: %s", domain, exc)
            sig = IntentSignals(domain=domain, error=str(exc))
            return idx, sig

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_score, i, row): i for i, row in enumerate(rows)}
        for future in as_completed(futures):
            idx, sig = future.result()
            results[idx] = sig

    return [r for r in results if r is not None]
