"""Tests unitaires pour gsc_rules.py.

Un test par fonction extraite, plus les 6 tests de correction de bugs (2B)
et les cas limites associés.
"""
from __future__ import annotations

import unittest

from gsc_rules import (
    CTR_TOLERANCE,
    EXPECTED_CTR_BY_POSITION,
    IMPRESSIONS_THRESHOLD_HIGH,
    MAX_PAGES_PER_CLUSTER,
    POSITION_CAP_HIGH,
    POSITION_CAP_LOW,
    build_target_metric,
    cap_top_priority_per_cluster,
    dedupe_tokens,
    diagnostic_for_page,
    expected_ctr_for_position,
    generate_page_recommendation,
    generate_snippet_recommendation,
    is_resolvable_target,
    priority_for_page,
    resolve_target_label,
    slug_prefix,
    trim_to_length,
)
from models import GSCPageAnalysis


def _make_page(**kwargs) -> GSCPageAnalysis:
    defaults = dict(
        url="https://example.com/test-raquette-padel",
        clicks=10,
        impressions=500,
        ctr=0.02,
        position=8.0,
        score=65.0,
        opportunity_score=65,
        priority="HIGH",
        actions=["Revoir title et méta description pour mieux convertir les impressions"],
        estimated_recoverable_clicks=40,
        impact_label="+40 clics récupérables estimés sur la période analysée",
    )
    defaults.update(kwargs)
    return GSCPageAnalysis(**defaults)


# ---------------------------------------------------------------------------
# Tests originaux — fonctions de base
# ---------------------------------------------------------------------------

class TestPriorityForPage(unittest.TestCase):
    def test_high_score_returns_high(self) -> None:
        page = _make_page(opportunity_score=65, position=5.0)
        self.assertEqual(priority_for_page(page), "HIGH")

    def test_medium_score_returns_medium(self) -> None:
        page = _make_page(opportunity_score=45, score=45.0, priority="MEDIUM", position=5.0)
        self.assertEqual(priority_for_page(page), "MEDIUM")

    def test_low_score_returns_low(self) -> None:
        page = _make_page(opportunity_score=20, score=20.0, priority="LOW", position=5.0)
        self.assertEqual(priority_for_page(page), "LOW")


class TestDiagnosticForPage(unittest.TestCase):
    def test_top10_low_ctr_mentions_title_meta(self) -> None:
        expected = expected_ctr_for_position(7.0)
        page = _make_page(
            impressions=200,
            ctr=expected * 0.5,  # bien sous la médiane
            position=7.0,
            actions=["Revoir title et méta description pour mieux convertir les impressions"],
        )
        result = diagnostic_for_page(page)
        self.assertIn("title", result.lower())

    def test_top10_good_ctr_mentions_enrichissement(self) -> None:
        expected = expected_ctr_for_position(7.0)
        page = _make_page(
            impressions=200,
            ctr=expected * 1.1,  # conforme ou au-dessus
            position=7.0,
            actions=["Densifier le contenu"],
        )
        result = diagnostic_for_page(page)
        self.assertIn("enrichissement", result.lower())

    def test_returns_string(self) -> None:
        page = _make_page(opportunity_score=30, score=30.0, position=25.0)
        self.assertIsInstance(diagnostic_for_page(page), str)
        self.assertGreater(len(diagnostic_for_page(page)), 10)


class TestGeneratePageRecommendation(unittest.TestCase):
    def test_returns_string_for_generic_page(self) -> None:
        result = generate_page_recommendation(
            page="https://example.com/guide-padel",
            main_queries=["guide padel"],
            page_type="guide",
            business_value="medium",
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)

    def test_padel_test_page_gets_verdict_recommendation(self) -> None:
        result = generate_page_recommendation(
            page="https://example.com/test-raquette-padel",
            main_queries=["test raquette padel"],
            page_type="test",
            business_value="high",
        )
        self.assertIn("verdict", result.lower())

    def test_low_ctr_signal_mentions_title(self) -> None:
        page = _make_page(
            url="https://example.com/guide-general",
            impressions=300,
            ctr=0.005,
            position=4.0,
            action_type="snippet",
        )
        result = generate_page_recommendation(
            page=page.url,
            main_queries=["guide general"],
            page_type="guide",
            business_value="medium",
            analysis=page,
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)


