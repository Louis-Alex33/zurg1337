"""Boutique-consulting GSC report renderer.

This module is intentionally presentation-only: it receives the report dict
already produced by gsc.py and projects that data into the v2 handoff design.
"""
from __future__ import annotations

import html as _html
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from ctr_benchmarks import ctr_median, ctr_p75  # noqa: E402
from gsc import (  # noqa: E402
    client_display_value,
    compact_url_for_display,
    display_query_label,
    format_number,
    format_percent,
    gsc_gettext,
    is_resolvable_target,
    page_priority_class,
    parse_position_value,
    priority_display_label,
    resolve_target_label,
    sanitize_gsc_language,
    translate_estimated_gain_value,
    translate_period_label,
)

from .gsc_report_styles import GSC_REPORT_STYLE


_INLINE_TAGS = ("em", "b", "strong", "mark", "br")


def _e(value: object) -> str:
    return _html.escape(str(value or ""))


def _inline(value: object) -> str:
    """Escape text while preserving the tiny inline tag set used by the handoff."""
    text = _html.escape(str(value or ""))
    for tag in _INLINE_TAGS:
        text = text.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        text = text.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return text


def _num(value: object, default: float = 0.0) -> float:
    text = str(value or "").replace("\xa0", " ").replace("\u202f", " ")
    text = re.sub(r"[^\d,.\-]", "", text).replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return default


def _int_from_text(value: object, default: int = 0) -> int:
    text = str(value or "").replace("\xa0", "").replace("\u202f", "").replace(" ", "")
    nums = re.findall(r"-?\d+", text)
    return int(nums[-1]) if nums else default


def _pct(value: object, default: float = 0.0) -> float:
    text = str(value or "")
    number = _num(text, default)
    return number / 100 if "%" in text else number


def _metric(page: dict, *names: str) -> object:
    metrics = page.get("metrics")
    if not isinstance(metrics, dict):
        return ""
    normalized = {_normalize(k): v for k, v in metrics.items()}
    for name in names:
        value = normalized.get(_normalize(name))
        if value is not None:
            return value
    return ""


def _normalize(value: object) -> str:
    text = str(value or "").lower()
    return (
        text.replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("û", "u")
        .replace("î", "i")
        .replace("ô", "o")
    )


def _period(report: dict, lang: str) -> str:
    return (
        translate_period_label(report.get("period_label", ""), lang)
        .removeprefix(gsc_gettext(lang)("Période analysée: "))
        .strip()
        or "export Google Search Console fourni"
    )


def _domain(value: object) -> str:
    text = str(value or "")
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.netloc or parsed.path).replace("www.", "").strip("/") or "Domaine non précisé"


def _path_label(url: object) -> str:
    text = str(url or "")
    parsed = urlparse(text if "://" in text else f"https://{text}")
    path = parsed.path or text
    return "/" + path.strip("/") + "/" if path.strip("/") else text


def _short_label(page: dict) -> str:
    label = str(page.get("slug") or "").strip()
    if label:
        return label
    return compact_url_for_display(str(page.get("url") or "")).strip("/") or "Page"


def _gain_range(report: dict) -> tuple[str, str]:
    value = translate_estimated_gain_value(report.get("estimated_gain_value", ""), "fr")
    nums = [
        int(n.replace(" ", "").replace("\xa0", "").replace("\u202f", ""))
        for n in re.findall(r"\d[\d\s\xa0\u202f]*", value)
    ]
    if len(nums) >= 2:
        return format_number(nums[0]), format_number(nums[1])
    if len(nums) == 1:
        return "0", format_number(nums[0])
    return "À", "confirmer"


def _has_gain_estimate(report: dict) -> bool:
    return bool(str(report.get("estimated_gain_value") or report.get("estimated_gain_cover") or "").strip())


def _render_toolbar(report: dict) -> str:
    active_lang = sanitize_gsc_language(str(report.get("lang") or "fr"))
    _ = gsc_gettext(active_lang)
    language_paths = report.get("language_paths")
    paths = language_paths if isinstance(language_paths, dict) else {}
    buttons = []
    for lang, label in (("fr", "FR"), ("en", "EN")):
        target = str(paths.get(lang) or report.get("html_output_path") or "")
        href = _e(Path(target).name) if target else "#"
        active_class = " is-active" if lang == active_lang else ""
        aria_current = ' aria-current="true"' if lang == active_lang else ""
        buttons.append(
            f'<a class="report-toolbar-button language-toggle{active_class}" '
            f'href="{href}"{aria_current}>{label}</a>'
        )
    return (
        '<div class="report-toolbar no-print">'
        f'<button class="report-toolbar-button" type="button" onclick="exportPDF()">{_e(_("Exporter en PDF"))}</button>'
        f'<span class="language-toggle-group">{"".join(buttons)}</span>'
        f'<a class="report-toolbar-button" href="./">{_e(_("Retour dashboard"))}</a>'
        "</div>"
    )


