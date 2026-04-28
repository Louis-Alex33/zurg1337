from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import _root_dir


def is_audit_report_json(relative_path: Path) -> bool:
    return (
        relative_path.suffix == ".json"
        and str(relative_path).startswith("reports/audits/")
        and relative_path.name != "audit_summary.json"
    )


def read_csv_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def format_report_datetime(value: object) -> str:
    if value in {None, ""}:
        return "-"
    raw_value = str(value)
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return raw_value
    months = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year} à {parsed.hour:02d}:{parsed.minute:02d}"


def audit_score_title(score: int) -> str:
    if score >= 75:
        return "Base globalement solide"
    if score >= 60:
        return "Base crédible, avec des optimisations visibles"
    return "Potentiel clair, mais plusieurs points sautent aux yeux"


def build_audit_hero_summary(
    score: int,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
) -> str:
    top_signal = ""
    if business_signals:
        top_signal = client_signal_label(
            str(business_signals[0].get("key") or ""),
            str(business_signals[0].get("signal") or ""),
        ).lower()

    if score >= 75:
        intro = "Le site donne une impression plutôt rassurante à première lecture."
    elif score >= 60:
        intro = "Le site repose sur une base crédible, avec plusieurs améliorations faciles à illustrer."
    else:
        intro = "Le site laisse apparaître plusieurs points visibles qui peuvent nourrir une prise de contact."

    if top_signal:
        intro += f" Le sujet le plus lisible aujourd'hui concerne {top_signal}."

    content_pages = int(summary.get("content_like_pages", 0) or 0)
    if content_pages:
        intro += f" L'analyse s'appuie sur {content_pages} contenus repérés sur le site."
    return intro


def sanitize_report_variant(variant: str) -> str:
    return "portfolio" if variant == "portfolio" else "full"


def client_report_subtitle() -> str:
    return "Analyse rapide d’un site de contenu pour repérer les pages à reprendre en priorité."


def client_score_label(score: int) -> str:
    if score >= 75:
        return "Base observée : plutôt saine"
    if score >= 60:
        return "Base observée : saine, avec plusieurs reprises utiles"
    return "Base observée : premiers signaux à corriger"


def client_score_note(score: int, pages_crawled: int) -> str:
    return (
        f"Lecture fondée sur {pages_crawled} page(s) publiques visitées. "
        f"L’indicateur {score}/100 aide à situer l’ensemble, sans prétendre résumer à lui seul la qualité du site."
    )


def client_scope_summary(summary: dict[str, object], pages_crawled: int) -> str:
    content_pages = int(summary.get("content_like_pages", 0) or 0)
    if content_pages:
        return f"{pages_crawled} pages visitées, dont {content_pages} pages de contenu réellement utiles pour la lecture."
    return f"{pages_crawled} pages publiques visitées pour établir une première lecture structurée."


def top_priority_summary(top_pages: list[dict[str, object]]) -> str:
    if not top_pages:
        return "Aucune page prioritaire nette n’a été isolée."
    first_targets = ", ".join(format_url_display(str(item.get("url") or "")) for item in top_pages[:2] if item.get("url"))
    if not first_targets:
        return "Quelques pages ressortent, mais demandent encore une vérification manuelle."
    return f"Les premières pages à regarder sont {first_targets}."


