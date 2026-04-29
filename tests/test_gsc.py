from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from gsc import (
    analyze_pages,
    build_report,
    calculate_ctr,
    compare_gsc_periods,
    derive_auto_stopwords,
    detect_cannibalization_groups,
    detect_csv_dialect,
    detect_possible_query_overlap,
    estimate_recoverable_clicks,
    format_ctr,
    generate_snippet_recommendation,
    load_gsc_csv,
    load_appareils,
    load_pays,
    match_gsc_page_to_crawl,
    normalize_url_for_matching,
    parse_ctr,
    parse_number,
    parse_pages_csv,
    parse_queries_csv,
    render_report,
    run_gsc_analysis,
)
from models import AuditPage, GSCPageAnalysis, GSCPageData, GSCQueryData


class GSCAnalysisTests(unittest.TestCase):
    def test_parse_and_overlap_filter_structural_urls(self) -> None:
        pages = parse_pages_csv("tests/fixtures/pages_recent.csv")
        queries = parse_queries_csv("tests/fixtures/queries.csv")
        overlap = detect_possible_query_overlap(pages, queries)

        self.assertEqual(len(pages), 2)
        self.assertFalse(any(page.url.endswith("/contact") for page in pages))
        self.assertIsInstance(overlap, dict)

    def test_impact_label_mentions_period_not_month(self) -> None:
        analysis = GSCPageAnalysis(
            url="https://example.com/guide-padel",
            clicks=12,
            impressions=1000,
            ctr=0.012,
            position=8.4,
        )
        gain, label = estimate_recoverable_clicks(analysis)

        self.assertIsNotNone(gain)
        self.assertIn("période analysée", label)
        self.assertNotIn("mois", label.lower())

    def test_build_report_deduplicates_urls_across_sections(self) -> None:
        shared = GSCPageAnalysis(
            url="https://example.com/tournoi-padel-p100/",
            clicks=5,
            impressions=1000,
            ctr=0.005,
            position=8.0,
            click_delta=-20,
            impression_delta=-200,
            position_delta=2.0,
            score=72,
            priority="HIGH",
            actions=[
                "Revoir title et méta description pour mieux convertir les impressions",
                "Revoir title et méta description pour mieux convertir les impressions",
                "Densifier le contenu avec sections, FAQ et signaux de fraîcheur",
            ],
            estimated_recoverable_clicks=55,
            impact_label="+55 clics récupérables estimés sur la période analysée si la page gagne environ 3 positions",
            possible_overlap_queries=["tournoi padel"],
        )
        near = GSCPageAnalysis(
            url="https://example.com/guide-raquette/",
            clicks=10,
            impressions=180,
            ctr=0.055,
            position=11.0,
            score=32,
            priority="LOW",
            actions=["Renforcer fortement le contenu et le maillage interne"],
            estimated_recoverable_clicks=12,
        )

        report = build_report([shared, near])
        all_urls = [page["url"] for section in report["sections"] for page in section["pages"]]

        self.assertEqual(len(all_urls), len(set(all_urls)))
        self.assertIn("https://example.com/tournoi-padel-p100/", all_urls)

    def test_build_report_deduplicates_actions_per_page(self) -> None:
        item = GSCPageAnalysis(
            url="https://example.com/title-test/",
            clicks=2,
            impressions=600,
            ctr=0.003,
            position=9.0,
            score=70,
            priority="HIGH",
            actions=[
                "Revoir title et méta description pour mieux convertir les impressions",
                "Revoir title et méta description pour mieux convertir les impressions",
            ],
            estimated_recoverable_clicks=30,
        )

        report = build_report([item])
        for section in report["sections"]:
            for page in section["pages"]:
                self.assertEqual(len(page["actions"]), len(set(page["actions"])))

    def test_analyze_pages_sets_priorities(self) -> None:
        current = parse_pages_csv("tests/fixtures/pages_recent.csv")
        previous = parse_pages_csv("tests/fixtures/pages_old.csv")
        results = analyze_pages(current=current, previous=previous, possible_overlap={})

        self.assertEqual(results[0].priority, "HIGH")
        self.assertTrue(any(item.click_delta is not None for item in results))

    def test_derive_auto_stopwords_picks_common_tokens(self) -> None:
        pages = [
            GSCPageData(url="https://example.com/padel-raquette-test-1"),
            GSCPageData(url="https://example.com/padel-raquette-test-2"),
            GSCPageData(url="https://example.com/padel-raquette-test-3"),
            GSCPageData(url="https://example.com/padel-raquette-test-4"),
            GSCPageData(url="https://example.com/padel-raquette-test-5"),
            GSCPageData(url="https://example.com/tennis-raquette-test-6"),
        ]

        stopwords = derive_auto_stopwords(pages, threshold=0.6)

        self.assertIn("padel", stopwords)

    def test_detect_overlap_respects_extra_stopwords(self) -> None:
        pages = [
            GSCPageData(url="https://example.com/padel-technique-service", position=8.0),
            GSCPageData(url="https://example.com/padel-chaussures-test", position=9.0),
        ]
        queries = [
            GSCQueryData(query="padel technique", impressions=60, position=6.0),
        ]

        overlap = detect_possible_query_overlap(pages, queries)
        filtered_overlap = detect_possible_query_overlap(pages, queries, extra_stopwords={"padel"})

        self.assertTrue(overlap)
        self.assertEqual(filtered_overlap, {})

    def test_run_gsc_analysis_integrates_auto_stopwords(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            current_csv = root / "current.csv"
            queries_csv = root / "queries.csv"
            output_csv = root / "report.csv"

            current_csv.write_text(
                "page,clicks,impressions,ctr,position\n"
                "https://example.com/padel-technique-service,12,400,0.03,8\n"
                "https://example.com/padel-chaussures-test,9,350,0.025,9\n"
                "https://example.com/padel-terrain-guide,8,320,0.025,10\n",
                encoding="utf-8",
            )
            queries_csv.write_text(
                "query,clicks,impressions,ctr,position\n"
                "padel technique,15,120,0.125,6\n",
                encoding="utf-8",
            )

            results = run_gsc_analysis(
                current_csv=str(current_csv),
                queries_csv=str(queries_csv),
                output_csv=str(output_csv),
                auto_niche_stopwords=True,
            )

            self.assertTrue(output_csv.exists())

        self.assertTrue(results)
        self.assertTrue(all(not item.possible_overlap_queries for item in results))

    def test_run_gsc_analysis_writes_action_oriented_html(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_csv = root / "report.csv"
            output_html = root / "report.html"

            run_gsc_analysis(
                current_csv="tests/fixtures/pages_recent.csv",
                previous_csv="tests/fixtures/pages_old.csv",
                queries_csv="tests/fixtures/queries.csv",
                output_csv=str(output_csv),
                output_html=str(output_html),
                site_name="Example",
            )

            report = output_html.read_text(encoding="utf-8")

        self.assertIn("Plan d’action SEO basé sur Google Search Console", report)
        self.assertIn("Domaine analysé", report)
        self.assertIn("Example", report)
        self.assertIn("Les 3 priorités du mois", report)
        self.assertIn("Top pages à traiter en premier", report)
        self.assertIn("Exploitation des requêtes", report)
        self.assertIn("Pages déjà visibles à renforcer", report)
        self.assertIn("Export Pages précédent: fourni", report)
        self.assertIn("Exporter en PDF", report)
        self.assertIn("@media print", report)
        self.assertNotIn("ACTION CONSEILLEE", report)
        self.assertNotIn("PRIORITE", report)
        self.assertNotIn("HIGH", report)

    def test_run_gsc_analysis_accepts_full_search_console_zip(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            archive = root / "performance-search.zip"
            output_csv = root / "report.csv"
            output_html = root / "report.html"

            with ZipFile(archive, "w") as zip_file:
                zip_file.writestr(
                    "Pages.csv",
                    "Pages les plus populaires,Clics,Impressions,CTR,Position\n"
                    "https://example.com/guide-padel,12,1000,1.2%,8.4\n"
                    "https://example.com/test-padel,4,500,0.8%,12\n",
                )
                zip_file.writestr(
                    "Requêtes.csv",
                    "Requêtes les plus fréquentes,Clics,Impressions,CTR,Position\n"
                    "guide padel,10,800,1.25%,7\n",
                )
                zip_file.writestr("Pays.csv", "Pays,Clics,Impressions,CTR,Position\nFrance,1,2,50%,1\n")
                zip_file.writestr("Appareils.csv", "Appareil,Clics,Impressions,CTR,Position\nMobile,1,2,50%,1\n")

            results = run_gsc_analysis(
                current_csv=str(archive),
                output_csv=str(output_csv),
                output_html=str(output_html),
            )

            report = output_html.read_text(encoding="utf-8")
            csv_exists = output_csv.exists()

        self.assertEqual(len(results), 2)
        self.assertTrue(csv_exists)
        self.assertIn("Export Requêtes: fourni", report)
        self.assertIn("Origine du trafic", report)
        self.assertIn("France", report)
        self.assertIn("Mobile", report)

    def test_gsc_zip_detection_uses_columns_when_filename_is_ambiguous(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            archive = root / "performance-search.zip"

            with ZipFile(archive, "w") as zip_file:
                zip_file.writestr(
                    "export_1.csv",
                    "Pages les plus populaires,Clics,Impressions,CTR,Position\n"
                    "https://example.com/guide-padel,12,1000,1.2%,8.4\n",
                )
                zip_file.writestr(
                    "Reque_tes.csv",
                    "Requêtes les plus fréquentes,Clics,Impressions,CTR,Position\n"
                    "guide padel,10,800,1.25%,7\n",
                )

            pages = parse_pages_csv(str(archive))
            queries = parse_queries_csv(str(archive))

        self.assertEqual(len(pages), 1)
        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].query, "guide padel")

    def test_missing_optional_gsc_csvs_do_not_crash_report_rendering(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pages_csv = root / "Pages.csv"
            pages_csv.write_text(
                "Page,Clicks,Impressions,CTR,Position\n"
                "https://example.com/guide,4,100,4%,12\n",
                encoding="utf-8",
            )

            report = build_report(
                pages_csv,
                graphique_csv=root / "Graphique.csv",
                pays_csv=root / "Pays.csv",
                appareils_csv=root / "Appareils.csv",
            )
            html = render_report(report)

        self.assertIsNotNone(html)
        self.assertNotIn("Aucun élément prioritaire dans cette section", html)

    def test_dimension_loaders_sort_and_limit_data(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pays_csv = root / "Pays.csv"
            appareils_csv = root / "Appareils.csv"
            pays_csv.write_text(
                "Pays,Clics,Impressions,CTR,Position\n"
                "Canada,49,100,49%,2\n"
                "France,1891,2000,94.55%,1\n"
                "Belgique,167,300,55.6%,1.5\n",
                encoding="utf-8",
            )
            appareils_csv.write_text(
                "Appareil,Clics,Impressions,CTR,Position\n"
                "Ordinateur,653,1000,65.3%,2\n"
                "Mobile,1636,2000,81.8%,1\n",
                encoding="utf-8",
            )

            pays = load_pays(str(pays_csv))
            appareils = load_appareils(str(appareils_csv))

        self.assertEqual(pays[0]["pays"], "France")
        self.assertEqual(appareils[0]["appareil"], "Mobile")

    def test_phase2_gsc_csv_import_is_tolerant(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            export = root / "pages_before.csv"
            export.write_text(
                " Page ; Clicks ; Impressions ; CTR ; Average position \n"
                " https://www.example.com/Guide/?utm=1 ; 1 234 ; 2,500 ; 12,5% ; 4,2 \n",
                encoding="utf-8",
            )

            rows = load_gsc_csv(export)
            dialect = detect_csv_dialect(export)

        self.assertEqual(dialect.delimiter, ";")
        self.assertEqual(rows[0]["page"], "https://www.example.com/Guide/?utm=1")
        self.assertEqual(rows[0]["clicks"], 1234)
        self.assertEqual(rows[0]["impressions"], 2500)
        self.assertAlmostEqual(rows[0]["ctr"], 1234 / 2500)
        self.assertAlmostEqual(rows[0]["position"], 4.2)

    def test_phase2_parsing_and_period_comparison_handle_zero_division(self) -> None:
        self.assertEqual(parse_number("1 234"), 1234)
        self.assertEqual(parse_number("1,25"), 1.25)
        self.assertAlmostEqual(parse_ctr("4,5%"), 0.045)
        comparison = compare_gsc_periods(
            before_df=[{"page": "https://example.com/a", "clicks": 0, "impressions": 0, "ctr": 0, "position": 0}],
            after_df=[{"page": "https://example.com/a", "clicks": 10, "impressions": 100, "ctr": 0.1, "position": 5}],
            key_column="page",
        )

        self.assertIsNone(comparison[0]["clicks_delta_pct"])
        self.assertEqual(comparison[0]["status"], "existing")
        self.assertEqual(comparison[0]["clicks_delta"], 10)

    def test_ctr_is_recalculated_from_clicks_and_impressions(self) -> None:
        self.assertAlmostEqual(calculate_ctr(1, 1564), 0.000639386, places=6)
        self.assertEqual(format_ctr(calculate_ctr(1, 1564)), "0,06 %")
        self.assertEqual(format_ctr(calculate_ctr(155, 13689)), "1,13 %")
        self.assertEqual(format_ctr(calculate_ctr(2322, 131243)), "1,77 %")

    def test_snippet_recommendation_avoids_generic_ai_phrases(self) -> None:
        snippet = generate_snippet_recommendation(
            page="https://eversportzone.com/tournoi-padel-p100/",
            main_query="tournoi padel p100",
            page_type="cluster guide",
            intent="Recherche d’explication pratique",
            gsc_data={},
        )
        combined = f"{snippet['title']} {snippet['meta']}".lower()

        self.assertIn("p100", combined)
        self.assertNotIn("guide clair", combined)
        self.assertNotIn("points clés", combined)
        self.assertNotIn("découvrez les informations essentielles", combined)

    def test_detect_cannibalization_groups_stays_cluster_specific(self) -> None:
        pages = [
            GSCPageData(url="https://example.com/tournoi-padel-p100/", impressions=1000, position=8),
            GSCPageData(url="https://example.com/tournoi-padel-p250/", impressions=800, position=9),
            GSCPageData(url="https://example.com/tenir-raquette-padel/", impressions=700, position=7),
        ]
        queries = [
            GSCQueryData(query="tournoi padel p100", impressions=200, position=8),
            GSCQueryData(query="tournoi padel inscription", impressions=160, position=9),
        ]

        groups = detect_cannibalization_groups(pages, queries)

        self.assertEqual(len(groups), 1)
        self.assertIn("tournoi", groups[0]["topic"])
        self.assertNotIn("https://example.com/tenir-raquette-padel/", groups[0]["urls"])

    def test_phase2_url_normalization_and_crawl_matching(self) -> None:
        page = AuditPage(
            url="https://example.com/final/",
            requested_url="http://www.example.com/old?x=1",
            final_url="https://example.com/final/",
            canonical="https://www.example.com/final#intro",
        )

        match = match_gsc_page_to_crawl("http://example.com/final?utm_source=x#frag", [page])

        self.assertEqual(normalize_url_for_matching("HTTP://www.Example.com/Final/?utm=1#x"), "example.com/final")
        self.assertTrue(match["matched"])
        self.assertEqual(match["match_type"], "final_url")


if __name__ == "__main__":
    unittest.main()