def _render_nav(lang: str) -> str:
    _ = gsc_gettext(lang)
    items = [
        ("synthese", "Synthèse"),
        ("decision-rapide", "Décision rapide"),
        ("diagnostic", "Diagnostic"),
        ("cartographie", "Cartographie"),
        ("pages-prioritaires", "Pages"),
        ("snippets", "Snippets"),
        ("requetes", "Requêtes"),
        ("cannibalisation", "Structure"),
        ("business", "Business"),
        ("plan", "30 jours"),
    ]
    return (
        f'<nav class="gsc-nav no-print" aria-label="{_e(_("Navigation du rapport"))}">'
        + "".join(f"<a href='#{anchor}'>{_e(_(label))}</a>" for anchor, label in items)
        + "</nav>"
    )


def _runhead(section: str) -> str:
    return f'<div class="runhead"><span class="mark">Prospect Machine</span><span>{_e(section)}</span></div>'


def _pagenum(site_name: str, page: int) -> str:
    return f'<div class="pagenum"><span class="mark">{_e(site_name)}</span><span class="num"><em>p.</em> {page:02d}</span></div>'


def _render_cover(report: dict, lang: str) -> str:
    _ = gsc_gettext(lang)
    site_name = _domain(report.get("site_name"))
    period = _period(report, lang)
    generated_at = str(report.get("generated_at") or "")
    low, high = _gain_range(report)
    estimate_marker = (
        '<span data-component="estimate-box">Potentiel théorique détecté</span>'
        if _has_gain_estimate(report)
        else ""
    )
    report_num = generated_at[:10] or ""
    mode_label = _(str(report.get("report_mode_label") or "Analyse de la période actuelle"))
    return f"""
    <section class="page cover no-running">
      <header class="cover-mast">
        <div class="wordmark"><span class="glyph"></span><span>Prospect <em>Machine</em></span></div>
        <div class="ref-block"><strong>{_e(_("RAPPORT N°"))} { _e(report_num) }</strong><br>{_e(mode_label)}<br>{_e(_("Préparé pour"))} {_e(site_name)}</div>
      </header>
      <div class="cover-body">
        <p class="cover-cat"><span>{_e(_("Opportunités SEO"))}</span><span class="dot">·</span><span>Google Search Console</span><span class="dot">·</span><span>{_e(period)}</span></p>
        <h1 class="cover-title"><em>Rapport</em><br>d'<em>opportunités</em><br><span class="ul">SEO.</span></h1>
        <p class="cover-tag">{_e(site_name)} · {_e(_("analyse des pages à fort potentiel de clic non capté."))}</p>
        <div class="cover-pull">
          <span class="pull-label">{_e(_("Potentiel théorique"))}{estimate_marker}</span>
          <span class="pull-number">{_e(low)}<span class="dash">—</span>{_e(high)}</span>
          <span class="pull-unit">{_e(_("clics/mois supplémentaires, à confirmer après mise en ligne"))}</span>
        </div>
      </div>
      <footer class="cover-foot">
        <div><span class="lbl">{_e(_("Client"))}</span><strong>{_e(site_name)}</strong></div>
        <div><span class="lbl">{_e(_("Période d'analyse"))}</span><strong>{_e(period)}</strong></div>
        <div><span class="lbl">{_e(_("Émis le"))}</span><strong>{_e(generated_at)}</strong></div>
        <div><span class="lbl">{_e(_("Préparé par"))}</span><strong>Prospect Machine</strong></div>
      </footer>
    </section>
"""


def _render_toc(site_name: str) -> str:
    rows = [
        ("I.", "Lettre de lecture", "contexte, prudence et mode d'emploi", "03"),
        ("II.", "Diagnostic", "les chiffres qui comptent", "04"),
        ("III.", "Cartographie CTR / position", "où le clic se perd", "05"),
        ("IV.", "Pages prioritaires", "les dix premières actions", "06"),
        ("V.", "Snippets Google", "titles et metas à réécrire", "08"),
        ("VI.", "Requêtes exploitables", "intentions et angles à traiter", "09"),
        ("VII.", "Structure interne", "cannibalisation et variantes d'URL", "10"),
        ("VIII.", "Opportunités commerciales", "affiliation, tests et pages business", "11"),
        ("IX.", "Plan d'exécution", "calendrier 30 jours et clôture", "12"),
    ]
    return f"""
    <section class="page no-running">
      <header class="toc-head">
        <p class="eyebrow"><span class="num">I.</span> Sommaire</p>
        <h2 class="section-title"><em>Lire vite,</em><br>agir dans le bon ordre.</h2>
        <p class="lede">Le rapport est structuré pour séparer les constats GSC, les décisions prioritaires et le plan d'exécution.</p>
      </header>
      <div class="toc-grid">
        {''.join(f'<div class="toc-row"><span class="toc-num">{num}</span><span class="toc-title">{_e(title)} <em>{_e(desc)}</em><span class="toc-dots"></span></span><span class="toc-page">p. {page}</span></div>' for num, title, desc, page in rows)}
      </div>
      <div class="colophon">
        <div class="col"><h4>Données</h4><p>Exports Google Search Console fournis. Les estimations restent des potentiels théoriques.</p></div>
        <div class="divider"></div>
        <div class="col"><h4>Usage</h4><p>Prioriser, produire, puis vérifier dans GSC après publication. Le rapport ne remplace pas un crawl technique complet.</p></div>
      </div>
      {_pagenum(site_name, 2)}
    </section>
"""