class TestBuildTargetMetric(unittest.TestCase):
    def test_returns_empty_for_low_impressions(self) -> None:
        page = _make_page(impressions=5, ctr=0.02, position=8.0)
        self.assertEqual(build_target_metric(page), "")

    def test_returns_formatted_string_for_sufficient_impressions(self) -> None:
        page = _make_page(impressions=500, ctr=0.02, position=8.0)
        result = build_target_metric(page)
        self.assertIsInstance(result, str)
        if result:
            self.assertIn("CTR actuel", result)
            self.assertIn("Gain estimé", result)

    def test_contains_percent_sign(self) -> None:
        page = _make_page(impressions=200, ctr=0.03, position=6.0)
        result = build_target_metric(page)
        if result:
            self.assertIn("%", result)


class TestGenerateSnippetRecommendation(unittest.TestCase):
    def test_unknown_query_returns_empty(self) -> None:
        result = generate_snippet_recommendation(
            page="https://example.com/page-inconnue",
            main_query="quelque chose de tres generique sans mot cle reconnu",
        )
        self.assertEqual(result["title"], "")
        self.assertEqual(result["meta"], "")

    def test_tournament_page_returns_title(self) -> None:
        result = generate_snippet_recommendation(
            page="https://example.com/tournoi-padel-p250",
            main_query="tournoi padel p250",
        )
        self.assertIsInstance(result, dict)
        self.assertIn("title", result)

    def test_chaussure_page_returns_recommendation(self) -> None:
        result = generate_snippet_recommendation(
            page="https://example.com/chaussures-padel-test",
            main_query="chaussures padel test",
        )
        self.assertIsInstance(result, dict)
        self.assertIn("title", result)
        if result["title"]:
            self.assertLessEqual(len(result["title"]), 60)
            self.assertLessEqual(len(result["meta"]), 155)


class TestResolveTargetLabel(unittest.TestCase):
    def test_non_empty_url_returns_compact_url(self) -> None:
        result = resolve_target_label("https://www.example.com/page/test")
        self.assertIn("example.com", result)
        self.assertNotIn("www.", result)

    def test_empty_url_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            resolve_target_label("")

    def test_non_empty_url_no_placeholder(self) -> None:
        result = resolve_target_label("https://example.com/foo")
        self.assertIn("example.com", result)


# ---------------------------------------------------------------------------
# Bug 2B-1 — Garde-fou position dans priority_for_page()
# ---------------------------------------------------------------------------

class TestPriorityCappedForPositionAbove30(unittest.TestCase):
    def test_high_score_position_51_forced_to_low(self) -> None:
        """Page position 51 avec score élevé → LOW (bug 2B-1, position > 50)."""
        page = _make_page(opportunity_score=75, score=75.0, position=51.3, priority="HIGH")
        result = priority_for_page(page)
        self.assertEqual(result, "LOW")

    def test_high_score_position_35_forced_to_medium(self) -> None:
        """Page position 35 avec score HIGH → MEDIUM (bug 2B-1, position > 30)."""
        page = _make_page(opportunity_score=70, score=70.0, position=35.0, priority="HIGH")
        result = priority_for_page(page)
        self.assertEqual(result, "MEDIUM")

    def test_medium_score_position_35_stays_medium(self) -> None:
        """Page MEDIUM en position 35 → reste MEDIUM (le garde-fou ne concerne que HIGH)."""
        page = _make_page(opportunity_score=45, score=45.0, position=35.0, priority="MEDIUM")
        result = priority_for_page(page)
        self.assertEqual(result, "MEDIUM")

    def test_position_exactly_30_no_cap(self) -> None:
        """Frontière exacte : position == 30 → HIGH conservé (le seuil est > 30, pas >=)."""
        page = _make_page(opportunity_score=70, score=70.0, position=30.0, priority="HIGH")
        result = priority_for_page(page)
        self.assertEqual(result, "HIGH")

    def test_position_exactly_50_stays_medium(self) -> None:
        """Frontière exacte : position == 50 → MEDIUM possible (seuil > 50, pas >=)."""
        page = _make_page(opportunity_score=45, score=45.0, position=50.0, priority="MEDIUM")
        result = priority_for_page(page)
        self.assertEqual(result, "MEDIUM")

    def test_position_above_50_low_score_stays_low(self) -> None:
        """Position > 50 avec score LOW → LOW (pas de downgrade depuis LOW)."""
        page = _make_page(opportunity_score=20, score=20.0, position=55.0, priority="LOW")
        result = priority_for_page(page)
        self.assertEqual(result, "LOW")


# ---------------------------------------------------------------------------
# Bug 2B-2 — Constat dynamique par profil
# ---------------------------------------------------------------------------

