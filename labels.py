from __future__ import annotations

LABEL_MAP: dict[str, str] = {
    "Pages analysées": "Pages analysées",
    "Pages analysees": "Pages analysées",
    "Actions prioritaires": "Opportunités détectées",
    "Pages en baisse": "Pages à surveiller",
    "Snippets à retravailler": "Résultats Google à améliorer",
    "Snippet": "Résultat Google (titre + description)",
    "CTR": "Taux de clic",
    "CTR moyen": "Taux de clic moyen",
    "Chevauchements à vérifier": "Conflits de mots-clés potentiels",
    "Cannibalisation potentielle": "Pages en concurrence",
    "Confiance high": "Signal fort",
    "Confiance medium": "Signal à vérifier",
    "Type d'action : Cannibalisation": "⚠ Pages en compétition",
    "Clics récupérables estimés": "Gain de trafic estimé",
    "PRIORITE": "Urgence",
    "Priorité": "Urgence",
    "ACTION CONSEILLEE": "Ce qu'on recommande",
    "Action conseillée": "Ce qu'on recommande",
    "POURQUOI CETTE PAGE RESSORT": "Pourquoi agir maintenant",
    "Pourquoi cette page ressort": "Pourquoi agir maintenant",
    "Pages à traiter en premier": "Opportunités prioritaires",
    "Pages qui perdent du terrain": "Pages à surveiller",
    "Pages proches d'un gain SEO": "Pages proches d'une percée",
    "Pages proches d’un gain SEO": "Pages proches d'une percée",
    "Pages faibles à réévaluer": "Pages sans traction",
    "Chevauchements possibles": "Conflits de mots-clés",
    "HIGH": "Haute",
    "MEDIUM": "Moyenne",
    "LOW": "Faible",
    "DEAD": "Faible",
    "Revoir title et meta description pour mieux convertir les impressions": "Améliorer le résultat affiché dans Google",
    "Revoir title et méta description pour mieux convertir les impressions": "Améliorer le résultat affiché dans Google",
    "Densifier le contenu avec sections, FAQ et signaux de fraicheur": "Enrichir la page (FAQ, exemples, mise à jour)",
    "Densifier le contenu avec sections, FAQ et signaux de fraîcheur": "Enrichir la page (FAQ, exemples, mise à jour)",
    "Renforcer fortement le contenu et le maillage interne": "Renforcer le contenu et les liens internes",
    "Tester un angle de title plus explicite sur l'intention": "Tester un titre plus explicite sur l'intention de recherche",
}

SECTION_INTROS: dict[str, str] = {
    "Opportunités prioritaires": (
        "Ces pages ont le meilleur rapport entre volume de recherches, position actuelle et gain estimé. "
        "À traiter en premier."
    ),
    "Pages à surveiller": (
        "Ces pages ont perdu des positions depuis la période précédente. Une vérification du contenu et des liens s'impose."
    ),
    "Résultats Google à améliorer": (
        "Ces pages apparaissent souvent dans Google mais génèrent peu de clics. "
        "Le titre ou la description affichée n'est pas assez convaincant."
    ),
    "Pages proches d'une percée": (
        "Ces pages sont bien positionnées (entre 4 et 20). Un effort ciblé peut les faire remonter rapidement."
    ),
    "Pages sans traction": (
        "Ces pages n'attirent ni clics ni impressions significatives. "
        "Envisager une fusion, une redirection ou un abandon."
    ),
    "Conflits de mots-clés": (
        "Ces URLs semblent cibler les mêmes requêtes. À vérifier manuellement avant toute conclusion."
    ),
}

EMPTY_SECTION_MESSAGES: dict[str, str] = {
    "Opportunités prioritaires": "Aucune opportunité prioritaire détectée sur cette période.",
    "Pages à surveiller": (
        "Aucune perte significative détectée — comparer avec un export précédent pour activer cette section."
    ),
    "Résultats Google à améliorer": "Aucun résultat Google à améliorer détecté sur cette période.",
    "Pages proches d'une percée": "Aucune page proche d'une percée détectée sur cette période.",
    "Pages sans traction": "Aucune page sans traction détectée sur cette période.",
    "Conflits de mots-clés": "Aucun conflit détecté sur cette période.",
}


def translate(key: str) -> str:
    return LABEL_MAP.get(key, key)