def _render_letter(report: dict, site_name: str) -> str:
    summary = str(report.get("executive_summary") or "")
    return f"""
    <section class="page" id="synthese">
      {_runhead("I. Lettre de lecture")}
      <header>
        <p class="eyebrow"><span class="num">I.</span> Lettre de lecture</p>
        <h2 class="section-title"><em>Ce que dit</em><br>l'export GSC.</h2>
      </header>
      <div class="letter-body">
        <p><span class="drop">L</span>e rapport part d'un principe simple : une page déjà visible dans Google peut créer de la marge avant même de créer un nouveau contenu.</p>
        <p>{_e(summary)}</p>
        <p><em>Les volumes affichés sont des ordres de grandeur.</em> Ils servent à choisir les meilleures actions, pas à promettre un niveau de trafic.</p>
      </div>
      <div class="letter-sign">
        <span class="sign-mark">PM</span>
        <span class="sign-meta"><strong>Prospect Machine</strong><br>Analyse GSC · {_e(site_name)}</span>
      </div>
      {_pagenum(site_name, 3)}
    </section>
"""


def _kpi_value(report: dict, label_part: str, fallback: str = "-") -> str:
    for kpi in report.get("kpis", []) or []:
        label = _normalize(kpi.get("label", ""))
        if _normalize(label_part) in label:
            return str(kpi.get("value") or fallback)
    return fallback


def _render_kpi_row(label: str, value: str, foot: str = "", tone: str = "") -> str:
    tone_class = f" {tone}" if tone else ""
    return (
        f'<div class="kpi-row{tone_class}">'
        f'<span class="kpi-l"><span class="kpi-label">{_e(label)}</span><span class="kpi-foot">{_e(foot)}</span></span>'
        f'<span class="kpi-v">{_e(value)}</span>'
        "</div>"
    )


def _render_diagnostic(report: dict, site_name: str) -> str:
    priorities = list(report.get("monthly_priorities") or [])
    ladder = []
    for index, item in enumerate(priorities[:4], start=1):
        ladder.append(
            f'<div class="ladder-row is-{index}">'
            f'<span class="ladder-num">{index}.</span>'
            f'<div class="ladder-body"><strong>{_e(item.get("title"))}</strong><p>{_e(item.get("why"))} {_e(item.get("action"))}</p></div>'
            f'<div class="ladder-meta"><span class="tag {"hot" if index == 1 else ""}">{_e(item.get("impact") or "à prioriser")}</span><span class="effort">{_e(item.get("effort") or "effort à qualifier")}</span></div>'
            "</div>"
        )
    if not ladder:
        ladder.append('<div class="empty-state">Aucune priorité mensuelle exploitable dans l\'export.</div>')
    return f"""
    <section class="page" id="diagnostic">
      {_runhead("II. Diagnostic")}
      <header>
        <span id="decision-rapide"></span>
        <p class="eyebrow"><span class="num">II.</span> Diagnostic</p>
        <h2 class="section-title"><em>La visibilité existe.</em><br>Le clic reste à capter.</h2>
      </header>
      <div class="diag-grid">
        <div class="diag-statement">
          <p class="diag-headline">Le site dispose déjà de signaux GSC utiles. <em>L'écart se gagne au clic</em>, puis par consolidation des pages proches.</p>
          <p>La lecture ci-dessous conserve la data du pipeline actuel : pages prioritaires, requêtes, snippets et signaux de structure.</p>
        </div>
        <div class="kpi-stack kpi-grid">
          {_render_kpi_row("Pages analysées", _kpi_value(report, "Pages analysées"), "base GSC", "")}
          {_render_kpi_row("Clics totaux", _kpi_value(report, "Clics totaux"), "période fournie", "")}
          {_render_kpi_row("Impressions", _kpi_value(report, "Impressions"), "visibilité brute", "is-accent")}
          {_render_kpi_row("CTR moyen", _kpi_value(report, "Taux de clic"), "signal de clic", "is-hot")}
          {_render_kpi_row("Pages prioritaires", _kpi_value(report, "Pages prioritaires"), "actions à trier", "")}
        </div>
      </div>
      <div class="priority-ladder">{''.join(ladder)}</div>
      {_pagenum(site_name, 4)}
    </section>
"""


def _scatter_point(page: dict) -> dict[str, object]:
    clicks = _int_from_text(_metric(page, "Clics"))
    impressions = _int_from_text(_metric(page, "Impressions"))
    ctr = _pct(_metric(page, "CTR", "Taux de clic"))
    position = _num(_metric(page, "Position"), 20.0)
    expected = ctr_median(position)
    return {
        "label": _short_label(page),
        "position": position,
        "ctr": ctr,
        "impressions": impressions,
        "clicks": clicks,
        "hot": impressions >= 50 and ctr < expected * 0.75,
    }


