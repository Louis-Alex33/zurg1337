from __future__ import annotations

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


def build_primary_rationale(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if business_signals:
        lines.append(
            f"Le rapport fait ressortir en priorité : {client_signal_label(str(business_signals[0].get('key') or ''), str(business_signals[0].get('signal') or '')).lower()}."
        )
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
    if signal_key in {"thin_content_pages", "weak_internal_linking_pages", "deep_pages_detected"}:
        reason_map = {
            "thin_content_pages": "contenu à enrichir pour mieux répondre à la recherche",
            "weak_internal_linking_pages": "peu de liens internes vers cette page",
            "deep_pages_detected": "page trop éloignée de l'accueil",
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
