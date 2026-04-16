from __future__ import annotations

import unittest

from models import QualificationSignals
from scoring import score_qualification


class QualificationScoringTests(unittest.TestCase):
    def test_score_qualification_uses_centralized_weights(self) -> None:
        signals = QualificationSignals(
            domain="example.com",
            cms="WordPress",
            estimated_pages=180,
            has_blog=True,
            has_dated_content=True,
            dated_urls_count=12,
            contact_found="hello@example.com",
            social_links=["instagram"],
            issues=["Homepage sans meta description", "Homepage sans H1"],
            sitemap_available=True,
        )

        score = score_qualification(signals)

        self.assertEqual(score, 90)

    def test_missing_sitemap_applies_small_penalty(self) -> None:
        base = QualificationSignals(domain="example.com", estimated_pages=60, sitemap_available=True)
        penalized = QualificationSignals(domain="example.com", estimated_pages=60, sitemap_available=False)

        self.assertEqual(score_qualification(base) - score_qualification(penalized), 2)

    def test_app_and_docs_like_sites_are_heavily_penalized(self) -> None:
        editorial = QualificationSignals(
            domain="media-example.com",
            estimated_pages=220,
            has_blog=True,
            has_dated_content=True,
            dated_urls_count=12,
            sitemap_available=True,
            is_editorial_candidate=True,
        )
        app_docs = QualificationSignals(
            domain="saas-example.com",
            estimated_pages=220,
            has_blog=True,
            has_dated_content=True,
            dated_urls_count=12,
            sitemap_available=True,
            is_app_like=True,
            is_docs_like=True,
        )

        self.assertGreaterEqual(score_qualification(editorial) - score_qualification(app_docs), 60)

    def test_score_qualification_is_capped_at_100(self) -> None:
        signals = QualificationSignals(
            domain="example.com",
            cms="WordPress",
            estimated_pages=500,
            has_blog=True,
            has_dated_content=True,
            dated_urls_count=50,
            contact_found="hello@example.com",
            social_links=["instagram", "linkedin"],
            issues=["a", "b", "c", "d"],
            sitemap_available=True,
            is_editorial_candidate=True,
        )

        self.assertEqual(score_qualification(signals), 100)

    def test_rejected_site_forces_score_to_zero(self) -> None:
        signals = QualificationSignals(
            domain="wikipedia.org",
            estimated_pages=5000,
            has_blog=True,
            has_dated_content=True,
            dated_urls_count=150,
            sitemap_available=True,
            is_editorial_candidate=True,
            rejected=True,
            rejection_reason="hard_blocked_domain",
        )

        self.assertEqual(score_qualification(signals), 0)

    def test_large_size_score_applies_penalty_before_cap(self) -> None:
        base = QualificationSignals(
            domain="editorial-medium.fr",
            estimated_pages=120,
            has_blog=True,
            has_dated_content=True,
            dated_urls_count=4,
            sitemap_available=True,
            is_editorial_candidate=True,
        )
        penalized = QualificationSignals(
            domain="editorial-large.fr",
            estimated_pages=120,
            has_blog=True,
            has_dated_content=True,
            dated_urls_count=4,
            sitemap_available=True,
            is_editorial_candidate=True,
            size_score=65,
        )

        self.assertEqual(score_qualification(base) - score_qualification(penalized), 25)


if __name__ == "__main__":
    unittest.main()