def _render_scatter(report: dict, site_name: str) -> str:
    pages = [_scatter_point(p) for p in list(report.get("priority_pages") or [])[:10]]
    if not pages:
        pages = [{"label": "Aucune page", "position": 20.0, "ctr": 0.0, "impressions": 1, "clicks": 0, "hot": False}]
    axis_max = max(0.06, min(0.16, max(float(p["ctr"]) for p in pages) * 1.25))

    def xy(position: float, ctr: float) -> tuple[float, float]:
        x = 80 + min(54, max(0, position - 1)) * (660 / 54)
        y = 300 - min(axis_max, max(0.0, ctr)) / axis_max * 270
        return x, y

    positions = [1, 3, 5, 8, 10, 15, 20, 30, 40, 50, 55]
    low = [xy(pos, ctr_median(pos) * 0.65) for pos in positions]
    high = [xy(pos, ctr_p75(max(1, min(20, pos)))) for pos in positions]
    polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in high + list(reversed(low)))
    high_line = " ".join(f"{x:.1f},{y:.1f}" for x, y in high)
    low_line = " ".join(f"{x:.1f},{y:.1f}" for x, y in low)
    point_markup = []
    label_candidates = sorted(pages, key=lambda p: int(p["impressions"]), reverse=True)[:6]
    label_ids = {id(p) for p in label_candidates}
    hottest = next((p for p in sorted(pages, key=lambda p: int(p["impressions"]), reverse=True) if p["hot"]), None)
    for p in pages:
        x, y = xy(float(p["position"]), float(p["ctr"]))
        radius = max(3.5, min(8.0, 2.3 + math.log10(int(p["impressions"]) + 1)))
        color = "var(--hot)" if p["hot"] else "var(--ink)"
        if p is hottest:
            point_markup.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="14" fill="var(--hot)" opacity=".12"></circle>')
        point_markup.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}"></circle>')
        if id(p) in label_ids:
            point_markup.append(f'<text x="{x + 9:.1f}" y="{max(18, y - 8):.1f}" font-family="Fraunces, Georgia, serif" font-style="italic" font-size="12" fill="var(--ink)">{_e(p["label"])}</text>')
    hot_count = sum(1 for p in pages if p["hot"])
    return f"""
    <section class="page" id="cartographie">
      {_runhead("III. Cartographie CTR / position")}
      <header>
        <p class="eyebrow"><span class="num">III.</span> Cartographie</p>
        <h2 class="section-title"><em>Où le clic</em><br>se perd.</h2>
        <p class="lede">Les pages prioritaires sont replacées face à une fourchette CTR attendue à position équivalente.</p>
      </header>
      <div class="chart-card">
        <div class="chart-cap">
          <h3>Distribution CTR / position — pages prioritaires</h3>
          <div class="leg"><span><i class="swatch hot"></i>sous-cliqué</span><span><i class="swatch"></i>dans la norme</span><span><i class="swatch band"></i>fourchette attendue</span></div>
        </div>
        <svg class="chart-svg" viewBox="0 0 760 360" role="img" aria-label="Distribution CTR et position">
          <rect x="80" y="30" width="660" height="270" fill="transparent" stroke="var(--line)"></rect>
          <polygon points="{polygon}" fill="var(--gain-soft)" opacity=".72"></polygon>
          <polyline points="{high_line}" fill="none" stroke="var(--gain)" stroke-dasharray="4 4"></polyline>
          <polyline points="{low_line}" fill="none" stroke="var(--gain)" stroke-dasharray="4 4" opacity=".7"></polyline>
          {''.join(f'<line x1="{80 + tick * 660 / 54:.1f}" y1="300" x2="{80 + tick * 660 / 54:.1f}" y2="306" stroke="var(--muted-soft)"></line><text x="{80 + tick * 660 / 54:.1f}" y="328" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="10" fill="var(--muted)">{tick + 1}</text>' for tick in (0, 4, 9, 14, 19, 29, 39, 49, 54))}
          {''.join(f'<line x1="74" y1="{300 - i * 270 / 3:.1f}" x2="80" y2="{300 - i * 270 / 3:.1f}" stroke="var(--muted-soft)"></line><text x="66" y="{304 - i * 270 / 3:.1f}" text-anchor="end" font-family="JetBrains Mono, monospace" font-size="10" fill="var(--muted)">{format_percent(axis_max * i / 3)}</text>' for i in range(4))}
          {''.join(point_markup)}
          <text x="410" y="350" text-anchor="middle" font-family="Inter, sans-serif" font-size="11" fill="var(--muted)">Position moyenne Google</text>
          <text x="18" y="170" transform="rotate(-90 18 170)" text-anchor="middle" font-family="Inter, sans-serif" font-size="11" fill="var(--muted)">CTR</text>
        </svg>
        <div class="chart-foot">
          <div class="stat"><span class="v"><em>{hot_count}</em></span><span class="l">pages sous la fourchette</span><span class="d">Signal prioritaire pour les snippets et l'angle d'entrée.</span></div>
          <div class="stat"><span class="v">{format_number(sum(int(p["impressions"]) for p in pages))}</span><span class="l">impressions analysées</span><span class="d">Volume cumulé des pages affichées sur la matrice.</span></div>
          <div class="stat"><span class="v">{format_number(len(pages))}</span><span class="l">pages prioritaires</span><span class="d">Sélection issue du pipeline GSC existant.</span></div>
        </div>
      </div>
      {_pagenum(site_name, 5)}
    </section>
"""