def build_client_takeaways(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if business_signals:
        lines.append(
            f"Le signal qui ressort en premier concerne {client_signal_label(str(business_signals[0].get('key') or ''), str(business_signals[0].get('signal') or '')).lower()}."
        )
    if int(summary.get("content_like_pages", 0) or 0):
        lines.append("Le site présente une base de contenus suffisante pour prioriser des reprises ciblées avant de produire du neuf.")
    if top_pages:
        lines.append("Quelques pages permettent de matérialiser rapidement l’analyse avec des exemples concrets à montrer.")
    return lines[:3]


def build_client_actions(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[str]:
    actions: list[str] = []
    if int(summary.get("noindex_pages", 0) or 0):
        actions.append("Vérifier les pages de contenu marquées noindex avant toute reprise éditoriale.")
    if int(summary.get("canonical_to_other_url_pages", 0) or 0) or int(summary.get("canonical_cross_domain_pages", 0) or 0):
        actions.append("Contrôler les canonicals qui pointent vers une autre URL.")
    if int(summary.get("dated_content_signals", 0) or 0):
        actions.append("Vérifier que les dates visibles correspondent bien à l’état réel des contenus importants.")
    if int(summary.get("thin_content_pages", 0) or 0):
        actions.append("Retravailler d’abord les pages les plus légères avant d’ouvrir de nouveaux sujets.")
    if int(summary.get("possible_content_overlap_pairs", 0) or 0):
        actions.append("Clarifier l’angle des contenus qui semblent répondre au même besoin.")
    if int(summary.get("probable_orphan_pages", 0) or 0) or int(summary.get("weak_internal_linking_pages", 0) or 0):
        actions.append("Renforcer le maillage interne depuis les pages déjà visibles ou déjà bien positionnées.")
    if top_pages:
        actions.append("Prioriser 2 à 3 pages à reprendre en premier pour montrer rapidement un avant / après.")
    if not actions:
        actions.append("Vérifier manuellement les pages les plus visibles avant de décider d’un plan de reprise.")
    return actions[:5]


def client_urgency_label(
    score: int,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
) -> str:
    high_signals = sum(1 for item in business_signals if str(item.get("severity") or "") == "HIGH")
    blocking_count = sum(
        _as_int(summary.get(key))
        for key in (
            "noindex_pages",
            "canonical_to_other_url_pages",
            "canonical_cross_domain_pages",
            "robots_blocked_pages",
        )
    )
    if score < 60 or blocking_count or high_signals >= 3:
        return "Niveau d’urgence : élevé"
    if score < 75 or business_signals:
        return "Niveau d’urgence : moyen"
    return "Niveau d’urgence : faible"


def build_client_strengths(summary: dict[str, object], observed_score: int) -> list[str]:
    pages_crawled = _as_int(summary.get("pages_crawled"))
    pages_ok = _as_int(summary.get("pages_ok"))
    content_pages = _as_int(summary.get("content_like_pages"))
    avg_score = _as_int(summary.get("avg_page_health_score"))
    strengths: list[str] = []
    if pages_ok and (pages_crawled == 0 or pages_ok >= max(1, round(pages_crawled * 0.85))):
        strengths.append("La majorité des pages visitées répond correctement, sans signal d’erreur massif dans le crawl.")
    if content_pages >= 5:
        strengths.append(f"Le site dispose déjà d’une base éditoriale exploitable avec {content_pages} contenus repérés.")
    elif content_pages:
        strengths.append(f"{content_pages} contenu(s) utile(s) ressortent déjà et peuvent servir de point de départ.")
    if avg_score >= 70 or observed_score >= 75:
        strengths.append("La base observée est plutôt saine : les reprises proposées visent surtout à consolider l’existant.")
    if not _as_int(summary.get("missing_titles")) and not _as_int(summary.get("missing_h1")):
        strengths.append("Les titres principaux et les titres Google ne montrent pas de manque généralisé sur les pages analysées.")
    if not _as_int(summary.get("pages_with_errors")):
        strengths.append("Aucune vague d’erreurs HTTP bloquantes n’apparaît dans les pages visitées.")
    if (
        not _as_int(summary.get("duplicate_title_groups"))
        and not _as_int(summary.get("duplicate_meta_description_groups"))
        and not _as_int(summary.get("possible_content_overlap_pairs"))
    ):
        strengths.append("Le crawl ne fait pas ressortir de duplication forte entre les contenus analysés.")
    if not strengths:
        strengths.append("Le site donne déjà assez de matière pour travailler avec des exemples concrets plutôt qu’avec des constats abstraits.")
    return strengths[:5]


def build_score_explanation(score: int, summary: dict[str, object]) -> list[str]:
    positives: list[str] = []
    limits: list[str] = []
    content_pages = _as_int(summary.get("content_like_pages"))
    pages_ok = _as_int(summary.get("pages_ok"))
    pages_with_errors = _as_int(summary.get("pages_with_errors"))
    avg_page_score = _as_int(summary.get("avg_page_health_score"))

    if pages_ok and not pages_with_errors:
        positives.append("les pages visitées répondent majoritairement correctement")
    if content_pages:
        positives.append(f"{content_pages} contenus donnent une base de travail concrète")
    if avg_page_score >= 70:
        positives.append(f"le score moyen des pages de contenu reste correct ({avg_page_score}/100)")

    blockers = [
        ("noindex_pages", "des pages importantes marquées noindex"),
        ("canonical_to_other_url_pages", "des canonicals à vérifier"),
        ("canonical_cross_domain_pages", "des canonicals externes à contrôler"),
        ("thin_content_pages", "des contenus encore trop légers"),
        ("dated_content_signals", "des dates visibles qui peuvent freiner la confiance"),
        ("weak_internal_linking_pages", "un soutien interne insuffisant sur certaines pages"),
        ("possible_content_overlap_pairs", "des sujets proches à clarifier"),
    ]
    for key, label in blockers:
        count = _as_int(summary.get(key))
        if count:
            limits.append(f"{count} {label}")

    lines: list[str] = []
    if positives:
        lines.append("Ce qui tire le score vers le haut : " + ", ".join(positives[:3]) + ".")
    if limits:
        lines.append("Ce qui empêche d’aller plus loin : " + ", ".join(limits[:3]) + ".")
    lines.append(
        f"Le score {score}/100 est un indicateur de priorisation, pas un verdict absolu : il sert à décider quoi reprendre en premier."
    )
    return lines


def build_priority_roadmap(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[dict[str, str]]:
    quick_actions: list[str] = []
    medium_actions: list[str] = []
    long_actions: list[str] = []

    if _as_int(summary.get("noindex_pages")):
        quick_actions.append("vérifier les pages noindex")
    if _as_int(summary.get("canonical_to_other_url_pages")) or _as_int(summary.get("canonical_cross_domain_pages")):
        quick_actions.append("contrôler les canonicals")
    if _as_int(summary.get("missing_meta_descriptions")):
        quick_actions.append("compléter les descriptions Google manquantes")
    if _as_int(summary.get("dated_content_signals")):
        quick_actions.append("actualiser les dates et éléments visibles obsolètes")
    if _as_int(summary.get("weak_internal_linking_pages")) or _as_int(summary.get("probable_orphan_pages")):
        quick_actions.append("ajouter des liens internes évidents vers les pages isolées")

    if top_pages:
        medium_actions.append("reprendre les pages prioritaires avec un brief clair page par page")
    if _as_int(summary.get("thin_content_pages")):
        medium_actions.append("enrichir les contenus trop courts avec exemples, critères de choix et FAQ")
    if _as_int(summary.get("possible_content_overlap_pairs")):
        medium_actions.append("différencier ou fusionner les contenus qui répondent au même besoin")
    if _as_int(summary.get("duplicate_title_groups")) or _as_int(summary.get("duplicate_meta_description_groups")):
        medium_actions.append("clarifier les titles et metas des groupes proches")

    if _as_int(summary.get("possible_content_overlap_pairs")) or _as_int(summary.get("content_like_pages")) >= 10:
        long_actions.append("structurer des clusters éditoriaux autour des pages les plus utiles")
    if _as_int(summary.get("deep_pages_detected")) or _as_int(summary.get("probable_orphan_pages")):
        long_actions.append("renforcer les pages hub et les chemins de navigation")
    if business_signals:
        long_actions.append("définir une feuille de route éditoriale à partir des signaux confirmés")

    if not quick_actions:
        quick_actions.append("relire manuellement les 2 ou 3 pages prioritaires et valider les constats")
    if not medium_actions:
        medium_actions.append("améliorer les contenus qui portent déjà un potentiel business clair")
    if not long_actions:
        long_actions.append("consolider les meilleurs contenus avant d’ouvrir de nouveaux sujets")

    return [
        {"period": "Sous 30 jours", "focus": "Corrections rapides", "actions": sentence_from_actions(quick_actions[:3])},
        {"period": "Sous 60 jours", "focus": "Reprises éditoriales", "actions": sentence_from_actions(medium_actions[:3])},
        {"period": "Sous 90 jours", "focus": "Consolidation", "actions": sentence_from_actions(long_actions[:3])},
    ]


def build_impact_effort_matrix(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[dict[str, str]]:
    matrix: list[dict[str, str]] = []
    seen_actions: set[str] = set()
    signal_actions = {
        "noindex_pages": ("Vérifier les pages noindex", "Élevé", "Faible", "Haute"),
        "canonical_to_other_url_pages": ("Contrôler les canonicals", "Élevé", "Moyen", "Haute"),
        "canonical_cross_domain_pages": ("Contrôler les canonicals externes", "Élevé", "Moyen", "Haute"),
        "robots_blocked_pages": ("Vérifier les pages bloquées par robots.txt", "Élevé", "Moyen", "Haute"),
        "dated_content_signals": ("Mettre à jour les contenus datés", "Élevé", "Moyen", "Haute"),
        "probable_orphan_pages": ("Remettre en avant les pages isolées", "Élevé", "Faible", "Haute"),
        "weak_internal_linking_pages": ("Renforcer le maillage interne", "Élevé", "Faible", "Haute"),
        "thin_content_pages": ("Enrichir les contenus légers", "Moyen", "Moyen", "Moyenne"),
        "possible_content_overlap_pairs": ("Clarifier les contenus proches", "Élevé", "Moyen", "Haute"),
        "duplicate_title_groups": ("Différencier les titres Google", "Moyen", "Faible", "Moyenne"),
        "duplicate_meta_description_groups": ("Différencier les descriptions Google", "Moyen", "Faible", "Moyenne"),
        "deep_pages_detected": ("Rapprocher les pages profondes", "Moyen", "Faible", "Moyenne"),
    }
    keys = [str(item.get("key") or "") for item in business_signals]
    keys.extend(key for key in signal_actions if _as_int(summary.get(key)))
    for key in keys:
        if key not in signal_actions:
            continue
        action, impact, effort, priority = signal_actions[key]
        if action in seen_actions:
            continue
        seen_actions.add(action)
        count = _as_int(summary.get(key))
        label = f"{action} ({count})" if count else action
        matrix.append({"priority": priority, "action": label, "impact": impact, "effort": effort})
        if len(matrix) >= 6:
            break
    if top_pages and "Prioriser les pages à reprendre" not in seen_actions:
        matrix.append(
            {
                "priority": "Haute",
                "action": f"Prioriser les {min(len(top_pages), 3)} premières pages à reprendre",
                "impact": "Élevé",
                "effort": "Moyen",
            }
        )
    if not matrix:
        matrix.append(
            {
                "priority": "Moyenne",
                "action": "Valider les pages les plus visibles avec une relecture manuelle",
                "impact": "Moyen",
                "effort": "Faible",
            }
        )
    return matrix[:6]


def build_editorial_opportunities(
    summary: dict[str, object],
    top_pages: list[dict[str, object]],
) -> list[str]:
    opportunities: list[str] = []
    content_pages = _as_int(summary.get("content_like_pages"))
    if content_pages >= 8:
        opportunities.append(
            f"Consolider les {content_pages} contenus repérés : le site a déjà assez de matière pour améliorer l’existant avant de produire du neuf."
        )
    if _as_int(summary.get("possible_content_overlap_pairs")):
        opportunities.append("Transformer les contenus proches en pages complémentaires : un hub, des guides spécialisés ou une fusion selon l’intention réelle.")
    if _as_int(summary.get("weak_internal_linking_pages")) or _as_int(summary.get("probable_orphan_pages")):
        opportunities.append("Créer des liens depuis les pages les plus complètes vers les contenus peu visibles afin de mieux distribuer l’autorité interne.")
    if _as_int(summary.get("dated_content_signals")):
        opportunities.append("Ajouter un angle fraîcheur : mise à jour, comparaison récente, exemples actuels, sélection par niveau ou par besoin.")
    if _as_int(summary.get("thin_content_pages")):
        opportunities.append("Enrichir les pages courtes avec des sections d’aide à la décision : critères, erreurs à éviter, FAQ et cas d’usage.")
    if top_pages:
        first_target = format_url_display(str(top_pages[0].get("url") or ""))
        opportunities.append(f"Utiliser {first_target} comme page pilote pour montrer rapidement la méthode de reprise.")
    if not opportunities:
        opportunities.append("Aucune grande faiblesse éditoriale ne ressort automatiquement : la suite logique est une validation manuelle des pages business clés.")
    return opportunities[:5]


def build_method_limit_lines(
    summary: dict[str, object],
    pages_crawled: int,
    crawl_metadata: dict[str, object],
    confidence_notes: list[str],
) -> list[str]:
    lines = [client_scope_summary(summary, pages_crawled)]
    crawl_source = str(crawl_metadata.get("crawl_source") or "").strip()
    if crawl_source:
        source_label = {"home": "page d’accueil", "sitemap": "sitemap", "mixed": "page d’accueil + sitemap"}.get(
            crawl_source,
            crawl_source,
        )
        lines.append(f"Source de crawl utilisée : {source_label}.")
    sitemap_count = _as_int(crawl_metadata.get("sitemap_urls_found"))
    if sitemap_count:
        lines.append(f"Sitemap détecté avec {sitemap_count} URL(s) exploitables pendant l’analyse.")
    elif crawl_source in {"sitemap", "mixed"}:
        lines.append("Aucun sitemap exploitable n’a été confirmé pendant cette analyse.")
    stop_reason = str(crawl_metadata.get("stop_reason") or "").strip()
    if stop_reason:
        lines.append(crawl_stop_reason_label(stop_reason, crawl_metadata))
    remaining = _as_int(crawl_metadata.get("queued_urls_remaining"))
    if remaining:
        lines.append(f"{remaining} URL(s) restaient en file d’attente au moment de l’arrêt du crawl.")
    if crawl_metadata:
        robots = "oui" if crawl_metadata.get("robots_txt_available") else "non"
        lines.append(f"Robots.txt détecté : {robots}.")
    lines.extend(str(item) for item in confidence_notes[:2] if item)
    return lines[:7]


def crawl_stop_reason_label(reason: str, crawl_metadata: dict[str, object]) -> str:
    labels = {
        "queue_empty": "Le crawl s’est arrêté naturellement après épuisement des URLs accessibles dans le budget.",
        "max_pages_reached": f"Le crawl a atteint la limite fixée de {_as_int(crawl_metadata.get('max_pages'))} pages.",
        "max_total_seconds_reached": "Le crawl a été arrêté par la limite de temps définie.",
        "max_total_requests_reached": "Le crawl a été arrêté par la limite de requêtes définie.",
        "max_consecutive_errors": "Le crawl a été interrompu après plusieurs erreurs consécutives.",
        "no_pages_collected": "Le crawl n’a pas réussi à collecter de pages HTML exploitables.",
    }
    return labels.get(reason, f"Raison d’arrêt du crawl : {reason}.")


def build_page_rework_brief(
    item: dict[str, object],
    page_details: dict[str, object],
) -> dict[str, str]:
    reasons = [client_reason_label(str(reason)) for reason in (item.get("reasons") or [])]
    issues = [str(issue) for issue in (page_details.get("issues") or [])]
    dated_refs = [str(ref) for ref in (page_details.get("dated_references") or [])]
    word_count = _as_int(item.get("word_count") or page_details.get("word_count"))
    priority = _as_int(item.get("priority_score"))
    h1_values = page_details.get("h1") or []
    first_h1 = str(h1_values[0]) if isinstance(h1_values, list) and h1_values else ""
    title = str(page_details.get("title") or first_h1 or "").strip()
    url = str(item.get("url") or page_details.get("url") or "")

    observation_parts: list[str] = []
    if word_count:
        observation_parts.append(f"{word_count} mots observés")
    observation_parts.extend(issues[:2])
    observation_parts.extend(dated_refs[:1])
    if not observation_parts:
        observation_parts.append("La page ressort dans les signaux prioritaires du crawl.")

    return {
        "why": ", ".join(reasons[:3]) if reasons else "La page ressort dans les priorités du crawl.",
        "observation": ". ".join(observation_parts[:3]),
        "recommended_action": recommend_page_action(reasons, issues),
        "effort": estimate_page_effort(reasons, word_count),
        "impact": estimate_page_impact(reasons, priority),
        "rewrite_angle": build_rewrite_angle(url, title, reasons),
    }


def recommend_page_action(reasons: list[str], issues: list[str]) -> str:
    haystack = " ".join([*reasons, *issues]).lower()
    if "noindex" in haystack:
        return "Vérifier l’intention d’indexation puis rouvrir la page si elle doit travailler en SEO."
    if "canonical" in haystack:
        return "Contrôler la canonical et confirmer quelle URL doit porter le sujet."
    if "date" in haystack or "daté" in haystack:
        return "Mettre à jour les informations visibles et ajouter un signal clair de fraîcheur éditoriale."
    if "lien" in haystack or "maillage" in haystack or "navigation" in haystack:
        return "Ajouter des liens internes depuis des pages proches et clarifier les ancres."
    if "contenu" in haystack or "mots" in haystack:
        return "Enrichir la page avec les réponses, critères et exemples attendus par l’utilisateur."
    if "description google" in haystack or "titre google" in haystack:
        return "Réécrire le title et la meta description autour d’une promesse plus précise."
    return "Relire la page, confirmer le signal, puis définir une reprise éditoriale ciblée."


def estimate_page_effort(reasons: list[str], word_count: int) -> str:
    haystack = " ".join(reasons).lower()
    if "canonical" in haystack or "noindex" in haystack:
        return "faible à moyen"
    if "contenu" in haystack or word_count and word_count < 350:
        return "moyen"
    if "lien" in haystack or "description google" in haystack or "titre google" in haystack:
        return "faible"
    return "moyen"


def estimate_page_impact(reasons: list[str], priority: int) -> str:
    haystack = " ".join(reasons).lower()
    if priority >= 8 or "noindex" in haystack or "canonical" in haystack:
        return "élevé"
    if priority >= 4 or "maillage" in haystack or "contenu" in haystack:
        return "moyen à élevé"
    return "moyen"


def build_rewrite_angle(url: str, title: str, reasons: list[str]) -> str:
    readable_topic = title.strip()
    if not readable_topic:
        slug = url.rstrip("/").split("/")[-1]
        readable_topic = re.sub(r"[-_]+", " ", slug).strip() or "le sujet principal"
    lower_reasons = " ".join(reasons).lower()
    if "date" in lower_reasons:
        return f"Repositionner la page comme une version actuelle de “{readable_topic}”."
    if "maillage" in lower_reasons or "navigation" in lower_reasons:
        return f"Faire de “{readable_topic}” une page mieux reliée depuis les contenus proches."
    if "contenu" in lower_reasons:
        return f"Transformer “{readable_topic}” en ressource plus complète, avec critères, exemples et réponses directes."
    return f"Clarifier la promesse de “{readable_topic}” pour mieux couvrir l’intention principale."


def sentence_from_actions(actions: list[str]) -> str:
    cleaned = [item.strip() for item in actions if item.strip()]
    if not cleaned:
        return "Prioriser les vérifications manuelles les plus simples."
    sentence = ", ".join(cleaned)
    return sentence[0].upper() + sentence[1:] + "."


def build_primary_rationale(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if business_signals:
        lines.append(
            f"Le rapport fait ressortir en priorité : {client_signal_label(str(business_signals[0].get('key') or ''), str(business_signals[0].get('signal') or '')).lower()}."
        )
    if int(summary.get("noindex_pages", 0) or 0):
        lines.append("Certaines pages de contenu sont marquées noindex, ce qui peut empêcher leur présence dans Google.")
    if int(summary.get("canonical_to_other_url_pages", 0) or 0) or int(summary.get("canonical_cross_domain_pages", 0) or 0):
        lines.append("Des canonicals demandent une vérification car elles peuvent déplacer le signal vers une autre URL.")
    if int(summary.get("weak_internal_linking_pages", 0) or 0):
        lines.append("Certaines pages semblent peu soutenues par les liens internes, ce qui limite leur visibilité dans le site.")
    if int(summary.get("possible_content_overlap_pairs", 0) or 0):
        lines.append("Plusieurs contenus paraissent proches dans leur intention, ce qui brouille parfois la lecture éditoriale.")
    if int(summary.get("dated_content_signals", 0) or 0):
        lines.append("Certaines dates visibles méritent une vérification, car elles influencent directement l’impression de fraîcheur.")
    return lines[:4]


def build_method_lines(summary: dict[str, object], pages_crawled: int) -> list[str]:
    content_pages = int(summary.get("content_like_pages", 0) or 0)
    return [
        f"Lecture fondée sur {pages_crawled} pages publiques visitées.",
        f"{content_pages} page(s) de contenu ont été retenues pour établir les priorités." if content_pages else "Le rapport repose sur les pages réellement accessibles pendant l’analyse.",
        "L’objectif est de prioriser les reprises utiles, pas de produire un audit exhaustif du site.",
    ]


def should_render_secondary_signal_section(
    overlaps: list[dict[str, object]],
    dated_content: list[dict[str, object]],
    business_signals: list[dict[str, object]],
) -> bool:
    return bool(overlaps or dated_content or business_signals)


def format_url_display(url: str, max_length: int = 58) -> str:
    if not url:
        return "-"
    cleaned = url.replace("https://", "").replace("http://", "").rstrip("/")
    return cleaned if len(cleaned) <= max_length else cleaned[: max_length - 1].rstrip("/") + "…"


def client_signal_label(signal_key: str, fallback: str) -> str:
    labels = {
        "thin_content_pages": "Pages à reprendre en priorité",
        "duplicate_title_groups": "Titres Google trop proches d’une page à l’autre",
        "duplicate_meta_description_groups": "Descriptions Google à clarifier",
        "dated_content_signals": "Dates visibles à vérifier",
        "probable_orphan_pages": "Pages peu mises en avant dans le site",
        "weak_internal_linking_pages": "Pages peu soutenues par les liens internes",
        "deep_pages_detected": "Pages éloignées de l’accueil",
        "possible_content_overlap_pairs": "Contenus trop proches sur le même sujet",
        "noindex_pages": "Pages importantes marquées noindex",
        "canonical_to_other_url_pages": "Canonicals à vérifier",
        "canonical_cross_domain_pages": "Canonicals externes à vérifier",
        "robots_blocked_pages": "Pages bloquées par robots.txt",
    }
    return labels.get(signal_key, fallback or "Aucune priorité nette")


def client_reason_label(reason: str) -> str:
    labels = {
        "contenu à enrichir pour mieux répondre à la recherche": "contenu à renforcer pour mieux couvrir le sujet",
        "date visible à actualiser": "date visible à vérifier",
        "page difficile à retrouver dans le site": "page peu visible dans la navigation",
        "peu de liens internes vers cette page": "page peu soutenue par les liens internes",
        "page trop éloignée de l'accueil": "page assez loin de l’accueil",
        "description Google absente": "description Google absente",
        "titre Google absent": "titre Google absent",
        "page marquée noindex": "page noindex",
        "canonical à vérifier": "canonical à vérifier",
        "ancres internes trop génériques": "ancres internes génériques",
    }
    return labels.get(reason, reason)


def client_finding_text(finding: str) -> str:
    cleaned = finding.strip()
    replacements = {
        " pages affichent une date qui peut donner une impression de contenu ancien": " pages affichent des dates visibles à vérifier",
        " paires de pages semblent répondre à la même intention": " paires de pages semblent traiter le même sujet",
        " pages reçoivent trop peu de liens internes pour bien remonter": " pages reçoivent peu de liens internes",
        " pages importantes semblent trop éloignées de l'accueil": " pages importantes semblent assez éloignées de l’accueil",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    return cleaned


def signal_helper_text(signal_key: str) -> str:
    helpers = {
        "thin_content_pages": "Ces pages méritent un enrichissement pour mieux répondre à la recherche.",
        "duplicate_title_groups": "Plusieurs pages envoient presque la même promesse dans Google.",
        "duplicate_meta_description_groups": "Le texte affiché sous le résultat Google semble répété sur plusieurs pages.",
        "dated_content_signals": "Une date visible mérite d’être vérifiée car elle influence la perception du contenu.",
        "probable_orphan_pages": "Certaines pages semblent difficiles à retrouver depuis le reste du site.",
        "weak_internal_linking_pages": "Certaines pages reçoivent trop peu de liens internes pour être bien soutenues.",
        "deep_pages_detected": "Certaines pages paraissent trop éloignées de la page d'accueil.",
        "possible_content_overlap_pairs": "Certaines pages semblent répondre au même besoin et peuvent se concurrencer.",
        "noindex_pages": "Certaines pages de contenu sont explicitement écartées de l'indexation.",
        "canonical_to_other_url_pages": "Certaines pages indiquent une URL canonique différente.",
        "canonical_cross_domain_pages": "Certaines pages indiquent une URL canonique sur un autre domaine.",
        "robots_blocked_pages": "Certaines URLs sont bloquées par les règles robots.txt observées.",
    }
    return helpers.get(signal_key, "Ce signal mérite une vérification manuelle dans le contexte du site.")


def build_signal_examples(signal_key: str, payload: dict[str, object]) -> list[str]:
    top_pages = payload.get("top_pages_to_rework") or []
    overlaps = payload.get("possible_content_overlap") or []
    dated_content = payload.get("dated_content_signals") or []
    duplicate_titles = payload.get("duplicate_titles") or {}
    duplicate_metas = payload.get("duplicate_meta_descriptions") or {}
    probable_orphans = payload.get("probable_orphan_pages") or []

    if signal_key == "dated_content_signals":
        return [
            f"{format_url_display(str(item.get('url', '-')))} : {', '.join(str(ref) for ref in item.get('references', [])[:2])}"
            for item in dated_content[:5]
        ]
    if signal_key == "possible_content_overlap_pairs":
        return [
            f"{item.get('title_1', '-')} / {item.get('title_2', '-')} ({item.get('similarity', 0)}%)"
            for item in overlaps[:5]
        ]
    if signal_key == "probable_orphan_pages":
        return [format_url_display(str(url)) for url in probable_orphans[:5]]
    if signal_key in {"thin_content_pages", "weak_internal_linking_pages", "deep_pages_detected", "noindex_pages", "canonical_to_other_url_pages"}:
        reason_map = {
            "thin_content_pages": "contenu à enrichir pour mieux répondre à la recherche",
            "weak_internal_linking_pages": "peu de liens internes vers cette page",
            "deep_pages_detected": "page trop éloignée de l'accueil",
            "noindex_pages": "page marquée noindex",
            "canonical_to_other_url_pages": "canonical à vérifier",
        }
        reason = reason_map[signal_key]
        return [
            format_url_display(str(item.get("url", "-")))
            for item in top_pages
            if reason in [str(value) for value in item.get("reasons", [])]
        ][:5]
    if signal_key == "duplicate_title_groups":
        return [f"\"{title}\" repris sur {len(urls)} pages" for title, urls in list(duplicate_titles.items())[:5]]
    if signal_key == "duplicate_meta_description_groups":
        return [f"Même texte de présentation repris sur {len(urls)} pages" for _meta, urls in list(duplicate_metas.items())[:5]]
    return []


def priority_score_label(value: object) -> str:
    score = _as_int(value)
    if score >= 10:
        return "priorité de reprise : très élevée"
    if score >= 7:
        return "priorité de reprise : élevée"
    if score >= 4:
        return "priorité de reprise : modérée"
    return "priorité de reprise : légère"


def depth_label(value: object) -> str:
    depth = _as_int(value)
    if depth <= 0:
        return "accès depuis l'accueil : page d'entrée"
    if depth == 1:
        return "accès depuis l'accueil : 1 clic"
    return f"accès depuis l'accueil : {depth} clics"


def build_commercial_read_lines(
    domain: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if business_signals:
        lead_signal = business_signals[0]
        lines.append(
            f"Pour {domain}, le point le plus simple à valoriser commercialement est : {str(lead_signal.get('signal') or 'une remise à niveau ciblée des contenus').lower()}."
        )
    content_pages = int(summary.get("content_like_pages", 0) or 0)
    if content_pages:
        lines.append(
            f"L'analyse a repéré {content_pages} pages qui ressemblent à de vrais contenus, ce qui suffit pour illustrer des gains rapides."
        )
    if top_pages:
        first_urls = ", ".join(str(item.get("url") or "-") for item in top_pages[:2])
        lines.append(f"Les premières pages à montrer dans un message ou une courte vidéo sont : {first_urls}.")
    if not lines:
        lines.append("Le rapport reste trop léger pour formuler un angle commercial fiable sans vérification manuelle.")
    return lines


def build_reusable_summary_text(
    domain: str,
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    summary: dict[str, object],
) -> str:
    signal_labels = [str(item.get("signal") or "").strip().lower() for item in business_signals[:2] if item.get("signal")]
    if signal_labels:
        signals_part = " et ".join(signal_labels)
    else:
        signals_part = "plusieurs signaux éditoriaux à vérifier"

    page_targets = ", ".join(str(item.get("url") or "-") for item in top_pages[:2])
    if not page_targets:
        page_targets = "quelques pages prioritaires du site"

    content_pages = int(summary.get("content_like_pages", 0) or 0)
    return (
        f"En regardant {domain}, le crawl observé remonte surtout {signals_part}. "
        f"Le site présente environ {content_pages} pages qui ressemblent à de vrais contenus, ce qui rend une mise à niveau éditoriale crédible. "
        f"Les premières URLs à revoir seraient {page_targets}. "
        "L'opportunité semble davantage liée à la clarté des contenus et à leur mise en avant qu'à un problème purement technique."
    )


def confidence_label(value: str) -> str:
    mapping = {
        "medium-high": "lecture assez solide",
        "medium": "lecture à confirmer",
        "low": "lecture à vérifier",
    }
    return mapping.get(value, value or "confiance non précisée")


def compute_audit_summary_metrics(rows: list[dict[str, str]]) -> dict[str, int]:
    scores = [_as_int(row.get("observed_health_score")) for row in rows]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    watch_domains = sum(1 for score in scores if score < 70)
    dated_signals = sum(_as_int(row.get("dated_content_signals")) for row in rows)
    return {
        "domains": len(rows),
        "columns": len(rows[0]) if rows else 0,
        "avg_score": avg_score,
        "watch_domains": watch_domains,
        "dated_signals": dated_signals,
    }


def build_priority_labels(row: dict[str, str], limit: int = 4) -> list[str]:
    mapping = [
        ("noindex_pages", "pages noindex"),
        ("canonical_to_other_url_pages", "canonicals à vérifier"),
        ("robots_blocked_pages", "bloquées robots.txt"),
        ("thin_content_pages", "contenus à enrichir"),
        ("duplicate_title_groups", "titres Google répétés"),
        ("duplicate_meta_description_groups", "descriptions Google répétées"),
        ("possible_content_overlap_pairs", "sujets trop proches"),
        ("probable_orphan_pages", "pages difficiles à retrouver"),
        ("weak_internal_linking_pages", "liens internes insuffisants"),
        ("deep_pages_detected", "pages loin de l'accueil"),
        ("dated_content_signals", "dates à actualiser"),
    ]
    labels: list[str] = []
    for key, label in mapping:
        count = _as_int(row.get(key))
        if count > 0:
            labels.append(f"{label} ({count})")
        if len(labels) >= limit:
            break
    return labels


def build_audit_summary_signal_note(row: dict[str, str]) -> str:
    score = _as_int(row.get("observed_health_score"))
    priorities = build_priority_labels(row, limit=2)
    if not priorities and score >= 75:
        return "Peu d'opportunités prioritaires ressortent dans ce récapitulatif."
    if priorities:
        return "À regarder d'abord : " + ", ".join(priorities)
    return "Audit présent, mais peu de points marquants dans ce résumé."


def audit_json_relative_path(domain: str) -> str:
    return f"reports/audits/{domain}.json"


def format_csv_cell(column_name: str, value: str) -> str:
    import html

    if not value:
        return "<span class='muted'>-</span>"
    escaped = html.escape(value)
    lower_name = column_name.lower()
    if lower_name == "domain":
        return f"<span class='pill domain-pill'>{escaped}</span>"
    if lower_name in {"source_query", "cms"}:
        return f"<span class='pill soft-pill'>{escaped}</span>"
    if lower_name == "score":
        try:
            score = int(float(value))
        except ValueError:
            return escaped
        tone = "score-low"
        if score >= 70:
            tone = "score-high"
        elif score >= 50:
            tone = "score-mid"
        return f"<span class='pill {tone}'>{score}</span>"
    if lower_name.endswith("provider"):
        return f"<span class='pill provider-pill'>{escaped}</span>"
    if lower_name in {"title", "snippet", "issues", "notes"}:
        return f"<div class='cell-text'>{escaped}</div>"
    return escaped


def human_file_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _as_int(value: object) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, str):
            return int(float(value.strip() or "0"))
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def root_has_file(relative_path: str) -> bool:
    return (_root_dir() / relative_path).exists()
