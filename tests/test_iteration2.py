"""Tests unitaires -- Iteration 2 rapport GSC."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from url_variants import detect_url_variants, canonical_url_from_pair


# ---------------------------------------------------------------------------
# T1 -- Detection variantes d'URL
# ---------------------------------------------------------------------------

def test_detect_url_variants_typo():
    urls = [
        "https://example.com/test-chassures-padel-kuikma/",
        "https://example.com/test-chaussures-padel-kuikma/",
        "https://example.com/page-totalement-differente/",
    ]
    variants = detect_url_variants(urls)
    assert len(variants) == 1
    assert "chassures" in variants[0][0] or "chaussures" in variants[0][0]


def test_detect_url_variants_no_false_positive_on_short_slugs():
    urls = [
        "https://example.com/produit-1/",
        "https://example.com/produit-2/",
    ]
    assert detect_url_variants(urls) == []


def test_detect_url_variants_no_false_positive_on_numeric_identifiers():
    urls = [
        "https://example.com/tournoi-padel-p100/",
        "https://example.com/tournoi-padel-p1000/",
        "https://example.com/tournoi-padel-p1500/",
    ]
    assert detect_url_variants(urls) == []


def test_detect_url_variants_different_domain():
    urls = [
        "https://example.com/test-chassures-padel-kuikma/",
        "https://other.com/test-chaussures-padel-kuikma/",
    ]
    assert detect_url_variants(urls) == []


def test_detect_url_variants_different_depth():
    urls = [
        "https://example.com/padel/test-chassures-kuikma/",
        "https://example.com/test-chaussures-padel-kuikma/",
    ]
    assert detect_url_variants(urls) == []


def test_detect_url_variants_two_differing_segments():
    urls = [
        "https://example.com/test-chassures-kuikma/produit-abc/",
        "https://example.com/test-chaussures-kuikma/produit-xyz/",
    ]
    assert detect_url_variants(urls) == []


def test_canonical_url_is_longest():
    a = "https://example.com/test-chassures-padel-kuikma/"
    b = "https://example.com/test-chaussures-padel-kuikma/"
    canonical = canonical_url_from_pair(a, b)
    assert canonical == b  # "chaussures" est plus long


# ---------------------------------------------------------------------------
# T3 -- Filtrage Top 10 sur seuil de gain minimum
# ---------------------------------------------------------------------------

def _make_analysis(url, impressions, ctr, position):
    from models import GSCPageAnalysis
    item = GSCPageAnalysis(url=url)
    item.impressions = impressions
    item.ctr = ctr
    item.position = position
    item.clicks = round(impressions * ctr)
    item.priority = "HIGH"
    item.opportunity_score = 50
    item.business_value = "medium"
    return item


def test_top10_excludes_low_potential_pages():
    from gsc import filter_top10_candidates
    high = _make_analysis("/a", impressions=500, ctr=0.01, position=8.0)
    low1 = _make_analysis("/b", impressions=10, ctr=0.30, position=2.0)
    low2 = _make_analysis("/c", impressions=5, ctr=0.10, position=5.0)
    result = filter_top10_candidates([high, low1, low2])
    assert any(p.url == "/a" for p in result)
    urls = [p.url for p in result]
    assert "/c" not in urls


def test_top10_filter_excludes_below_threshold():
    from gsc import filter_top10_candidates
    near_optimal = _make_analysis("/near-optimal", impressions=20, ctr=0.27, position=1.0)
    result = filter_top10_candidates([near_optimal])
    # gain_low = 20 * max(0, 0.275 - 0.27) = 0.1 -> rounds to 0 < MIN_POTENTIAL_CLICKS_FOR_TOP10
    assert near_optimal not in result


# ---------------------------------------------------------------------------
# T4 -- Deduplication business vs top10
# ---------------------------------------------------------------------------

def test_business_opportunities_excludes_top10_urls():
    from gsc import filter_business_opportunities
    top10_urls = {"/page-a", "/page-b"}
    pages = [{"url": "/page-a"}, {"url": "/page-c"}]
    filtered = filter_business_opportunities(pages, top10_urls)
    assert len(filtered) == 1
    assert filtered[0]["url"] == "/page-c"


# ---------------------------------------------------------------------------
# T5 -- Fourchette CTR cible non degeneree
# ---------------------------------------------------------------------------

def test_target_metric_always_returns_range():
    from gsc import compute_target_metric
    result = compute_target_metric(position=5.4, ctr_actual=0.06, impressions=467)
    assert result["ctr_high_target"] > result["ctr_low_target"]
    assert result["gain_high"] > result["gain_low"]
    assert result["ctr_high_target"] / result["ctr_low_target"] >= 1.3


def test_target_metric_never_negative_low_gain():
    from gsc import compute_target_metric
    result = compute_target_metric(position=3.0, ctr_actual=0.30, impressions=100)
    assert result["gain_low"] >= 0


def test_target_metric_range_factor_satisfied():
    from gsc import compute_target_metric
    for pos in [1, 2, 3, 4, 5, 6, 7, 8, 10, 15]:
        result = compute_target_metric(position=float(pos), ctr_actual=0.005, impressions=100)
        ratio = result["ctr_high_target"] / result["ctr_low_target"]
        assert ratio >= 1.3, f"Position {pos}: ratio {ratio:.2f} < 1.3"


# ---------------------------------------------------------------------------
# T6 -- Agregation requetes par (action, URL cible)
# ---------------------------------------------------------------------------

def test_query_aggregation_dedupes_by_url_and_action():
    from gsc import aggregate_queries_by_target_url
    from models import GSCQueryData

    queries = [
        GSCQueryData(query="p500 padel", target_url="/tournoi-p500/", impressions=900, clicks=0, position=8.0),
        GSCQueryData(query="p500 points", target_url="/tournoi-p500/", impressions=600, clicks=0, position=8.0),
        GSCQueryData(query="autre requete", target_url="/autre-page/", impressions=300, clicks=5, position=10.0),
    ]

    aggregated = aggregate_queries_by_target_url(queries, [], top_n=20)
    p500_rows = [r for r in aggregated if "tournoi-p500" in str(r.get("target_url", ""))]
    assert len(p500_rows) >= 1
    p500_row = p500_rows[0]
    assert p500_row["queries_count"] == 2
    assert p500_row["total_impressions"] == 1500


def test_query_aggregation_uniqueness():
    from gsc import aggregate_queries_by_target_url
    from models import GSCQueryData

    queries = [
        GSCQueryData(query=f"requete-{i}", target_url="/page-unique/", impressions=100, clicks=1, position=7.0)
        for i in range(5)
    ]
    aggregated = aggregate_queries_by_target_url(queries, [], top_n=20)
    pairs = [(r["recommendation"], r["target_url"]) for r in aggregated]
    assert len(pairs) == len(set(pairs)), "Doublons (action, URL) detectes dans le tableau"


# ---------------------------------------------------------------------------
# T2 -- Unicite des snippets
# ---------------------------------------------------------------------------

def test_snippet_uniqueness_check():
    from gsc import check_snippet_uniqueness
    snippets = [
        {
            "url": "/a",
            "title_example": "Tournoi P100 : niveau et points",
            "meta_example": "Decouvrez le niveau P100, les points a gagner et les conditions d'inscription.",
        },
        {
            "url": "/b",
            "title_example": "Tournoi P250 : niveau et points",
            "meta_example": "Decouvrez le niveau P250, les points a gagner et les conditions d'inscription.",
        },
        {
            "url": "/c",
            "title_example": "Guide complet padel debutant",
            "meta_example": "Tout ce qu'il faut savoir pour debuter au padel : regles, materiel et conseils.",
        },
    ]
    duplicates = check_snippet_uniqueness(snippets)
    assert "/b" in duplicates


def test_snippet_uniqueness_no_false_positive():
    from gsc import check_snippet_uniqueness
    snippets = [
        {
            "url": "/a",
            "title_example": "Guide padel debutant",
            "meta_example": "Tout pour debuter.",
        },
        {
            "url": "/b",
            "title_example": "Meilleur raquette padel 2025",
            "meta_example": "Comparatif complet des meilleures raquettes de padel.",
        },
    ]
    duplicates = check_snippet_uniqueness(snippets)
    assert duplicates == []
