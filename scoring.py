from __future__ import annotations

from config import QUALIFICATION_WEIGHTS
from models import GSCPageAnalysis, QualificationSignals


def score_qualification(signals: QualificationSignals) -> int:
    if signals.rejected:
        return 0

    score = 0
    pages = signals.estimated_pages

    if pages > 200:
        score += QUALIFICATION_WEIGHTS.pages_200
    elif pages > 100:
        score += QUALIFICATION_WEIGHTS.pages_100
    elif pages > 50:
        score += QUALIFICATION_WEIGHTS.pages_50
    elif pages > 20:
        score += QUALIFICATION_WEIGHTS.pages_20

    if signals.has_blog:
        score += QUALIFICATION_WEIGHTS.has_blog

    if signals.cms == "WordPress":
        score += QUALIFICATION_WEIGHTS.wordpress
    elif signals.cms in {"Ghost", "Squarespace", "Webflow"}:
        score += QUALIFICATION_WEIGHTS.modern_cms

    if signals.has_dated_content:
        score += QUALIFICATION_WEIGHTS.has_dated_content

    if signals.dated_urls_count > 10:
        score += QUALIFICATION_WEIGHTS.dated_urls_high
    elif signals.dated_urls_count > 3:
        score += QUALIFICATION_WEIGHTS.dated_urls_low

    if signals.contact_found:
        score += QUALIFICATION_WEIGHTS.contact_found

    if signals.social_links:
        score += QUALIFICATION_WEIGHTS.social_links

    score += min(
        QUALIFICATION_WEIGHTS.issue_cap,
        len(signals.issues) * QUALIFICATION_WEIGHTS.issue_unit,
    )

    if signals.is_editorial_candidate:
        score += QUALIFICATION_WEIGHTS.editorial_candidate_bonus
    if signals.is_marketplace_like:
        score -= QUALIFICATION_WEIGHTS.marketplace_like_penalty
    if signals.is_docs_like:
        score -= QUALIFICATION_WEIGHTS.docs_like_penalty
    if signals.is_app_like:
        score -= QUALIFICATION_WEIGHTS.app_like_penalty

    if not signals.sitemap_available:
        score = max(0, score - QUALIFICATION_WEIGHTS.missing_sitemap_penalty)

    if signals.size_score >= 60:
        score = max(0, score - QUALIFICATION_WEIGHTS.size_score_high_penalty)
    elif signals.size_score >= 40:
        score = max(0, score - QUALIFICATION_WEIGHTS.size_score_medium_penalty)

    return min(100, score)


def gsc_score_position(position: float) -> float:
    if 4 <= position <= 10:
        return 30
    if 10 < position <= 20:
        return 20
    if 2 <= position < 4:
        return 15
    if 20 < position <= 40:
        return 5
    return 0


def gsc_score_impressions(impressions: int, max_impressions: int) -> float:
    if max_impressions <= 0:
        return 0
    return round((impressions / max_impressions) * 25, 1)


def gsc_score_ctr(ctr: float, position: float) -> float:
    expected_ctr = {
        1: 0.30,
        2: 0.18,
        3: 0.12,
        4: 0.08,
        5: 0.06,
        6: 0.05,
        7: 0.04,
        8: 0.03,
        9: 0.025,
        10: 0.02,
    }
    position_bucket = max(1, min(10, round(position)))
    expected = expected_ctr.get(position_bucket, 0.015)
    if expected <= 0:
        return 0
    gap = (expected - ctr) / expected
    return round(max(0, min(25, gap * 25)), 1)


def gsc_score_decline(click_delta: int | None, impression_delta: int | None) -> float:
    if click_delta is None:
        return 0
    penalty = 0.0
    if click_delta < 0:
        penalty += min(10, abs(click_delta) / 5)
    if impression_delta is not None and impression_delta < 0:
        penalty += min(10, abs(impression_delta) / 50)
    return round(min(20, penalty), 1)


def is_dead_gsc_page(analysis: GSCPageAnalysis) -> bool:
    low_impressions = analysis.impressions < 50
    bad_position = analysis.position > 40 or analysis.position == 0
    no_clicks = analysis.clicks < 5
    return low_impressions and bad_position and no_clicks
