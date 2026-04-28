from __future__ import annotations

import html
import json
import math
import os
import re
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


DEFAULT_TOOL_NAME = "AuditSEO Pro"
DEFAULT_TOOL_TAGLINE = "L'audit SEO indépendant"
DEFAULT_CONTACT_CTA = "contact@monagence.fr"
DEFAULT_ANALYSTE_NOM = "Consultant SEO"
DEFAULT_ANALYSTE_TITRE = "Consultant SEO indépendant"

DEFAULT_OFFERS = [
    {
        "nom": "Audit ponctuel",
        "prix": "149€",
        "periode": "/ rapport",
        "mise_en_avant": False,
        "features": [
            "1 rapport complet",
            "3 pages prioritaires identifiées",
            "Plan d'action 30/60/90j",
        ],
    },
    {
        "nom": "Suivi mensuel",
        "prix": "249€",
        "periode": "/ mois",
        "mise_en_avant": True,
        "features": [
            "1 audit par mois",
            "Suivi de progression",
            "Briefs éditoriaux inclus",
            "1 appel de 30min",
        ],
    },
    {
        "nom": "Accompagnement",
        "prix": "Sur devis",
        "periode": "",
        "mise_en_avant": False,
        "features": [
            "Audit + rédaction",
            "Gestion de contenu",
            "Reporting mensuel",
        ],
    },
]

EFFORT_MAP = {
    ("page", "court"): (1, 2, "1 à 2h de travail éditorial"),
    ("page", "moyen"): (2, 4, "2 à 4h de travail éditorial"),
    ("page", "long"): (3, 6, "3 à 6h de travail éditorial"),
    ("article", "court"): (2, 3, "2 à 3h de rédaction"),
    ("article", "moyen"): (3, 5, "3 à 5h de rédaction"),
    ("article", "long"): (4, 8, "4 à 8h de rédaction"),
}

FRENCH_MONTHS = {
    1: "janvier",
    2: "février",
    3: "mars",
    4: "avril",
    5: "mai",
    6: "juin",
    7: "juillet",
    8: "août",
    9: "septembre",
    10: "octobre",
    11: "novembre",
    12: "décembre",
}

TITLE_EXCEPTIONS = {
    "seo": "SEO",
    "url": "URL",
    "h1": "H1",
    "http": "HTTP",
    "https": "HTTPS",
    "ia": "IA",
}

FRENCH_LANGUAGE_MARKERS = {
    "aides",
    "avec",
    "choisir",
    "comment",
    "conseils",
    "dans",
    "des",
    "devis",
    "du",
    "et",
    "les",
    "pour",
    "prix",
    "quel",
    "quelle",
    "retrouvez",
    "sur",
    "votre",
    "vous",
}

ENGLISH_LANGUAGE_MARKERS = {
    "about",
    "and",
    "best",
    "browse",
    "clear",
    "discover",
    "essential",
    "find",
    "for",
    "guide",
    "how",
    "in",
    "information",
    "shopping",
    "style",
    "the",
    "tips",
    "to",
    "travel",
    "what",
    "why",
    "with",
    "your",
}

SEUIL_LENT = 3.0
SEUIL_CRITIQUE = 4.0
SEUIL_TITRE_LONG = 60
SEUIL_DESC_COURTE = 70
SEUIL_DESC_LONGUE = 160


def slug_to_title(value: str) -> str:
    """Transforme un slug ou une URL en titre lisible côté client."""
    slug = value.strip()
    if not slug:
        return "Page sans titre"
    if "://" in slug:
        path = urlparse(slug).path.rstrip("/")
        slug = path.split("/")[-1] or urlparse(slug).netloc
    slug = re.sub(r"\.(html?|php)$", "", slug, flags=re.I)
    raw_tokens = [token for token in re.split(r"[-_\s]+", slug) if token]
    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        next_token = raw_tokens[index + 1] if index + 1 < len(raw_tokens) else ""
        after_next = raw_tokens[index + 2] if index + 2 < len(raw_tokens) else ""
        if token.isdigit() and next_token.isdigit() and len(next_token) == 1 and len(after_next) == 4:
            tokens.append(f"{token}.{next_token}")
            index += 2
            continue
        tokens.append(token)
        index += 1
    words = [TITLE_EXCEPTIONS.get(token.lower(), token[:1].upper() + token[1:].lower()) for token in tokens]
    return " ".join(words) or "Page sans titre"


def score_color_class(score: int) -> str:
    if score >= 90:
        return "score-high"
    if score >= 75:
        return "score-mid"
    return "score-low"


def classify_speed(load_time: float | None) -> str:
    if load_time is None:
        return "inconnu"
    if load_time < SEUIL_LENT:
        return "correct"
    if load_time < SEUIL_CRITIQUE:
        return "lent"
    return "critique"


def speed_color_class(load_time: float | None) -> str:
    return {
        "correct": "score-high",
        "lent": "score-mid",
        "critique": "score-low",
        "inconnu": "score-unknown",
    }[classify_speed(load_time)]


def needs_title_fix(page: dict[str, Any]) -> bool:
    title = str(page.get("titre_google") or "")
    return not title or len(title) > SEUIL_TITRE_LONG


def needs_desc_fix(page: dict[str, Any]) -> bool:
    desc = str(page.get("description_google") or "")
    if not desc:
        return True
    return len(desc) < SEUIL_DESC_COURTE or len(desc) > SEUIL_DESC_LONGUE


def analyste_name_is_valid(value: str) -> bool:
    name = value.strip()
    return bool(name and name != DEFAULT_ANALYSTE_NOM and len(name) > 2)


def resolve_date_placeholders(text: str) -> str:
    current_year = str(datetime.now().year)
    pattern = r"\[current_date\s+format\s*=\s*[\"']?Y[\"']?\s*\]"
    return re.sub(pattern, current_year, text)


def resolve_all_placeholders(obj: Any) -> Any:
    if isinstance(obj, str):
        return resolve_date_placeholders(obj)
    if isinstance(obj, list):
        return [resolve_all_placeholders(item) for item in obj]
    if isinstance(obj, dict):
        return {key: resolve_all_placeholders(value) for key, value in obj.items()}
    return obj


def render_premium_audit_report(source: Any, *, standalone: bool = True, overrides: dict[str, Any] | None = None) -> str:
    context = prepare_audit_report_context(source, overrides=overrides)
    body = render_report_body(context)
    styles = render_report_styles()
    script = render_report_script()
    if not standalone:
        return f"<style>{styles}</style>{body}{script}"
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="audit-report">
  <title>Audit SEO - {escape(context["domain"])}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>{styles}</style>
</head>
<body class="report-document">
  {body}
  {script}
</body>
</html>"""


def prepare_audit_report_context(source: Any, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    data = object_to_mapping(source)
    if overrides:
        data = {**data, **overrides}
    data = resolve_all_placeholders(data)
    summary = as_dict(data.get("summary"))
    pages = [as_dict(page) for page in data.get("pages", []) if isinstance(page, dict)]
    pages_by_url = {str(page.get("url") or ""): page for page in pages if page.get("url")}
    top_pages = [as_dict(page) for page in data.get("top_pages_to_rework", []) if isinstance(page, dict)]
    business_signals = [as_dict(item) for item in data.get("business_priority_signals", []) if isinstance(item, dict)]
    dated_content = [as_dict(item) for item in data.get("dated_content_signals", []) if isinstance(item, dict)]

    score = clamp_score(get_int(data, "score_global", get_int(data, "observed_health_score", 0)))
    domain = str(data.get("domain") or "Domaine audité")
    pages_analysees = get_int(data, "pages_analysees", get_int(data, "pages_crawled", get_int(summary, "pages_crawled", len(pages))))
    pages_erreur = get_int(data, "pages_erreur", get_int(summary, "pages_with_errors", 0))
    signal_principal = str(data.get("signal_principal") or build_primary_signal(summary, business_signals))
    pages_prioritaires = normalize_priority_pages(data.get("pages_prioritaires") or top_pages, pages_by_url)
    urls_crawlees = normalize_crawled_urls(data.get("urls_crawlees") or pages)
    enrich_priority_pages_with_maillage(pages_prioritaires, urls_crawlees, domain)
    urls_crawlees = generate_seo_suggestions_for_priority_pages(urls_crawlees, pages_prioritaires)
    perf = build_perf_data(urls_crawlees)
    analyste_nom = str(data.get("analyste_nom") or DEFAULT_ANALYSTE_NOM).strip()
    analyste_titre = str(data.get("analyste_titre") or DEFAULT_ANALYSTE_TITRE).strip()
    logo_url = str(data.get("logo_url") or "").strip()
    dirigeant_defaults = build_dirigeant_texts(
        domain=domain,
        score=score,
        pages_analysees=pages_analysees,
        contenus_utiles=get_int(data, "contenus_utiles", get_int(summary, "content_like_pages", 0)),
        score_moyen_page=get_int(data, "score_moyen_page", get_int(summary, "avg_page_health_score", 0)),
        signal_principal=signal_principal,
        dates_a_verifier=get_int(data, "dates_a_verifier", get_int(summary, "dated_content_signals", len(dated_content))),
        pages_prioritaires=pages_prioritaires,
    )
    dirigeant_overrides = as_dict(data.get("dirigeant"))
    benchmark = normalize_benchmark(data.get("benchmark"))
    benchmark_disponible = get_bool(data.get("benchmark_disponible"), default=bool(benchmark)) and bool(benchmark)
    offres_source = data.get("offres") if "offres" in data else DEFAULT_OFFERS
    context = {
        "tool_name": str(data.get("tool_name") or DEFAULT_TOOL_NAME),
        "tool_tagline": str(data.get("tool_tagline") or DEFAULT_TOOL_TAGLINE),
        "logo_url": logo_url,
        "contact_cta": str(data.get("contact_cta") or DEFAULT_CONTACT_CTA),
        "analyste_nom": analyste_nom,
        "analyste_titre": analyste_titre,
        "analyste_valide": analyste_name_is_valid(analyste_nom),
        "analyste_linkedin": str(data.get("analyste_linkedin") or ""),
        "analyste_photo": str(data.get("analyste_photo") or ""),
        "domain": domain,
        "audit_date": str(data.get("audit_date") or format_audit_date(str(data.get("audited_at") or ""))),
        "score_global": score,
        "urgency_level": str(data.get("urgency_level") or infer_urgency(score, summary, business_signals)),
        "base_status": str(data.get("base_status") or infer_base_status(score)),
        "pages_analysees": pages_analysees,
        "pages_saines": get_int(data, "pages_saines", get_int(summary, "pages_ok", max(0, pages_analysees - pages_erreur))),
        "contenus_utiles": get_int(data, "contenus_utiles", get_int(summary, "content_like_pages", 0)),
        "pages_erreur": pages_erreur,
        "descriptions_manquantes": get_int(data, "descriptions_manquantes", get_int(summary, "missing_meta_descriptions", 0)),
        "titres_manquants": get_int(data, "titres_manquants", get_int(summary, "missing_titles", 0)),
        "score_moyen_page": get_int(data, "score_moyen_page", get_int(summary, "avg_page_health_score", 0)),
        "pages_noindex": get_int(data, "pages_noindex", get_int(summary, "noindex_pages", 0)),
        "canonicals": get_int(data, "canonicals", get_int(summary, "canonical_to_other_url_pages", 0)),
        "pages_peu_reliees": get_int(data, "pages_peu_reliees", get_int(summary, "weak_internal_linking_pages", 0)),
        "sujets_trop_proches": get_int(data, "sujets_trop_proches", get_int(summary, "possible_content_overlap_pairs", 0)),
        "dates_a_verifier": get_int(data, "dates_a_verifier", get_int(summary, "dated_content_signals", len(dated_content))),
        "signal_principal": signal_principal,
        "resume_dirigeant": str(data.get("resume_dirigeant") or dirigeant_overrides.get("resume_dirigeant") or dirigeant_defaults["resume_dirigeant"]),
        "ou_vous_en_etes": str(data.get("ou_vous_en_etes") or dirigeant_overrides.get("ou_vous_en_etes") or dirigeant_defaults["ou_vous_en_etes"]),
        "risque_attente": str(data.get("risque_attente") or dirigeant_overrides.get("risque_attente") or dirigeant_defaults["risque_attente"]),
        "recommandation_courte": str(data.get("recommandation_courte") or dirigeant_overrides.get("recommandation_courte") or dirigeant_defaults["recommandation_courte"]),
        "benchmark_disponible": benchmark_disponible,
        "benchmark": benchmark,
        "ce_qui_fonctionne": list_or_default(data.get("ce_qui_fonctionne"), build_strengths(summary, pages_analysees, score)),
        "points_attention": list_or_default(data.get("points_attention"), build_attention_points(summary, business_signals, data)),
        "plan_action": as_dict(data.get("plan_action")) or build_plan_action(summary, top_pages),
        "matrice": normalize_matrix(as_dict(data.get("matrice")) or build_matrix(summary, top_pages)),
        "pages_prioritaires": pages_prioritaires,
        "signaux": normalize_signals(data.get("signaux") or dated_content),
        "opportunites": list_or_default(data.get("opportunites"), build_editorial_opportunities(summary, top_pages)),
        "urls_crawlees": urls_crawlees,
        "perf": perf,
        "methode": as_dict(data.get("methode")) or build_method(data, summary),
        "offres": normalize_offers(offres_source),
    }
    context["gauge"] = score_gauge_values(score)
    context["actions_30j"] = build_conclusion_actions(context)
    return context


def render_report_body(context: dict[str, Any]) -> str:
    priority_pages = render_priority_pages(context)
    signals = render_secondary_signals(context)
    return f"""
<main class="premium-report">
  {render_cover(context)}
  {render_dirigeant_summary(context)}
  {render_executive_summary(context)}
  {render_benchmark_section(context)}
  {render_action_plan(context)}
  {priority_pages}
  {render_performance_section(context)}
  {render_seo_suggestions_section(context)}
  {signals}
  {render_final_section(context)}
  {render_method_about(context)}
  {render_appendix(context)}