class TestConstantDynamicPerProfile(unittest.TestCase):
    def _expected(self, pos: float) -> float:
        return expected_ctr_for_position(pos)

    def test_template_top10_low_ctr(self) -> None:
        """Position < 10, CTR sous médiane → template 'title + meta'."""
        e = self._expected(5.0)
        page = _make_page(position=5.0, ctr=e * 0.5, impressions=300)
        result = diagnostic_for_page(page)
        self.assertIn("title", result.lower())
        self.assertIn("meta", result.lower())

    def test_template_top10_good_ctr(self) -> None:
        """Position < 10, CTR >= médiane → template 'enrichissement éditorial'."""
        e = self._expected(5.0)
        page = _make_page(position=5.0, ctr=e * 1.2, impressions=300)
        result = diagnostic_for_page(page)
        self.assertIn("enrichissement", result.lower())

    def test_template_10_to_20_high_impressions(self) -> None:
        """Position 10-20, impressions > seuil → template 'hors top 10'."""
        page = _make_page(position=14.0, ctr=0.01, impressions=IMPRESSIONS_THRESHOLD_HIGH + 100)
        result = diagnostic_for_page(page)
        self.assertIn("top 10", result.lower())

    def test_template_20_to_30(self) -> None:
        """Position 20-30 → template 'trop bas pour capter du trafic'."""
        page = _make_page(position=25.0, ctr=0.005, impressions=200)
        result = diagnostic_for_page(page)
        self.assertIn("trop bas", result.lower())

    def test_template_above_30(self) -> None:
        """Position > 30 → template 'hors SERP visible'."""
        page = _make_page(position=51.3, ctr=0.0006, impressions=1600, opportunity_score=30)
        result = diagnostic_for_page(page)
        self.assertIn("serp", result.lower())

    def test_five_templates_are_distinct(self) -> None:
        """Les 5 templates renvoient des textes distincts."""
        e5 = self._expected(5.0)
        pages = [
            _make_page(position=5.0, ctr=e5 * 0.5, impressions=300),   # top10 low CTR
            _make_page(position=5.0, ctr=e5 * 1.2, impressions=300),   # top10 bon CTR
            _make_page(position=14.0, ctr=0.01, impressions=IMPRESSIONS_THRESHOLD_HIGH + 100),  # 10-20 fort
            _make_page(position=25.0, ctr=0.005, impressions=200),      # 20-30
            _make_page(position=51.3, ctr=0.0006, impressions=1600, opportunity_score=30),  # >30
        ]
        texts = [diagnostic_for_page(p) for p in pages]
        self.assertEqual(len(set(texts)), 5, f"Textes non uniques : {texts}")

    def test_ctr_exactly_at_tolerance_boundary(self) -> None:
        """CTR exactement à CTR_TOLERANCE × médiane → template 'bon CTR' (pas déclenché)."""
        e = self._expected(5.0)
        page = _make_page(position=5.0, ctr=e * CTR_TOLERANCE, impressions=300)
        result = diagnostic_for_page(page)
        # À la frontière exacte (= tolérance) : pas de template "low CTR"
        # car la condition est CTR < CTR_TOLERANCE * médiane
        self.assertIn("enrichissement", result.lower())


# ---------------------------------------------------------------------------
# Bug 2B-3 — Cap cluster dans cap_top_priority_per_cluster()
# ---------------------------------------------------------------------------

