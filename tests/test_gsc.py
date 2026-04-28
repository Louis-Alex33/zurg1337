from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from gsc import (
    analyze_pages,
    derive_auto_stopwords,
    detect_possible_query_overlap,
    estimate_recoverable_clicks,
    parse_pages_csv,
    parse_queries_csv,
    run_gsc_analysis,
)
from models import GSCPageAnalysis, GSCPageData, GSCQueryData


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
        self.assertIn("periode analysee", label)
        self.assertNotIn("mois", label.lower())

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

        self.assertIn("Plan d'action GSC - Example", report)
        self.assertIn("1. Pages a traiter en premier", report)
        self.assertIn("3. Snippets a retravailler", report)
        self.assertIn("Export Pages precedent: fourni", report)

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

            results = run_gsc_analysis(
                current_csv=str(archive),
                output_csv=str(output_csv),
                output_html=str(output_html),
            )

            report = output_html.read_text(encoding="utf-8")
            csv_exists = output_csv.exists()

        self.assertEqual(len(results), 2)
        self.assertTrue(csv_exists)
        self.assertIn("Export Requetes: fourni", report)


if __name__ == "__main__":
    unittest.main()
