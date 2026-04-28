from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from unittest.mock import patch

from audit_report_design import (
    build_local_seo_suggestion,
    fit_meta_description,
    fit_seo_title,
    render_premium_audit_report,
    sanitize_seo_suggestion,
    score_color_class,
    slug_to_title,
)
from audit import (
    audit_domains,
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
    write_audit_html_report,
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
    def test_report_design_helpers_match_expected_labels(self) -> None:
        self.assertEqual(slug_to_title("padel-porto-vecchio"), "Padel Porto Vecchio")
        self.assertEqual(
            slug_to_title("test-dreampadel-match-carbon-2-0-2025"),
            "Test Dreampadel Match Carbon 2.0 2025",
        )
        self.assertEqual(score_color_class(45), "score-low")
        self.assertEqual(score_color_class(80), "score-mid")
        self.assertEqual(score_color_class(96), "score-high")

    def test_local_seo_suggestion_keeps_valid_title_out_of_desc_fix(self) -> None:
        title = "Cutest Planners For 2025: Keeping Your Life Organized"
        suggestion = build_local_seo_suggestion(
            {
                "url": "https://example.com/cutest-planners-for-keeping-your-life-organized",
                "titre_google": title,
                "description_google": "",
            }
        )

        self.assertNotIn("titre_suggere", suggestion)
        self.assertNotIn("titre_longueur", suggestion)
        self.assertIn("description_suggeree", suggestion)
        self.assertIn("Find essential information", suggestion["description_suggeree"])
        self.assertNotIn("Retrouvez", suggestion["description_suggeree"])

    def test_fit_seo_title_does_not_pad_valid_title_with_generic_suffix(self) -> None:
        title = "Guide to the Hottest Summer Style Trends in 2025"

        self.assertEqual(fit_seo_title(title, "https://example.com/hottest-summer-style-trends-2025"), title)

    def test_sanitize_seo_suggestion_removes_duplicate_valid_title(self) -> None:
        title = "Cutest Planners For 2025: Keeping Your Life Organized"
        suggestion = sanitize_seo_suggestion(
            {
                "url": "https://example.com/cutest-planners-for-keeping-your-life-organized",
                "titre_google": title,
                "description_google": "",
            },
            {
                "url": "https://example.com/cutest-planners-for-keeping-your-life-organized",
                "titre_suggere": title,
                "titre_longueur": len(title),
                "description_suggeree": "Retrouvez les informations essentielles sur cette page, avec une description claire et utile pour Google.",
            },
        )

        self.assertNotIn("titre_suggere", suggestion)
        self.assertIn("description_suggeree", suggestion)
        self.assertIn("Find essential information", suggestion["description_suggeree"])
        self.assertNotIn("Retrouvez", suggestion["description_suggeree"])

    def test_fit_meta_description_keeps_french_for_french_pages(self) -> None:
        description = fit_meta_description(
            "https://example.com/douche-senior-bordeaux-prix-aides",
            "Douche senior Bordeaux : prix 2026, aides MaPrimeAdapt",
        )

        self.assertIn("Retrouvez les informations", description)

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

    def test_audit_domains_raises_request_budget_to_requested_page_budget(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            with (
                patch("audit.crawl_site", return_value=[]) as mock_crawl_site,
                patch("audit.record_audit_report"),
            ):
                audit_domains(
                    input_csv=None,
                    output_dir=tmp_dir,
                    site="example.com",
                    max_pages=100,
                    max_total_seconds_per_domain=0,
                    delay=0,
                    history=False,
                    sqlite_index=f"{tmp_dir}/index.sqlite",
                )

        self.assertEqual(mock_crawl_site.call_args.kwargs["max_pages"], 100)
        self.assertEqual(mock_crawl_site.call_args.kwargs["max_total_requests_per_domain"], 100)

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

    def test_crawl_site_records_request_budget_stop_reason(self) -> None:
        pages_by_url = {
            "https://example.com/": AuditPage(
                url="https://example.com/",
                word_count=800,
                internal_links_out=["https://example.com/a", "https://example.com/b"],
            ),
            "https://example.com/a": AuditPage(url="https://example.com/a", word_count=600),
            "https://example.com/b": AuditPage(url="https://example.com/b", word_count=600),
        }
        metadata: dict[str, object] = {}

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
                max_total_requests_per_domain=2,
                delay=0,
                session=object(),  # type: ignore[arg-type]
                metadata=metadata,
            )

        self.assertEqual(len(pages), 2)
        self.assertEqual(metadata["stop_reason"], "max_total_requests_reached")
        self.assertEqual(metadata["max_total_requests_per_domain"], 2)

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

    def test_standalone_audit_html_is_client_facing(self) -> None:
        home = AuditPage(
            url="https://example.com/",
            title="Magazine SEO",
            meta_description="Magazine SEO avec des guides complets pour les lecteurs.",
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
        report = build_report(
            [home, thin],
            domain="example.com",
            crawl_metadata={"crawl_source": "mixed", "stop_reason": "queue_empty", "sitemap_urls_found": 2},
        )

        with TemporaryDirectory() as tmp_dir:
            output = write_audit_html_report(report, Path(tmp_dir) / "audit.html")
            page = output.read_text(encoding="utf-8")

        self.assertIn("Audit SEO", page)
        self.assertIn("Rapport confidentiel", page)
        self.assertIn("Ce qui fonctionne", page)
        self.assertIn("Points d'attention", page)
        self.assertIn("Plan d’action 30 / 60 / 90 jours", page)
        self.assertIn("Matrice impact / effort", page)
        self.assertIn("Pages à revoir en priorité", page)
        self.assertIn("Opportunités éditoriales", page)
        self.assertIn("Prochaines étapes", page)
        self.assertIn("section-finale", page)
        self.assertIn("Annexe technique", page)
        self.assertIn(".premium-report .annexe", page)
        self.assertIn("display: none !important", page)
        self.assertIn("Pourquoi elle ressort", page)

    def test_premium_report_v3_density_regressions_are_rendered(self) -> None:
        current_year = str(datetime.now().year)
        page = render_premium_audit_report(
            {
                "domain": "example.com",
                "audited_at": "2026-04-15T00:47:42",
                "pages_crawled": 3,
                "observed_health_score": 92,
                "summary": {
                    "pages_ok": 3,
                    "pages_with_errors": 0,
                    "missing_titles": 0,
                    "missing_meta_descriptions": 0,
                    "avg_page_health_score": 91,
                    "noindex_pages": 0,
                    "canonical_to_other_url_pages": 0,
                    "weak_internal_linking_pages": 0,
                    "possible_content_overlap_pairs": 0,
                    "dated_content_signals": 2,
                },
                "signal_principal": "Relire les contenus [current_date format='Y']",
                "pages_prioritaires": [
                    {
                        "url": "https://example.com/blog/test",
                        "titre": "Page test",
                        "score": 88,
                        "mots": 600,
                        "observation": "Observation [current_date format=Y]",
                        "action": "Action [current_date format = \"Y\"]",
                        "angle": "Angle [current_date format=Y]",
                    }
                ],
                "signaux": [
                    {
                        "url": "https://example.com/blog/date",
                        "dates": [
                            {"type": "titre", "valeur": "Date visible dans le titre: 2025"},
                            {"type": "titre", "valeur": "Date visible dans le titre: 2024"},
                            {"type": "url", "valeur": "Date visible dans l'URL: 2023"},
                            {"type": "contenu", "valeur": "Date visible dans le contenu: 2022"},
                        ],
                    }
                ],
                "opportunites": ["Mettre à jour [current_date format=Y]"],
                "matrice": {
                    "quick_wins": [{"titre": "Relire les dates", "impact": "élevé", "effort": "faible", "priorite": "haute"}],
                    "projets_structurants": [],
                    "optimisations_simples": [],
                    "backlog": [],
                },
                "urls_crawlees": [
                    {"url": "example.com/", "type": "accueil", "score": 95, "mots": 900, "points": "-"},
                    {"url": "example.com/blog/date", "type": "article", "score": 88, "mots": 600, "points": "date visible"},
                ],
            }
        )

        self.assertNotIn("[current_date", page)
        self.assertIn(f"Angle {current_year}", page)
        self.assertIn('class="report-page executive-page synthese" id="synthese"', page)
        self.assertIn(".premium-report .synthese", page)
        for label in (
            "Pages analysées",
            "Pages saines",
            "Pages en erreur",
            "Descriptions manquantes",
            "Titres manquants",
            "Score moyen",
            "Pages noindex",
            "Canonicals à vérifier",
            "Pages peu reliées",
            "Sujets trop proches",
            "Dates visibles à vérifier",
        ):
            self.assertIn(label, page)
        self.assertIn("is-zero", page)
        self.assertIn("is-warning", page)
        self.assertIn("date-badge--titre", page)
        self.assertIn("dates-table", page)
        self.assertIn("<th>Page</th><th>Titre</th><th>URL</th><th>Contenu</th>", page)
        self.assertIn("2025", page)
        self.assertIn("2024", page)
        self.assertNotIn("titre :", page)
        self.assertIn("Bricolage+Grotesque", page)
        self.assertIn("pages-prioritaires-grid", page)
        self.assertIn("fiche-page", page)
        self.assertIn("finale-grid", page)
        self.assertIn("Voir l'annexe technique (2 URLs)", page)
        self.assertIn("Imprimer avec annexe", page)
        self.assertIn("printWithAnnexe", page)
        self.assertIn("<th>URL</th><th>Type</th><th>Score</th><th>Mots</th><th>Points relevés</th>", page)
        self.assertIn("Les autres quadrants ne présentent pas d'action prioritaire", page)
        self.assertLess(page.find("Prochaines étapes"), page.find("Annexe technique"))

    def test_premium_report_v4_commercial_sections_are_rendered_in_order(self) -> None:
        page = render_premium_audit_report(
            {
                "domain": "example.com",
                "audited_at": "2026-04-15T00:47:42",
                "observed_health_score": 82,
                "summary": {
                    "pages_crawled": 24,
                    "content_like_pages": 9,
                    "pages_ok": 24,
                    "avg_page_health_score": 79,
                    "dated_content_signals": 2,
                    "canonical_to_other_url_pages": 1,
                },
                "business_priority_signals": [
                    {"signal": "Canonicals à vérifier", "severity": "HIGH", "count": 1}
                ],
                "pages_prioritaires": [
                    {
                        "url": "https://example.com/blog/test",
                        "titre": "Page test",
                        "type": "article",
                        "mots": 600,
                        "score": 76,
                    }
                ],
                "benchmark_disponible": True,
                "benchmark": [
                    {
                        "domaine": "concurrent1.fr",
                        "score_estime": 88,
                        "nb_pages_contenu": 120,
                        "signal": "Contenu dense, bon maillage",
                    }
                ],
                "methode": {"pages_visitees": 24, "sitemap_urls": 58},
                "analyste_nom": "Jean Dupont",
                "analyste_titre": "Consultant SEO indépendant",
                "analyste_linkedin": "https://linkedin.com/in/jean-dupont",
            }
        )

        self.assertIn("POUR LE DIRIGEANT", page)
        self.assertIn("Où vous en êtes", page)
        self.assertIn("certaines pages doivent être vérifiées", page)
        self.assertIn("3 à 5h de rédaction", page)
        self.assertIn("Votre position face à la concurrence", page)
        self.assertIn("concurrent1.fr", page)
        self.assertIn("benchmark-vous-badge", page)
        self.assertIn("Jean Dupont", page)
        self.assertIn("Limites de cette analyse", page)
        self.assertIn("Formules disponibles", page)
        self.assertIn("Suivi mensuel", page)
        self.assertIn(".premium-report .offre-suivi", page)
        self.assertIn("display: none !important", page)

        dirigeant = page.find("POUR LE DIRIGEANT")
        synthese = page.find("Synthèse exécutive")
        benchmark = page.find("Votre position face à la concurrence")
        plan = page.find("Plan d’action 30 / 60 / 90 jours")
        conclusion = page.find("Prochaines étapes")
        methode = page.find("MÉTHODE")
        annexe = page.find("Annexe technique")

        self.assertLess(dirigeant, synthese)
        self.assertLess(synthese, benchmark)
        self.assertLess(benchmark, plan)
        self.assertLess(conclusion, methode)
        self.assertLess(methode, annexe)

        dirigeant_block = page[dirigeant:synthese]
        self.assertNotIn("canonical", dirigeant_block.lower())
        self.assertNotIn("noindex", dirigeant_block.lower())

    def test_premium_report_v4_hides_benchmark_when_disabled(self) -> None:
        page = render_premium_audit_report(
            {
                "domain": "example.com",
                "observed_health_score": 82,
                "benchmark_disponible": False,
                "benchmark": [
                    {
                        "domaine": "concurrent1.fr",
                        "score_estime": 88,
                        "nb_pages_contenu": 120,
                        "signal": "Contenu dense",
                    }
                ],
            }
        )

        self.assertNotIn("Votre position face à la concurrence", page)
        self.assertNotIn("concurrent1.fr", page)

    def test_premium_report_v5_identity_perf_suggestions_and_maillage(self) -> None:
        long_slug = "blog/cutest-planners-for-keeping-your-life-organized-in-2026-with-extra-details"
        page = render_premium_audit_report(
            {
                "domain": "example.com",
                "audited_at": "2026-04-15T00:47:42",
                "tool_name": "ZURG 1337",
                "tool_tagline": "Audit SEO automatisé",
                "observed_health_score": 76,
                "summary": {
                    "pages_crawled": 3,
                    "pages_ok": 3,
                    "content_like_pages": 3,
                    "avg_page_health_score": 74,
                    "missing_meta_descriptions": 1,
                    "dated_content_signals": 1,
                },
                "pages_prioritaires": [
                    {
                        "url": f"https://example.com/{long_slug}",
                        "titre": "Planner article",
                        "type": "article",
                        "mots": 850,
                        "score": 70,
                    }
                ],
                "urls_crawlees": [
                    {
                        "url": "https://example.com/",
                        "type": "accueil",
                        "score": 90,
                        "mots": 900,
                        "load_time": 1.2,
                        "redirect_count": 0,
                        "title": "Accueil Example",
                        "meta_description": "Une description suffisamment claire pour la page d'accueil du site Example.",
                        "internal_links_out": [],
                    },
                    {
                        "url": f"https://example.com/{long_slug}",
                        "type": "article",
                        "score": 70,
                        "mots": 850,
                        "load_time": 4.4,
                        "redirect_count": 1,
                        "title": "Cutest Planners For Keeping Your Life Organized In 2026 With Extra Details And Ideas",
                        "meta_description": "",
                        "images_total": 18,
                        "internal_links_out": [],
                    },
                    {
                        "url": "https://example.com/blog/medium-page",
                        "type": "article",
                        "score": 80,
                        "mots": 700,
                        "load_time": 3.2,
                        "redirect_count": 0,
                        "title": "Medium Page Example",
                        "meta_description": "Une description suffisamment claire pour cette page moyenne du site Example.",
                        "images_total": 3,
                        "internal_links_out": [],
                    },
                ],
                "signaux": [
                    {
                        "url": f"https://example.com/{long_slug}",
                        "dates": [{"type": "url", "valeur": "Date visible dans l'URL: 2026"}],
                    }
                ],
            }
        )

        self.assertIn("RAPPORT SEO", page)
        self.assertNotIn("ZURG 1337", page)
        self.assertNotIn("Audit SEO automatisé", page)
        self.assertNotIn("Rapport généré automatiquement", page)
        self.assertNotIn('class="tool-name"', page)
        self.assertNotIn("Consultant SEO", page)

        self.assertIn(long_slug, page)
        self.assertNotIn("cutest-planners-for-keeping-your-life-o…", page)

        self.assertIn("Vitesse de chargement", page)
        perf_block = page[page.find("Vitesse de chargement") : page.find("Titres et descriptions à corriger")]
        self.assertLess(perf_block.find("4.4s"), perf_block.find("3.2s"))
        self.assertIn("Actions ciblées sur les pages lentes", perf_block)
        self.assertEqual(page.count('class="perf-action-card"'), 2)
        self.assertIn(f"{long_slug} : supprimer la redirection mesurée", perf_block)
        self.assertIn("blog/medium-page : isoler les ressources", perf_block)
        self.assertNotIn("Compresser les images", perf_block)
        self.assertNotIn("Les images non compressées sont la première cause de lenteur", perf_block)

        self.assertIn("Titres et descriptions à corriger", page)
        self.assertIn("suggestion-actuel", page)
        self.assertIn("suggestion-propose", page)
        self.assertIn("Titre Google", page)
        self.assertIn("Description Google", page)
        self.assertIn("car.", page)

        self.assertIn("0 liens internes", page)
        self.assertIn("Aucune page ne pointe vers celle-ci", page)

        self.assertLess(page.find("Pages à revoir en priorité"), page.find("Vitesse de chargement"))
        self.assertLess(page.find("Vitesse de chargement"), page.find("Titres et descriptions à corriger"))
        self.assertLess(page.find("Titres et descriptions à corriger"), page.find("Repères complémentaires"))

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