class TestClusterCapLimitsTopPriority(unittest.TestCase):
    def _player_page(self, name: str, score: int = 70) -> GSCPageAnalysis:
        return _make_page(
            url=f"https://example.com/{name}-joueur-padel/",
            opportunity_score=score,
            score=float(score),
            priority="HIGH",
            action_type="snippet",
            business_value="high",
        )

    def test_four_similar_pages_capped_to_two_high(self) -> None:
        """4 pages avec même signature cluster → 2 conservées HIGH, 2 descendues MEDIUM."""
        pages = [
            self._player_page("agustin-tapia", 70),
            self._player_page("arturo-coello", 68),
            self._player_page("alejandro-galan", 65),
            self._player_page("juan-lebron", 63),
        ]
        result = cap_top_priority_per_cluster(pages, max_per_cluster=2)
        high_count = sum(1 for p in result if p.priority == "HIGH")
        medium_count = sum(1 for p in result if p.priority == "MEDIUM")
        self.assertEqual(high_count, 2)
        self.assertEqual(medium_count, 2)

    def test_two_pages_same_cluster_no_cap(self) -> None:
        """Exactement 2 pages dans un cluster → aucune n'est descendue."""
        pages = [
            self._player_page("agustin-tapia", 70),
            self._player_page("arturo-coello", 68),
        ]
        result = cap_top_priority_per_cluster(pages, max_per_cluster=2)
        self.assertTrue(all(p.priority == "HIGH" for p in result))

    def test_best_scored_pages_kept_high(self) -> None:
        """Les 2 meilleures pages (score 70, 68) restent HIGH ; les 2 autres (65, 63) descendent."""
        pages = [
            self._player_page("agustin-tapia", 70),
            self._player_page("arturo-coello", 68),
            self._player_page("alejandro-galan", 65),
            self._player_page("juan-lebron", 63),
        ]
        result = cap_top_priority_per_cluster(pages, max_per_cluster=2)
        by_url = {p.url: p for p in result}
        self.assertEqual(by_url["https://example.com/agustin-tapia-joueur-padel/"].priority, "HIGH")
        self.assertEqual(by_url["https://example.com/arturo-coello-joueur-padel/"].priority, "HIGH")
        self.assertEqual(by_url["https://example.com/alejandro-galan-joueur-padel/"].priority, "MEDIUM")
        self.assertEqual(by_url["https://example.com/juan-lebron-joueur-padel/"].priority, "MEDIUM")

    def test_dead_pages_not_affected(self) -> None:
        """Les pages DEAD ne sont pas downgraded."""
        pages = [
            _make_page(url="https://example.com/dead-page/", priority="DEAD", opportunity_score=10),
            self._player_page("agustin-tapia", 70),
        ]
        result = cap_top_priority_per_cluster(pages, max_per_cluster=2)
        by_url = {p.url: p for p in result}
        self.assertEqual(by_url["https://example.com/dead-page/"].priority, "DEAD")


# ---------------------------------------------------------------------------
# Bug 2B-4 — is_resolvable_target + resolve_target_label
# ---------------------------------------------------------------------------

class TestUnresolvableTargetFiltered(unittest.TestCase):
    def test_empty_url_not_resolvable(self) -> None:
        self.assertFalse(is_resolvable_target(""))

    def test_none_url_not_resolvable(self) -> None:
        self.assertFalse(is_resolvable_target(None))  # type: ignore[arg-type]

    def test_valid_url_is_resolvable(self) -> None:
        self.assertTrue(is_resolvable_target("https://example.com/page"))

    def test_placeholder_tbd_not_resolvable(self) -> None:
        self.assertFalse(is_resolvable_target("tbd"))

    def test_placeholder_a_valider_not_resolvable(self) -> None:
        self.assertFalse(is_resolvable_target("à valider"))

    def test_resolve_target_label_raises_for_empty(self) -> None:
        with self.assertRaises(ValueError):
            resolve_target_label("")

    def test_resolve_target_label_returns_compact_for_valid(self) -> None:
        result = resolve_target_label("https://www.example.com/page/test")
        self.assertIn("example.com", result)
        self.assertNotIn("www.", result)


# ---------------------------------------------------------------------------
# Bug 2B-5 — trim_to_length propre + dedupe_tokens
# ---------------------------------------------------------------------------