</main>"""


def render_cover(context: dict[str, Any]) -> str:
    urgency_class = urgency_color_class(context["urgency_level"])
    score_class = score_color_class(int(context["score_global"]))
    logo = (
        f'<img src="{escape(context["logo_url"])}" alt="" class="header-logo cover-logo">'
        if context.get("logo_url")
        else ""
    )
    return f"""
  <section class="report-page report-page-cover cover-page">
    <header class="rapport-header cover-brand">
      <div class="header-left cover-branding">{logo}</div>
      <div class="header-right">
        <span class="header-label">RAPPORT SEO</span>
      </div>
    </header>
    <div class="cover-center">
      <div>
        <p class="label">Audit réalisé le {escape(context["audit_date"])}</p>
        <h1 class="cover-title">Audit SEO</h1>
        <p class="cover-domain">{escape(context["domain"])}</p>
      </div>
      <div class="cover-score">
        {render_score_gauge(int(context["score_global"]), score_class)}
        <div class="score-context">
          <span class="score-badge {score_class}">{int(context["score_global"])}/100</span>
          <p>{escape(context["base_status"])}</p>
        </div>
      </div>
      <div class="cover-meta">
        <span class="urgency-badge {urgency_class}">Niveau d'urgence : {escape(context["urgency_level"])}</span>
        <span>{int(context["pages_analysees"])} pages analysées</span>
      </div>
    </div>
    {render_page_footer(context)}
  </section>"""


def render_page_footer(context: dict[str, Any]) -> str:
    return (
        '<div class="page-footer">'
        f'<span class="footer-domain">{escape(context["domain"])}</span>'
        f'<span class="footer-date">{escape(context["audit_date"])}</span>'
        "</div>"
    )


def render_dirigeant_summary(context: dict[str, Any]) -> str:
    score = int(context["score_global"])
    return f"""
  <section class="report-page section-dirigeant">
    <div class="section-label">POUR LE DIRIGEANT</div>
    <div class="dirigeant-card">
      <div class="dirigeant-header">
        <div class="dirigeant-score-bloc">
          <span class="dirigeant-score-value {score_color_class(score)}">{score}/100</span>
          <span class="dirigeant-score-label">état général du site</span>
        </div>
        <div class="dirigeant-phrase">{escape(context["resume_dirigeant"])}</div>
      </div>
      <div class="dirigeant-trois-colonnes">
        <div class="dirigeant-col">
          <div class="dirigeant-col-icon">📍</div>
          <div class="dirigeant-col-title">Où vous en êtes</div>
          <div class="dirigeant-col-text">{escape(context["ou_vous_en_etes"])}</div>
        </div>
        <div class="dirigeant-col">
          <div class="dirigeant-col-icon">⚠️</div>
          <div class="dirigeant-col-title">Le risque si vous attendez</div>
          <div class="dirigeant-col-text">{escape(context["risque_attente"])}</div>
        </div>
        <div class="dirigeant-col">
          <div class="dirigeant-col-icon">✅</div>
          <div class="dirigeant-col-title">Ce qu'on vous recommande</div>
          <div class="dirigeant-col-text">{escape(context["recommandation_courte"])}</div>
        </div>
      </div>
    </div>
    {render_page_footer(context)}
  </section>"""


def render_executive_summary(context: dict[str, Any]) -> str:
    metrics = [
        ("Pages saines", context["pages_saines"], "pages sans erreur observée", ""),
        ("Contenus utiles", context["contenus_utiles"], "pages éditoriales ou informatives", ""),
        ("Score moyen", f"{context['score_moyen_page']}/100", "moyenne des pages analysées", score_color_class(int(context["score_moyen_page"]))),
        ("Dates à vérifier", context["dates_a_verifier"], "signaux visibles à relire", ""),
    ]
    return f"""
  <section class="report-page executive-page synthese" id="synthese">
    <div class="section-head">
      <p class="label section-label">Synthèse exécutive</p>
      <h2>Lecture rapide du site</h2>
    </div>
    <div class="executive-grid">
      <div class="executive-left synthese-texte">
        <article class="card insight-card insight-positive">
          <span class="insight-icon">✓</span>
          <div>
            <h3>Ce qui fonctionne</h3>
            {render_text_list(context["ce_qui_fonctionne"])}
          </div>
        </article>
        <article class="card insight-card insight-warning">
          <span class="insight-icon">!</span>
          <div>
            <h3>Points d'attention</h3>
            {render_text_list(context["points_attention"])}
          </div>
        </article>
        <article class="card main-signal">
          <p class="label">Signal principal</p>
          <strong>{escape(context["signal_principal"])}</strong>
        </article>
      </div>
      <div class="metric-grid metriques-grid executive-metrics synthese-metriques">
        {''.join(render_metric_card(label, value, note, tone, warning=label == "Dates à vérifier") for label, value, note, tone in metrics)}
      </div>
    </div>
    {render_page_footer(context)}
  </section>"""


def render_benchmark_section(context: dict[str, Any]) -> str:
    benchmark = context.get("benchmark") or []
    if not context.get("benchmark_disponible") or not benchmark:
        return ""
    competitor_rows = "".join(
        f"""
        <tr class="benchmark-row">
          <td>{escape(item.get("domaine", "-"))}</td>
          <td><span class="score-pill {score_color_class(get_int(item, "score_estime", 0))}">{get_int(item, "score_estime", 0)}/100</span></td>
          <td>{get_int(item, "nb_pages_contenu", 0)} contenus</td>
          <td>{escape(str(item.get("signal") or "-"))}</td>
        </tr>"""
        for item in benchmark[:3]
    )
    score = int(context["score_global"])
    return f"""
  <section class="report-page section-benchmark">
    <div class="section-label">POSITIONNEMENT</div>
    <h2>Votre position face à la concurrence</h2>
    <p class="benchmark-intro">Comparaison indicative basée sur les signaux observés lors de l'analyse.</p>
    <div class="benchmark-table-wrapper">
      <table class="benchmark-table">
        <thead>
          <tr>
            <th>Site</th>
            <th>Score estimé</th>
            <th>Volume de contenu</th>
            <th>Signal principal</th>
          </tr>
        </thead>
        <tbody>
          <tr class="benchmark-row benchmark-row--vous">
            <td><strong>{escape(context["domain"])}</strong><span class="benchmark-vous-badge">vous</span></td>
            <td><span class="score-pill {score_color_class(score)}">{score}/100</span></td>
            <td>{int(context["contenus_utiles"])} contenus</td>
            <td>{escape(context["signal_principal"])}</td>
          </tr>
          {competitor_rows}
        </tbody>
      </table>
    </div>
    <p class="benchmark-disclaimer">Les données concurrentes sont des estimations indicatives issues d'une analyse de surface.</p>
    {render_page_footer(context)}
  </section>"""


def render_action_plan(context: dict[str, Any]) -> str:
    plan = context["plan_action"]
    steps = [
        ("1", "J30", as_dict(plan.get("j30")), "is-current"),
        ("2", "J60", as_dict(plan.get("j60")), ""),
        ("3", "J90", as_dict(plan.get("j90")), ""),
    ]
    timeline = "".join(
        f"""
        <article class="timeline-step {step_class}">
          <span class="timeline-number">{number}</span>
          <div>
            <p class="label">{period}</p>
            <h3>{escape(str(item.get("titre") or "Action à cadrer"))}</h3>
            <p>{escape(str(item.get("description") or "Priorité à valider manuellement."))}</p>
          </div>
        </article>"""
        for number, period, item, step_class in steps
    )
    return f"""
  <section class="report-page plan-page">
    <div class="section-head">
      <p class="label section-label">Plan d’action</p>
      <h2>Plan d’action 30 / 60 / 90 jours</h2>
    </div>
    <div class="timeline">{timeline}</div>
    <section class="matrix-section">
      <h2>Matrice impact / effort</h2>
      {render_matrix(context["matrice"])}
    </section>
    {render_page_footer(context)}
  </section>"""


def render_matrix(matrix: dict[str, list[dict[str, Any]]]) -> str:
    labels = [
        ("quick_wins", "Quick wins", "Impact fort / effort faible"),
        ("projets_structurants", "Projets structurants", "Impact fort / effort élevé"),
        ("optimisations_simples", "Optimisations simples", "Impact modéré / effort faible"),
        ("backlog", "Backlog", "Impact modéré / effort élevé"),
    ]
    cards: list[str] = []
    for key, title, axis in labels:
        actions = matrix.get(key, [])
        if not actions:
            continue
        rows = "".join(
            f"""
            <article class="matrix-action">
              <span class="priority-badge priority-{priority_color_class(str(action.get("priorite") or ""))}">{escape(str(action.get("priorite") or "priorité"))}</span>
              <strong>{escape(str(action.get("titre") or "Action à cadrer"))}</strong>
              <p><span>Impact {escape(str(action.get("impact") or "-"))}</span><span>Effort {escape(str(action.get("effort") or "-"))}</span></p>
            </article>"""
            for action in actions
        )
        cards.append(
            f"""
            <section class="card matrix-quadrant matrix-{key}">
              <p class="label">{escape(axis)}</p>
              <h3>{escape(title)}</h3>
              <div class="matrix-actions">{rows}</div>
            </section>"""
        )
    if not cards:
        return "<p class='empty-state'>Aucune action prioritaire identifiée dans cette matrice.</p>"
    note = ""
    if len(cards) < 2:
        note = (
            "<p class='matrice-note'>Les autres quadrants ne présentent pas d'action prioritaire "
            "identifiée à ce stade — c'est un signal positif sur l'état général du site.</p>"
        )
    return f"<div class='matrix-grid'>{''.join(cards)}</div>{note}"


def render_priority_pages(context: dict[str, Any]) -> str:
    pages = context["pages_prioritaires"]
    if not pages:
        return ""
    cards = []
    for page in pages:
        score = clamp_score(get_int(page, "score", 0))
        score_class = score_color_class(score)
        priority = str(page.get("priorite") or "modérée")
        nb_liens = get_int(page, "nb_liens_internes", 0)
        plural = "s" if nb_liens != 1 else ""
        maillage_label = str(page.get("maillage_label") or classify_maillage(nb_liens))
        maillage_alert = (
            '<span class="fiche-maillage-alerte"> ⚠ Aucune page ne pointe vers celle-ci</span>'
            if nb_liens == 0
            else ""
        )
        cards.append(
            f"""
      <article class="card priority-page-card fiche-page">
        <div class="priority-card-head">
          <div>
            <h3>{escape(str(page.get("titre") or slug_to_title(str(page.get("slug") or page.get("url") or ""))))}</h3>
            <p class="muted-url fiche-url">{escape(str(page.get("url") or ""))}</p>
          </div>
          <div class="priority-score-stack">
            <span class="score-badge {score_class}">{score}/100</span>
            <span class="priority-badge priority-{priority_color_class(priority)}">{escape(priority)}</span>
          </div>
        </div>
        <div class="page-tags">
          <span>{int(get_int(page, "mots", 0))} mots</span>
          <span>{escape(str(page.get("type") or "page"))}</span>
        </div>
        <section class="page-reason">
          <span class="section-icon">!</span>
          <div>
            <p class="label fiche-section-label">Pourquoi elle ressort</p>
            <p>{escape(str(page.get("pourquoi") or "Page prioritaire du crawl."))}</p>
          </div>
        </section>
        <section>
          <p class="label fiche-section-label">Observation</p>
          <p>{escape(str(page.get("observation") or "À relire dans le contexte business de la page."))}</p>
        </section>
        <section class="recommended-action">
          <span>→</span>
          <div>
            <p class="label fiche-section-label">Action recommandée</p>
            <p>{escape(str(page.get("action") or "Définir une reprise ciblée."))}</p>
          </div>
        </section>
        <section class="rewrite-angle">
          <p class="label fiche-section-label">Angle possible</p>
          <p>{escape(str(page.get("angle") or "Clarifier la promesse et renforcer l'intention principale."))}</p>
        </section>
        <div class="fiche-meta-bas">
          <div class="fiche-effort-temps">
            <span class="fiche-meta-icon">⏱</span>
            <span>{escape(str(page.get("effort_temps") or get_effort_label(str(page.get("type") or "page"), get_int(page, "mots", 0))))}</span>
          </div>
          <div class="fiche-badges-ei impact-effort-row">
            <span class="badge badge--effort">Effort : {escape(str(page.get("effort") or "moyen"))}</span>
            <span class="badge badge--impact">Impact : {escape(str(page.get("impact") or "moyen"))}</span>
          </div>
        </div>
        <div class="fiche-maillage">
          <span class="fiche-maillage-icon">🔗</span>
          <span class="fiche-maillage-count {escape(str(page.get("maillage_class") or classify_maillage_class(nb_liens)))}">
            {nb_liens} lien{plural} interne{plural}
          </span>
          <span class="fiche-maillage-label">— {escape(maillage_label)}{maillage_alert}</span>
        </div>
      </article>"""
        )
    return f"""
  <section class="report-page priority-pages">
    <div class="section-head">
      <p class="label section-label">Pages prioritaires</p>
      <h2>Pages à revoir en priorité</h2>
    </div>
    <div class="priority-page-list pages-prioritaires-grid">{''.join(cards)}</div>
    {render_page_footer(context)}
  </section>"""


def render_performance_section(context: dict[str, Any]) -> str:
    perf = as_dict(context.get("perf"))
    if not perf.get("pages_lentes"):
        return ""
    temps_moyen = optional_float(perf.get("temps_moyen"))
    temps_max = optional_float(perf.get("temps_max"))
    pct_lentes = get_int(perf, "pct_lentes", 0)
    pct_class = "score-low" if pct_lentes > 50 else "score-mid" if pct_lentes > 20 else "score-high"
    rows = []
    for page in perf.get("top_10_lentes", []) if isinstance(perf.get("top_10_lentes"), list) else []:
        item = as_dict(page)
        load_time = optional_float(item.get("load_time"))
        speed = classify_speed(load_time)
        speed_label = {"correct": "OK", "lent": "Lent", "critique": "Critique", "inconnu": "Inconnu"}[speed]
        redirects = get_int(item, "redirections", 0)
        redirects_html = (
            f'<span class="perf-redirect-warning">{redirects} redirect.</span>'
            if redirects > 0
            else '<span class="perf-redirect-ok">—</span>'
        )
        rows.append(
            f"""
      <tr>
        <td class="perf-url">
          <a href="{escape(appendix_href(str(item.get("url") or "")))}" target="_blank" rel="noreferrer">
            {escape(display_url_label(str(item.get("url") or ""), str(context["domain"]), empty_label="Accueil"))}
          </a>
        </td>
        <td>
          <span class="perf-time {speed_color_class(load_time)}">{escape(format_seconds(load_time))}</span>
        </td>
        <td>
          <span class="perf-badge perf-badge--{speed}">{escape(speed_label)}</span>
        </td>
        <td class="perf-redirects">{redirects_html}</td>
      </tr>"""
        )
    return f"""
  <section class="report-page section-perf">
    <div class="section-label">PERFORMANCE</div>
    <h2>Vitesse de chargement</h2>

    <div class="perf-intro">
      <p>
        Google considère qu'une page qui met plus de
        <strong>3 secondes</strong> à charger perd une part
        significative de ses visiteurs avant même qu'ils aient vu le contenu.
        Sur votre site, <strong>{pct_lentes}% des pages analysées</strong>
        dépassent ce seuil.
      </p>
    </div>

    <div class="perf-metrics">
      <div class="perf-metric">
        <div class="perf-metric-value {speed_color_class(temps_moyen)}">{escape(format_seconds(temps_moyen))}</div>
        <div class="perf-metric-label">Temps moyen observé</div>
      </div>
      <div class="perf-metric">
        <div class="perf-metric-value {speed_color_class(temps_max)}">{escape(format_seconds(temps_max))}</div>
        <div class="perf-metric-label">Page la plus lente</div>
      </div>
      <div class="perf-metric">
        <div class="perf-metric-value {pct_class}">{pct_lentes}%</div>
        <div class="perf-metric-label">Pages dépassant 3s</div>
      </div>
    </div>

    <table class="perf-table">
      <thead>
        <tr>
          <th>Page</th>
          <th>Temps</th>
          <th>Niveau</th>
          <th>Redirections</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>

    <div class="perf-actions">
      <div class="perf-actions-title">Comment améliorer la vitesse</div>
      <div class="perf-actions-grid">
        <div class="perf-action-card">
          <div class="perf-action-icon">🖼</div>
          <div class="perf-action-content">
            <div class="perf-action-title">Compresser les images</div>
            <div class="perf-action-text">Les images non compressées sont la première cause de lenteur. Passer au format WebP et réduire la taille à moins de 150 Ko par image. Outils : Squoosh, TinyPNG, ShortPixel.</div>
            <div class="perf-action-effort">Effort : faible — Impact : élevé</div>
          </div>
        </div>
        <div class="perf-action-card">
          <div class="perf-action-icon">↪️</div>
          <div class="perf-action-content">
            <div class="perf-action-title">Réduire les redirections</div>
            <div class="perf-action-text">Chaque redirection ajoute un aller-retour réseau. Les pages avec 1+ redirection observée gagnent à être liées directement vers leur URL finale.</div>
            <div class="perf-action-effort">Effort : moyen — Impact : moyen</div>
          </div>
        </div>
        <div class="perf-action-card">
          <div class="perf-action-icon">⚡</div>
          <div class="perf-action-content">
            <div class="perf-action-title">Activer la mise en cache</div>
            <div class="perf-action-text">Un plugin de cache (WP Rocket, W3 Total Cache, LiteSpeed Cache) permet de servir des pages pré-générées sans recalcul serveur à chaque visite.</div>
            <div class="perf-action-effort">Effort : faible — Impact : élevé</div>
          </div>
        </div>
        <div class="perf-action-card">
          <div class="perf-action-icon">🌐</div>
          <div class="perf-action-content">
            <div class="perf-action-title">Utiliser un CDN</div>
            <div class="perf-action-text">Un CDN (Cloudflare, BunnyCDN) distribue les fichiers statiques depuis des serveurs proches de vos visiteurs. Gratuit chez Cloudflare pour la formule de base.</div>
            <div class="perf-action-effort">Effort : moyen — Impact : élevé</div>
          </div>
        </div>
      </div>
    </div>
    {render_page_footer(context)}
  </section>"""


def render_seo_suggestions_section(context: dict[str, Any]) -> str:
    pages = [page for page in context.get("urls_crawlees", []) if as_dict(page).get("seo_suggestions")]
    if not pages:
        return ""
    cards = []
    for raw_page in pages:
        page = as_dict(raw_page)
        suggestion = as_dict(page.get("seo_suggestions"))
        title = str(page.get("titre_google") or "")
        desc = str(page.get("description_google") or "")
        title_suggested = str(suggestion.get("titre_suggere") or "").strip()
        desc_suggested = str(suggestion.get("description_suggeree") or "").strip()
        title_block = ""
        if title_suggested:
            title_bad = len(title) > SEUIL_TITRE_LONG
            title_note = " — trop long (max 60)" if title_bad else ""
            title_status = (
                '<span class="suggestion-longueur--bad">Absent</span>'
                if not title
                else f'<span class="suggestion-longueur {"suggestion-longueur--bad" if title_bad else "suggestion-longueur--ok"}">{len(title)} car.{title_note}</span>'
            )
            current_title = (
                f"""
      <div class="suggestion-actuel">
        <span class="suggestion-label-actuel">Actuel</span>
        <span class="suggestion-texte-actuel">{escape(title)}</span>
      </div>"""
                if title
                else ""
            )
            title_block = f"""
    <div class="suggestion-bloc">
      <div class="suggestion-bloc-header">
        <span class="suggestion-type">Titre Google</span>
        {title_status}
      </div>
      {current_title}
      <div class="suggestion-propose">
        <span class="suggestion-label-propose">Suggéré</span>
        <span class="suggestion-texte-propose">{escape(title_suggested)}</span>
        <span class="suggestion-longueur-ok">{get_int(suggestion, "titre_longueur", len(title_suggested))} car.</span>
      </div>
      {render_suggestion_explanation(str(suggestion.get("explication_titre") or ""))}
    </div>"""
        desc_block = ""
        if desc_suggested:
            desc_bad = not desc or len(desc) < SEUIL_DESC_COURTE or len(desc) > SEUIL_DESC_LONGUE
            desc_status = (
                '<span class="suggestion-longueur--bad">Absente</span>'
                if not desc
                else f'<span class="suggestion-longueur {"suggestion-longueur--bad" if desc_bad else "suggestion-longueur--ok"}">{len(desc)} car.</span>'
            )
            current_desc = (
                f"""
      <div class="suggestion-actuel">
        <span class="suggestion-label-actuel">Actuel</span>
        <span class="suggestion-texte-actuel">{escape(desc)}</span>
      </div>"""
                if desc
                else ""
            )
            desc_block = f"""
    <div class="suggestion-bloc">
      <div class="suggestion-bloc-header">
        <span class="suggestion-type">Description Google</span>
        {desc_status}
      </div>
      {current_desc}
      <div class="suggestion-propose">
        <span class="suggestion-label-propose">Suggéré</span>
        <span class="suggestion-texte-propose">{escape(desc_suggested)}</span>
        <span class="suggestion-longueur-ok">{get_int(suggestion, "description_longueur", len(desc_suggested))} car.</span>
      </div>
      {render_suggestion_explanation(str(suggestion.get("explication_description") or ""))}
    </div>"""
        if not title_block and not desc_block:
            continue
        cards.append(
            f"""
  <div class="suggestion-card">
    <div class="suggestion-url">{escape(display_url_label(str(page.get("url") or ""), str(context["domain"]), empty_label="Accueil"))}</div>
    {title_block}
    {desc_block}
  </div>"""
        )
    if not cards:
        return ""
    return f"""
  <section class="report-page section-suggestions">
    <div class="section-label">OPTIMISATIONS</div>
    <h2>Titres et descriptions à corriger</h2>
    <p class="suggestions-intro">
      Ces éléments sont ce que Google affiche dans ses résultats de recherche.
      Un titre trop long est tronqué, une description absente est remplacée par
      un extrait aléatoire du contenu.
    </p>
    {''.join(cards)}
    {render_page_footer(context)}
  </section>"""


def render_suggestion_explanation(value: str) -> str:
    return f'<div class="suggestion-explication">{escape(value)}</div>' if value.strip() else ""


def render_secondary_signals(context: dict[str, Any]) -> str:
    signals = context["signaux"]
    metrics = [
        ("Pages analysées", context["pages_analysees"], "volume couvert par le crawl", False),
        ("Pages saines", context["pages_saines"], "pages sans erreur observée", False),
        ("Pages en erreur", context["pages_erreur"], "réponses HTTP à vérifier", True),
        ("Descriptions manquantes", context["descriptions_manquantes"], "balises description absentes", True),
        ("Titres manquants", context["titres_manquants"], "titres HTML absents", True),
        ("Score moyen", f"{context['score_moyen_page']}/100", "moyenne des pages analysées", False),
        ("Pages noindex", context["pages_noindex"], "pages écartées de l'indexation", False),
        ("Canonicals à vérifier", context["canonicals"], "canonicals pointant ailleurs", True),
        ("Pages peu reliées", context["pages_peu_reliees"], "maillage interne à renforcer", True),
        ("Sujets trop proches", context["sujets_trop_proches"], "intentions éditoriales proches", True),
        ("Dates visibles à vérifier", context["dates_a_verifier"], "mentions datées repérées", True),
    ]
    return f"""
  <section class="report-page secondary-page">
    <div class="section-head">
      <p class="label section-label">Repères complémentaires</p>
      <h2>Repères complémentaires</h2>
    </div>
    <div class="metric-grid secondary-metrics">
      {''.join(render_metric_card(label, value, note, muted_zero=True, warning=is_warning_metric) for label, value, note, is_warning_metric in metrics)}
    </div>
    <section class="card signal-check-list">
      <h3>Éléments à vérifier</h3>
      {render_signal_groups(signals, str(context["domain"]))}
    </section>
    {render_page_footer(context)}
  </section>"""


def render_signal_groups(signals: list[dict[str, Any]], domain: str = "") -> str:
    if not signals:
        return "<p class='empty-state'>Aucun signal de date visible à vérifier.</p>"
    rows = []
    for signal in signals:
        url = str(signal.get("url") or "")
        dates = signal.get("dates") or []
        rows.append(
            f"""
            <tr>
              <td class="dates-url"><a href="{escape(appendix_href(url))}" target="_blank" rel="noreferrer">{escape(compact_url_label(url, domain))}</a></td>
              <td class="dates-cell">{render_date_table_cell(dates, "titre")}</td>
              <td class="dates-cell">{render_date_table_cell(dates, "url")}</td>
              <td class="dates-cell">{render_date_table_cell(dates, "contenu")}</td>
            </tr>"""
        )
    return (
        "<table class='dates-table'>"
        "<thead><tr><th>Page</th><th>Titre</th><th>URL</th><th>Contenu</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def render_date_table_cell(dates: list[Any], expected_type: str) -> str:
    badges = []
    for item in dates:
        if not isinstance(item, dict):
            continue
        date_type = date_type_class(str(item.get("type") or "contenu"))
        if date_type != expected_type:
            continue
        for value in extract_year_values(str(item.get("valeur") or "date à vérifier")):
            badges.append(f"<span class='date-badge date-badge--{expected_type} date-{expected_type}'>{escape(value)}</span>")
    return "".join(badges) or "<span class='dates-empty'>—</span>"


def compact_url_label(url: str, domain: str = "") -> str:
    return display_url_label(url, domain)


def display_url_label(url: str, domain: str = "", *, empty_label: str = "") -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    label = parsed.path.lstrip("/")
    if not label and parsed.netloc and parsed.netloc != domain.strip("/"):
        label = parsed.netloc
    if domain and label.startswith(domain.strip("/") + "/"):
        label = label[len(domain.strip("/")) + 1 :]
    return label or empty_label or parsed.netloc or url


def render_date_badges(dates: list[Any]) -> str:
    grouped: dict[str, list[str]] = {"titre": [], "url": [], "contenu": []}
    for item in dates:
        if not isinstance(item, dict):
            continue
        date_type = date_type_class(str(item.get("type") or "contenu"))
        values = extract_year_values(str(item.get("valeur") or "date à vérifier"))
        grouped.setdefault(date_type, []).extend(values)
    lines = []
    for date_type in ("titre", "url", "contenu"):
        values = grouped.get(date_type, [])
        if not values:
            continue
        value_text = ", ".join(values)
        lines.append(
            "<p class='date-signal-line'>"
            f"<span class='date-badge date-badge--{date_type} date-{date_type}'>{escape(date_type)}</span>"
            f"<span class='date-values'>{escape(value_text)}</span>"
            "</p>"
        )
    if not lines:
        lines.append(
            "<p class='date-signal-line'>"
            "<span class='date-badge date-badge--contenu date-contenu'>contenu</span>"
            "<span class='date-values'>date à vérifier</span>"
            "</p>"
        )
    return f"<div class='date-signal-lines'>{''.join(lines)}</div>"


def extract_year_values(value: str) -> list[str]:
    years = re.findall(r"\b(?:19|20)\d{2}\b", value)
    if years:
        return years
    cleaned = value.strip()
    return [cleaned] if cleaned else ["date à vérifier"]


def render_opportunities(context: dict[str, Any]) -> str:
    opportunities = context["opportunites"][:3]
    cards = "".join(
        f"""
        <article class="opportunity-item">
          <span>+</span>
          <p>{escape(str(item))}</p>
        </article>"""
        for item in opportunities
    )
    return f"""
  <section class="report-page opportunities-page">
    <div class="section-head">
      <p class="label">Éditorial</p>
      <h2>Opportunités éditoriales</h2>
    </div>
    <section class="opportunity-panel">{cards}</section>
  </section>"""


def render_final_section(context: dict[str, Any]) -> str:
    opportunities = context["opportunites"][:3]
    opportunity_items = "".join(
        f"""
        <li class="opportunite-item">
          <span class="opportunite-icon">+</span>
          <span>{escape(str(item))}</span>
        </li>"""
        for item in opportunities
    )
    actions = "".join(f"<li>{escape(str(action))}</li>" for action in context["actions_30j"][:3])
    contact = str(context["contact_cta"])
    href = f"mailto:{contact}" if "@" in contact and not contact.startswith("mailto:") else contact
    analyste = (
        f'<span class="footer-analyste">{escape(context["analyste_nom"])}</span>'
        if context.get("analyste_valide")
        else ""
    )
    return f"""
  <section class="report-page section-finale">
    <div class="section-label">Conclusion</div>
    <div class="finale-grid">
      <div class="finale-col">
        <h2>Opportunités éditoriales</h2>
        <ul class="opportunites-list">{opportunity_items}</ul>
      </div>
      <div class="finale-col">
        <h2>Prochaines étapes</h2>
        <ol class="etapes-list">{actions}</ol>
        <div class="cta-block">
          <p class="cta-question">Vous souhaitez qu'on travaille ces pages ensemble ?</p>
          <a href="{escape(href)}" class="cta-email">{escape(contact)}</a>
        </div>
      </div>
    </div>
    {render_followup_offers(context)}
    <div class="rapport-footer">
      {analyste}
      <span class="footer-date">{escape(context["audit_date"])}</span>
      <span class="footer-confidential">Rapport confidentiel — {escape(context["domain"])}</span>
    </div>
  </section>"""


def render_followup_offers(context: dict[str, Any]) -> str:
    offers = context.get("offres") or []
    if not offers:
        return ""
    cards = []
    for offer in offers:
        featured = bool(offer.get("mise_en_avant"))
        features = "".join(f"<li>{escape(str(feature))}</li>" for feature in offer.get("features", []))
        badge = "<div class='offre-badge-featured'>Recommandé</div>" if featured else ""
        card_class = "offre-card offre-card--featured" if featured else "offre-card"
        cards.append(
            f"""
        <div class="{card_class}">
          {badge}
          <div class="offre-nom">{escape(offer.get("nom", "Formule"))}</div>
          <div class="offre-prix">{escape(offer.get("prix", "-"))}<span class="offre-prix-periode">{escape(offer.get("periode", ""))}</span></div>
          <ul class="offre-features">{features}</ul>
        </div>"""
        )
    return f"""
    <div class="offre-suivi">
      <div class="offre-titre">Formules disponibles</div>
      <div class="offre-grid">{''.join(cards)}</div>
    </div>"""


def render_method_about(context: dict[str, Any]) -> str:
    method = as_dict(context.get("methode"))
    pages_visitees = get_int(method, "pages_visitees", int(context["pages_analysees"]))
    sitemap_urls = get_int(method, "sitemap_urls", 0)
    analyste_nom = str(context["analyste_nom"])
    analyste_photo = str(context.get("analyste_photo") or "")
    analyste_linkedin = str(context.get("analyste_linkedin") or "")
    analyste_card = ""
    if context.get("analyste_valide"):
        analyste_visual = (
            f'<img src="{escape(analyste_photo)}" alt="{escape(analyste_nom)}" class="analyste-photo">'
            if analyste_photo
            else f'<div class="analyste-avatar">{escape(analyste_nom[0].upper())}</div>'
        )
        analyste_title = ""
        if context.get("analyste_titre") and context["analyste_titre"] != DEFAULT_ANALYSTE_TITRE:
            analyste_title = f'<div class="analyste-titre">{escape(context["analyste_titre"])}</div>'
        linkedin = (
            f'<a href="{escape(analyste_linkedin)}" class="analyste-linkedin" target="_blank" rel="noreferrer">Voir le profil LinkedIn →</a>'
            if analyste_linkedin
            else ""
        )
        analyste_card = f"""
      <div class="methode-col">
        <h2>Préparé par</h2>
        <div class="analyste-card">
          {analyste_visual}
          <div class="analyste-info">
            <div class="analyste-nom">{escape(analyste_nom)}</div>
            {analyste_title}
            {linkedin}
          </div>
        </div>
      </div>"""
    return f"""
  <section class="report-page section-methode">
    <div class="section-label">MÉTHODE</div>
    <div class="methode-grid">
      <div class="methode-col">
        <h2>Ce qui a été analysé</h2>
        <ul class="methode-list">
          <li><span class="methode-bullet">→</span><span><strong>{pages_visitees} pages</strong> crawlées depuis l'accueil et le sitemap</span></li>
          <li><span class="methode-bullet">→</span><span>Réponses HTTP, redirections, temps de chargement</span></li>
          <li><span class="methode-bullet">→</span><span>Titres, descriptions, structure des contenus</span></li>
          <li><span class="methode-bullet">→</span><span>Dates visibles dans les titres, URLs et contenus</span></li>
          <li><span class="methode-bullet">→</span><span>Maillage interne et accessibilité des pages</span></li>
        </ul>
        <div class="methode-limites">
          <strong>Limites de cette analyse</strong>
          <p>Ce rapport s'appuie sur un crawl de surface. Il ne couvre pas les données Search Console, les backlinks, ni les performances Core Web Vitals en conditions réelles. {pages_visitees} pages analysées sur {sitemap_urls} détectées dans le sitemap.</p>
        </div>
      </div>
      {analyste_card}
    </div>
    {render_page_footer(context)}
  </section>"""


def render_appendix(context: dict[str, Any]) -> str:
    urls = context["urls_crawlees"]
    rows = "".join(render_appendix_row(row) for row in urls)
    if not rows:
        rows = "<tr><td colspan='5'>Aucune URL détaillée disponible.</td></tr>"
    method = context["methode"]
    method_items = [
        ("Pages visitées", method.get("pages_visitees", context["pages_analysees"])),
        ("URLs sitemap", method.get("sitemap_urls", 0)),
        ("URLs restantes", method.get("urls_restantes", 0)),
        ("Raison d'arrêt", method.get("raison_arret", "-")),
    ]
    return f"""
  <div class="annexe-actions">
    <button class="annexe-toggle" type="button" onclick="toggleAnnexe()">Voir l'annexe technique ({len(urls)} URLs)</button>
    <button class="annexe-toggle annexe-print-toggle" type="button" onclick="printWithAnnexe()">Imprimer avec annexe</button>
  </div>
  <section class="report-page annexe" id="annexe" style="display:none">
    <div class="section-head appendix-head">
      <div>
        <p class="label section-label">Annexe</p>
        <h2>Annexe technique</h2>
      </div>
    </div>
    <div class="annexe-body">
      <div class="method-grid">
        {''.join(f"<article class='card method-card'><span>{escape(label)}</span><strong>{escape(str(value))}</strong></article>" for label, value in method_items)}
      </div>
      <div class="technical-table-wrap">
        <table class="annexe-table technical-table">
          <thead><tr><th>URL</th><th>Type</th><th>Score</th><th>Mots</th><th>Points relevés</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
  </section>"""


def render_appendix_row(row: dict[str, Any]) -> str:
    url = str(row.get("url") or "")
    short = truncate(url, 50)
    score = clamp_score(get_int(row, "score", 0))
    href = appendix_href(url)
    return (
        "<tr>"
        f"<td><a href='{escape(href)}' target='_blank' rel='noreferrer' title='{escape(url)}'>{escape(short)}</a></td>"
        f"<td><span class='type-badge'>{escape(str(row.get('type') or '-'))}</span></td>"
        f"<td><span class='score-pill {score_color_class(score)}'>{score}/100</span></td>"
        f"<td>{get_int(row, 'mots', 0)}</td>"
        f"<td class='points-releves'>{escape(str(row.get('points') or '-'))}</td>"
        "</tr>"
    )


def appendix_href(url: str) -> str:
    if not url:
        return "#"
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def render_conclusion(context: dict[str, Any]) -> str:
    contact = str(context["contact_cta"])
    href = f"mailto:{contact}" if "@" in contact and not contact.startswith("mailto:") else contact
    actions = "".join(f"<li>{escape(str(action))}</li>" for action in context["actions_30j"][:3])
    analyste = (
        f'<strong>{escape(context["analyste_nom"])}</strong>'
        if context.get("analyste_valide")
        else ""
    )
    return f"""
  <section class="report-page conclusion-page">
    <div class="section-head">
      <p class="label">Conclusion</p>
      <h2>Prochaines étapes recommandées</h2>
    </div>
    <ol class="next-actions">{actions}</ol>
    <section class="final-cta">
      <h3>Vous souhaitez qu'on travaille ces pages ensemble ?</h3>
      <a href="{escape(href)}">{escape(contact)}</a>
    </section>
    <footer class="signature">
      {analyste}
      <span>{escape(context["audit_date"])}</span>
      <span>Rapport confidentiel — {escape(context["domain"])}</span>
    </footer>
  </section>"""


def render_metric_card(label: str, value: Any, note: str, tone: str = "", *, muted_zero: bool = False, warning: bool = False) -> str:
    value_text = str(value)
    is_zero = metric_value_is_zero(value_text)
    classes = "metric-card metrique-card"
    if tone:
        classes += f" {tone}"
    if muted_zero and is_zero:
        classes += " metric-muted is-zero"
    if warning and not is_zero and metric_numeric_value(value_text) > 0:
        classes += " metric-warning is-warning"
    return (
        f"<article class='card {classes}'>"
        f"<strong class='metric-value metrique-value'>{escape(value_text)}</strong>"
        f"<span class='metric-label metrique-label'>{escape(label)}</span>"
        f"<p class='metric-note metrique-sublabel'>{escape(note)}</p>"
        "</article>"
    )


def metric_value_is_zero(value: str) -> bool:
    return metric_numeric_value(value) == 0


def metric_numeric_value(value: str) -> int:
    match = re.match(r"\s*(-?\d+)", value)
    if not match:
        return 0
    return int(match.group(1))


def render_text_list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in items) + "</ul>"


def render_score_gauge(score: int, score_class: str) -> str:
    gauge = score_gauge_values(score)
    return f"""
        <svg class="score-gauge {score_class}" viewBox="0 0 140 140" role="img" aria-label="Score global {score} sur 100">
          <circle class="gauge-track" cx="70" cy="70" r="54"></circle>
          <circle class="gauge-meter" cx="70" cy="70" r="54"
            stroke-dasharray="{gauge['circumference']}"
            stroke-dashoffset="{gauge['offset']}"
            transform="rotate(-90 70 70)"></circle>
          <text x="70" y="66" text-anchor="middle">{score}</text>
          <text x="70" y="88" text-anchor="middle">/100</text>
        </svg>"""


def score_gauge_values(score: int) -> dict[str, str]:
    radius = 54
    circumference = 2 * math.pi * radius
    offset = circumference - (clamp_score(score) / 100) * circumference
    return {"circumference": f"{circumference:.2f}", "offset": f"{offset:.2f}"}


def normalize_priority_pages(items: Any, pages_by_url: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for raw in items if isinstance(items, list) else []:
        item = as_dict(raw)
        url = str(item.get("url") or "")
        details = pages_by_url.get(url, {})
        reasons = [str(reason) for reason in (item.get("reasons") or [])]
        raw_score = get_int(item, "score", get_int(item, "page_health_score", get_int(details, "page_health_score", -1)))
        score = raw_score if raw_score >= 0 else 75
        word_count = get_int(item, "mots", get_int(item, "word_count", get_int(details, "word_count", 0)))
        priority_score = get_int(item, "priority_score", 0)
        page_type = str(item.get("type") or item.get("page_type") or details.get("page_type") or "page")
        normalized.append(
            {
                "slug": str(item.get("slug") or slug_from_url(url)),
                "titre": str(item.get("titre") or slug_to_title(str(item.get("slug") or url))),
                "url": url,
                "score": score,
                "priorite": str(item.get("priorite") or priority_label(priority_score, score)),
                "type": page_type,
                "mots": word_count,
                "pourquoi": str(item.get("pourquoi") or ", ".join(reasons[:3]) or "Page prioritaire du crawl."),
                "observation": str(item.get("observation") or build_page_observation(item, details, word_count)),
                "action": str(item.get("action") or page_action_from_reasons(reasons)),
                "angle": str(item.get("angle") or page_angle(url, details)),
                "effort": str(item.get("effort") or page_effort(reasons)),
                "effort_temps": str(item.get("effort_temps") or get_effort_label(page_type, word_count)),
                "impact": str(item.get("impact") or page_impact(priority_score, reasons)),
            }
        )
    return normalized


def normalize_signals(items: Any) -> list[dict[str, Any]]:
    normalized = []
    for raw in items if isinstance(items, list) else []:
        item = as_dict(raw)
        url = str(item.get("url") or "")
        dates = []
        if isinstance(item.get("dates"), list):
            dates = [as_dict(date) for date in item["dates"] if isinstance(date, dict)]
        else:
            for value in item.get("references") or []:
                dates.append({"type": infer_date_type(str(value)), "valeur": str(value)})
        if url or dates:
            normalized.append({"url": url, "dates": dates})
    return normalized


def normalize_crawled_urls(items: Any) -> list[dict[str, Any]]:
    normalized = []
    for raw in items if isinstance(items, list) else []:
        item = as_dict(raw)
        issues = item.get("points")
        if issues is None:
            issues = " | ".join(str(issue) for issue in (item.get("issues") or [])[:4]) or "-"
        outgoing_links = item.get("liens_internes_sortants", item.get("internal_links_out", []))
        if not isinstance(outgoing_links, list):
            outgoing_links = []
        title = str(item.get("titre_google") or item.get("title") or "")
        description = str(item.get("description_google") or item.get("meta_description") or "")
        load_time = optional_float(item.get("load_time"))
        redirections = get_int(item, "redirections", get_int(item, "redirect_count", 0))
        seo_suggestions = as_dict(item.get("seo_suggestions")) if item.get("seo_suggestions") else None
        normalized.append(
            {
                "url": str(item.get("url") or ""),
                "type": str(item.get("type") or item.get("page_type") or "-"),
                "score": get_int(item, "score", get_int(item, "page_health_score", 0)),
                "mots": get_int(item, "mots", get_int(item, "word_count", 0)),
                "points": str(issues),
                "load_time": load_time,
                "redirections": redirections,
                "liens_internes_sortants": [str(link) for link in outgoing_links if str(link).strip()],
                "titre_google": title,
                "description_google": description,
                **({"seo_suggestions": seo_suggestions} if seo_suggestions else {}),
            }
        )
    return normalized


def build_perf_data(urls_crawlees: list[dict[str, Any]]) -> dict[str, Any]:
    pages_avec_temps = [page for page in urls_crawlees if page.get("load_time") is not None]
    pages_avec_temps.sort(key=lambda page: optional_float(page.get("load_time")) or 0.0, reverse=True)
    temps_values = [optional_float(page.get("load_time")) for page in pages_avec_temps]
    temps_connus = [value for value in temps_values if value is not None]
    pages_lentes = [page for page in pages_avec_temps if (optional_float(page.get("load_time")) or 0.0) >= SEUIL_LENT]
    pages_critiques = [page for page in pages_avec_temps if (optional_float(page.get("load_time")) or 0.0) >= SEUIL_CRITIQUE]
    return {
        "pages_lentes": pages_lentes,
        "pages_critiques": pages_critiques,
        "temps_moyen": round(sum(temps_connus) / len(temps_connus), 2) if temps_connus else None,
        "temps_max": round(max(temps_connus), 2) if temps_connus else None,
        "pct_lentes": round(len(pages_lentes) / len(pages_avec_temps) * 100) if pages_avec_temps else 0,
        "top_10_lentes": pages_avec_temps[:10],
    }


def build_internal_link_map(urls_crawlees: list[dict[str, Any]], domain: str) -> dict[str, int]:
    incoming: defaultdict[str, int] = defaultdict(int)
    for page in urls_crawlees:
        for link in page.get("liens_internes_sortants", []):
            if not is_internal_link(str(link), domain):
                continue
            path = normalized_url_path(str(link), domain)
            incoming[path] += 1
    return dict(incoming)


def enrich_priority_pages_with_maillage(
    pages_prioritaires: list[dict[str, Any]],
    urls_crawlees: list[dict[str, Any]],
    domain: str,
) -> None:
    link_map = build_internal_link_map(urls_crawlees, domain)
    for page in pages_prioritaires:
        path = normalized_url_path(str(page.get("url") or ""), domain)
        nb = link_map.get(path, get_int(page, "incoming_links_observed", 0))
        page["nb_liens_internes"] = nb
        page["maillage_label"] = classify_maillage(nb)
        page["maillage_class"] = classify_maillage_class(nb)


def classify_maillage(nb_liens: int) -> str:
    if nb_liens == 0:
        return "isolée"
    if nb_liens < 3:
        return "faible"
    if nb_liens < 8:
        return "correct"
    return "bien reliée"


def classify_maillage_class(nb_liens: int) -> str:
    return {
        "isolée": "score-low",
        "faible": "score-mid",
        "correct": "score-high",
        "bien reliée": "score-high",
    }[classify_maillage(nb_liens)]


def generate_seo_suggestions_for_priority_pages(
    urls_crawlees: list[dict[str, Any]],
    pages_prioritaires: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    priority_keys = [canonical_url_key(str(page.get("url") or "")) for page in pages_prioritaires]
    priority_keys = [key for key in priority_keys if key]
    priority_set = set(priority_keys)
    candidates = []
    for page in urls_crawlees:
        if page.get("seo_suggestions"):
            continue
        if priority_set and canonical_url_key(str(page.get("url") or "")) not in priority_set:
            continue
        if needs_title_fix(page) or needs_desc_fix(page):
            candidates.append(page)
    if not candidates:
        return urls_crawlees
    suggestions_source = generate_seo_suggestions(candidates[:10])
    suggestions_by_url = {
        canonical_url_key(str(page.get("url") or "")): as_dict(page.get("seo_suggestions"))
        for page in suggestions_source
        if as_dict(page.get("seo_suggestions"))
    }
    for page in urls_crawlees:
        key = canonical_url_key(str(page.get("url") or ""))
        if key in suggestions_by_url:
            page["seo_suggestions"] = suggestions_by_url[key]
    return urls_crawlees


def generate_seo_suggestions(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pages_a_corriger = [page for page in pages if needs_title_fix(page) or needs_desc_fix(page)]
    if not pages_a_corriger:
        return pages
    raw_suggestions = generate_seo_suggestions_with_anthropic(pages_a_corriger)
    suggestions_by_url = {str(suggestion.get("url") or ""): suggestion for suggestion in raw_suggestions}
    for page in pages:
        if not (needs_title_fix(page) or needs_desc_fix(page)):
            continue
        raw_suggestion = suggestions_by_url.get(str(page.get("url") or "")) or build_local_seo_suggestion(page)
        suggestion = sanitize_seo_suggestion(page, raw_suggestion)
        if has_actionable_seo_suggestion(suggestion):
            page["seo_suggestions"] = suggestion
    return pages


def generate_seo_suggestions_with_anthropic(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return []
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        return []
    pages_json = json.dumps(
        [
            {
                "url": page["url"],
                "titre_actuel": page.get("titre_google", ""),
                "description_actuelle": page.get("description_google", ""),
                "nb_mots": page.get("mots", 0),
                "type": page.get("type", "page"),
                "problemes": {
                    "titre_absent": not page.get("titre_google"),
                    "titre_trop_long": len(str(page.get("titre_google") or "")) > SEUIL_TITRE_LONG,
                    "description_absente": not page.get("description_google"),
                    "description_trop_longue": len(str(page.get("description_google") or "")) > SEUIL_DESC_LONGUE,
                    "description_trop_courte": 0 < len(str(page.get("description_google") or "")) < SEUIL_DESC_COURTE,
                },
            }
            for page in pages
        ],
        ensure_ascii=False,
        indent=2,
    )
    prompt = f"""Tu es un expert SEO. Pour chaque page ci-dessous, génère un titre Google optimisé et une description Google optimisée.