def _priority_tone(page: dict) -> str:
    return page_priority_class(str(page.get("priority", "p3")))


def _render_priority_card(page: dict, index: int, *, compact: bool = False) -> str:
    clicks = _metric(page, "Clics")
    impressions = _metric(page, "Impressions")
    ctr = _metric(page, "CTR", "Taux de clic")
    position = _metric(page, "Position")
    gain = _metric(page, "Gain estimé", "Potentiel")
    ctr_value = _pct(ctr)
    pos_value = _num(position, 20.0)
    axis_max = max(0.05, ctr_p75(max(1, min(20, round(pos_value)))) * 1.15)
    target_low = min(100.0, ctr_median(pos_value) * 0.65 / axis_max * 100)
    target_high = min(100.0, ctr_p75(pos_value) / axis_max * 100)
    now_width = min(100.0, ctr_value / axis_max * 100)
    tag_class = {"high": "hot", "medium": "warn", "low": "gain", "dead": "ghost"}.get(_priority_tone(page), "")
    badge_class = f"priority-badge--{_priority_tone(page)}"
    return f"""
      <article class="page-card{' is-top' if index == 1 else ''}{' compact' if compact else ''}" data-priority="{_e(_priority_tone(page))}">
        <div class="page-card-rank">{index}.</div>
        <div class="page-card-main">
          <header class="page-card-head">
            <div>
              <h3 class="page-card-title">{_e(_short_label(page))}</h3>
              <a class="page-card-url" href="{_e(page.get('url'))}">{_e(compact_url_for_display(str(page.get('url') or '')))}</a>
            </div>
            <div class="page-card-tag"><span class="tag {tag_class} priority-badge {badge_class}">{_e(priority_display_label(str(page.get("priority", "p3")), str(page.get("priority_label", ""))))}</span><span class="field-label">{_e(page.get("effort") or "")}</span></div>
          </header>
          <div class="metric-row page-metrics">
            <div class="metric"><span class="metric-label">Clics</span><span class="metric-value">{_e(clicks)}</span></div>
            <div class="metric"><span class="metric-label">Impr.</span><span class="metric-value">{_e(impressions)}</span></div>
            <div class="metric"><span class="metric-label">CTR</span><span class="metric-value">{_e(ctr)}</span></div>
            <div class="metric"><span class="metric-label">Pos.</span><span class="metric-value">{_e(str(position).replace(".", ","))}</span></div>
            <div class="metric delta"><span class="metric-label">Gain</span><span class="metric-value">{_e(re.sub(r"^\\+|jusqu.?à\\s*", "", str(gain), flags=re.I).strip() or "0")}</span></div>
          </div>
          <div class="page-card-body">
            <div class="page-card-col">
              <span class="field-label">Diagnostic</span>
              <p class="field-text">{_e(page.get("diagnostic") or page.get("why") or "")}</p>
              <div class="ctr-row">
                <div class="ctr-row-stat"><span>CTR actuel <b>{_e(ctr)}</b></span><span>Fourchette cible <b>{format_percent(ctr_median(pos_value) * 0.65)} — {format_percent(ctr_p75(pos_value))}</b></span></div>
                <div class="ctr-track"><span class="ctr-band" style="left:{target_low:.1f}%;right:{100 - target_high:.1f}%"></span><span class="ctr-now" style="width:{now_width:.1f}%"></span></div>
                <div class="ctr-axis"><span>0</span><span>{format_percent(axis_max)}</span></div>
              </div>
            </div>
            <div class="page-card-col">
              <span class="field-label">Geste recommandé</span>
              <p class="field-text">{_inline(page.get("recommendation") or "Action à confirmer avec la SERP cible.")}</p>
              <p class="gain-line">Potentiel théorique : <b>{_e(gain)}</b> · horizon 6-8 semaines.</p>
              {f'<div class="note-block"><b>SERP enrichie à confirmer.</b> Vérifier la page de résultats avant de modifier le title seul.</div>' if page.get("serp_anomaly") else ''}
            </div>
          </div>
        </div>
      </article>
"""


def _render_priority_page(report: dict, site_name: str, start: int, end: int, page_no: int, label: str, compact: bool = False) -> str:
    pages = list(report.get("priority_pages") or [])[start:end]
    body = "".join(_render_priority_card(page, start + idx + 1, compact=compact) for idx, page in enumerate(pages))
    if not body:
        body = '<div class="empty-state">Aucune page prioritaire disponible dans cet export.</div>'
    return f"""
    <section class="page" id="{'pages-prioritaires' if start == 0 else 'pages-prioritaires-suite'}">
      {_runhead(f"IV. Pages prioritaires · {label}")}
      <header>
        <p class="eyebrow"><span class="num">IV.</span> Pages prioritaires <span style="margin-left: 8px; color: var(--muted-soft);">— {label}</span></p>
        <h2 class="section-title"><em>Traiter d'abord</em><br>les pages déjà visibles.</h2>
      </header>
      <div class="filter-bar no-print"><div class="filter-group"><span class="filter-label">Urgence</span><button class="filter-btn is-active" data-filter-kind="priority" data-section="pages-prioritaires" data-filter-value="all">Toutes</button><button class="filter-btn" data-filter-kind="priority" data-section="pages-prioritaires" data-filter-value="high">Haute</button><button class="filter-btn" data-filter-kind="priority" data-section="pages-prioritaires" data-filter-value="medium">Moyenne</button></div></div>
      {body}
      {_pagenum(site_name, page_no)}
    </section>
"""


