from __future__ import annotations

import unittest

from audit import find_editorial_dates, find_dated_references, should_check_dates


class FindEditorialDatesTests(unittest.TestCase):
    # --- Vrais signaux éditoriaux ---

    def test_mis_a_jour_avec_mois(self) -> None:
        assert find_editorial_dates("Article mis à jour en avril 2026") == ["2026"]

    def test_publie_avec_jour_mois(self) -> None:
        assert find_editorial_dates("Publié le 12 mars 2024") == ["2024"]

    def test_mois_annee_isole(self) -> None:
        assert find_editorial_dates("Dernière révision : septembre 2023") == ["2023"]

    def test_copyright_footer(self) -> None:
        assert find_editorial_dates("© 2023 Ever SportZone") == ["2023"]

    def test_copyright_parenthese(self) -> None:
        assert find_editorial_dates("(c) 2022 Acme Corp") == ["2022"]

    def test_updated_english(self) -> None:
        assert find_editorial_dates("Last updated April 2025") == ["2025"]

    def test_emoji_redaction(self) -> None:
        assert find_editorial_dates("✍️ mis à jour 2024") == ["2024"]

    # --- Faux positifs à ignorer ---

    def test_produit_asics(self) -> None:
        assert find_editorial_dates("Asics Gel 9 Clay 2025") == []

    def test_produit_head(self) -> None:
        assert find_editorial_dates("Head Extreme Pro 2024 : test complet") == []

    def test_produit_starvie(self) -> None:
        assert find_editorial_dates("Test de la Starvie Drax Pro Touch 2025") == []

    def test_evenement_tournoi(self) -> None:
        assert find_editorial_dates("Tournoi P1000 de 2024") == []

    def test_annee_seule_sans_contexte(self) -> None:
        assert find_editorial_dates("Chaussures padel 2025") == []

    def test_texte_vide(self) -> None:
        assert find_editorial_dates("") == []

    def test_texte_none_like(self) -> None:
        assert find_editorial_dates(None) == []  # type: ignore[arg-type]


class ShouldCheckDatesTests(unittest.TestCase):
    # --- URLs à exclure ---

    def test_chaussures_padel_hub(self) -> None:
        assert should_check_dates("/chaussures-padel/") is False

    def test_chaussures_marque(self) -> None:
        assert should_check_dates("/chaussures-padel-asics-gel-9-clay") is False

    def test_test_chaussures(self) -> None:
        assert should_check_dates("/test-chaussures-padel-asics-gel-9-clay") is False

    def test_test_raquette(self) -> None:
        assert should_check_dates("/test-raquette-babolat") is False

    def test_raquette_hub(self) -> None:
        assert should_check_dates("/raquette-padel/") is False

    # --- URLs à inclure ---

    def test_lexique(self) -> None:
        assert should_check_dates("/lexique-padel") is True

    def test_tournois(self) -> None:
        assert should_check_dates("/tournois-de-padel") is True

    def test_homepage(self) -> None:
        assert should_check_dates("/") is True

    def test_url_vide(self) -> None:
        assert should_check_dates("") is True

    def test_article_blog(self) -> None:
        assert should_check_dates("/actualites/nouveau-club-padel-lyon") is True


class FindDatedReferencesTests(unittest.TestCase):
    def test_editorial_date_in_title_is_found(self) -> None:
        refs = find_dated_references(
            text="",
            title="Mis à jour en mars 2020",
            url="https://example.com/guide",
        )
        assert any("titre" in r.lower() for r in refs), refs

    def test_product_url_excluded(self) -> None:
        refs = find_dated_references(
            text="Asics Gel 2024 test complet",
            title="Asics Gel 2024",
            url="https://example.com/test-chaussures-padel-asics-gel-2024",
        )
        assert refs == []

    def test_product_name_in_content_not_flagged(self) -> None:
        refs = find_dated_references(
            text="Le modèle Asics Gel 9 Clay 2025 est disponible.",
            title="Asics Gel 9 Clay 2025",
            url="https://example.com/chaussures-padel/",
        )
        assert refs == []

    def test_dated_url_segment_is_flagged(self) -> None:
        refs = find_dated_references(
            text="",
            title="Article de fond",
            url="https://example.com/blog/2020/article-seo",
        )
        assert any("url" in r.lower() for r in refs), refs


if __name__ == "__main__":
    unittest.main()