Règles strictes :
- Titre : entre 50 et 60 caractères maximum
- Description : entre 140 et 155 caractères
- Langue : même langue que le titre actuel
- Ton : professionnel, accrocheur, fidèle au sujet
- Ne pas inventer de contenu qui n'existe pas
- Si le titre actuel n'est pas absent ou trop long, laisse "titre_suggere" vide et "titre_longueur" à 0
- Ne propose jamais le même titre que le titre actuel
- N'allonge pas un titre correct avec un suffixe générique comme ": informations essentielles"

Pages à corriger :
{pages_json}

Réponds UNIQUEMENT avec un JSON valide, sans markdown, sans backticks, sans commentaires :
[
  {{
    "url": "...",
    "titre_suggere": "...",
    "titre_longueur": 0,
    "description_suggeree": "...",
    "description_longueur": 0,
    "explication_titre": "...",
    "explication_description": "..."
  }}
]"""
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        suggestions = json.loads(content)
    except Exception:
        return []
    return [as_dict(item) for item in suggestions if isinstance(item, dict)]


def build_local_seo_suggestion(page: dict[str, Any]) -> dict[str, Any]:
    url = str(page.get("url") or "")
    title_current = str(page.get("titre_google") or slug_to_title(url)).strip()
    title = fit_seo_title(title_current, url) if needs_title_fix(page) else ""
    description_seed = title or title_current or slug_to_title(url)
    description = fit_meta_description(url, description_seed) if needs_desc_fix(page) else ""
    suggestion = {
        "url": url,
    }
    if title:
        suggestion.update(
            {
                "titre_suggere": title,
                "titre_longueur": len(title),
                "explication_titre": "Titre resserré pour éviter la troncature dans Google.",
            }
        )
    if description:
        suggestion.update(
            {
                "description_suggeree": description,
                "description_longueur": len(description),
                "explication_description": "Description reformulée pour garder un extrait clair et exploitable dans les résultats.",
            }
        )
    return suggestion


def fit_seo_title(title: str, url: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip(" -|")
    if not cleaned:
        cleaned = slug_to_title(url)
    return trim_at_word(cleaned, SEUIL_TITRE_LONG)


def infer_seo_language(*values: str) -> str:
    text = " ".join(str(value or "") for value in values).casefold()
    if re.search(r"[àâçéèêëîïôûùüÿœæ]", text):
        return "fr"
    tokens = re.findall(r"[a-z']+", text)
    french_score = sum(1 for token in tokens if token in FRENCH_LANGUAGE_MARKERS)
    english_score = sum(1 for token in tokens if token in ENGLISH_LANGUAGE_MARKERS)
    return "fr" if french_score > english_score else "en"


def sanitize_seo_suggestion(page: dict[str, Any], suggestion: dict[str, Any]) -> dict[str, Any]:
    url = str(page.get("url") or suggestion.get("url") or "")
    cleaned = as_dict(suggestion).copy()
    cleaned["url"] = url

    title_current = re.sub(r"\s+", " ", str(page.get("titre_google") or "")).strip()
    title_suggested = re.sub(r"\s+", " ", str(cleaned.get("titre_suggere") or "")).strip(" -|")
    title_needs_work = needs_title_fix(page)
    if title_needs_work:
        if not title_suggested:
            title_suggested = fit_seo_title(title_current, url)
        else:
            title_suggested = trim_at_word(title_suggested, SEUIL_TITRE_LONG)
        if title_suggested and not same_normalized_text(title_current, title_suggested):
            cleaned["titre_suggere"] = title_suggested
            cleaned["titre_longueur"] = len(title_suggested)
            cleaned.setdefault("explication_titre", "Titre resserré pour éviter la troncature dans Google.")
        else:
            remove_title_suggestion(cleaned)
    else:
        remove_title_suggestion(cleaned)

    desc_suggested = re.sub(r"\s+", " ", str(cleaned.get("description_suggeree") or "")).strip()
    target_language = infer_seo_language(title_current, str(page.get("description_google") or ""), slug_to_title(url))
    if needs_desc_fix(page):
        seed_title = str(cleaned.get("titre_suggere") or title_current or slug_to_title(url))
        if (
            not desc_suggested
            or not (SEUIL_DESC_COURTE <= len(desc_suggested) <= SEUIL_DESC_LONGUE)
            or infer_seo_language(desc_suggested) != target_language
        ):
            desc_suggested = fit_meta_description(url, seed_title, language=target_language)
        cleaned["description_suggeree"] = desc_suggested
        cleaned["description_longueur"] = len(desc_suggested)
        cleaned.setdefault(
            "explication_description",
            "Description reformulée pour garder un extrait clair et exploitable dans les résultats.",
        )
    else:
        remove_description_suggestion(cleaned)

    return cleaned


def has_actionable_seo_suggestion(suggestion: dict[str, Any]) -> bool:
    return bool(str(suggestion.get("titre_suggere") or "").strip() or str(suggestion.get("description_suggeree") or "").strip())


def same_normalized_text(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" -|:").casefold()

    return bool(left or right) and normalize(left) == normalize(right)


def remove_title_suggestion(suggestion: dict[str, Any]) -> None:
    suggestion.pop("titre_suggere", None)
    suggestion.pop("titre_longueur", None)
    suggestion.pop("explication_titre", None)


def remove_description_suggestion(suggestion: dict[str, Any]) -> None:
    suggestion.pop("description_suggeree", None)
    suggestion.pop("description_longueur", None)
    suggestion.pop("explication_description", None)


def fit_meta_description(url: str, title: str, *, language: str | None = None) -> str:
    topic = slug_to_title(url)
    if topic.lower() in {"page sans titre", "accueil"}:
        topic = title
    language = language or infer_seo_language(title, topic)
    topic = trim_at_word(topic, 42 if language == "fr" else 58)
    if language == "fr":
        description = (
            f"Retrouvez les informations essentielles sur {topic}, avec conseils pratiques, "
            "points clés et prochaines étapes."
        )
    else:
        description = (
            f"Find essential information about {topic}, with practical tips, key details, "
            "and clear next steps for readers."
        )
    return complete_meta_description(description, language)


def complete_meta_description(description: str, language: str) -> str:
    if 140 <= len(description) <= 155:
        return finish_sentence(description)
    extras = (
        (
            "À jour.",
            "Conseils pratiques inclus.",
            "Points clés et conseils pratiques.",
            "Conseils pratiques pour avancer avec confiance.",
        )
        if language == "fr"
        else (
            "Useful for planning.",
            "Useful for browsing and planning.",
            "Useful for browsing and planning with confidence.",
        )
    )
    for extra in extras:
        candidate = f"{description} {extra}"
        if 140 <= len(candidate) <= 155:
            return finish_sentence(candidate)
    return finish_sentence(trim_at_word(description, 155))


def finish_sentence(value: str) -> str:
    cleaned = value.strip(" ,;:-")
    if cleaned.endswith((".", "!", "?")):
        return cleaned
    return f"{cleaned}."


def trim_at_word(value: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rsplit(" ", 1)[0].strip(" -|,.;")
    return trimmed or cleaned[:limit].strip()


def normalize_matrix(matrix: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    normalized: dict[str, list[dict[str, Any]]] = {}
    for key in ("quick_wins", "projets_structurants", "optimisations_simples", "backlog"):
        normalized[key] = []
        for raw in matrix.get(key, []) if isinstance(matrix.get(key), list) else []:
            item = as_dict(raw)
            title = item.get("titre") or item.get("action")
            if not title:
                continue
            normalized[key].append(
                {
                    "titre": str(title),
                    "impact": str(item.get("impact") or "-"),
                    "effort": str(item.get("effort") or "-"),
                    "priorite": str(item.get("priorite") or item.get("priority") or "modérée"),
                }
            )
    return normalized


def normalize_benchmark(items: Any) -> list[dict[str, Any]]:
    normalized = []
    for raw in items if isinstance(items, list) else []:
        item = as_dict(raw)
        domaine = str(item.get("domaine") or item.get("domain") or item.get("site") or "").strip()
        if not domaine:
            continue
        normalized.append(
            {
                "domaine": domaine,
                "score_estime": clamp_score(get_int(item, "score_estime", get_int(item, "score", 0))),
                "nb_pages_contenu": get_int(item, "nb_pages_contenu", get_int(item, "content_like_pages", 0)),
                "signal": str(item.get("signal") or "Signal à vérifier"),
            }
        )
    return normalized[:3]


def normalize_offers(items: Any) -> list[dict[str, Any]]:
    normalized = []
    for raw in items if isinstance(items, list) else []:
        item = as_dict(raw)
        features = [str(feature) for feature in item.get("features", []) if str(feature).strip()] if isinstance(item.get("features"), list) else []
        if not item.get("nom") and not item.get("prix"):
            continue
        normalized.append(
            {
                "nom": str(item.get("nom") or "Formule"),
                "prix": str(item.get("prix") or "-"),
                "periode": str(item.get("periode") or ""),
                "mise_en_avant": get_bool(item.get("mise_en_avant"), default=False),
                "features": features,
            }
        )
    return normalized


def build_dirigeant_texts(
    *,
    domain: str,
    score: int,
    pages_analysees: int,
    contenus_utiles: int,
    score_moyen_page: int,
    signal_principal: str,
    dates_a_verifier: int,
    pages_prioritaires: list[dict[str, Any]],
) -> dict[str, str]:
    simple_signal = plain_business_signal(signal_principal)
    if score >= 90:
        opening = "Votre site est dans un bon état général."
    elif score >= 75:
        opening = "Votre site part d'une base saine, avec quelques reprises utiles à prévoir."
    else:
        opening = "Votre site montre plusieurs points faciles à améliorer sans refonte complète."

    priority_pages = pages_prioritaires[:3]
    page_count = len(priority_pages) or min(3, max(1, contenus_utiles))
    min_hours, max_hours = estimate_total_effort(priority_pages)
    if priority_pages:
        page_word = "page" if page_count == 1 else "pages"
        recommendation = (
            f"Reprendre {page_count} {page_word} en priorité. Effort estimé : {min_hours} à {max_hours}h au total, "
            "pour améliorer la clarté et la fraîcheur sous 30 à 60 jours."
        )
    else:
        recommendation = (
            "Valider les pages commerciales clés avant d'engager un gros chantier. "
            "Effort estimé : 2 à 4h pour cadrer les premières priorités."
        )

    if dates_a_verifier:
        risk = (
            "Des pages qui semblent anciennes peuvent réduire la confiance des visiteurs. "
            "Plus on attend, plus cette impression peut s'installer."
        )
    elif pages_prioritaires:
        risk = (
            "Les pages à reprendre peuvent continuer à laisser filer des demandes utiles. "
            "Le risque principal est de repousser des corrections simples."
        )
    else:
        risk = (
            "Le risque immédiat reste limité, mais une relecture régulière évite que le site vieillisse sans signal visible."
        )

    return {
        "resume_dirigeant": f"{opening} Le principal frein aujourd'hui : {simple_signal}. Ce point peut être traité par étapes, sans refaire tout le site.",
        "ou_vous_en_etes": f"{pages_analysees} pages analysées sur {domain}, dont {contenus_utiles} contenus exploitables. Le score moyen des pages est de {score_moyen_page}/100.",
        "risque_attente": risk,
        "recommandation_courte": recommendation,
    }


def plain_business_signal(signal: str) -> str:
    text = signal.lower()
    if "date" in text or "ancien" in text:
        return "certaines pages donnent une impression de contenu ancien"
    if "maillage" in text or "lien" in text or "reli" in text:
        return "certaines pages importantes sont encore trop isolées"
    if "contenu" in text and ("léger" in text or "leger" in text or "enrichir" in text):
        return "certaines pages ne donnent pas encore assez d'informations"
    if "proche" in text or "concurr" in text or "même intention" in text:
        return "plusieurs pages semblent parler du même sujet"
    if "titre" in text or "description" in text:
        return "certains intitulés visibles doivent être clarifiés"
    if "noindex" in text or "canonical" in text or "robots" in text:
        return "certaines pages doivent être vérifiées avant d'être mises en avant"
    cleaned = signal.strip().rstrip(".")
    return cleaned[:1].lower() + cleaned[1:] if cleaned else "les priorités doivent être clarifiées"


def estimate_total_effort(pages: list[dict[str, Any]]) -> tuple[int, int]:
    if not pages:
        return (2, 4)
    minimum = 0
    maximum = 0
    for page in pages[:3]:
        low, high = get_effort_bounds(str(page.get("type") or "page"), get_int(page, "mots", 0))
        minimum += low
        maximum += high
    return (max(1, minimum), max(2, maximum))


def get_effort_label(page_type: str, mots: int) -> str:
    _, _, label = get_effort_entry(page_type, mots)
    return label


def get_effort_bounds(page_type: str, mots: int) -> tuple[int, int]:
    minimum, maximum, _ = get_effort_entry(page_type, mots)
    return minimum, maximum


def get_effort_entry(page_type: str, mots: int) -> tuple[int, int, str]:
    if mots < 500:
        longueur = "court"
    elif mots < 1200:
        longueur = "moyen"
    else:
        longueur = "long"
    key = (normalize_effort_page_type(page_type), longueur)
    return EFFORT_MAP.get(key, (2, 4, "2 à 4h estimées"))


def normalize_effort_page_type(page_type: str) -> str:
    lowered = page_type.strip().lower()
    article_markers = ("article", "blog", "post", "guide", "actualite", "actualité", "news")
    if any(marker in lowered for marker in article_markers):
        return "article"
    return "page"


def build_strengths(summary: dict[str, Any], pages: int, score: int) -> list[str]:
    strengths: list[str] = []
    pages_ok = get_int(summary, "pages_ok", 0)
    if pages_ok and pages and pages_ok >= max(1, round(pages * 0.85)):
        strengths.append("La majorité des pages visitées répond correctement.")
    content_pages = get_int(summary, "content_like_pages", 0)
    if content_pages:
        strengths.append(f"{content_pages} contenus utiles sont déjà exploitables.")
    if not get_int(summary, "missing_titles", 0) and not get_int(summary, "missing_h1", 0):
        strengths.append("Les titres principaux ne montrent pas de manque généralisé.")
    if score >= 90:
        strengths.append("Le socle observé est solide, les actions relèvent surtout de l'optimisation.")
    return strengths[:4] or ["Le crawl donne assez de matière pour établir un plan d'action concret."]


def build_attention_points(summary: dict[str, Any], signals: list[dict[str, Any]], data: dict[str, Any]) -> list[str]:
    if data.get("critical_findings"):
        return [str(item) for item in data.get("critical_findings", [])[:4]]
    points = []
    for signal in signals[:4]:
        count = get_int(signal, "count", 0)
        label = str(signal.get("signal") or "Signal à vérifier")
        points.append(f"{label} ({count})" if count else label)
    if get_int(summary, "dated_content_signals", 0) and not points:
        points.append("Des dates visibles méritent une vérification.")
    return points or ["Aucun point bloquant majeur n'a été isolé automatiquement."]


def build_primary_signal(summary: dict[str, Any], signals: list[dict[str, Any]]) -> str:
    if signals:
        first = signals[0]
        count = get_int(first, "count", 0)
        label = str(first.get("signal") or "Signal à vérifier")
        return f"{label} ({count})" if count else label
    if get_int(summary, "dated_content_signals", 0):
        return "Dates visibles à vérifier"
    return "Socle globalement sain, à confirmer sur les pages business."


def build_plan_action(summary: dict[str, Any], top_pages: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    quick = []
    if get_int(summary, "dated_content_signals", 0):
        quick.append("vérifier les dates visibles")
    if get_int(summary, "missing_meta_descriptions", 0):
        quick.append("compléter les descriptions Google")
    if get_int(summary, "weak_internal_linking_pages", 0):
        quick.append("renforcer les liens internes évidents")
    if top_pages:
        quick.append("reprendre les pages prioritaires")
    if not quick:
        quick = ["relire les pages business clés"]
    return {
        "j30": {"titre": "Corriger les signaux visibles", "description": sentence_from_items(quick[:3])},
        "j60": {"titre": "Reprendre les pages prioritaires", "description": "Transformer les fiches page en briefs éditoriaux puis publier un premier lot."},
        "j90": {"titre": "Consolider la structure", "description": "Renforcer les hubs, le maillage interne et les contenus qui soutiennent les pages business."},
    }


def build_matrix(summary: dict[str, Any], top_pages: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    actions: list[dict[str, str]] = []
    mapping = [
        ("noindex_pages", "Vérifier les pages noindex", "élevé", "faible", "haute"),
        ("canonical_to_other_url_pages", "Contrôler les canonicals", "élevé", "moyen", "haute"),
        ("dated_content_signals", "Mettre à jour les contenus datés", "élevé", "moyen", "haute"),
        ("weak_internal_linking_pages", "Renforcer le maillage interne", "élevé", "faible", "haute"),
        ("thin_content_pages", "Enrichir les contenus légers", "modéré", "moyen", "modérée"),
        ("possible_content_overlap_pairs", "Clarifier les contenus proches", "élevé", "moyen", "haute"),
        ("duplicate_title_groups", "Différencier les titres Google", "modéré", "faible", "modérée"),
    ]
    for key, title, impact, effort, priority in mapping:
        count = get_int(summary, key, 0)
        if count:
            actions.append({"titre": f"{title} ({count})", "impact": impact, "effort": effort, "priorite": priority})
    if top_pages and not actions:
        actions.append({"titre": "Relire les premières pages prioritaires", "impact": "modéré", "effort": "faible", "priorite": "modérée"})
    matrix = {"quick_wins": [], "projets_structurants": [], "optimisations_simples": [], "backlog": []}
    for action in actions[:6]:
        high_impact = "élev" in action["impact"] or "fort" in action["impact"]
        low_effort = "faible" in action["effort"]
        if high_impact and low_effort:
            matrix["quick_wins"].append(action)
        elif high_impact:
            matrix["projets_structurants"].append(action)
        elif low_effort:
            matrix["optimisations_simples"].append(action)
        else:
            matrix["backlog"].append(action)
    return matrix


def build_editorial_opportunities(summary: dict[str, Any], top_pages: list[dict[str, Any]]) -> list[str]:
    opportunities = []
    content_pages = get_int(summary, "content_like_pages", 0)
    if content_pages:
        opportunities.append(f"Consolider les {content_pages} contenus utiles déjà repérés.")
    if get_int(summary, "dated_content_signals", 0):
        opportunities.append("Ajouter un angle fraîcheur sur les contenus qui affichent une date ancienne.")
    if get_int(summary, "weak_internal_linking_pages", 0):
        opportunities.append("Créer des liens depuis les contenus forts vers les pages peu visibles.")
    if top_pages:
        opportunities.append(f"Utiliser {truncate(str(top_pages[0].get('url') or ''), 54)} comme page pilote.")
    return opportunities[:3] or ["Formaliser trois contenus piliers à partir des pages business les plus importantes."]


def build_method(data: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    metadata = as_dict(data.get("crawl_metadata"))
    return {
        "pages_visitees": get_int(summary, "pages_crawled", get_int(data, "pages_crawled", 0)),
        "sitemap_urls": get_int(metadata, "sitemap_urls_found", 0),
        "urls_restantes": get_int(metadata, "queued_urls_remaining", 0),
        "raison_arret": str(metadata.get("stop_reason") or "-"),
    }


def build_conclusion_actions(context: dict[str, Any]) -> list[str]:
    quick_wins = [str(item.get("titre")) for item in context["matrice"].get("quick_wins", []) if item.get("titre")]
    if len(quick_wins) >= 3:
        return quick_wins[:3]
    pages = [f"Reprendre {page.get('titre')}" for page in context["pages_prioritaires"][:3]]
    actions = [*quick_wins, *pages]
    if len(actions) < 3:
        actions.append(str(context["plan_action"]["j30"].get("description") or "Valider les priorités J30."))
    return actions[:3]


def infer_urgency(score: int, summary: dict[str, Any], signals: list[dict[str, Any]]) -> str:
    blocking = sum(get_int(summary, key, 0) for key in ("noindex_pages", "canonical_to_other_url_pages", "canonical_cross_domain_pages", "robots_blocked_pages"))
    high_signals = sum(1 for item in signals if str(item.get("severity") or "").upper() == "HIGH")
    if score < 75 or blocking or high_signals >= 3:
        return "élevé"
    if score < 90 or signals:
        return "moyen"
    return "faible"


def infer_base_status(score: int) -> str:
    if score >= 90:
        return "Base observée : plutôt saine"
    if score >= 75:
        return "Base observée : saine, avec plusieurs reprises utiles"
    return "Base observée : premiers signaux à corriger"


def page_action_from_reasons(reasons: list[str]) -> str:
    haystack = " ".join(reasons).lower()
    if "date" in haystack:
        return "Mettre à jour les informations visibles et ajouter un signal de fraîcheur."
    if "liens" in haystack or "retrouver" in haystack:
        return "Ajouter des liens internes depuis des contenus proches."
    if "contenu" in haystack:
        return "Enrichir la page avec critères, exemples et réponses directes."
    if "canonical" in haystack:
        return "Contrôler quelle URL doit porter le sujet."
    return "Relire la page et définir une reprise ciblée."


def page_effort(reasons: list[str]) -> str:
    haystack = " ".join(reasons).lower()
    if "liens" in haystack or "description" in haystack or "titre" in haystack:
        return "faible"
    if "canonical" in haystack:
        return "faible à moyen"
    return "moyen"


def page_impact(priority_score: int, reasons: list[str]) -> str:
    haystack = " ".join(reasons).lower()
    if priority_score >= 8 or "canonical" in haystack or "noindex" in haystack:
        return "élevé"
    if priority_score >= 4:
        return "moyen à élevé"
    return "moyen"


def page_angle(url: str, details: dict[str, Any]) -> str:
    title = str(details.get("title") or "").strip() or slug_to_title(url)
    return f"Clarifier la promesse de \"{title}\" et mieux couvrir l'intention principale."


def build_page_observation(item: dict[str, Any], details: dict[str, Any], words: int) -> str:
    issues = [str(issue) for issue in (details.get("issues") or [])[:2]]
    bits = [f"{words} mots"] if words else []
    bits.extend(issues)
    return ", ".join(bits) if bits else "Aucun point technique bloquant dans les données de crawl."


def format_audit_date(value: str) -> str:
    if not value:
        return datetime.now().strftime(f"%-d {FRENCH_MONTHS[datetime.now().month]} %Y")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return f"{parsed.day} {FRENCH_MONTHS[parsed.month]} {parsed.year}"


def priority_label(priority_score: int, score: int) -> str:
    if priority_score >= 7 or score < 75:
        return "haute"
    if priority_score >= 4 or score < 90:
        return "modérée"
    return "faible"


def priority_color_class(value: str) -> str:
    normalized = value.lower()
    if "haut" in normalized or "élev" in normalized or "eleve" in normalized:
        return "high"
    if "mod" in normalized or "moy" in normalized:
        return "mid"
    return "low"


def urgency_color_class(value: str) -> str:
    normalized = value.lower()
    if "élev" in normalized or "eleve" in normalized:
        return "urgency-high"
    if "moy" in normalized:
        return "urgency-mid"
    return "urgency-low"


def infer_date_type(value: str) -> str:
    normalized = value.lower()
    if "titre" in normalized or "title" in normalized:
        return "titre"
    if "url" in normalized:
        return "url"
    return "contenu"


def date_type_class(value: str) -> str:
    normalized = value.lower()
    if "titre" in normalized:
        return "titre"
    if "url" in normalized:
        return "url"
    return "contenu"


def sentence_from_items(items: list[str]) -> str:
    cleaned = [item.strip().rstrip(".") for item in items if item]
    if not cleaned:
        return "Valider les priorités avec une relecture manuelle."
    sentence = ", ".join(cleaned)
    return sentence[:1].upper() + sentence[1:] + "."


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_seconds(value: float | None) -> str:
    if value is None:
        return "—"
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{formatted}s"


def canonical_url_key(url: str) -> str:
    parsed = parse_url_for_domain(url, "")
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{netloc}{path}".strip("/")


def normalized_url_path(url: str, domain: str) -> str:
    return parse_url_for_domain(url, domain).path.rstrip("/")


def is_internal_link(url: str, domain: str) -> bool:
    parsed = parse_url_for_domain(url, domain)
    if not parsed.netloc:
        return True
    clean_netloc = parsed.netloc.lower().removeprefix("www.")
    clean_domain = domain.lower().removeprefix("www.").strip("/")
    return clean_netloc == clean_domain


def parse_url_for_domain(url: str, domain: str):
    value = str(url or "").strip()
    if not value:
        return urlparse("")
    if value.startswith(("http://", "https://")):
        return urlparse(value)
    if value.startswith("/"):
        base = domain.strip("/") or "example.com"
        return urlparse(f"https://{base}{value}")
    return urlparse(f"https://{value}")


def object_to_mapping(source: Any) -> dict[str, Any]:
    if is_dataclass(source):
        return asdict(source)
    if isinstance(source, dict):
        return source
    return dict(getattr(source, "__dict__", {}))


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    return {}


def get_int(mapping: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(mapping.get(key, default) or 0)
    except (TypeError, ValueError):
        return default


def get_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "oui", "on"}:
            return True
        if normalized in {"0", "false", "no", "non", "off"}:
            return False
    return bool(value)


def list_or_default(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = [str(item) for item in value if str(item).strip()]
        if cleaned:
            return cleaned
    return default


def clamp_score(score: int) -> int:
    return max(0, min(100, int(score or 0)))


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] or urlparse(url).netloc or "page"


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip("/") + "…"


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_report_script() -> str:
    return """