def _render_serp(domain: str, title: str, desc: str, stamp: str, after: bool = False) -> str:
    cls = "serp after" if after else "serp"
    return f"""
        <div class="{cls}">
          <span class="serp-stamp">{_e(stamp)}</span>
          <div class="serp-favicon"><span class="dot"></span><span class="domain"><span class="site">{_e(domain)}</span><span class="url">{_e(domain)}</span></span></div>
          <h5 class="serp-title">{_inline(title)}</h5>
          <p class="serp-desc">{_inline(desc)}</p>
        </div>
"""


def _render_snippets(report: dict, site_name: str) -> str:
    domain = _domain(site_name)
    snippets = list(report.get("snippet_pages") or [])[:5]
    blocks = []
    for item in snippets:
        after_title = str(item.get("title_example") or item.get("title") or _short_label(item))
        after_meta = str(item.get("meta_example") or "")
        before_title = str(item.get("current_title") or "(snippet actuel à insérer)")
        before_meta = str(item.get("current_meta") or "Description actuelle non disponible dans l'export fourni.")
        blocks.append(
            f"""
      <article class="snippet-block snippet-card" data-priority="{_e(_priority_tone(item))}">
        <div class="snippet-title-row"><h4>{_e(_short_label(item))}</h4><span class="snippet-meta"><b>{_e(item.get("metrics") or "")}</b></span></div>
        <div class="serp-pair">
          {_render_serp(domain, before_title, before_meta, "Avant")}
          <div class="serp-arrow">→</div>
          {_render_serp(domain, after_title, after_meta, "Après", True)}
        </div>
        <div class="serp-notes"><div class="col"><h5>Intention</h5><p>{_e(item.get("intent") or item.get("main_query") or "")}</p></div><div class="col"><h5>Angle</h5><p>{_e(item.get("angle") or item.get("problem") or "")}</p></div></div>
      </article>
"""
        )
    body = "".join(blocks) if blocks else '<div class="empty-state">Aucun snippet hors top prioritaire dans cet export.</div>'
    return f"""
    <section class="page" id="snippets">
      {_runhead("V. Snippets Google")}
      <header>
        <p class="eyebrow"><span class="num">V.</span> Snippets Google</p>
        <h2 class="section-title"><em>Réécrire</em><br>ce qui s'affiche dans Google.</h2>
        <p class="lede">Les propositions conservent les pages sélectionnées par le pipeline et ciblent un meilleur taux de clic.</p>
      </header>
      {body}
      {_pagenum(site_name, 8)}
    </section>
"""


def _render_queries(report: dict, site_name: str) -> str:
    rows = []
    for row in list(report.get("top_query_opportunities") or [])[:12]:
        target_url = str(row.get("target_url") or "")
        target_label = resolve_target_label(target_url) if is_resolvable_target(target_url) else _path_label(target_url)
        rows.append(
            "<tr>"
            f'<td><span class="action-chip rewrite">{_e(row.get("recommendation") or "Action")}</span></td>'
            f'<td><span class="urlcell">{_e(target_label)}</span></td>'
            f'<td><div class="qrow"><span class="qprimary">{_e(display_query_label(row.get("top_queries") or row.get("query") or ""))}</span><span class="qsecondary">{_e(row.get("queries_count") or 1)} requête(s)</span></div></td>'
            f'<td class="r">{_e(row.get("clicks"))}</td>'
            f'<td class="r"><em>{_e(row.get("impressions"))}</em></td>'
            f'<td class="r">{_e(row.get("ctr"))}</td>'
            f'<td class="r">{_e(str(row.get("position") or "").replace(".", ","))}</td>'
            "</tr>"
        )
    body = (
        '<div class="table-card"><table><thead><tr><th>Action</th><th>URL cible</th><th>Requêtes principales</th><th class="r">Clics</th><th class="r">Impr.</th><th class="r">CTR</th><th class="r">Pos.</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
        if rows
        else '<div class="empty-state">Export Requêtes non fourni ou aucune requête exploitable détectée.</div>'
    )
    return f"""
    <section class="page" id="requetes">
      {_runhead("VI. Requêtes exploitables")}
      <header>
        <p class="eyebrow"><span class="num">VI.</span> Requêtes exploitables</p>
        <h2 class="section-title"><em>Les intentions</em><br>à recycler dans les pages.</h2>
      </header>
      {body}
      {_pagenum(site_name, 9)}
    </section>
"""


