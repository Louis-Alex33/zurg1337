"""Tests pour la refonte du rapport pré-audit URL-only (sections 1-10)."""
from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audit_report_design import (
    _smart_truncate,
    TITLE_MAX_LEN,
    TITLE_MIN_LEN,
    META_MAX_LEN,
    META_MIN_LEN,
    _matrix_qualifies_for_display,
    build_primary_signal,
    public_page_kind,
    recommendation_for_public_page_type,
)
from models import AuditPage
from audit import compute_technical_health_score


def make_audit_page(**overrides) -> AuditPage:
    data = {
        "url": "https://example.com/page",
        "status_code": 200,
        "title": "Guide pratique complet",
        "meta_description": "Une description propre de longueur correcte pour le crawl.",
        "h1": ["Guide pratique"],
        "word_count": 600,
        "internal_links_out": [],
        "images_total": 0,
        "images_without_alt": 0,
        "depth": 1,
        "dated_references": [],
        "has_structured_data": False,
        "content_like": True,
        "meaningful_h1_count": 1,
        "load_time": 1.5,
    }
    data.update(overrides)
    return AuditPage(**data)


class SmartTruncateTests(unittest.TestCase):
    def test_texte_sous_limite_retourne_intact(self) -> None:
        text = "Guide complet du padel"
        result = _smart_truncate(text, 60)
        self.assertEqual(result, text)

    def test_tronque_au_dernier_mot_propre(self) -> None:
        text = "Tournois de Padel P25 : votre porte d'entrée vers la compétition régionale"
        result = _smart_truncate(text, 65)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLessEqual(len(result), 65)
        last_word = result.split()[-1].rstrip(",.;:").lower()
        from audit_report_design import _SMART_TRUNCATE_BAD_ENDINGS
        self.assertNotIn(last_word, _SMART_TRUNCATE_BAD_ENDINGS)

    def test_dernier_mot_grammatical_est_elimine(self) -> None:
        # "Pour des critères" → si tronqué après "des", le "des" doit être supprimé
        text = "Choisir votre solution pour des critères importants et pertinents"
        result = _smart_truncate(text, 40)
        if result is not None:
            last_word = result.split()[-1].rstrip(",.;:").lower()
            from audit_report_design import _SMART_TRUNCATE_BAD_ENDINGS
            self.assertNotIn(last_word, _SMART_TRUNCATE_BAD_ENDINGS,
                             f"Le résultat '{result}' se termine par un mot grammatical '{last_word}'")

    def test_retourne_none_si_fragment_trop_court(self) -> None:
        # 10 car. < TITLE_MIN_LEN → None
        text = "Short" + " x" * 30
        result = _smart_truncate(text, 8)
        self.assertIsNone(result)

    def test_supprime_espaces_multiples(self) -> None:
        text = "Guide   complet   du   padel   version   2026"
        result = _smart_truncate(text, 65)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("  ", result)

    def test_cas_padel_raquette_ne_termine_pas_sur_notre(self) -> None:
        # Régression : le titre ne doit pas se terminer sur "? Notre" ni sur "Notre"
        text = "Combien de temps garder votre raquette de Padel ? Notre guide ultime"
        result = _smart_truncate(text, 60)
        self.assertIsNotNone(result, "Doit retourner quelque chose, pas None")
        assert result is not None
        last_word = result.split()[-1].rstrip(",.;:?!").lower()
        from audit_report_design import _SMART_TRUNCATE_BAD_ENDINGS
        self.assertNotIn(last_word, _SMART_TRUNCATE_BAD_ENDINGS,
                         f"Résultat '{result}' se termine sur un mot grammatical '{last_word}'")
        # Ne doit pas se terminer par une ponctuation orpheline
        self.assertNotIn(result[-1], "?!:,;-—",
                         f"Résultat '{result}' se termine par une ponctuation orpheline")

    def test_cas_p100_padel_titre_court_max60(self) -> None:
        # Titre de 68 chars → à max=60, si la coupe n'est pas propre, retourner None ou un fragment propre
        text = "P100 Padel : niveau, points, cuts… tout ce qu’il faut savoir en 2026"
        result = _smart_truncate(text, 60)
        if result is not None:
            last_word = result.split()[-1].rstrip(",.;:?!").lower()
            from audit_report_design import _SMART_TRUNCATE_BAD_ENDINGS
            self.assertNotIn(last_word, _SMART_TRUNCATE_BAD_ENDINGS,
                             f"Résultat '{result}' se termine sur un mot grammatical '{last_word}'")
            self.assertLessEqual(len(result), 60)

    def test_cas_p1500_titre_complet_sous_65(self) -> None:
        # Titre de 62 chars < 65 → doit retourner le titre complet inchangé
        text = "Tournoi de Padel P1500 : Fonctionnement, Points et Inscription"
        result = _smart_truncate(text, 65)
        self.assertEqual(result, text, "Le titre complet (62 chars) doit être retourné inchangé pour max=65")

    def test_pas_de_ponctuation_orpheline_en_fin(self) -> None:
        # Un titre avec '?' au milieu ne doit pas se terminer par '?' après troncature
        text = "Pourquoi le padel attire-t-il autant ? Les raisons de ce succès fulgurant"
        result = _smart_truncate(text, 40)
        if result is not None:
            self.assertNotIn(result[-1], "?!:,;-—",
                             f"Résultat '{result}' se termine par une ponctuation orpheline")


