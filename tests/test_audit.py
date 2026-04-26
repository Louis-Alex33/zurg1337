from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace

from unittest.mock import patch

from audit import (
    build_report,
    classify_page_type,
    compute_observed_health_score,
    crawl_page,
    crawl_site,
    detect_possible_overlap,
    detect_probable_orphans,
    find_dated_references,
    parse_robots_txt,
    robots_can_fetch,
    should_crawl,
)
from models import AuditPage


def make_page(**overrides) -> AuditPage:
    data = {
        "url": "https://example.com/blog/page",
        "status_code": 200,
        "title": "Guide SEO complet utile",
        "meta_description": "Meta description propre pour un contenu editorial utile et exploitable.",
        "h1": ["Guide SEO complet"],
        "word_count": 800,
        "internal_links_out": ["https://example.com/blog/autre-page"],
        "images_total": 2,
        "images_without_alt": 0,
        "depth": 1,
        "dated_references": [],
        "has_structured_data": True,
        "content_like": True,
        "meaningful_h1_count": 1,
    }
    data.update(overrides)
    return AuditPage(**data)


class AuditHeuristicsTests(unittest.TestCase):
    def test_overlap_and_orphan_labels_are_prudent(self) -> None:
        home = AuditPage(
            url="https://example.com/",
            title="Guide padel complet",
            meta_description="Guide padel complet pour debutants",
            h1=["Guide padel complet"],
            word_count=900,
            internal_links_out=[
                "https://example.com/guide-padel-debutant",
                "https://example.com/guide-padel-confirmes",
            ],
            has_structured_data=True,
        )
        page_a = AuditPage(
            url="https://example.com/guide-padel-debutant",
            title="Guide padel debutant",
            meta_description="Tout savoir pour debuter au padel",
            h1=["Guide padel debutant"],
            word_count=700,
            internal_links_out=[],
            has_structured_data=False,
            depth=1,
        )
        page_b = AuditPage(
            url="https://example.com/guide-padel-confirmes",
            title="Guide padel debutant avance",
            meta_description="Conseils padel pour progresser",
            h1=["Guide padel debutant avance"],
            word_count=650,
            internal_links_out=[],
            has_structured_data=False,
            depth=1,
        )

        overlaps = detect_possible_overlap([home, page_a, page_b], threshold=0.45)
        orphans = detect_probable_orphans([home, page_a, page_b])
        report = build_report([home, page_a, page_b], domain="example.com")

        self.assertTrue(overlaps)
        self.assertEqual(orphans, [])
        self.assertIn("sujet très proche", overlaps[0]["note"])
        self.assertIn("pendant l'analyse", " ".join(report.notes))
        self.assertLessEqual(report.observed_health_score, 100)

    def test_should_crawl_excludes_non_relevant_paths(self) -> None:
        self.assertFalse(should_crawl("https://example.com/login", "example.com"))
        self.assertFalse(should_crawl("https://example.com/docs/getting-started", "example.com"))
        self.assertFalse(should_crawl("https://example.com/cart", "example.com"))
        self.assertFalse(should_crawl("https://example.com/go/affiliate-offer", "example.com"))
        self.assertTrue(should_crawl("https://example.com/golf-guide", "example.com"))
        self.assertTrue(should_crawl("https://example.com/blog/refresh-seo", "example.com"))

    def test_crawl_site_deduplicates_queue_entries(self) -> None:
        home = AuditPage(
            url="https://example.com/",
            word_count=800,
            internal_links_out=[
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/a",
            ],
        )
        page_a = AuditPage(
            url="https://example.com/a",
            word_count=600,
            internal_links_out=[
                "https://example.com/b",
                "https://example.com/c",
            ],
        )
        page_b = AuditPage(url="https://example.com/b", word_count=600, internal_links_out=[])
        page_c = AuditPage(url="https://example.com/c", word_count=600, internal_links_out=[])
        pages_by_url = {
            "https://example.com/": home,
            "https://example.com/a": page_a,
            "https://example.com/b": page_b,
            "https://example.com/c": page_c,
        }
        crawled: list[str] = []

        def fake_crawl_page(
            url: str,
            session,
            timeout: int,
            max_html_bytes: int = 0,
            max_links_per_page: int = 0,
            max_redirects: int = 0,
            excluded_path_prefixes=None,
            cancel_callback=None,
        ):  # type: ignore[no-untyped-def]
            crawled.append(url)
            return pages_by_url[url]

        with patch("audit.crawl_page", side_effect=fake_crawl_page):
            pages = crawl_site(
                "https://example.com/",
                max_pages=10,
                delay=0,
                session=object(),  # type: ignore[arg-type]
            )

        self.assertEqual(crawled, ["https://example.com/", "https://example.com/a", "https://example.com/b", "https://example.com/c"])
        self.assertEqual([page.url for page in pages], crawled)

    def test_crawl_site_does_not_count_skipped_urls_as_page_budget(self) -> None:
        home = AuditPage(
            url="https://example.com/",
            word_count=800,
            internal_links_out=[
                "https://example.com/tracking-1.pdf",
                "https://example.com/tracking-2.pdf",
                "https://example.com/tracking-3.pdf",
                "https://example.com/tracking-4.pdf",
                "https://example.com/tracking-5.pdf",
                "https://example.com/a",
            ],
        )
        page_a = AuditPage(url="https://example.com/a", word_count=600, internal_links_out=[])
        pages_by_url = {
            "https://example.com/": home,
            "https://example.com/a": page_a,
        }

        def fake_crawl_page(
            url: str,
            session,
            timeout: int,
            max_html_bytes: int = 0,
            max_links_per_page: int = 0,
            max_redirects: int = 0,
            excluded_path_prefixes=None,
            cancel_callback=None,
        ):  # type: ignore[no-untyped-def]
            return pages_by_url.get(url)

        with patch("audit.crawl_page", side_effect=fake_crawl_page):
            pages = crawl_site(
                "https://example.com/",
                max_pages=2,
                delay=0,
                session=object(),  # type: ignore[arg-type]
            )

        self.assertEqual([page.url for page in pages], ["https://example.com/", "https://example.com/a"])

    def test_crawl_site_respects_max_depth_budget(self) -> None:
        home = AuditPage(
            url="https://example.com/",
            word_count=800,
            internal_links_out=["https://example.com/a"],
        )
        page_a = AuditPage(
            url="https://example.com/a",
            word_count=650,
            internal_links_out=["https://example.com/b"],
        )
        page_b = AuditPage(
            url="https://example.com/b",
            word_count=650,
            internal_links_out=[],
        )
        pages_by_url = {
            "https://example.com/": home,
            "https://example.com/a": page_a,
            "https://example.com/b": page_b,
        }

        def fake_crawl_page(
            url: str,
            session,
            timeout: int,
            max_html_bytes: int = 0,
            max_links_per_page: int = 0,
            max_redirects: int = 0,
            excluded_path_prefixes=None,
            cancel_callback=None,
        ):  # type: ignore[no-untyped-def]
            return pages_by_url[url]

        with patch("audit.crawl_page", side_effect=fake_crawl_page):
            pages = crawl_site(
                "https://example.com/",
                max_pages=10,
                max_depth=1,
                delay=0,
                session=object(),  # type: ignore[arg-type]
            )

        self.assertEqual([page.url for page in pages], ["https://example.com/", "https://example.com/a"])

    def test_overlap_ignores_ui_like_pages(self) -> None:
        login = AuditPage(
            url="https://example.com/login",
            title="Login",
            h1=["Login"],
            word_count=400,
        )
        pricing = AuditPage(
            url="https://example.com/pricing",
            title="Pricing",
            h1=["Pricing"],
            word_count=420,
        )
        help_page = AuditPage(
            url="https://example.com/help",
            title="Help Center",
            h1=["Help Center"],
            word_count=380,
        )

        overlaps = detect_possible_overlap([login, pricing, help_page], threshold=0.2)

        self.assertEqual(overlaps, [])

    def test_build_report_surfaces_business_priority_signals(self) -> None:
        home = AuditPage(
            url="https://example.com/",
            title="Magazine SEO",
            meta_description="Magazine SEO",
            h1=["Magazine SEO"],
            word_count=900,
            internal_links_out=["https://example.com/blog/refresh"],
            has_structured_data=True,
        )
        thin = AuditPage(
            url="https://example.com/blog/refresh",
            title="Refresh SEO",
            meta_description="",
            h1=["Refresh SEO"],
            word_count=120,
            internal_links_out=[],
            depth=4,
        )

        report = build_report([home, thin], domain="example.com")

        self.assertTrue(report.business_priority_signals)
        self.assertTrue(report.top_pages_to_rework)
        self.assertIn("contenu à enrichir", " ".join(report.top_pages_to_rework[0]["reasons"]))  # type: ignore[index]

    def test_build_report_can_disable_overlap_for_light_mode(self) -> None:
        home = AuditPage(
            url="https://example.com/",
            title="Guide padel complet",
            meta_description="Guide padel complet",
            h1=["Guide padel complet"],
            word_count=900,
            internal_links_out=[
                "https://example.com/guide-padel-debutant",
                "https://example.com/guide-padel-confirmes",
            ],
        )
        page_a = AuditPage(
            url="https://example.com/guide-padel-debutant",
            title="Guide padel debutant",
            meta_description="Conseils padel",
            h1=["Guide padel debutant"],
            word_count=700,
        )
        page_b = AuditPage(
            url="https://example.com/guide-padel-confirmes",
            title="Guide padel debutant avance",
            meta_description="Conseils padel avances",
            h1=["Guide padel debutant avance"],
            word_count=700,
        )

        report = build_report([home, page_a, page_b], domain="example.com", overlap_enabled=False)

        self.assertEqual(report.possible_content_overlap, [])
        self.assertEqual(report.summary["possible_content_overlap_pairs"], 0)

    def test_crawl_page_parses_html_once(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <h1>Guide SEO</h1>
              <p>{copy}</p>
              <a href="/blog/guide-seo">Guide</a>
            </main>
          </body>
        </html>
        """.format(copy="mot " * 200)
        limited_response = SimpleNamespace(
            url="https://example.com/",
            status_code=200,
            skip_reason="",
            text=html,
        )
        import audit as audit_module

        original_parser = audit_module.BeautifulSoup
        with patch("audit.fetch_limited_html", return_value=limited_response), patch(
            "audit.BeautifulSoup",
            side_effect=original_parser,
        ) as mock_parser:
            page = crawl_page(
                "https://example.com/",
                session=object(),  # type: ignore[arg-type]
                timeout=5,
                max_html_bytes=200_000,
                max_links_per_page=10,
                max_redirects=4,
            )

        self.assertIsNotNone(page)
        self.assertEqual(mock_parser.call_count, 1)

    def test_crawl_page_extracts_indexation_and_page_score_signals(self) -> None:
        html = """
        <html>
          <head>
            <title>Guide SEO complet pour WordPress</title>
            <meta name="description" content="Un guide SEO complet pour améliorer les pages WordPress avec des exemples concrets.">
            <meta name="robots" content="noindex,follow">
            <link rel="canonical" href="https://other.example/guide-seo">
          </head>
          <body>
            <main>
              <h1>Guide SEO complet</h1>
              <p>{copy}</p>
              <a href="/blog/a">Lire plus</a>
              <a href="/blog/b">Lire plus</a>
              <a href="/blog/c">Lire plus</a>
              <a href="/blog/d">Lire plus</a>
              <a href="/blog/e">Lire plus</a>
            </main>
          </body>
        </html>
        """.format(copy="mot " * 500)
        limited_response = SimpleNamespace(
            url="https://example.com/blog/guide-seo",
            request_url="https://example.com/blog/guide-seo",
            status_code=200,
            skip_reason="",
            text=html,
            redirect_count=1,
        )

        with patch("audit.fetch_limited_html", return_value=limited_response):
            page = crawl_page(
                "https://example.com/blog/guide-seo",
                session=object(),  # type: ignore[arg-type]
                timeout=4,
                max_html_bytes=100_000,
                max_links_per_page=10,
                max_redirects=4,
            )

        self.assertIsNotNone(page)
        assert page is not None
        self.assertTrue(page.is_noindex)
        self.assertEqual(page.canonical_status, "cross_domain")
        self.assertEqual(page.page_type, "article")
        self.assertEqual(page.generic_internal_anchor_count, 5)

        report = build_report([page], domain="example.com")

        self.assertEqual(report.summary["noindex_pages"], 1)
        self.assertEqual(report.summary["canonical_cross_domain_pages"], 1)
        self.assertLess(report.pages[0]["page_health_score"], 100)

    def test_robots_parser_blocks_disallowed_paths(self) -> None:
        rules = parse_robots_txt(
            """
            User-agent: *
            Disallow: /private
            Sitemap: https://example.com/sitemap.xml
            """
        )

        self.assertEqual(rules["sitemaps"], ["https://example.com/sitemap.xml"])
        self.assertFalse(robots_can_fetch({"disallow": rules["disallow"]}, "https://example.com/private/page"))
        self.assertTrue(robots_can_fetch({"disallow": rules["disallow"]}, "https://example.com/blog/page"))

    def test_classify_page_type_uses_url_and_heading_hints(self) -> None:
        self.assertEqual(classify_page_type("https://example.com/"), "homepage")
        self.assertEqual(classify_page_type("https://example.com/blog/test"), "article")
        self.assertEqual(classify_page_type("https://example.com/product/test"), "product")
        self.assertEqual(classify_page_type("https://example.com/any", title="Guide complet"), "article")

    def test_find_dated_references_ignores_current_year_but_flags_older_dates(self) -> None:
        references = find_dated_references(
            text="Mise a jour octobre 2024 pour le guide complet.",
            title="Guide renovation 2026",
            url="https://example.com/guide-renovation-2025",
            reference_date=datetime(2026, 4, 16),
        )

        joined = " | ".join(references)
        self.assertIn("2025", joined)
        self.assertIn("octobre 2024", joined.lower())
        self.assertNotIn("2026", joined)
        self.assertNotIn("'26'", joined)


class ObservedHealthScoreTests(unittest.TestCase):
    def test_empty_pages_returns_zero(self) -> None:
        score = compute_observed_health_score(
            pages=[],
            possible_overlap=[],
            probable_orphans=[],
            duplicate_titles={},
            duplicate_metas={},
            weak_internal_linking=[],
        )

        self.assertEqual(score, 0)

    def test_only_error_pages_returns_zero(self) -> None:
        pages = [
            make_page(url="https://example.com/a", status_code=404, content_like=False),
            make_page(url="https://example.com/b", status_code=404, content_like=False),
        ]

        score = compute_observed_health_score(
            pages=pages,
            possible_overlap=[],
            probable_orphans=[],
            duplicate_titles={},
            duplicate_metas={},
            weak_internal_linking=[],
        )

        self.assertEqual(score, 0)

    def test_clean_site_returns_100(self) -> None:
        pages = [
            make_page(
                url=f"https://example.com/blog/page-{index}",
                title=f"Guide SEO {index:02d} propre et utile",
                meta_description=f"Meta description propre et utile pour la page {index:02d} avec une longueur ideale.",
                h1=[f"Guide SEO {index:02d}"],
                word_count=800,
                depth=2,
            )
            for index in range(10)
        ]

        score = compute_observed_health_score(
            pages=pages,
            possible_overlap=[],
            probable_orphans=[],
            duplicate_titles={},
            duplicate_metas={},
            weak_internal_linking=[],
        )

        self.assertEqual(score, 100)

    def test_thin_content_penalty_bounded_at_22(self) -> None:
        pages = [
            make_page(url=f"https://example.com/blog/thin-{index}", word_count=120)
            for index in range(10)
        ]

        score = compute_observed_health_score(
            pages=pages,
            possible_overlap=[],
            probable_orphans=[],
            duplicate_titles={},
            duplicate_metas={},
            weak_internal_linking=[],
        )

        self.assertEqual(score, 78)

    def test_duplicate_titles_penalty_bounded_at_18(self) -> None:
        pages = [make_page(url=f"https://example.com/blog/page-{index}") for index in range(10)]
        duplicate_titles = {
            f"duplicate-title-{index}": [
                f"https://example.com/blog/dup-{index}-a",
                f"https://example.com/blog/dup-{index}-b",
            ]
            for index in range(10)
        }

        score = compute_observed_health_score(
            pages=pages,
            possible_overlap=[],
            probable_orphans=[],
            duplicate_titles=duplicate_titles,
            duplicate_metas={},
            weak_internal_linking=[],
        )

        self.assertEqual(score, 82)

    def test_combined_penalties_do_not_underflow(self) -> None:
        pages = [
            make_page(
                url=f"https://example.com/blog/bad-{index}",
                title="",
                meta_description="",
                h1=[],
                word_count=120,
                dated_references=["2024"],
                images_without_alt=8,
                depth=5,
                has_structured_data=False,
                meaningful_h1_count=0,
            )
            for index in range(10)
        ]
        possible_overlap = [{"title_1": "A", "title_2": "B", "similarity": 91.0} for _ in range(10)]
        probable_orphans = [f"https://example.com/orphan-{index}" for index in range(10)]
        duplicate_titles = {
            f"title-{index}": [f"https://example.com/a-{index}", f"https://example.com/b-{index}"]
            for index in range(10)
        }
        duplicate_metas = {
            f"meta-{index}": [f"https://example.com/a-{index}", f"https://example.com/b-{index}"]
            for index in range(10)
        }
        weak_internal_linking = [f"https://example.com/weak-{index}" for index in range(10)]

        score = compute_observed_health_score(
            pages=pages,
            possible_overlap=possible_overlap,
            probable_orphans=probable_orphans,
            duplicate_titles=duplicate_titles,
            duplicate_metas=duplicate_metas,
            weak_internal_linking=weak_internal_linking,
        )

        self.assertEqual(score, 0)
        self.assertGreaterEqual(score, 0)

    def test_dated_content_alone_caps_penalty_at_14(self) -> None:
        pages = [
            make_page(url=f"https://example.com/blog/page-{index}", dated_references=["2024"])
            for index in range(10)
        ]

        score = compute_observed_health_score(
            pages=pages,
            possible_overlap=[],
            probable_orphans=[],
            duplicate_titles={},
            duplicate_metas={},
            weak_internal_linking=[],
        )

        self.assertEqual(score, 86)

    def test_deep_pages_penalty_scales_linearly_until_cap(self) -> None:
        scores = []
        for count in [1, 2, 3, 4, 5]:
            pages = [
                make_page(url=f"https://example.com/blog/deep-{index}", depth=4)
                for index in range(count)
            ]
            scores.append(
                compute_observed_health_score(
                    pages=pages,
                    possible_overlap=[],
                    probable_orphans=[],
                    duplicate_titles={},
                    duplicate_metas={},
                    weak_internal_linking=[],
                )
            )

        self.assertEqual(scores, [97, 94, 91, 88, 88])

    def test_score_is_clamped_0_100(self) -> None:
        clean_score = compute_observed_health_score(
            pages=[make_page(url="https://example.com/blog/clean")],
            possible_overlap=[],
            probable_orphans=[],
            duplicate_titles={},
            duplicate_metas={},
            weak_internal_linking=[],
        )
        bad_score = compute_observed_health_score(
            pages=[
                make_page(
                    url=f"https://example.com/blog/catastrophe-{index}",
                    title="",
                    meta_description="",
                    h1=[],
                    word_count=100,
                    dated_references=["2024"],
                    images_without_alt=10,
                    depth=6,
                    meaningful_h1_count=0,
                )
                for index in range(12)
            ],
            possible_overlap=[{"title_1": "A", "title_2": "B", "similarity": 90.0} for _ in range(12)],
            probable_orphans=[f"https://example.com/orphan-{index}" for index in range(12)],
            duplicate_titles={f"title-{index}": ["a", "b"] for index in range(12)},
            duplicate_metas={f"meta-{index}": ["a", "b"] for index in range(12)},
            weak_internal_linking=[f"https://example.com/weak-{index}" for index in range(12)],
        )

        self.assertGreaterEqual(clean_score, 0)
        self.assertLessEqual(clean_score, 100)
        self.assertGreaterEqual(bad_score, 0)
        self.assertLessEqual(bad_score, 100)


if __name__ == "__main__":
    unittest.main()
