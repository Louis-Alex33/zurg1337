from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup

from models import DomainDiscovery, QualificationSignals
from qualify import (
    classify_site_type,
    collect_signals,
    compute_size_score,
    extract_editorial_word_count,
    should_reject,
)


class SiteTypeClassifierTests(unittest.TestCase):
    def test_editorial_candidate_is_detected_from_paths_and_copy(self) -> None:
        html = """
        <html>
          <body>
            <header><nav><a href="/about">About</a><a href="/contact">Contact</a></nav></header>
            <main>
              <article>
                <h1>Guide complet du padel en 2026</h1>
                <p>{copy}</p>
                <a href="/blog/padel">Blog</a>
                <a href="/guides/choisir-sa-raquette">Guide</a>
                <a href="/articles/regles-padel">Article</a>
              </article>
            </main>
          </body>
        </html>
        """.format(copy="mot " * 500)
        soup = BeautifulSoup(html, "html.parser")

        result = classify_site_type(
            soup=soup,
            html=html.lower(),
            homepage_url="https://example.com",
            has_blog=True,
            has_dated_content=True,
            editorial_word_count=extract_editorial_word_count(html),
        )

        self.assertTrue(result["is_editorial_candidate"])
        self.assertFalse(result["is_app_like"])
        self.assertFalse(result["is_docs_like"])
        self.assertEqual(result["app_signal"], 0)
        self.assertEqual(result["refresh_repair_fit"], "good_fit")

    def test_app_docs_and_marketplace_signals_are_flagged(self) -> None:
        html = """
        <html>
          <body>
            <header>
              <nav>
                <a href="/login">Login</a>
                <a href="/dashboard">Dashboard</a>
                <a href="/docs">Docs</a>
                <a href="/help">Help</a>
                <a href="/pricing">Pricing</a>
                <a href="/product/seo-tool">Product</a>
                <a href="/cart">Cart</a>
              </nav>
            </header>
            <main><p>Short copy for a software homepage.</p></main>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        result = classify_site_type(
            soup=soup,
            html=html.lower(),
            homepage_url="https://example.com",
            has_blog=False,
            has_dated_content=False,
            editorial_word_count=extract_editorial_word_count(html),
        )

        self.assertFalse(result["is_editorial_candidate"])
        self.assertTrue(result["is_app_like"])
        self.assertTrue(result["is_docs_like"])
        self.assertTrue(result["is_marketplace_like"])
        self.assertGreaterEqual(result["app_signal"], 3)
        self.assertGreaterEqual(result["docs_signal"], 3)
        self.assertGreaterEqual(result["marketplace_signal"], 3)
        self.assertEqual(result["refresh_repair_fit"], "low_fit")

    def test_compute_size_score_flags_very_large_editorial_sites(self) -> None:
        signals = QualificationSignals(
            domain="huge-media.fr",
            estimated_pages=5200,
            dated_urls_count=140,
            has_blog=True,
            is_editorial_candidate=True,
        )

        self.assertEqual(compute_size_score(signals), 90)

    def test_should_reject_returns_reason_for_hard_blocked_domain(self) -> None:
        signals = QualificationSignals(
            domain="wikipedia.org",
            hard_blocked=True,
        )

        rejected, reason, confidence = should_reject(signals)

        self.assertTrue(rejected)
        self.assertEqual(reason, "hard_blocked_domain")
        self.assertEqual(confidence, "high")

    def test_should_reject_large_site_after_size_score_threshold(self) -> None:
        signals = QualificationSignals(
            domain="big-editorial.fr",
            estimated_pages=6000,
            dated_urls_count=120,
            has_blog=True,
            is_editorial_candidate=True,
            size_score=90,
        )

        rejected, reason, confidence = should_reject(signals)

        self.assertTrue(rejected)
        self.assertEqual(reason, "site_too_large")
        self.assertEqual(confidence, "high")

    def test_should_reject_returns_low_confidence_for_borderline_app_signals(self) -> None:
        signals = QualificationSignals(
            domain="borderline-app.example",
            is_app_like=True,
            app_signal=3,
            nav_link_ratio=0.36,
            editorial_word_count=800,
        )

        rejected, reason, confidence = should_reject(signals)

        self.assertFalse(rejected)
        self.assertEqual(reason, "app_like_site")
        self.assertEqual(confidence, "low")

    def test_should_reject_returns_high_confidence_when_signals_are_strong(self) -> None:
        signals = QualificationSignals(
            domain="strong-app.example",
            is_app_like=True,
            app_signal=8,
            editorial_word_count=50,
        )

        rejected, reason, confidence = should_reject(signals)

        self.assertTrue(rejected)
        self.assertEqual(reason, "app_like_site")
        self.assertEqual(confidence, "high")

    def test_borderline_app_like_is_not_rejected_but_flagged_in_notes(self) -> None:
        discovery = DomainDiscovery(
            domain="example.com",
            source_query="seo",
            source_provider="manual",
            first_seen="2026-04-16T12:00:00",
        )
        html = "<html><body><main><article><p>" + ("mot " * 800) + "</p></article></main></body></html>"
        response = SimpleNamespace(
            text=html,
            url="https://example.com",
            request_url="https://example.com",
            status_code=200,
            skip_reason="",
        )
        site_type = {
            "is_editorial_candidate": False,
            "is_app_like": True,
            "app_signal": 3,
            "is_docs_like": False,
            "docs_signal": 0,
            "is_marketplace_like": False,
            "marketplace_signal": 0,
            "refresh_repair_fit": "review_fit",
            "site_type_note": "navigation orientee app/login/dashboard",
            "nav_link_ratio": 0.36,
            "content_link_ratio": 0.12,
        }

        with patch("qualify.fetch_homepage", return_value=response), patch(
            "qualify.classify_site_type",
            return_value=site_type,
        ):
            signals = collect_signals(
                discovery,
                session=object(),  # type: ignore[arg-type]
                check_sitemap=False,
            )

        self.assertFalse(signals.rejected)
        self.assertEqual(signals.rejection_reason, "app_like_site")
        self.assertEqual(signals.rejection_confidence, "low")
        self.assertIn("Signaux app-like borderline", signals.notes)

    def test_extract_editorial_word_count_reuses_existing_soup_without_reparsing(self) -> None:
        html = "<html><body><main><article><p>" + ("mot " * 120) + "</p></article></main></body></html>"
        soup = BeautifulSoup(html, "html.parser")

        with patch("qualify.BeautifulSoup") as mock_parser:
            count = extract_editorial_word_count(soup=soup)

        self.assertGreater(count, 100)
        mock_parser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