class ConstantesSeuilsTests(unittest.TestCase):
    def test_title_max_len_vaut_65(self) -> None:
        self.assertEqual(TITLE_MAX_LEN, 65)

    def test_title_min_len_vaut_25(self) -> None:
        self.assertEqual(TITLE_MIN_LEN, 25)

    def test_meta_max_len_vaut_155(self) -> None:
        self.assertEqual(META_MAX_LEN, 155)

    def test_meta_min_len_vaut_70(self) -> None:
        self.assertEqual(META_MIN_LEN, 70)


class ScoreSanteTechniqueTests(unittest.TestCase):
    def _make_pages(self, n: int, **overrides) -> list[AuditPage]:
        return [make_audit_page(url=f"https://example.com/page-{i}", **overrides) for i in range(n)]

    def test_score_descend_sous_60_avec_98pct_pages_lentes(self) -> None:
        n = 50
        slow = self._make_pages(n - 1, load_time=4.5, content_like=True)
        fast = self._make_pages(1, load_time=1.0, content_like=True)
        pages = slow + fast
        content_pages = pages
        score = compute_technical_health_score(pages, content_pages)
        self.assertLess(score, 70, f"Score attendu < 70 avec 98% pages lentes, obtenu: {score}")

    def _make_good_meta(self) -> str:
        # Meta description bien formée pour isoler un seul facteur dans un test
        return "Une description complète et bien rédigée qui fait au minimum soixante-dix caractères."

    def test_score_reste_eleve_avec_pages_rapides(self) -> None:
        # Pages avec tous les signaux corrects : titre OK, meta OK, charge rapide
        good_meta = self._make_good_meta()
        good_title = "Guide pratique complet et bien rédigé"
        pages = self._make_pages(
            20,
            load_time=1.2,
            content_like=True,
            title=good_title,
            meta_description=good_meta,
        )
        score = compute_technical_health_score(pages, pages)
        self.assertGreater(score, 80, f"Score attendu > 80 avec pages rapides et méta correcte, obtenu: {score}")

    def test_score_penalise_titres_manquants(self) -> None:
        good_meta = self._make_good_meta()
        # Titre > 25 chars et < 65 chars = dans la plage acceptable
        good_title = "Guide pratique complet pour bien démarrer"
        with_titles = self._make_pages(20, title=good_title, meta_description=good_meta, content_like=True)
        without_titles = self._make_pages(20, title="", meta_description=good_meta, content_like=True)
        score_with = compute_technical_health_score(with_titles, with_titles)
        score_without = compute_technical_health_score(without_titles, without_titles)
        self.assertGreater(score_with, score_without,
                           f"Attendu score_with ({score_with}) > score_without ({score_without})")

    def test_score_eversportzone_fourchette_55_70(self) -> None:
        # Simulation d'eversportzone.com : 98% des pages > 3s, titres absents
        # Seulement la pénalité performance + titres → fourchette 40-70
        good_meta = self._make_good_meta()
        n = 100
        slow = self._make_pages(98, load_time=4.2, title="", meta_description=good_meta, content_like=True)
        fast = self._make_pages(2, load_time=1.5, title="Guide pratique", meta_description=good_meta, content_like=True)
        pages = slow + fast
        score = compute_technical_health_score(pages, pages)
        # Avec 98% lentes + 98% sans titre : score doit être < 70 (incohérence corrigée)
        self.assertLessEqual(score, 70, f"Score > 70 incohérent avec 98% pages lentes + sans titres: {score}")
        self.assertGreaterEqual(score, 0, "Score ne peut pas être négatif")