def _render_clusters(report: dict, site_name: str) -> str:
    cluster_cards = []
    for idx, group in enumerate(list(report.get("cannibalization_groups") or [])[:3], start=1):
        group_id = str(group.get("group_id") or group.get("id") or f"CAN-{idx:02d}")
        queries = group.get("shared_queries") or group.get("queries") or []
        urls = group.get("urls") or []
        cluster_cards.append(
            f"""
      <article class="cluster-card">
        <header class="cluster-head"><div><h3>{_e(group.get("topic") or group.get("title") or "Pages en concurrence")}</h3><span class="id">{_e(group_id)} · {len(urls)} URLs · signal {_e(client_display_value(group.get("confidence") or "à confirmer"))}</span></div><span class="tag danger">Signal</span></header>
        <div class="cluster-grid"><div><h4>Requêtes partagées</h4><div class="query-chips">{''.join(f'<span class="chip">{_e(q)}</span>' for q in list(queries)[:8])}</div></div><div><h4>URLs concernées</h4><ul class="url-list">{''.join(f'<li><span>{_e(compact_url_for_display(str(u)))}</span></li>' for u in list(urls)[:8])}</ul></div></div>
        <div class="cluster-action"><b>Décision :</b> {_inline(group.get("recommendation") or "Clarifier l'intention de chaque page et valider manuellement le bon arbitrage.")}</div>
      </article>
"""
        )
    clusters = "".join(cluster_cards) if cluster_cards else '<div class="empty-state">Aucun cluster de cannibalisation significatif détecté.</div>'
    variants = []
    for pair in list(report.get("url_variant_pairs") or [])[:5]:
        canonical = str(pair.get("canonical_url") or pair.get("url_b") or "")
        arrow = "→" if canonical else "↔"
        variants.append(
            f"""
      <div class="variant-row">
        <div class="variant-url-cell"><span class="badge">URL A</span>{_e(_path_label(pair.get("url_a")))}</div>
        <div class="variant-arrow">{arrow}</div>
        <div class="variant-url-cell canonical"><span class="badge">Canonique</span>{_e(_path_label(canonical or pair.get("url_b")))}</div>
        <dl class="variant-meta"><div><dt>Clics</dt><dd>{_e(pair.get("total_clicks") or pair.get("clicks") or 0)}</dd></div><div><dt>Impr.</dt><dd>{_e(pair.get("total_impressions") or pair.get("impressions") or 0)}</dd></div><div><dt>Pos.</dt><dd>{_e(str(pair.get("avg_position") or pair.get("position") or "-").replace(".", ","))}</dd></div></dl>
      </div>
"""
        )
    variant_block = (
        '<header style="margin-top:16px"><p class="eyebrow smallcaps">Variantes d\'URL — fusion ou 301</p><p class="lede" style="margin-top:6px">Si une 301 est déjà en place, ignorer. Sinon, choisir une URL canonique et poser une redirection.</p></header>'
        + "".join(variants)
        if variants
        else ""
    )
    return f"""
    <section class="page" id="cannibalisation">
      {_runhead("VII. Structure interne")}
      <header>
        <p class="eyebrow"><span class="num">VII.</span> Structure interne</p>
        <h2 class="section-title"><em>Cannibalisation</em><br>et variantes d'URL.</h2>
      </header>
      <div class="cluster-section">{clusters}</div>
      {variant_block}
      {_pagenum(site_name, 10)}
    </section>
"""


def _render_business(report: dict, site_name: str) -> str:
    rows = []
    for page in list(report.get("business_opportunities") or [])[:10]:
        rows.append(
            "<tr>"
            f'<td><span class="qprimary" style="display:block;color:var(--ink);font-family:var(--serif);font-size:14px;font-weight:500;">{_e(_short_label(page))}</span><span class="qsecondary">{_e(_path_label(page.get("url")))}</span></td>'
            f'<td><span class="tag danger">{_e(client_display_value(page.get("business_value"), "fr") or "à qualifier")}</span></td>'
            f'<td><span class="tag ghost">{_e(client_display_value(page.get("monetization_possible"), "fr") or "à confirmer")}</span></td>'
            f'<td class="r">{_e(page.get("opportunity_score") or "")}</td>'
            f'<td>{_e(page.get("recommendation") or "")}</td>'
            "</tr>"
        )
    body = (
        '<div class="table-card"><table><thead><tr><th>Page</th><th>Valeur</th><th>Monétisation</th><th class="r">Score</th><th>Geste recommandé</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
        if rows
        else '<div class="empty-state">Toutes les pages business à fort potentiel sont déjà traitées dans le top prioritaire.</div>'
    )
    return f"""
    <section class="page" id="business">
      {_runhead("VIII. Opportunités commerciales")}
      <header>
        <p class="eyebrow"><span class="num">VIII.</span> Opportunités commerciales</p>
        <h2 class="section-title"><em>Pages à intention</em><br>business.</h2>
        <p class="lede">Hors top prioritaire. À intégrer en relais des actions principales.</p>
      </header>
      {body}
      {_pagenum(site_name, 11)}
    </section>
"""


def _deliverables_from_body(body: str) -> list[str]:
    found = re.findall(r"`([^`]+)`", body)
    if found:
        return found[:5]
    urls = re.findall(r"/[a-z0-9][a-z0-9\-/]+/?", body, flags=re.I)
    return urls[:5]


