from __future__ import annotations

import unittest

from web_ui.gsc_report_renderer import render_gsc_report


def _minimal_report(**overrides) -> dict:
    base = {
        "mode": "executive",
        "lang": "fr",
        "title": "Test GSC Report",
        "site_name": "example.com",
        "period_label": "mars 2026",
        "generated_at": "2026-03-15",
        "report_mode_label": "Analyse de la période actuelle",
        "report_mode": "current_period_only",
        "executive_summary": "Résumé test.",
        "estimated_gain_value": "jusqu'à 500 clics non captés",
        "estimated_gain_note": "",
        "kpis": [
            {"label": "Pages analysées", "value": "42"},
            {"label": "Clics totaux", "value": "1 234"},
            {"label": "Impressions totales", "value": "98 765"},
            {"label": "Taux de clic moyen", "value": "1,2 %"},
            {"label": "Position moyenne", "value": "11,4"},
            {"label": "Pages prioritaires", "value": "3"},
        ],
        "monthly_priorities": [
            {
                "title": "Améliorer les résultats Google",
                "why": "Les pages visibles doivent donner une raison plus claire de cliquer.",
                "action": "Réécrire titles et meta descriptions.",
                "impact": "Potentiel d'amélioration du CTR.",
            }
        ],
        "priority_pages": [],
        "top_query_opportunities": [],
        "snippet_pages": [],
        "snippet_section_note": "",
        "business_opportunities": [],
        "cannibalization_groups": [],
        "url_variant_pairs": [],
        "annex_files": [
            {"name": "pages_opportunities.csv", "description": "Pages prioritaires", "category": "prioritaire"},
        ],
        "action_plan_30_days": None,
        "language_paths": {},
        "html_output_path": "",
    }
    base.update(overrides)
    return base


class RenderGscReportTests(unittest.TestCase):

    def test_returns_string(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIsInstance(result, str)

    def test_starts_with_doctype(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertTrue(result.strip().startswith("<!DOCTYPE html>"))

    def test_contains_site_name(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("example.com", result)

    def test_contains_design_tokens(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("--paper:#faf9f4", result)
        self.assertIn("--hot:#b45309", result)
        self.assertIn("--accent:#1f3a8a", result)

    def test_contains_google_fonts(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("Fraunces", result)
        self.assertIn("JetBrains+Mono", result)

    def test_cover_page_rendered(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn('class="page cover no-running"', result)
        self.assertIn("Opportunités SEO", result)

    def test_cover_title_uses_site_name(self) -> None:
        result = render_gsc_report(_minimal_report(site_name="eversportzone.com"))
        self.assertIn('<h1 class="cover-title display" style="font-family: system-ui">eversportzone.com</h1>', result)
        self.assertNotIn("Faire cliquer", result)
        self.assertNotIn("ce qui est", result)

    def test_kpi_grid_rendered(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("kpi-grid", result)
        self.assertIn("Pages analysées", result)
        self.assertIn("42", result)

    def test_sections_present(self) -> None:
        result = render_gsc_report(_minimal_report())
        for anchor in ("synthese", "decision-rapide", "pages-prioritaires", "requetes", "snippets", "business"):
            self.assertIn(f'id="{anchor}"', result, f"missing section #{anchor}")

    def test_estimate_box_with_value(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("estimate-box", result)
        self.assertIn("Potentiel théorique détecté", result)

    def test_estimate_box_absent_when_empty(self) -> None:
        report = _minimal_report(estimated_gain_value="", estimated_gain_note="")
        result = render_gsc_report(report)
        # The CSS defines `.estimate-box` so we check the class attribute isn't used
        self.assertNotIn("class='estimate-box'", result)
        self.assertNotIn('class="estimate-box"', result)

    def test_empty_state_for_priority_pages(self) -> None:
        result = render_gsc_report(_minimal_report(priority_pages=[]))
        self.assertIn("empty-state", result)

    def test_priority_card_rendered(self) -> None:
        report = _minimal_report(
            priority_pages=[
                {
                    "url": "https://example.com/guide-padel",
                    "slug": "guide-padel",
                    "priority": "p1",
                    "priority_label": "P1",
                    "diagnostic": "Fort potentiel SEO non exploité.",
                    "recommendation": "Recentrer la page sur l'intention principale.",
                    "metrics": {
                        "Clics": "120",
                        "Impressions": "4 500",
                        "CTR": "2,7 %",
                        "Position": "7.3",
                        "Gain estimé": "+200",
                    },
                    "action_type_labels": ["rewrite"],
                    "effort": "Moyen",
                    "impact": "Fort",
                    "business_value": "medium",
                    "monetization_possible": "lead",
                    "target_metric": "",
                    "serp_anomaly": "",
                }
            ]
        )
        result = render_gsc_report(report)
        self.assertIn("guide-padel", result)
        self.assertIn("page-card", result)
        self.assertIn("priority-badge--high", result)
        self.assertIn("Fort potentiel SEO non exploité.", result)

    def test_monthly_priority_rendered(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("priorities-list", result)
        self.assertIn("Améliorer les résultats Google", result)

    def test_annex_links_rendered(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("pages_opportunities.csv", result)
        self.assertIn("annex-grid", result)

    def test_print_css_present(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("@media print", result)
        self.assertIn("@page", result)

    def test_export_pdf_script(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("exportPDF", result)

    def test_lang_fr_default(self) -> None:
        report = _minimal_report()
        del report["lang"]
        result = render_gsc_report(report)
        self.assertIn('lang="fr"', result)

    def test_position_bar_rendered_for_page_card(self) -> None:
        report = _minimal_report(
            priority_pages=[
                {
                    "url": "https://example.com/test",
                    "slug": "test",
                    "priority": "p2",
                    "priority_label": "P2",
                    "diagnostic": "Test.",
                    "recommendation": "",
                    "metrics": {"Position": "12.5"},
                    "action_type_labels": [],
                    "effort": "Faible",
                    "impact": "Moyen",
                    "business_value": "low",
                    "monetization_possible": "",
                    "target_metric": "",
                    "serp_anomaly": "",
                }
            ]
        )
        result = render_gsc_report(report)
        self.assertIn("position-bar", result)

    def test_no_xss_in_site_name(self) -> None:
        report = _minimal_report(site_name='<script>alert("xss")</script>')
        result = render_gsc_report(report)
        self.assertNotIn("<script>alert", result)
        self.assertIn("&lt;script&gt;", result)

    def test_nav_links_present(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("gsc-nav", result)
        self.assertIn("href='#synthese'", result)

    def test_filter_bar_present(self) -> None:
        result = render_gsc_report(_minimal_report())
        self.assertIn("filter-bar", result)
        self.assertIn("filter-btn", result)


if __name__ == "__main__":
    unittest.main()
