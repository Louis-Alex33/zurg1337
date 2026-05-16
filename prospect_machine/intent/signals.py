from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IntentSignals:
    domain: str
    # Raw signals
    last_post_age_days: int | None = None       # None if unknown
    wayback_trend: float | None = None          # slope of quarterly snapshots [-1, 1], negative = declining
    wayback_quarters: list[int] = field(default_factory=list)  # snapshot count per quarter, oldest→newest
    whois_domain_age_years: float | None = None
    whois_stagnation_ratio: float | None = None  # domain_age_years / (last_post_age_days/365)
    ga_has_ua_tag: bool = False
    ga_has_ga4_tag: bool = False
    # Normalised [0,1] components
    post_age_score: float = 0.0
    wayback_score: float = 0.0
    whois_score: float = 0.0
    ga_obsolete_score: float = 0.0
    # Final
    intent_score: float = 0.0
    error: str = ""