def _render_plan(report: dict, site_name: str) -> str:
    weeks = list(report.get("action_plan_30_days") or [])
    if not weeks:
        weeks = [
            {"week": "Semaine 1", "focus": "Réécriture des résultats Google", "body": "Réécrire les snippets prioritaires."},
            {"week": "Semaine 2", "focus": "Enrichissement contenu", "body": "Renforcer les pages proches du haut des résultats."},
            {"week": "Semaine 3", "focus": "Structure interne", "body": "Clarifier les clusters et variantes d'URL."},
            {"week": "Semaine 4", "focus": "Suivi GSC", "body": "Mesurer CTR, position et clics sur les pages modifiées."},
        ]
    week_html = []
    for index, week in enumerate(weeks[:4], start=1):
        body = str(week.get("body") or "")
        deliverables = _deliverables_from_body(body) or [str(week.get("focus") or "action")]
        week_html.append(
            f"""
      <div class="plan-week">
        <div class="plan-when"><span class="num">{index:02d}</span><span class="label">Semaine</span></div>
        <div class="plan-body"><h3>{_e(week.get("focus") or week.get("title") or f"Semaine {index}")}</h3><p>{_e(body)}</p><div class="deliverables">{''.join(f'<span>{_e(item)}</span>' for item in deliverables)}</div></div>
      </div>
"""
        )
    annexes = report.get("annex_files") or []
    annex_grid = "".join(
        f'<div class="annex-item"><span class="annex-name">{_e(item.get("name") if isinstance(item, dict) else item)}</span><span class="annex-category">{_e(item.get("category", "export") if isinstance(item, dict) else "export")}</span><span class="annex-desc">{_e(item.get("description", "") if isinstance(item, dict) else "")}</span></div>'
        for item in annexes
    )
    return f"""
    <section class="page" id="plan">
      {_runhead("IX. Plan d'exécution")}
      <header>
        <p class="eyebrow"><span class="num">IX.</span> Plan d'exécution</p>
        <h2 class="section-title"><em>Quatre semaines</em><br>pour activer la marge.</h2>
      </header>
      <div class="plan-grid">{''.join(week_html)}</div>
      <header style="margin-top:14px"><p class="eyebrow smallcaps">Lectures à conserver à l'esprit</p></header>
      <div class="lectures"><div class="col"><h4>Ce que ce rapport dit</h4><ul><li>Le <b>potentiel théorique</b> est un ordre de grandeur, pas une promesse.</li><li>Les <b>positions</b> sont des moyennes GSC.</li><li>Les actions doivent être validées après mise en ligne.</li></ul></div><div class="col"><h4>Ce qu'il ne dit pas</h4><ul><li>Il ne remplace pas un audit technique complet.</li><li>Les signaux de cannibalisation nécessitent une validation manuelle.</li><li>Sans export précédent, il ne diagnostique pas une baisse.</li></ul></div></div>
      <div class="annex-grid">{annex_grid}</div>
      <div class="closing"><div><h3>Prochain rapport — dans 4 semaines.</h3><p>Relancer GSC avec un export de comparaison pour vérifier les effets page par page.</p></div><div class="closing-mark"><strong>Prospect Machine</strong>contact@prospect-machine.fr</div></div>
      {_pagenum(site_name, 12)}
    </section>
"""


def render_gsc_report(report: dict, *, lang: str = "fr") -> str:
    """Render a standalone HTML document using the v2 boutique design."""
    active_lang = sanitize_gsc_language(str(report.get("lang") or lang))
    _ = gsc_gettext(active_lang)
    site_name = _domain(report.get("site_name"))
    generated_at = str(report.get("generated_at") or "")
    title = str(report.get("title") or _("Rapport d'opportunités SEO"))
    sections = [
        _render_cover(report, active_lang),
        _render_toc(site_name),
        _render_letter(report, site_name),
        _render_diagnostic(report, site_name),
        _render_scatter(report, site_name),
        _render_priority_page(report, site_name, 0, 4, 6, "rangs 1 à 4"),
        _render_priority_page(report, site_name, 4, 10, 7, "rangs 5 à 10", compact=True),
        _render_snippets(report, site_name),
        _render_queries(report, site_name),
        _render_clusters(report, site_name),
        _render_business(report, site_name),
        _render_plan(report, site_name),
    ]
    return f"""<!DOCTYPE html>
<html lang="{_e(active_lang)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_e(_(title))}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,300;1,9..144,400;1,9..144,500;1,9..144,600&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>{GSC_REPORT_STYLE}</style>
</head>
<body>
  {_render_toolbar(report)}
  {_render_nav(active_lang)}
  <div class="doc">
    {''.join(sections)}
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
      document.querySelectorAll('.filter-btn[data-filter-kind="priority"]').forEach(function(button) {{
        button.addEventListener('click', function() {{
          var value = button.dataset.filterValue || 'all';
          document.querySelectorAll('.filter-btn[data-filter-kind="priority"]').forEach(function(peer) {{
            peer.classList.toggle('is-active', peer === button);
          }});
          document.querySelectorAll('.page-card, .snippet-card').forEach(function(card) {{
            card.classList.toggle('is-filtered-out', value !== 'all' && card.dataset.priority !== value);
          }});
        }});
      }});
    }});
  </script>
  <div class="print-footer">{_e(_("Rapport d'opportunités GSC"))} · {_e(site_name)} · {_e(generated_at)}</div>
</body>
</html>"""
