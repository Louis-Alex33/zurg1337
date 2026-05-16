from __future__ import annotations

from datetime import date


def compute_post_age_score(last_post_date_str: str, inactive_days: int = 180) -> tuple[int | None, float]:
    """Return (age_in_days, normalised_score).

    Score is clamped to [0, 1]: 0 if the site posted today, 1 if age >= inactive_days.
    Returns (None, 0.0) when last_post_date is empty/unparseable.
    """
    if not last_post_date_str:
        return None, 0.0
    try:
        last = date.fromisoformat(last_post_date_str[:10])
    except ValueError:
        return None, 0.0
    age = (date.today() - last).days
    score = min(1.0, age / inactive_days) if inactive_days > 0 else 0.0
    return age, score