<script>
  function toggleAnnexe() {
    const el = document.getElementById('annexe');
    if (!el) return;
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
  }

  function printWithAnnexe() {
    document.body.classList.add('print-with-annexe');
    window.print();
    document.body.classList.remove('print-with-annexe');
  }
</script>"""


def render_report_styles() -> str:
    return """
    @import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&family=Inter:wght@400;500;600&display=swap');
    :root {
      --font-display: 'Bricolage Grotesque', sans-serif;
      --font-body: 'Inter', sans-serif;
      --color-bg: #F9F8F6;
      --color-surface: #FFFFFF;
      --color-border: #E8E4DC;
      --color-text-primary: #1A1917;
      --color-text-secondary: #6B6660;
      --color-text-muted: #A09A94;
      --color-accent: #2D5BFF;
      --color-accent-light: #EEF2FF;
      --color-success: #16A34A;
      --color-warning: #D97706;
      --color-danger: #DC2626;
      --color-score-high: #16A34A;
      --color-score-mid: #D97706;
      --color-score-low: #DC2626;
      --space-xs: 4px;
      --space-sm: 8px;
      --space-md: 16px;
      --space-lg: 24px;
      --space-xl: 40px;
      --space-2xl: 64px;
    }
    .report-document {
      margin: 0;
      background: var(--color-bg);
      color: var(--color-text-primary);
      font-family: var(--font-body);
      font-size: 15px;
      line-height: 1.6;
    }
    .premium-report {
      max-width: 1120px;
      margin: 0 auto;
      padding: var(--space-lg);
      color: var(--color-text-primary);
      font-family: var(--font-body);
      font-size: 15px;
      line-height: 1.6;
    }
    .premium-report * { box-sizing: border-box; }
    .premium-report body,
    .premium-report p,
    .premium-report td,
    .premium-report th,
    .premium-report li,
    .premium-report span,
    .premium-report a,
    .premium-report button {
      font-family: var(--font-body);
    }
    .premium-report h1,
    .premium-report h2,
    .premium-report h3 {
      margin: 0;
      font-family: var(--font-display);
      font-weight: 700;
      line-height: 1.12;
      letter-spacing: 0;
    }
    .premium-report h1 { font-size: 56px; }
    .premium-report h2 { font-size: 22px; }
    .premium-report h3 { font-size: 16px; }
    .premium-report p { margin: 0; }
    .premium-report a { color: inherit; }
    .premium-report .label {
      color: var(--color-text-muted);
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.08em;
      line-height: 1.2;
      text-transform: uppercase;
    }
    .premium-report .tool-name,
    .premium-report .cover-title,
    .premium-report .section-label,
    .premium-report .metrique-value {
      font-family: var(--font-display);
    }
    .premium-report .section-label {
      color: var(--color-text-muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      line-height: 1.2;
      text-transform: uppercase;
      break-before: page;
      page-break-before: always;
    }
    .premium-report .report-page {
      display: grid;
      gap: var(--space-lg);
      min-height: auto;
      padding: var(--space-lg) 0;
    }
    .premium-report .card {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      padding: var(--space-lg);
    }
    .premium-report .section-head {
      display: grid;
      gap: var(--space-sm);
      align-content: end;
    }
    .premium-report .cover-page {
      min-height: 1040px;
      padding: var(--space-xl);
      border-radius: 16px;
      background:
        linear-gradient(140deg, rgba(45,91,255,0.10), transparent 42%),
        var(--color-surface);
      border: 1px solid var(--color-border);
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .premium-report .cover-brand,
    .premium-report .cover-meta,
    .premium-report .signature {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    .premium-report .rapport-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      min-height: 48px;
    }
    .premium-report .cover-branding {
      min-width: 1px;
    }
    .premium-report .header-logo,
    .premium-report .cover-logo {
      display: block;
      max-width: 180px;
      max-height: 56px;
      object-fit: contain;
    }
    .premium-report .header-label {
      color: var(--color-text-muted);
      font-family: var(--font-body);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      line-height: 1.2;
    }
    .premium-report .cover-brand strong,
    .premium-report .signature strong {
      display: block;
      font-family: var(--font-display);
      font-size: 18px;
    }
    .premium-report .tool-name {
      font-weight: 700;
      font-size: 18px;
      letter-spacing: 0;
    }
    .premium-report .cover-brand span,
    .premium-report .signature span,
    .premium-report .cover-meta span,
    .premium-report .muted-url {
      color: var(--color-text-secondary);
    }
    .premium-report .cover-center {
      display: grid;
      gap: var(--space-xl);
      place-items: center;
      text-align: center;
      align-self: center;
    }
    .premium-report .cover-domain {
      margin-top: var(--space-md);
      color: var(--color-accent);
      font-family: var(--font-display);
      font-size: 24px;
      font-weight: 600;
    }
    .premium-report .cover-title {
      color: var(--color-text-primary);
      font-family: var(--font-display);
      font-size: 72px;
      font-style: normal;
      font-weight: 800;
      letter-spacing: 0;
      line-height: 1;
      text-shadow: none;
    }
    .premium-report .cover-score {
      display: grid;
      gap: var(--space-md);
      justify-items: center;
    }
    .premium-report .score-gauge {
      width: 184px;
      height: 184px;
    }
    .premium-report .gauge-track,
    .premium-report .gauge-meter {
      fill: none;
      stroke-width: 12;
    }
    .premium-report .gauge-track { stroke: var(--color-border); }
    .premium-report .gauge-meter {
      stroke-linecap: round;
      transition: stroke-dashoffset 240ms ease;
    }
    .premium-report .score-gauge.score-high .gauge-meter { stroke: var(--color-score-high); }
    .premium-report .score-gauge.score-mid .gauge-meter { stroke: var(--color-score-mid); }
    .premium-report .score-gauge.score-low .gauge-meter { stroke: var(--color-score-low); }
    .premium-report .score-gauge text:first-of-type {
      fill: var(--color-text-primary);
      font-family: var(--font-display);
      font-size: 34px;
      font-weight: 700;
    }
    .premium-report .score-gauge text:last-of-type {
      fill: var(--color-text-secondary);
      font-size: 14px;
      font-weight: 700;
    }
    .premium-report .score-badge,
    .premium-report .score-pill,
    .premium-report .urgency-badge,
    .premium-report .priority-badge,
    .premium-report .type-badge,
    .premium-report .badge,
    .premium-report .page-tags span,
    .premium-report .impact-effort-row span {
      display: inline-flex;
      align-items: center;
      width: fit-content;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.2;
      white-space: nowrap;
    }
    .premium-report .score-high,
    .premium-report .priority-low,
    .premium-report .urgency-low {
      background: rgba(22,163,74,0.12);
      color: var(--color-success);
    }
    .premium-report .score-mid,
    .premium-report .priority-mid,
    .premium-report .urgency-mid,
    .premium-report .metric-warning {
      background: rgba(217,119,6,0.12);
      color: var(--color-warning);
    }
    .premium-report .score-low,
    .premium-report .priority-high,
    .premium-report .urgency-high {
      background: rgba(220,38,38,0.12);
      color: var(--color-danger);
    }
    .premium-report .score-context {
      display: grid;
      gap: var(--space-sm);
      justify-items: center;
      color: var(--color-text-secondary);
    }
    .premium-report .cover-page footer {
      align-self: end;
      color: var(--color-text-muted);
      font-size: 13px;
      text-align: center;
    }
    .premium-report .page-footer {
      align-self: end;
      display: flex;
      justify-content: space-between;
      gap: var(--space-md);
      color: var(--color-text-muted);
      font-size: 12px;
      border-top: 1px solid var(--color-border);
      padding-top: var(--space-md);
    }
    .premium-report .section-dirigeant {
      break-before: page;
      page-break-before: always;
      align-content: start;
    }
    .premium-report .dirigeant-card {
      background: var(--color-surface);
      border: 2px solid var(--color-accent);
      border-radius: 16px;
      padding: var(--space-xl);
      margin-top: var(--space-lg);
      box-shadow: 0 10px 26px rgba(45,91,255,0.08);
    }
    .premium-report .dirigeant-header {
      display: flex;
      align-items: flex-start;
      gap: var(--space-xl);
      margin-bottom: var(--space-xl);
      padding-bottom: var(--space-xl);
      border-bottom: 1px solid var(--color-border);
    }
    .premium-report .dirigeant-score-bloc {
      display: flex;
      flex-direction: column;
      align-items: center;
      flex-shrink: 0;
      background: var(--color-bg);
      border-radius: 12px;
      padding: var(--space-md) var(--space-lg);
      min-width: 100px;
    }
    .premium-report .dirigeant-score-value {
      background: transparent;
      font-family: var(--font-display);
      font-size: 40px;
      font-weight: 800;
      line-height: 1;
    }
    .premium-report .dirigeant-score-label {
      margin-top: 4px;
      color: var(--color-text-muted);
      font-size: 11px;
      line-height: 1.25;
      text-align: center;
    }
    .premium-report .dirigeant-phrase {
      color: var(--color-text-primary);
      font-size: 16px;
      font-weight: 500;
      line-height: 1.6;
    }
    .premium-report .dirigeant-trois-colonnes {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--space-lg);
    }
    .premium-report .dirigeant-col {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
    }
    .premium-report .dirigeant-col-icon {
      font-size: 24px;
      line-height: 1;
    }
    .premium-report .dirigeant-col-title {
      color: var(--color-text-primary);
      font-family: var(--font-display);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.05em;
      line-height: 1.25;
      text-transform: uppercase;
    }
    .premium-report .dirigeant-col-text {
      color: var(--color-text-secondary);
      font-size: 13px;
      line-height: 1.6;
    }
    .premium-report .executive-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
      gap: var(--space-lg);
    }
    .premium-report .synthese {
      page-break-inside: avoid;
      break-inside: avoid;
    }
    .premium-report .executive-left {
      display: grid;
      gap: var(--space-md);
    }
    .premium-report .insight-card {
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr);
      gap: var(--space-md);
    }
    .premium-report .insight-icon {
      display: grid;
      place-items: center;
      width: 36px;
      height: 36px;
      border-radius: 999px;
      font-weight: 800;
    }
    .premium-report .insight-positive .insight-icon {
      background: rgba(22,163,74,0.12);
      color: var(--color-success);
    }
    .premium-report .insight-warning .insight-icon {
      background: rgba(217,119,6,0.14);
      color: var(--color-warning);
    }
    .premium-report ul {
      margin: var(--space-sm) 0 0;
      padding-left: 18px;
      color: var(--color-text-secondary);
    }
    .premium-report li + li { margin-top: var(--space-xs); }
    .premium-report .main-signal {
      background: var(--color-accent-light);
      border-color: var(--color-accent);
    }
    .premium-report .main-signal strong {
      display: block;
      margin-top: var(--space-sm);
      font-size: 18px;
    }
    .premium-report .metric-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--space-md);
    }
    .premium-report .metriques-grid,
    .premium-report .secondary-metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .premium-report .metriques-grid,
    .premium-report .metrique-card {
      page-break-inside: avoid;
      break-inside: avoid;
    }
    .premium-report .metrique-card {
      padding: 16px 20px;
      border-radius: 10px;
    }
    .premium-report .synthese-texte {
      page-break-after: auto;
      break-after: auto;
    }
    .premium-report .synthese-metriques {
      page-break-before: auto;
      page-break-inside: avoid;
      break-before: auto;
      break-inside: avoid;
    }
    .premium-report .metric-card strong {
      display: block;
      margin-bottom: 4px;
      font-family: var(--font-display);
      font-size: 36px;
      font-weight: 800;
      line-height: 1;
    }
    .premium-report .metric-card span {
      display: block;
      color: var(--color-text-secondary);
      font-size: 12px;
      font-weight: 700;
      line-height: 1.4;
    }
    .premium-report .metric-card p {
      margin-top: 2px;
      color: var(--color-text-muted);
      font-size: 11px;
    }
    .premium-report .metric-muted strong,
    .premium-report .metric-muted span,
    .premium-report .metric-muted p {
      color: var(--color-text-muted);
    }
    .premium-report .metrique-card.is-zero .metrique-value,
    .premium-report .metrique-card.is-zero .metrique-label {
      color: var(--color-text-muted);
    }
    .premium-report .metrique-card.is-warning .metrique-value {
      color: var(--color-warning);
    }
    .premium-report .section-benchmark {
      align-content: start;
    }
    .premium-report .benchmark-intro {
      color: var(--color-text-secondary);
      max-width: 660px;
    }
    .premium-report .benchmark-table-wrapper {
      margin-top: var(--space-lg);
      overflow-x: auto;
    }
    .premium-report .benchmark-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .premium-report .benchmark-table th {
      background: var(--color-bg);
      border-bottom: 2px solid var(--color-border);
      color: var(--color-text-secondary);
      font-family: var(--font-body);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      padding: 10px 14px;
      text-align: left;
      text-transform: uppercase;
    }
    .premium-report .benchmark-table td {
      border-bottom: 1px solid var(--color-border);
      padding: 12px 14px;
      vertical-align: middle;
    }
    .premium-report .benchmark-row--vous td {
      background: var(--color-accent-light);
      font-weight: 500;
    }
    .premium-report .benchmark-vous-badge {
      display: inline-block;
      margin-left: 6px;
      border-radius: 4px;
      background: var(--color-accent);
      color: white;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.04em;
      line-height: 1.4;
      padding: 1px 6px;
      text-transform: uppercase;
    }
    .premium-report .benchmark-disclaimer {
      margin-top: var(--space-md);
      color: var(--color-text-muted);
      font-size: 11px;
      font-style: italic;
    }
    .premium-report .timeline {
      position: relative;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--space-lg);
    }
    .premium-report .timeline::before {
      content: "";
      position: absolute;
      top: 24px;
      left: 12%;
      right: 12%;
      height: 1px;
      background: var(--color-border);
    }
    .premium-report .timeline-step {
      position: relative;
      display: grid;
      gap: var(--space-md);
      justify-items: start;
      background: var(--color-bg);
      padding: var(--space-md);
      border-radius: 12px;
    }
    .premium-report .timeline-number {
      display: grid;
      place-items: center;
      width: 48px;
      height: 48px;
      border-radius: 999px;
      background: var(--color-border);
      color: var(--color-text-secondary);
      font-weight: 800;
      z-index: 1;
    }
    .premium-report .timeline-step.is-current .timeline-number {
      background: var(--color-accent);
      color: white;
    }
    .premium-report .timeline-step p:last-child {
      color: var(--color-text-secondary);
    }
    .premium-report .matrix-section {
      display: grid;
      gap: var(--space-md);
    }
    .premium-report .matrix-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--space-md);
    }
    .premium-report .matrix-quadrant {
      display: grid;
      gap: var(--space-md);
    }
    .premium-report .matrix-actions {
      display: grid;
      gap: var(--space-sm);
    }
    .premium-report .matrix-action {
      display: grid;
      gap: var(--space-sm);
      padding: var(--space-md);
      border-radius: 10px;
      background: var(--color-bg);
    }
    .premium-report .matrix-action p {
      display: flex;
      gap: var(--space-sm);
      flex-wrap: wrap;
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    .premium-report .matrice-note {
      font-size: 13px;
      color: var(--color-text-muted);
      font-style: italic;
      margin-top: var(--space-md);
      text-align: center;
    }
    .premium-report .empty-state {
      color: var(--color-text-secondary);
      padding: var(--space-lg);
      border: 1px dashed var(--color-border);
      border-radius: 12px;
    }
    .premium-report .priority-page-list {
      display: grid;
      gap: var(--space-lg);
    }
    .premium-report .pages-prioritaires-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-lg);
    }
    .premium-report .priority-page-card {
      display: grid;
      gap: var(--space-md);
      page-break-inside: avoid;
      break-inside: avoid;
    }
    .premium-report .fiche-page {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      padding: var(--space-lg);
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .premium-report .priority-card-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: var(--space-md);
      align-items: start;
    }
    .premium-report .muted-url {
      margin-top: var(--space-xs);
      overflow-wrap: anywhere;
      font-size: 13px;
    }
    .premium-report .priority-score-stack {
      display: grid;
      gap: var(--space-sm);
      justify-items: end;
    }
    .premium-report .page-tags,
    .premium-report .impact-effort-row {
      display: flex;
      gap: var(--space-sm);
      flex-wrap: wrap;
    }
    .premium-report .page-tags span,
    .premium-report .impact-effort-row span {
      background: var(--color-bg);
      color: var(--color-text-secondary);
    }
    .premium-report .fiche-meta-bas {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: var(--space-md);
      padding-top: var(--space-md);
      border-top: 1px solid var(--color-border);
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    .premium-report .fiche-effort-temps {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--color-accent);
      font-size: 13px;
      font-weight: 600;
      line-height: 1.35;
    }
    .premium-report .fiche-meta-icon {
      font-size: 16px;
      line-height: 1;
    }
    .premium-report .fiche-badges-ei {
      justify-content: flex-end;
    }
    .premium-report .fiche-maillage {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      margin-top: var(--space-sm);
      color: var(--color-text-secondary);
      flex-wrap: wrap;
    }
    .premium-report .fiche-maillage-icon {
      font-size: 14px;
      line-height: 1;
    }
    .premium-report .fiche-maillage-count {
      font-weight: 700;
      font-size: 13px;
    }
    .premium-report .fiche-maillage-alerte {
      color: var(--color-danger);
      font-weight: 600;
    }
    .premium-report .page-reason,
    .premium-report .recommended-action {
      display: grid;
      grid-template-columns: 28px minmax(0, 1fr);
      gap: var(--space-sm);
      padding: var(--space-md);
      border-radius: 10px;
    }
    .premium-report .page-reason {
      background: rgba(217,119,6,0.08);
    }
    .premium-report .recommended-action {
      background: var(--color-accent-light);
    }
    .premium-report .section-icon,
    .premium-report .recommended-action > span {
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 999px;
      background: white;
      color: var(--color-warning);
      font-weight: 800;
    }
    .premium-report .recommended-action > span {
      color: var(--color-accent);
    }
    .premium-report .rewrite-angle {
      padding: var(--space-md);
      border-radius: 10px;
      background: #F4F3F0;
      color: var(--color-text-secondary);
      font-style: italic;
    }
    .premium-report .section-perf,
    .premium-report .section-suggestions {
      break-before: page;
      page-break-before: always;
    }
    .premium-report .perf-intro {
      background: var(--color-bg);
      border-left: 3px solid var(--color-warning);
      border-radius: 0 8px 8px 0;
      padding: var(--space-md) var(--space-lg);
      margin: var(--space-lg) 0;
      font-size: 14px;
      line-height: 1.6;
    }
    .premium-report .perf-metrics {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: var(--space-md);
      margin-bottom: var(--space-xl);
    }
    .premium-report .perf-metric {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 10px;
      padding: var(--space-lg);
      text-align: center;
    }
    .premium-report .perf-metric-value {
      font-family: var(--font-display);
      font-size: 36px;
      font-weight: 800;
      line-height: 1;
      margin-bottom: 6px;
    }
    .premium-report .perf-metric-label {
      font-size: 12px;
      color: var(--color-text-muted);
    }
    .premium-report .perf-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      margin-bottom: var(--space-xl);
    }
    .premium-report .perf-table th {
      text-align: left;
      padding: 8px 12px;
      background: var(--color-bg);
      border-bottom: 2px solid var(--color-border);
      font-size: 10px;
      letter-spacing: 0.07em;
      text-transform: uppercase;
      color: var(--color-text-secondary);
    }
    .premium-report .perf-table td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--color-border);
      vertical-align: middle;
    }
    .premium-report .perf-url a {
      color: var(--color-text-primary);
      text-decoration: none;
      font-size: 12px;
      word-break: break-word;
    }
    .premium-report .perf-time {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 14px;
    }
    .premium-report .perf-badge {
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .premium-report .perf-badge--correct {
      background: #DCFCE7;
      color: #166534;
    }
    .premium-report .perf-badge--lent {
      background: #FEF3C7;
      color: #92400E;
    }
    .premium-report .perf-badge--critique {
      background: #FEE2E2;
      color: #991B1B;
    }
    .premium-report .perf-badge--inconnu {
      background: #F3F4F6;
      color: #6B7280;
    }
    .premium-report .score-unknown {
      color: var(--color-text-muted);
    }
    .premium-report .perf-redirect-warning {
      font-size: 11px;
      color: var(--color-warning);
      font-weight: 600;
    }
    .premium-report .perf-redirect-ok {
      color: var(--color-text-muted);
    }
    .premium-report .perf-actions {
      margin-top: var(--space-xl);
    }
    .premium-report .perf-actions-title {
      font-family: var(--font-display);
      font-size: 16px;
      font-weight: 700;
      margin-bottom: var(--space-lg);
    }
    .premium-report .perf-actions-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-md);
    }
    .premium-report .perf-action-card {
      display: flex;
      gap: var(--space-md);
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 10px;
      padding: var(--space-md);
      break-inside: avoid;
    }
    .premium-report .perf-action-icon {
      font-size: 24px;
      flex-shrink: 0;
      margin-top: 2px;
    }
    .premium-report .perf-action-title {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 14px;
      margin-bottom: 4px;
    }
    .premium-report .perf-action-text {
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.5;
      margin-bottom: 6px;
    }
    .premium-report .perf-action-effort {
      font-size: 11px;
      color: var(--color-text-muted);
      font-style: italic;
    }
    .premium-report .suggestions-intro {
      font-size: 14px;
      color: var(--color-text-secondary);
      line-height: 1.6;
      margin: var(--space-lg) 0;
    }
    .premium-report .suggestion-card {
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      padding: var(--space-lg);
      margin-bottom: var(--space-lg);
      break-inside: avoid;
    }
    .premium-report .suggestion-url {
      font-size: 12px;
      color: var(--color-text-muted);
      font-family: monospace;
      margin-bottom: var(--space-md);
      padding-bottom: var(--space-md);
      border-bottom: 1px solid var(--color-border);
      word-break: break-word;
    }
    .premium-report .suggestion-bloc {
      margin-bottom: var(--space-lg);
    }
    .premium-report .suggestion-bloc:last-child {
      margin-bottom: 0;
    }
    .premium-report .suggestion-bloc-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: var(--space-md);
      margin-bottom: var(--space-sm);
    }
    .premium-report .suggestion-type {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--color-text-secondary);
    }
    .premium-report .suggestion-longueur {
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .premium-report .suggestion-longueur--bad {
      font-size: 11px;
      font-weight: 700;
      color: var(--color-danger);
    }
    .premium-report .suggestion-longueur--ok {
      font-size: 11px;
      color: var(--color-success);
    }
    .premium-report .suggestion-actuel,
    .premium-report .suggestion-propose {
      display: flex;
      gap: var(--space-sm);
      align-items: flex-start;
      border-radius: 6px;
      padding: var(--space-sm) var(--space-md);
    }
    .premium-report .suggestion-actuel {
      background: #FEF2F2;
      margin-bottom: 6px;
    }
    .premium-report .suggestion-propose {
      background: #F0FDF4;
    }
    .premium-report .suggestion-label-actuel,
    .premium-report .suggestion-label-propose {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      flex-shrink: 0;
      margin-top: 2px;
      min-width: 44px;
    }
    .premium-report .suggestion-label-actuel {
      color: var(--color-danger);
    }
    .premium-report .suggestion-label-propose {
      color: var(--color-success);
    }
    .premium-report .suggestion-texte-actuel {
      font-size: 13px;
      color: #7F1D1D;
      line-height: 1.4;
      flex: 1;
    }
    .premium-report .suggestion-texte-propose {
      font-size: 13px;
      color: #14532D;
      line-height: 1.4;
      flex: 1;
      font-weight: 500;
    }
    .premium-report .suggestion-longueur-ok {
      font-size: 11px;
      color: var(--color-success);
      font-weight: 600;
      flex-shrink: 0;
      margin-top: 2px;
    }
    .premium-report .suggestion-explication {
      font-size: 11px;
      color: var(--color-text-muted);
      font-style: italic;
      margin-top: 6px;
      padding-left: var(--space-sm);
    }
    .premium-report .signal-check-list {
      display: grid;
      gap: var(--space-md);
    }
    .premium-report .signal-url-group {
      display: grid;
      gap: var(--space-sm);
      padding: var(--space-md);
      border-radius: 10px;
      background: var(--color-bg);
    }
    .premium-report .signal-url-group a {
      color: var(--color-text-primary);
      font-weight: 700;
      overflow-wrap: anywhere;
    }
    .premium-report .date-signal-lines {
      display: grid;
      gap: var(--space-xs);
    }
    .premium-report .date-signal-line {
      display: flex;
      align-items: center;
      gap: var(--space-xs);
      flex-wrap: wrap;
    }
    .premium-report .date-badge {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
      padding: 2px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      margin-right: 4px;
      margin-bottom: 4px;
    }
    .premium-report .date-badge--titre,
    .premium-report .date-titre {
      background: #FEF3C7;
      color: #92400E;
    }
    .premium-report .date-badge--url,
    .premium-report .date-url {
      background: #DBEAFE;
      color: #1E40AF;
    }
    .premium-report .date-badge--contenu,
    .premium-report .date-contenu {
      background: #F3F4F6;
      color: #374151;
    }
    .premium-report .date-values {
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    .premium-report .dates-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .premium-report .dates-table th {
      text-align: left;
      padding: 8px 12px;
      background: var(--color-bg);
      border-bottom: 2px solid var(--color-border);
      font-size: 10px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--color-text-secondary);
      font-family: var(--font-body);
    }
    .premium-report .dates-table td {
      padding: 8px 12px;
      border-bottom: 1px solid var(--color-border);
      vertical-align: middle;
    }
    .premium-report .dates-table tr:hover td {
      background: var(--color-bg);
    }
    .premium-report .dates-url {
      max-width: 280px;
      font-size: 12px;
      color: var(--color-text-secondary);
      word-break: break-word;
      white-space: normal;
    }
    .premium-report .dates-url a {
      color: var(--color-accent);
      text-decoration: none;
      word-break: inherit;
    }
    .premium-report .dates-cell {
      white-space: nowrap;
    }
    .premium-report .dates-empty {
      color: var(--color-text-muted);
      font-size: 12px;
    }
    .premium-report .opportunity-panel {
      display: grid;
      gap: var(--space-md);
      padding: var(--space-lg);
      background: var(--color-accent-light);
      border-left: 5px solid var(--color-accent);
      border-radius: 12px;
    }
    .premium-report .opportunity-item {
      display: grid;
      grid-template-columns: 28px minmax(0, 1fr);
      gap: var(--space-sm);
      align-items: start;
      padding: var(--space-md);
      background: rgba(255,255,255,0.72);
      border-radius: 10px;
    }
    .premium-report .opportunity-item span {
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 999px;
      background: var(--color-accent);
      color: white;
      font-weight: 800;
    }
    .premium-report .section-finale {
      align-content: start;
      gap: var(--space-lg);
    }
    .premium-report .finale-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-xl);
      margin-top: var(--space-md);
    }
    .premium-report .finale-col {
      display: grid;
      align-content: start;
      gap: var(--space-md);
    }
    .premium-report .opportunites-list {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: var(--space-md);
    }
    .premium-report .opportunite-item {
      display: flex;
      gap: var(--space-sm);
      align-items: flex-start;
      color: var(--color-text-secondary);
      font-size: 14px;
      line-height: 1.5;
    }
    .premium-report .opportunite-icon {
      color: var(--color-accent);
      font-weight: 700;
      font-size: 18px;
      line-height: 1.2;
      flex-shrink: 0;
    }
    .premium-report .etapes-list {
      padding-left: var(--space-lg);
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
      color: var(--color-text-secondary);
      font-size: 14px;
      line-height: 1.5;
    }
    .premium-report .cta-block {
      margin-top: var(--space-md);
      background: var(--color-accent);
      border-radius: 12px;
      padding: var(--space-lg);
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .premium-report .cta-question {
      color: white;
      font-size: 15px;
      font-weight: 600;
      margin: 0 0 var(--space-sm) 0;
    }
    .premium-report .cta-email {
      color: white;
      font-size: 14px;
      text-decoration: underline;
      opacity: 0.85;
    }
    .premium-report .offre-suivi {
      margin-top: var(--space-xl);
      padding-top: var(--space-xl);
      border-top: 1px solid var(--color-border);
    }
    .premium-report .offre-titre {
      margin-bottom: var(--space-lg);
      color: var(--color-text-muted);
      font-family: var(--font-display);
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.06em;
      line-height: 1.2;
      text-transform: uppercase;
    }
    .premium-report .offre-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--space-md);
    }
    .premium-report .offre-card {
      position: relative;
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      padding: var(--space-lg);
    }
    .premium-report .offre-card--featured {
      background: var(--color-surface);
      border-color: var(--color-accent);
      border-width: 2px;
    }
    .premium-report .offre-badge-featured {
      position: absolute;
      top: -10px;
      left: 50%;
      transform: translateX(-50%);
      background: var(--color-accent);
      color: white;
      border-radius: 20px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.04em;
      line-height: 1.4;
      padding: 2px 10px;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .premium-report .offre-nom {
      margin-bottom: var(--space-sm);
      font-family: var(--font-display);
      font-size: 16px;
      font-weight: 700;
      line-height: 1.25;
    }
    .premium-report .offre-prix {
      margin-bottom: var(--space-md);
      color: var(--color-accent);
      font-family: var(--font-display);
      font-size: 28px;
      font-weight: 800;
      line-height: 1.1;
    }
    .premium-report .offre-prix-periode {
      margin-left: 4px;
      color: var(--color-text-muted);
      font-size: 13px;
      font-weight: 400;
    }
    .premium-report .offre-features {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
      color: var(--color-text-secondary);
      font-size: 12px;
      line-height: 1.4;
    }
    .premium-report .offre-features li + li {
      margin-top: 0;
    }
    .premium-report .offre-features li::before {
      content: "✓ ";
      color: var(--color-success);
      font-weight: 700;
    }
    .premium-report .rapport-footer {
      margin-top: var(--space-xl);
      padding-top: var(--space-lg);
      border-top: 1px solid var(--color-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: var(--space-md);
      flex-wrap: wrap;
      font-size: 12px;
      color: var(--color-text-muted);
    }
    .premium-report .methode-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-2xl);
      margin-top: var(--space-xl);
    }
    .premium-report .methode-col {
      display: grid;
      align-content: start;
      gap: var(--space-lg);
    }
    .premium-report .methode-list {
      list-style: none;
      padding: 0;
      margin: 0 0 var(--space-xl);
      display: flex;
      flex-direction: column;
      gap: var(--space-md);
    }
    .premium-report .methode-list li {
      display: flex;
      gap: var(--space-sm);
      margin: 0;
      color: var(--color-text-primary);
      font-size: 14px;
      line-height: 1.5;
    }
    .premium-report .methode-bullet {
      color: var(--color-accent);
      font-weight: 700;
      flex-shrink: 0;
      margin-top: 1px;
    }
    .premium-report .methode-limites {
      background: var(--color-bg);
      border-radius: 10px;
      padding: var(--space-md);
      color: var(--color-text-secondary);
      font-size: 12px;
      line-height: 1.6;
    }
    .premium-report .methode-limites strong {
      display: block;
      margin-bottom: var(--space-sm);
      color: var(--color-text-muted);
      font-size: 11px;
      letter-spacing: 0.06em;
      line-height: 1.2;
      text-transform: uppercase;
    }
    .premium-report .analyste-card {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      padding: var(--space-lg);
    }
    .premium-report .analyste-photo,
    .premium-report .analyste-avatar {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .premium-report .analyste-photo {
      object-fit: cover;
    }
    .premium-report .analyste-avatar {
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--color-accent);
      color: white;
      font-family: var(--font-display);
      font-size: 24px;
      font-weight: 800;
    }
    .premium-report .analyste-nom {
      font-family: var(--font-display);
      font-size: 18px;
      font-weight: 700;
      line-height: 1.2;
    }
    .premium-report .analyste-titre {
      margin-top: 2px;
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    .premium-report .analyste-linkedin {
      display: inline-block;
      margin-top: var(--space-sm);
      color: var(--color-accent);
      font-size: 12px;
      text-decoration: none;
    }
    .premium-report .outil-card {
      background: var(--color-bg);
      border-radius: 10px;
      padding: var(--space-md);
    }
    .premium-report .outil-nom {
      font-family: var(--font-display);
      font-size: 15px;
      font-weight: 700;
      line-height: 1.25;
    }
    .premium-report .outil-description {
      margin-top: 2px;
      color: var(--color-text-secondary);
      font-size: 12px;
    }
    .premium-report .outil-meta {
      margin-top: var(--space-sm);
      color: var(--color-text-muted);
      font-size: 11px;
    }
    .premium-report .appendix-head {
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
    }
    .premium-report .annexe-actions {
      display: flex;
      justify-content: center;
      gap: var(--space-sm);
      flex-wrap: wrap;
      padding: var(--space-xl) 0 0;
    }
    .premium-report .annexe-toggle {
      border: 0;
      border-radius: 8px;
      padding: 10px 14px;
      background: var(--color-text-primary);
      color: white;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }
    .premium-report .annexe-body {
      display: grid;
      gap: var(--space-md);
    }
    .premium-report .annexe-body[hidden] { display: none; }
    .premium-report .method-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: var(--space-md);
    }
    .premium-report .method-card span {
      display: block;
      color: var(--color-text-muted);
      font-size: 12px;
      font-weight: 700;
    }
    .premium-report .method-card strong {
      display: block;
      margin-top: var(--space-sm);
      overflow-wrap: anywhere;
    }
    .premium-report .technical-table-wrap {
      overflow: auto;
      border: 1px solid var(--color-border);
      border-radius: 12px;
      background: var(--color-surface);
    }
    .premium-report .technical-table {
      width: 100%;
      min-width: 880px;
      border-collapse: collapse;
      font-size: 13px;
    }
    .premium-report .annexe-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .premium-report .annexe-table th {
      text-align: left;
      padding: 8px 12px;
      background: var(--color-bg);
      border-bottom: 2px solid var(--color-border);
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--color-text-secondary);
    }
    .premium-report .annexe-table td {
      padding: 8px 12px;
      border-bottom: 1px solid var(--color-border);
      vertical-align: top;
    }
    .premium-report .annexe-table tr:hover td {
      background: var(--color-bg);
    }
    .premium-report .points-releves {
      color: var(--color-text-secondary);
      font-size: 12px;
      max-width: 300px;
    }
    .premium-report th,
    .premium-report td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--color-border);
      text-align: left;
      vertical-align: top;
    }
    .premium-report th {
      color: var(--color-text-muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .premium-report td:first-child {
      overflow-wrap: anywhere;
    }
    .premium-report .next-actions {
      margin: 0;
      padding-left: 22px;
      color: var(--color-text-secondary);
      font-weight: 600;
    }
    .premium-report .next-actions li + li {
      margin-top: var(--space-sm);
    }
    .premium-report .final-cta {
      display: grid;
      gap: var(--space-md);
      justify-items: start;
      padding: var(--space-xl);
      border-radius: 14px;
      background: var(--color-accent);
      color: white;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .premium-report .final-cta a {
      display: inline-flex;
      border-radius: 8px;
      padding: 10px 14px;
      background: white;
      color: var(--color-accent);
      font-weight: 800;
      text-decoration: none;
    }
    .premium-report .signature {
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    @page {
      size: A4;
      margin: 15mm;
    }
    @media print {
      .report-document {
        background: #ffffff !important;
      }
      .premium-report {
        max-width: none;
        padding: 0;
        background: #ffffff !important;
      }
      .premium-report section {
        break-before: avoid;
        page-break-before: avoid;
      }
      .premium-report .report-page {
        min-height: auto;
        padding: 0 0 18px;
        page-break-before: avoid;
        break-before: avoid;
      }
      .premium-report .report-page-cover {
        page-break-before: auto;
        break-before: auto;
      }
      .premium-report .section-label {
        break-before: page;
        page-break-before: always;
        margin-top: 0;
        padding-top: 0;
      }
      .premium-report .section-label + * {
        break-before: avoid;
        page-break-before: avoid;
      }
      .premium-report .timeline,
      .premium-report .matrix-grid,
      .premium-report .method-grid {
        grid-template-columns: 1fr !important;
      }
      .premium-report .metriques-grid,
      .premium-report .secondary-metrics {
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
        gap: 8px;
      }
      .premium-report .metrique-card {
        padding: 12px 16px;
      }
      .premium-report .metrique-value {
        font-size: 28px;
      }
      .premium-report .dirigeant-card {
        padding: var(--space-lg);
        border-width: 1.5px;
      }
      .premium-report .dirigeant-trois-colonnes {
        gap: var(--space-md);
      }
      .premium-report .dirigeant-phrase {
        font-size: 14px;
      }
      .premium-report .pages-prioritaires-grid {
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }
      .premium-report .fiche-page {
        padding: 16px;
        break-inside: avoid;
        page-break-inside: avoid;
        font-size: 12px;
      }
      .premium-report .fiche-page h3 {
        font-size: 14px;
      }
      .premium-report .fiche-page .fiche-url {
        font-size: 10px;
      }
      .premium-report .fiche-section-label {
        font-size: 9px;
        letter-spacing: 0.08em;
      }
      .premium-report .finale-grid {
        grid-template-columns: 1fr 1fr;
        gap: var(--space-lg);
        margin-top: var(--space-lg);
      }
      .premium-report .section-finale {
        page-break-inside: avoid;
        break-inside: avoid;
      }
      .premium-report .cta-block {
        padding: var(--space-md);
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }
      .premium-report .rapport-footer {
        margin-top: var(--space-lg);
      }
      .premium-report .offre-suivi {
        display: none !important;
      }
      .premium-report .perf-actions-grid {
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .premium-report .perf-action-card {
        padding: 10px;
      }
      .premium-report .perf-action-text {
        font-size: 11px;
      }
      .premium-report .suggestion-card {
        padding: var(--space-md);
      }
      .premium-report .suggestion-texte-actuel,
      .premium-report .suggestion-texte-propose {
        font-size: 12px;
      }
      .premium-report .dates-table {
        font-size: 11px;
      }
      .premium-report .dates-table td,
      .premium-report .dates-table th {
        padding: 6px 8px;
      }
      .premium-report .card,
      .premium-report .priority-page-card,
      .premium-report .metric-card,
      .premium-report .metriques-grid,
      .premium-report .metrique-card,
      .premium-report .matrix-quadrant,
      .premium-report .matrix-action {
        page-break-inside: avoid;
        break-inside: avoid;
      }
      .premium-report .synthese {
        page-break-inside: avoid;
        break-inside: avoid;
      }
      .premium-report .synthese-texte {
        page-break-after: auto;
        break-after: auto;
      }
      .premium-report .synthese-metriques {
        page-break-before: auto;
        page-break-inside: avoid;
        break-before: auto;
        break-inside: avoid;
      }
      .premium-report .annexe,
      .premium-report .annexe-actions,
      .premium-report .annexe-toggle,
      .premium-report button {
        display: none !important;
      }
      .print-with-annexe .premium-report .annexe {
        display: grid !important;
      }
      .premium-report .card,
      .premium-report .timeline-step,
      .premium-report .matrix-action,
      .premium-report .signal-url-group,
      .premium-report .perf-action-card,
      .premium-report .rewrite-angle,
      .premium-report .page-reason,
      .premium-report .recommended-action,
      .premium-report .opportunity-item {
        background: #ffffff !important;
        box-shadow: none !important;
      }
      .premium-report .cover-page,
      .premium-report .final-cta,
      .premium-report .cta-block {
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }
    }
    @media (max-width: 820px) {
      .premium-report {
        padding: var(--space-md);
      }
      .premium-report h1 {
        font-size: 42px;
      }
      .premium-report .executive-grid,
      .premium-report .metric-grid,
      .premium-report .timeline,
      .premium-report .matrix-grid,
      .premium-report .priority-card-head,
      .premium-report .secondary-metrics,
      .premium-report .dirigeant-trois-colonnes,
      .premium-report .offre-grid,
      .premium-report .perf-metrics,
      .premium-report .perf-actions-grid,
      .premium-report .methode-grid,
      .premium-report .method-grid,
      .premium-report .appendix-head {
        grid-template-columns: 1fr;
      }
      .premium-report .suggestion-bloc-header,
      .premium-report .suggestion-actuel,
      .premium-report .suggestion-propose {
        flex-direction: column;
        align-items: flex-start;
      }
      .premium-report .dirigeant-header,
      .premium-report .analyste-card {
        flex-direction: column;
      }
      .premium-report .priority-score-stack {
        justify-items: start;
      }
      .premium-report .timeline::before {
        display: none;
      }
    }
    """