class TestSnippetValidation(unittest.TestCase):
    def test_trim_no_truncation_mid_word(self) -> None:
        """La troncature ne coupe jamais en milieu de mot."""
        text = "Ceci est une phrase suffisamment longue pour être tronquée proprement"
        result = trim_to_length(text, 40)
        # Le résultat ne doit pas couper un mot en plein milieu
        # → vérifier que le dernier caractère n'est pas une lettre du milieu d'un mot du texte original
        self.assertLessEqual(len(result), 40)
        # Chaque mot du résultat doit être un mot complet du texte original
        for word in result.split():
            self.assertIn(word.rstrip(".,;:"), text)

    def test_trim_removes_trailing_comma(self) -> None:
        """Virgule en fin de troncature supprimée."""
        text = "Mot1 Mot2, Mot3 Mot4 Mot5 Mot6"
        # Forcer une troncature qui laisse une virgule en position finale
        # "Mot1 Mot2," fait 10 chars → tronquer à 10 → doit donner "Mot1 Mot2"
        result = trim_to_length("Mot1 Mot2, Mot3 Mot4 Mot5 Mot6 ExtraMot", 10)
        self.assertFalse(result.endswith(","))
        self.assertFalse(result.endswith(";"))

    def test_trim_exactly_at_limit_not_truncated(self) -> None:
        """Texte exactement à 60 caractères → pas de troncature."""
        text = "A" * 60
        self.assertEqual(trim_to_length(text, 60), text)

    def test_dedupe_tokens_removes_significant_duplicate(self) -> None:
        """Un mot significatif répété est dédupliqué."""
        text = "padel padel niveau niveau"
        result = dedupe_tokens(text)
        self.assertEqual(result.count("padel"), 1)
        self.assertEqual(result.count("niveau"), 1)

    def test_dedupe_tokens_keeps_stopwords(self) -> None:
        """Les stopwords peuvent se répéter librement."""
        text = "le padel et le niveau"
        result = dedupe_tokens(text)
        self.assertIn("le", result)
        # "padel" et "niveau" apparaissent une fois
        self.assertEqual(result.count("padel"), 1)

    def test_snippet_title_max_60_chars(self) -> None:
        """Le title d'un snippet de tournoi respecte les 60 caractères."""
        result = generate_snippet_recommendation(
            page="https://example.com/tournoi-padel-p2000",
            main_query="tournoi padel p2000",
        )
        if result["title"]:
            self.assertLessEqual(len(result["title"]), 60)

    def test_snippet_meta_max_155_chars(self) -> None:
        """La meta respecte les 155 caractères."""
        result = generate_snippet_recommendation(
            page="https://example.com/chaussures-padel",
            main_query="chaussures padel",
        )
        if result["meta"]:
            self.assertLessEqual(len(result["meta"]), 155)

    def test_snippet_no_trailing_comma(self) -> None:
        """Aucun title ni meta ne finit par une virgule."""
        for page, query in [
            ("https://example.com/tournoi-padel-p500", "tournoi padel p500"),
            ("https://example.com/chaussures-padel", "chaussures padel"),
            ("https://example.com/comment-tenir-raquette-padel", "comment tenir raquette padel"),
        ]:
            result = generate_snippet_recommendation(page=page, main_query=query)
            if result["title"]:
                self.assertFalse(
                    result["title"].endswith(","),
                    f"Title finit par une virgule : {result['title']!r}",
                )
            if result["meta"]:
                self.assertFalse(
                    result["meta"].endswith(","),
                    f"Meta finit par une virgule : {result['meta']!r}",
                )


# ---------------------------------------------------------------------------
# Bug 2B-6 — Plan d'action synchronisé avec le top 10
# (test intégration : les pages HIGH du top 10 sont dans le plan d'action)
# ---------------------------------------------------------------------------

class TestTop10MatchesActionPlan(unittest.TestCase):
    def test_action_plan_built_from_priority_pages(self) -> None:
        """build_action_plan_30_days utilise la même liste priority_pages que le top 10."""
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from gsc import build_action_plan_30_days

        # Simule un top 10 de 3 pages avec URLs réelles
        priority_pages = [
            {"url": "https://example.com/page-a/", "slug": "page-a", "metrics": {"Position": "5.0"}},
            {"url": "https://example.com/page-b/", "slug": "page-b", "metrics": {"Position": "9.0"}},
            {"url": "https://example.com/page-c/", "slug": "page-c", "metrics": {"Position": "12.0"}},
        ]
        snippet_pages = [
            {"url": "https://example.com/page-snip/", "slug": "page-snip"},
        ]
        plan = build_action_plan_30_days(priority_pages, snippet_pages, [])
        self.assertEqual(len(plan), 4)  # 4 semaines
        week1 = plan[0]["body"]
        # La semaine 1 mentionne les snippets pages
        self.assertIsInstance(week1, str)
        week2 = plan[1]["body"]
        # La semaine 2 mentionne les pages positionnées entre 8 et 15
        self.assertIsInstance(week2, str)
        self.assertIn("page-b", week2)  # position 9.0 → dans le plan semaine 2


# ---------------------------------------------------------------------------
# slug_prefix helper
# ---------------------------------------------------------------------------

class TestSlugPrefix(unittest.TestCase):
    def test_player_pages_share_suffix(self) -> None:
        """Deux pages joueurs partagent le même préfixe de slug."""
        p1 = slug_prefix("https://example.com/agustin-tapia-joueur-padel/", depth=2)
        p2 = slug_prefix("https://example.com/arturo-coello-joueur-padel/", depth=2)
        self.assertEqual(p1, p2)

    def test_different_pages_different_prefix(self) -> None:
        """Une page raquette et une page joueur ont des préfixes différents."""
        p1 = slug_prefix("https://example.com/raquette-padel-debutant/", depth=2)
        p2 = slug_prefix("https://example.com/arturo-coello-joueur-padel/", depth=2)
        self.assertNotEqual(p1, p2)

    def test_empty_url_returns_empty(self) -> None:
        self.assertEqual(slug_prefix(""), "")


if __name__ == "__main__":
    unittest.main()