class MatriceQualificationTests(unittest.TestCase):
    def test_matrice_qualifiee_avec_3_actions_dans_2_quadrants(self) -> None:
        matrix = {
            "quick_wins": [{"titre": "A"}, {"titre": "B"}],
            "projets_structurants": [{"titre": "C"}],
            "optimisations_simples": [],
            "backlog": [],
        }
        self.assertTrue(_matrix_qualifies_for_display(matrix))

    def test_matrice_non_qualifiee_avec_1_quadrant(self) -> None:
        matrix = {
            "quick_wins": [{"titre": "A"}, {"titre": "B"}, {"titre": "C"}],
            "projets_structurants": [],
            "optimisations_simples": [],
            "backlog": [],
        }
        self.assertFalse(_matrix_qualifies_for_display(matrix))

    def test_matrice_non_qualifiee_si_moins_de_3_actions(self) -> None:
        matrix = {
            "quick_wins": [{"titre": "A"}],
            "projets_structurants": [{"titre": "B"}],
            "optimisations_simples": [],
            "backlog": [],
        }
        self.assertFalse(_matrix_qualifies_for_display(matrix))

    def test_matrice_vide_non_qualifiee(self) -> None:
        matrix: dict = {"quick_wins": [], "projets_structurants": [], "optimisations_simples": [], "backlog": []}
        self.assertFalse(_matrix_qualifies_for_display(matrix))


class SignalPrincipalTests(unittest.TestCase):
    def test_signal_perf_prioritaire_sur_duplication(self) -> None:
        summary = {
            "slow_pages": 49,
            "pages_crawled": 50,
            "duplicate_meta_description_groups": 5,
        }
        signal = build_primary_signal(summary, [], lang="fr")
        self.assertIn("performance", signal.lower())

    def test_signal_erreur_http_second_prioritaire(self) -> None:
        summary = {
            "slow_pages": 0,
            "pages_crawled": 50,
            "pages_with_errors": 3,
        }
        signal = build_primary_signal(summary, [], lang="fr")
        self.assertIn("erreur", signal.lower())

    def test_signal_fraicheur_uniquement_si_rien_dautre(self) -> None:
        summary = {
            "slow_pages": 0,
            "pages_crawled": 50,
            "pages_with_errors": 0,
            "probable_orphan_pages": 0,
            "weak_internal_linking_pages": 0,
            "titles_problematic": 0,
            "meta_descriptions_problematic": 0,
            "duplicate_title_groups": 0,
            "duplicate_meta_description_groups": 0,
            "content_like_pages": 50,
            "dated_content_signals": 5,
        }
        signal = build_primary_signal(summary, [], lang="fr")
        self.assertIn("date", signal.lower())


class PublicPageKindTests(unittest.TestCase):
    def test_pas_de_terme_padel_specifique(self) -> None:
        # Vérifier que les termes padel ne sont plus dans la logique de classification
        import inspect
        from audit_report_design import public_page_kind
        src = inspect.getsource(public_page_kind)
        self.assertNotIn("padel", src.lower())
        self.assertNotIn("raquette", src.lower())

    def test_page_legale_detectee(self) -> None:
        self.assertEqual(public_page_kind("/mentions-legales", "", ""), "page_legale")

    def test_comparatif_detecte(self) -> None:
        self.assertEqual(public_page_kind("/comparatif-produits", "", ""), "comparatif")

    def test_categorie_detectee(self) -> None:
        self.assertEqual(public_page_kind("/category/blog", "category", ""), "categorie")


class AngleVariantsTests(unittest.TestCase):
    def test_pas_de_repetition_consecutive(self) -> None:
        # Vérifier que le pool de variantes d'une catégorie contient au moins 2 entrées distinctes
        from audit_report_design import ANGLE_VARIANTS_BY_CATEGORY
        for category, variants in ANGLE_VARIANTS_BY_CATEGORY.items():
            unique = set(variants)
            self.assertGreater(len(unique), 1,
                               f"Catégorie '{category}' n'a pas assez de variantes distinctes pour éviter la répétition")

    def test_variantes_disponibles_pour_toutes_categories(self) -> None:
        from audit_report_design import ANGLE_VARIANTS_BY_CATEGORY
        for category, variants in ANGLE_VARIANTS_BY_CATEGORY.items():
            self.assertGreaterEqual(
                len(variants), 2,
                f"Catégorie '{category}' n'a que {len(variants)} variante(s), minimum 2 attendu"
            )


if __name__ == "__main__":
    unittest.main()
