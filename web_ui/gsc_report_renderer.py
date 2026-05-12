"""Boutique-consulting GSC report renderer (v2 design).

Entry point: render_gsc_report(report, lang="fr") -> str
All helper functions delegate back to gsc.py to avoid duplication.
"""
from __future__ import annotations

import html as _html
import sys
from pathlib import Path

# Ensure project root is importable when this module is loaded from web_ui/
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from gsc import (  # noqa: E402
    client_display_value,
    compact_url_for_display,
    confidence_label,
    display_query_label,
    filter_button,
    format_position_value,
    gsc_gettext,
    is_resolvable_target,
    metric_state_class,
    page_priority_class,
    parse_position_value,
    position_bar_color,
    position_fill_width,
    priority_display_label,
    render_action_plan_section,
    render_annex_links,
    render_cannibalization_groups_section,
    render_empty_state,
    render_methodology_section,
    render_snippet_section,
    sanitize_gsc_language,
    translate_estimated_gain_value,
    translate_period_label,
)

from .gsc_report_styles import GSC_REPORT_STYLE


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------

def _render_toolbar(report: dict) -> str:
    active_lang = sanitize_gsc_language(str(report.get("lang") or "fr"))
    language_paths = report.get("language_paths")
    paths = language_paths if isinstance(language_paths, dict) else {}
    buttons = []
    for lang, label in (("fr", "FR"), ("en", "EN")):
        target = str(paths.get(lang) or report.get("html_output_path") or "")
        href = f"/files?path={_html.escape(target)}" if target else "#"
        active_class = " is-active" if lang == active_lang else ""
        aria_current = ' aria-current="true"' if lang == active_lang else ""
        buttons.append(
            f'<a class="report-toolbar-button language-toggle{active_class}" '
            f'href="{_html.escape(href)}"{aria_current}>{label}</a>'
        )
    _ = gsc_gettext(active_lang)
    export_label = _("Exporter en PDF")
    dashboard_label = _("Retour dashboard")
    return (
        '<div class="report-toolbar no-print">'
        f'<button class="report-toolbar-button" type="button" onclick="exportPDF()">'
        f"{_html.escape(export_label)}</button>"
        f'<span class="language-toggle-group">{"".join(buttons)}</span>'
        f'<a class="report-toolbar-button" href="./">{_html.escape(dashboard_label)}</a>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _render_kpi_card(kpi: dict, lang: str = "fr") -> str:
    from gsc import strip_accents
    _ = gsc_gettext(lang)
    label = str(kpi.get("label", ""))
    value = translate_estimated_gain_value(kpi.get("value", ""), lang)
    label_lower = strip_accents(label).lower()
    classes = ["kpi-card"]
    note = ""
    if "ctr" in label_lower or "taux de clic" in label_lower:
        classes.append("kpi-card--warning")
        note = f"<div class='kpi-note'>{_html.escape(_('À surveiller selon la position moyenne'))}</div>"
    elif "prioritaires" in label_lower:
        classes.append("kpi-card--accent")
    elif "recuperables" in label_lower or "gain" in label_lower or "potentiel" in label_lower or value.startswith("+"):
        classes.append("kpi-card--positive")
        note = f"<div class='kpi-note'>{_html.escape(_('estimation qualifiée'))}</div>"
    return (
        f"<div class='{' '.join(classes)}'>"
        f"<div class='kpi-label'>{_html.escape(_(label))}</div>"
        f"<div class='kpi-value'>{_html.escape(value)}</div>"
        f"{note}"
        "</div>"
    )


def _render_estimate_box(report: dict, lang: str = "fr") -> str:
    _ = gsc_gettext(lang)
    value = translate_estimated_gain_value(report.get("estimated_gain_value") or "", lang)
    note = _(str(report.get("estimated_gain_note") or ""))
    if not value and not note:
        return ""
    explanation = _("selon comparaison CTR à position équivalente")
    return (
        "<div class='estimate-box'>"
        f"<strong>{_html.escape(_('Potentiel théorique détecté :'))} {_html.escape(value)}, "
        f"{_html.escape(explanation)}.</strong>"
        f"<p>{_html.escape(note)}</p>"
        "</div>"
    )


def _render_position_bar(position: float, lang: str = "fr") -> str:
    _ = gsc_gettext(lang)
    pos_width = position_fill_width(position)
    pos_color = position_bar_color(position)
    return (
        '<div class="position-bar">'
        f'<div class="position-bar-label">{_html.escape(_("Position actuelle dans Google"))}</div>'
        '<div class="position-bar-track">'
        f'<div class="position-bar-fill" data-position-width="{pos_width:.0f}" '
        f'style="width: 0%; --print-position-width: {pos_width:.0f}%; background: {pos_color}"></div>'
        "</div>"
        f'<span class="position-bar-value">{_html.escape(format_position_value(position))}</span>'
        "</div>"
    )


def _render_data_item(label: str, value: object, lang: str = "fr", *, translate_value: bool = True) -> str:
    _ = gsc_gettext(lang)
    display_value = _(str(value)) if translate_value else str(value)
    return (
        "<div class='data-item'>"
        f"<span class='data-label'>{_html.escape(_(label))}</span>"
        f"<span class='data-value'>{_html.escape(display_value)}</span>"
        "</div>"
    )


def _render_monthly_priorities(items: list, lang: str = "fr") -> str:
    if not items:
        return render_empty_state(lang=lang)
    _ = gsc_gettext(lang)
    cards = []
    for index, item in enumerate(items[:3], start=1):
        cards.append(
            "<article class='priority-item'>"
            f"<div class='priority-number'>{index:02d}</div>"
            "<div class='priority-body'>"
            f"<h3>{_html.escape(_(item.get('title', '')))}</h3>"
            "<div class='priority-meta'>"
            f"<span class='priority-why'><strong>{_html.escape(_('Pourquoi :'))}</strong> "
            f"{_html.escape(_(item.get('why', '')))}</span>"
            f"<span class='priority-action'><strong>{_html.escape(_('Action :'))}</strong> "
            f"{_html.escape(_(item.get('action', '')))}</span>"
            f"<span class='priority-impact'><strong>{_html.escape(_('Impact :'))}</strong> "
            f"{_html.escape(_(item.get('impact', '')))}</span>"
            "</div></div></article>"
        )
    return f"<div class='priorities-list'>{''.join(cards)}</div>"


def _render_client_page_card(page: dict, lang: str = "fr") -> str:
    _ = gsc_gettext(lang)
    position = parse_position_value(dict(page.get("metrics", {})).get("Position", ""))
    priority_class = page_priority_class(str(page.get("priority", "p3")))
    url = str(page.get("url", ""))
    url_label = compact_url_for_display(url)
    metrics = "".join(
        f"<div class='metric {metric_state_class(str(lbl))}'>"
        f"<span class='metric-label'>{_html.escape(_(str(lbl)))}</span>"
        f"<span class='metric-value'>{_html.escape(translate_estimated_gain_value(val, lang))}</span>"
        "</div>"
        for lbl, val in dict(page.get("metrics", {})).items()
    )
    action_labels = "".join(
        f"<span class='type-tag'>{_html.escape(_(str(lbl)))}</span>"
        for lbl in page.get("action_type_labels", [])
    )
    business = (
        f"<div class='insight'><span class='mini-label'>{_html.escape(_('Valeur business'))}</span>"
        f"<strong>{_html.escape(_(client_display_value(page.get('business_value', ''), lang)))} · "
        f"{_html.escape(_(client_display_value(page.get('monetization_possible', ''), lang)))}</strong></div>"
    )
    recommendation = (
        f"<div class='page-constat'><span class='constat-label'>"
        f"{_html.escape(_('Action recommandée spécifique'))}</span>"
        f"{_html.escape(_(str(page.get('recommendation', ''))))}</div>"
        if page.get("recommendation")
        else ""
    )
    target_metric_block = ""
    target_metric = str(page.get("target_metric", ""))
    if target_metric:
        target_metric_block = (
            f"<div class='target-metric-box'>"
            f"<span class='target-metric-label'>{_html.escape(_('Objectif mesurable'))}</span>"
            f"{_html.escape(target_metric)}"
            "</div>"
        )
    serp_block = ""
    if str(page.get("serp_anomaly", "")) == "serp_features_suspected":
        _serp_msg = _(
            "Le CTR est anormalement bas pour cette position. "
            "Des features SERP (featured snippet, Knowledge Panel, annonces) captent probablement une partie des clics. "
            "Vérifier la SERP avant d'optimiser le titre seul."
        )
        serp_block = (
            "<div class='serp-warning'>"
            f"<span class='serp-warning-label'>"
            f"{_html.escape(_('Attention : SERP enrichie suspectée'))}</span>"
            f"{_html.escape(_serp_msg)}"
            "</div>"
        )
    return (
        f'<article class="page-card page-card--{priority_class}" data-priority="{_html.escape(priority_class)}">'
        '<div class="page-card-header">'
        '<div class="page-info">'
        f'<span class="page-slug">{_html.escape(str(page.get("slug", "")))}</span>'
        f'<a class="page-url" href="{_html.escape(url)}" title="{_html.escape(url)}">'
        f"{_html.escape(url_label)} ↗</a>"
        "</div>"
        f'<span class="priority-badge priority-badge--{priority_class}">'
        f"{_html.escape(_(priority_display_label(str(page.get('priority', 'p3')), str(page.get('priority_label', '')))))}"
        "</span>"
        "</div>"
        f'<div class="page-metrics">{metrics}</div>'
        f"{_render_position_bar(position, lang)}"
        f'<div class="page-constat"><span class="constat-label">{_html.escape(_("Constat"))}</span>'
        f"{_html.escape(_(str(page.get('diagnostic', ''))))}</div>"
        f"{recommendation}"
        '<div class="insight-grid">'
        f'<div class="insight"><span class="mini-label">{_html.escape(_("Effort estimé"))}</span>'
        f"<strong>{_html.escape(_(str(page.get('effort', ''))))}</strong></div>"
        f"{business}"
        f'<div class="insight"><span class="mini-label">{_html.escape(_("Type d\'action"))}</span>'
        f'<div class="chip-row">{action_labels}</div></div>'
        f'<div class="insight"><span class="mini-label">{_html.escape(_("Impact attendu"))}</span>'
        f"<strong>{_html.escape(_(str(page.get('impact', ''))))}</strong></div>"
        "</div>"
        f"{target_metric_block}"
        f"{serp_block}"
        "</article>"
    )


def _render_priority_page_cards(pages: list, lang: str = "fr") -> str:
    if not pages:
        return render_empty_state(lang=lang)
    return f"<div class='cards-grid'>{''.join(_render_client_page_card(p, lang) for p in pages)}</div>"


def _render_filter_bar(section_id: str, lang: str = "fr") -> str:
    _ = gsc_gettext(lang)
    priorities = [("all", _("Toutes")), ("high", _("Haute")), ("medium", _("Moyenne")), ("low", _("Faible"))]
    priority_buttons = "".join(
        filter_button(section_id, "priority", value, label, active=value == "all")
        for value, label in priorities
    )
    return (
        '<div class="filter-bar">'
        f'<div class="filter-group"><span class="filter-label">{_("Urgence")}</span>'
        f"{priority_buttons}</div>"
        "</div>"
    )


def _render_summary_links(lang: str = "fr") -> str:
    _ = gsc_gettext(lang)
    links = [
        ("pages-prioritaires", "Pages"),
        ("snippets", "Résultats Google"),
        ("business", "Business"),
    ]
    return (
        "<div class='summary-links'>"
        + "".join(
            f"<a class='summary-link' href='#{_html.escape(a)}'>{_html.escape(_(lbl))}</a>"
            for a, lbl in links
        )
        + "</div>"
    )


def _render_business_section(pages: list, lang: str = "fr") -> str:
    if not pages:
        return render_empty_state(
            "Toutes les pages business à fort potentiel sont déjà traitées dans le Top prioritaire ci-dessus. "
            "Voir opportunities_full_export.csv pour la liste complète.",
            lang,
        )
    _ = gsc_gettext(lang)
    if len(pages) < 3:
        note = _html.escape(
            "Pages business hors top prioritaire — à intégrer en relais des actions du top prioritaire. "
            f"({len(pages)} page{'s' if len(pages) > 1 else ''} — les autres sont déjà dans le Top prioritaire.)"
        )
    else:
        note = _html.escape(
            "Pages business hors top prioritaire — à intégrer en relais des actions du top prioritaire."
        )
    rows = []
    for page in pages[:10]:
        action = (
            ", ".join(_(str(lbl)) for lbl in page.get("action_type_labels", []))
            if isinstance(page.get("action_type_labels"), list)
            else ""
        )
        page_url = str(page.get("url", ""))
        rows.append(
            "<tr>"
            f"<td class='url-cell'><a href='{_html.escape(page_url)}' title='{_html.escape(page_url)}'>"
            f"{_html.escape(str(page.get('slug', '')))}</a></td>"
            f"<td>{_html.escape(_(client_display_value(page.get('business_value', ''), lang)))}</td>"
            f"<td>{_html.escape(_(client_display_value(page.get('monetization_possible', ''), lang)))}</td>"
            f"<td>{_html.escape(str(page.get('opportunity_score', '')))}</td>"
            f"<td>{_html.escape(display_query_label(page.get('main_query', '')))}</td>"
            f"<td>{_html.escape(action)}</td>"
            f"<td>{_html.escape(_(str(page.get('recommendation', ''))))}</td>"
            "</tr>"
        )
    return (
        f"<p class='reliability-note' style='margin-bottom:10px;'>{note}</p>"
        "<table class='compact-table'><thead><tr>"
        f"<th>Page</th><th>{_html.escape(_('Valeur'))}</th><th>{_html.escape(_('Monétisation'))}</th>"
        f"<th>{_html.escape(_('Score'))}</th><th>{_html.escape(_('Requête'))}</th>"
        f"<th>{_html.escape(_('Action'))}</th><th>{_html.escape(_('Recommandation'))}</th>"
        "</tr></thead><tbody>"
        f"{''.join(rows)}"
        "</tbody></table>"
    )


def _render_executive_query_opportunities(rows: list, lang: str = "fr") -> str:
    if not rows:
        return render_empty_state(
            "Export Requêtes non fourni ou aucune requête exploitable détectée.", lang
        )
    _ = gsc_gettext(lang)
    table_rows = []
    for row in rows[:20]:
        target_url = str(row.get("target_url", "") or "")
        if not is_resolvable_target(target_url):
            continue
        from gsc import resolve_target_label
        target_label = resolve_target_label(target_url)
        top_queries = str(row.get("top_queries") or row.get("query") or "")
        queries_count = row.get("queries_count", 1)
        table_rows.append(
            "<tr>"
            f"<td>{_html.escape(_(str(row.get('recommendation', ''))))}</td>"
            f"<td class='url-cell'><a href='{_html.escape(target_url)}' title='{_html.escape(target_url)}'>"
            f"{_html.escape(target_label)}</a></td>"
            f"<td>{_html.escape(top_queries)}</td>"
            f"<td style='text-align:center'>{_html.escape(str(queries_count))}</td>"
            f"<td>{_html.escape(str(row.get('clicks', '')))}</td>"
            f"<td>{_html.escape(str(row.get('impressions', '')))}</td>"
            f"<td>{_html.escape(str(row.get('ctr', '')))}</td>"
            f"<td>{_html.escape(str(row.get('position', '')))}</td>"
            "</tr>"
        )
    if not table_rows:
        return render_empty_state(
            "Export Requêtes non fourni ou aucune requête exploitable détectée.", lang
        )
    return (
        "<table class='compact-table'><thead><tr>"
        f"<th>{_html.escape(_('Action'))}</th><th>{_html.escape(_('URL cible'))}</th>"
        f"<th>{_html.escape(_('Requêtes principales'))}</th><th>{_html.escape(_('Nb'))}</th>"
        f"<th>{_html.escape(_('Clics'))}</th><th>{_html.escape(_('Impr.'))}</th>"
        f"<th>{_html.escape(_('CTR'))}</th><th>{_html.escape(_('Pos.'))}</th>"
        "</tr></thead><tbody>"
        f"{''.join(table_rows)}"
        "</tbody></table>"
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_gsc_report(report: dict, *, lang: str = "fr") -> str:
    """Render the boutique-consulting GSC opportunity report as a standalone HTML document."""
    active_lang = sanitize_gsc_language(str(report.get("lang") or lang))
    _ = gsc_gettext(active_lang)

    toolbar = _render_toolbar(report)
    title = str(report.get("title", _("Rapport d'opportunités SEO")))
    site_name = _html.escape(str(report.get("site_name") or _("Non précisé")))
    period_label = _html.escape(
        translate_period_label(report.get("period_label", ""), active_lang)
        .removeprefix(_("Période analysée: "))
    )
    generated_at = _html.escape(str(report.get("generated_at") or ""))
    report_num = _html.escape(str(report.get("generated_at") or "")[:10] or "")
    mode_label = _(str(report.get("report_mode_label") or "Analyse de la période actuelle"))

    kpis = "".join(_render_kpi_card(kpi, active_lang) for kpi in report.get("kpis", []))
    estimate_box = _render_estimate_box(report, active_lang)
    priorities = _render_monthly_priorities(report.get("monthly_priorities", []), active_lang)
    priority_cards = _render_priority_page_cards(report.get("priority_pages", []), active_lang)
    queries = _render_executive_query_opportunities(
        report.get("top_query_opportunities", []), active_lang
    )
    snippets = render_snippet_section(
        report.get("snippet_pages", []),
        str(report.get("snippet_section_note") or ""),
        active_lang,
    )
    business = _render_business_section(report.get("business_opportunities", []), active_lang)
    cannibalization = render_cannibalization_groups_section(
        report.get("cannibalization_groups", []),
        active_lang,
        url_variant_pairs=report.get("url_variant_pairs", []),
    )
    annexes = render_annex_links(report.get("annex_files", []), active_lang)
    action_plan = render_action_plan_section(active_lang, report.get("action_plan_30_days") or None)
    methodology = render_methodology_section(
        str(report.get("report_mode") or "current_period_only"), active_lang
    )

    nav_items = [
        ("synthese", "Synthèse"),
        ("decision-rapide", "Décision rapide"),
        ("priorites", "Priorités"),
        ("pages-prioritaires", "Pages"),
        ("requetes", "Requêtes"),
        ("snippets", "Résultats Google"),
        ("cannibalisation", "Pages en concurrence"),
        ("business", "Business"),
        ("plan", "30 jours"),
        ("methodologie", "Méthode"),
    ]
    nav = "".join(
        f"<a href='#{anchor}'>{_html.escape(_(label))}</a>"
        for anchor, label in nav_items
    )

    n_priority = len(list(report.get("priority_pages") or []))

    return f"""<!DOCTYPE html>
<html lang="{_html.escape(active_lang)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_html.escape(_(title))}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,300;1,9..144,400;1,9..144,500;1,9..144,600&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>{GSC_REPORT_STYLE}</style>
</head>
<body>
  {toolbar}
  <nav class="gsc-nav no-print" aria-label="{_html.escape(_('Navigation du rapport'))}">{nav}</nav>
  <div class="doc">
    <section class="page cover no-running">
      <header class="cover-mast">
        <div class="wordmark">
          <span class="glyph"></span>
          <span>Prospect <em>Machine</em></span>
        </div>
        <div class="ref-block">
          <strong>{_html.escape(_("RAPPORT N°"))} {report_num}</strong><br>
          {_html.escape(mode_label)}<br>
          {_html.escape(_("Préparé pour"))} {site_name}
        </div>
      </header>
      <div class="cover-body">
        <p class="cover-cat">
          <span>{_html.escape(_("Opportunités SEO"))}</span>
          <span class="dot">·</span>
          <span>{_html.escape(_("Google Search Console"))}</span>
          <span class="dot">·</span>
          <span>{period_label}</span>
        </p>
        <h1 class="cover-title display">{site_name}</h1>
        <p class="cover-tag">{_html.escape(_("Rapport d'opportunités SEO — analyse des pages à fort potentiel de clic non capté."))}</p>
        {estimate_box}
      </div>
      <footer class="cover-foot">
        <div><span class="lbl">{_html.escape(_("Client"))}</span><strong>{site_name}</strong></div>
        <div><span class="lbl">{_html.escape(_("Période d'analyse"))}</span><strong>{period_label}</strong></div>
        <div><span class="lbl">{_html.escape(_("Émis le"))}</span><strong>{generated_at}</strong></div>
        <div><span class="lbl">{_html.escape(_("Préparé par"))}</span><strong>Prospect Machine</strong></div>
      </footer>
    </section>

    <section class="page">
      <div class="runhead"><span class="mark">Prospect Machine</span><span>{_html.escape(_("Synthèse exécutive"))}</span></div>
      <div class="section-header">
        <p class="eyebrow"><span class="num">I.</span> {_html.escape(_("Synthèse"))}</p>
        <h2 class="section-title">{_html.escape(_("Les chiffres qui comptent."))}</h2>
        <p class="lede">{_html.escape(_("Les chiffres et décisions à retenir avant l'exécution."))}</p>
      </div>
      <section class="kpi-grid" id="synthese">{kpis}</section>
      <div class="executive-summary"><p>{_html.escape(_(str(report.get("executive_summary", ""))))}</p></div>
      {_render_summary_links(active_lang)}
      <div class="pagenum"><span class="mark">{site_name}</span><span class="num"><em>p.</em> 02</span></div>
    </section>

    <section class="page">
      <div class="runhead"><span class="mark">Prospect Machine</span><span>{_html.escape(_("Décision rapide"))}</span></div>
      <div class="section-header" id="decision-rapide">
        <p class="eyebrow"><span class="num">II.</span> {_html.escape(_("Décision rapide"))}</p>
        <h2 class="section-title">{_html.escape(_("Les 3 priorités du mois."))}</h2>
      </div>
      {priorities}
      <div class="pagenum"><span class="mark">{site_name}</span><span class="num"><em>p.</em> 03</span></div>
    </section>

    <section class="page" id="pages-prioritaires">
      <div class="runhead"><span class="mark">Prospect Machine</span><span>{_html.escape(_("Pages prioritaires"))}</span></div>
      <div class="section-header">
        <p class="eyebrow"><span class="num">III.</span> {_html.escape(_("Pages prioritaires"))}</p>
        <h2 class="section-title">{_html.escape(_(str(n_priority) + " pages prioritaires."))}</h2>
        <p class="lede">{_html.escape(_("Maximum 10 pages dans le PDF principal, classées par potentiel SEO et valeur business."))}</p>
      </div>
      {_render_filter_bar("pages-prioritaires", active_lang)}
      {priority_cards}
      <div class="pagenum"><span class="mark">{site_name}</span><span class="num"><em>p.</em> 04</span></div>
    </section>

    <section class="page" id="requetes">
      <div class="runhead"><span class="mark">Prospect Machine</span><span>{_html.escape(_("Requêtes exploitables"))}</span></div>
      <div class="section-header">
        <p class="eyebrow"><span class="num">IV.</span> {_html.escape(_("Requêtes exploitables"))}</p>
        <h2 class="section-title">{_html.escape(_("Top opportunités requêtes."))}</h2>
        <p class="lede">{_html.escape(_("Regroupées par URL cible et action. Les requêtes brutes complètes sont dans queries_full_export.csv."))}</p>
      </div>
      {queries}
      <div class="pagenum"><span class="mark">{site_name}</span><span class="num"><em>p.</em> 05</span></div>
    </section>

    {snippets}
    {cannibalization}

    <section class="page" id="business">
      <div class="runhead"><span class="mark">Prospect Machine</span><span>{_html.escape(_("Opportunités business"))}</span></div>
      <div class="section-header">
        <p class="eyebrow"><span class="num">VI.</span> {_html.escape(_("Opportunités business"))}</p>
        <h2 class="section-title">{_html.escape(_("Pages à intention business."))}</h2>
        <p class="lede">{_html.escape(_("Pages à forte valeur business : équipement, comparatifs, tests, affiliation, prospects ou produits numériques."))}</p>
      </div>
      {business}
      <div class="pagenum"><span class="mark">{site_name}</span><span class="num"><em>p.</em> 07</span></div>
    </section>

    {action_plan}
    {methodology}
    {annexes}
  </div>
  <script>
    function exportPDF() {{
      var original = document.title;
      document.title = 'GSC_Opportunity_Report_' + new Date().toISOString().slice(0,10);
      document.fonts.ready.then(function() {{
        window.print();
        document.title = original;
      }});
    }}
    document.addEventListener('DOMContentLoaded', function() {{
      document.querySelectorAll('.position-bar-fill').forEach(function(bar, index) {{
        bar.style.transitionDelay = (index * 80) + 'ms';
        requestAnimationFrame(function() {{
          bar.style.width = (bar.dataset.positionWidth || '0') + '%';
        }});
      }});
      document.querySelectorAll('.filter-btn[data-filter-kind="priority"]').forEach(function(button) {{
        button.addEventListener('click', function() {{
          var section = document.getElementById(button.dataset.section || '');
          if (!section) return;
          var value = button.dataset.filterValue || 'all';
          section.querySelectorAll('.filter-btn[data-filter-kind="priority"]').forEach(function(peer) {{
            peer.classList.toggle('is-active', peer === button);
          }});
          section.querySelectorAll('.page-card, .snippet-card').forEach(function(card) {{
            card.classList.toggle('is-filtered-out', value !== 'all' && card.dataset.priority !== value);
          }});
        }});
      }});
    }});
  </script>
  <div class="print-footer">{_html.escape(_("Rapport d'opportunités GSC"))} · {site_name} · {generated_at}</div>
</body>
</html>"""
