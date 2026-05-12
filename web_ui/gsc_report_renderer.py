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
from urllib.parse import quote, urlparse

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
    language_paths = report.get("language_paths")
    paths = language_paths if isinstance(language_paths, dict) else {}
    buttons = []
    for lang, label in (("fr", "FR"), ("en", "EN")):
        target = str(paths.get(lang) or report.get("html_output_path") or "")
        href = f"/files?path={quote(target)}" if target else "#"
        active_class = " is-active" if lang == active_lang else ""
        aria_current = ' aria-current="true"' if lang == active_lang else ""
        buttons.append(
            f'<a class="report-toolbar-button language-toggle{active_class}" '
            f'href="{href}"{aria_current}>{label}</a>'
        )
    export_label = "Export PDF" if active_lang == "en" else "Exporter en PDF"
    dashboard_label = "Back to dashboard" if active_lang == "en" else "Retour dashboard"
    return (
        '<div class="report-toolbar no-print">'
        f'<button class="report-toolbar-button" type="button" onclick="exportPDF()">{_e(export_label)}</button>'
        f'<span class="language-toggle-group">{"".join(buttons)}</span>'
        f'<a class="report-toolbar-button" href="/">{_e(dashboard_label)}</a>'
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


_MONTHS_FR = {
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


def _date_parts(value: object) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    for pattern in (r"^(\d{4})-(\d{2})-(\d{2})", r"^(\d{2})/(\d{2})/(\d{4})"):
        match = re.match(pattern, text)
        if not match:
            continue
        parts = [int(part) for part in match.groups()]
        if pattern.startswith("^(\\d{4})"):
            year, month, day = parts
        else:
            day, month, year = parts
        if 1 <= month <= 12 and 1 <= day <= 31:
            return year, month, day
    return None


def _date_label(value: object) -> str:
    parts = _date_parts(value)
    if not parts:
        return str(value or "")
    year, month, day = parts
    return f"{day} {_MONTHS_FR[month]} {year}"


def _date_ref(value: object) -> str:
    parts = _date_parts(value)
    if not parts:
        return str(value or "")
    year, month, day = parts
    return f"{year:04d}-{month:02d}-{day:02d}"


def _source_metric(report: dict, key: str, fallback: object = 0) -> object:
    metrics = report.get("metrics_source")
    if isinstance(metrics, dict) and key in metrics:
        return metrics[key]
    return fallback


def _kpi_metric(report: dict, label_part: str, fallback: str = "-") -> str:
    value = _kpi_value(report, label_part, "")
    return value if value else fallback


def _roman_lower(index: int) -> str:
    values = (
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    )
    remaining = max(1, index)
    out = []
    for value, letter in values:
        while remaining >= value:
            out.append(letter)
            remaining -= value
    return "".join(out)


def _axis_percent(value: float) -> str:
    pct = value * 100
    return f"{pct:.0f}%".replace(".", ",")


def _gain_label(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^jusqu.?à\s*", "", text, flags=re.I)
    text = text.replace("clics/mois supplémentaires", "").replace("clics / mois", "").replace("clics/mois", "")
    text = text.strip(" ·")
    if not text:
        return "+0"
    return text if text.startswith("+") else f"+{text}"


def _render_cover(report: dict, lang: str) -> str:
    _ = gsc_gettext(lang)
    site_name = _domain(report.get("site_name"))
    period = _period(report, lang)
    generated_at = str(report.get("generated_at") or "")
    low, high = _gain_range(report)
    report_num = _date_ref(generated_at) or ""
    mode_label = _(str(report.get("report_mode_label") or "Analyse de la période actuelle"))
    return f"""
    <section class="page cover no-running">
      <header class="cover-mast">
        <div class="wordmark"><span class="glyph"></span><span>Prospect <em>Machine</em></span></div>
        <div class="ref-block"><strong>{_e(_("RAPPORT N°"))} {_e(report_num)}</strong><br>{_e(mode_label)}<br>{_e(_("Préparé pour"))} {_e(site_name)}</div>
      </header>
      <div class="cover-body">
        <p class="cover-cat"><span>{_e(_("Opportunités SEO"))}</span><span class="dot">·</span><span>Google Search Console</span><span class="dot">·</span><span>{_e(period)}</span></p>
        <h1 class="cover-title display" style="font-family: system-ui">{_e(site_name)}</h1>
        <p class="cover-tag">Une lecture stratégique de ce que Google affiche, et de l'écart entre l'impression et le clic — accompagnée de gestes concrets pour activer la marge.</p>
        <div class="cover-pull">
          <div class="pull-label">Potentiel détecté</div>
          <div class="pull-number"><span class="tnum">{_e(low)}</span><span class="dash">–</span><span class="tnum">{_e(high)}</span></div>
          <div class="pull-unit">clics organiques supplémentaires par mois, à position équivalente.</div>
        </div>
      </div>
      <footer class="cover-foot">
        <div><span class="lbl">{_e(_("Client"))}</span><strong>{_e(site_name)}</strong></div>
        <div><span class="lbl">{_e(_("Période d'analyse"))}</span><strong>{_e(period)}</strong></div>
        <div><span class="lbl">{_e(_("Émis le"))}</span><strong>{_e(_date_label(generated_at))}</strong></div>
        <div><span class="lbl">{_e(_("Préparé par"))}</span><strong>Prospect Machine</strong></div>
      </footer>
    </section>
"""


def _render_toc(site_name: str) -> str:
    rows = [
        ("II.", "Lettre d'analyse", "— pourquoi ce rapport, et ce qu'il propose", "03"),
        ("III.", "État des lieux", "— les chiffres qui comptent", "04"),
        ("IV.", "L'écart", "— position contre taux de clic, ce que dit le nuage", "05"),
        ("V.", "Pages prioritaires", "— les dix premières actions", "06 — 08"),
        ("VI.", "Réécriture des résultats Google", "— avant / après", "09"),
        ("VII.", "Requêtes exploitables", "— par URL cible et action", "10"),
        ("VIII.", "Pages en concurrence", "— clusters et variantes d'URL", "11"),
        ("IX.", "Opportunités commerciales", "— pages à intention business", "12"),
        ("X.", "Plan d'exécution", "— calendrier 30 jours et clôture", "13"),
    ]
    return f"""
    <section class="page no-running">
      <header class="toc-head">
        <p class="eyebrow"><span class="num">I.</span> Sommaire</p>
        <h2 class="section-title"><em>Comment lire</em><br>ce rapport.</h2>
        <p class="lede">Douze pages organisées comme une décision : d'abord ce qu'il faut retenir, puis ce qu'il faut faire — et enfin, les preuves derrière chaque recommandation.</p>
      </header>
      <div class="toc-grid">
        {''.join(f'<div class="toc-row"><span class="toc-num">{num}</span><span class="toc-title">{_e(title)} <em>{_e(desc)}</em></span><span class="toc-page">p. {page}</span></div>' for num, title, desc, page in rows)}
      </div>
      <div class="colophon">
        <div class="col"><h4>Méthode</h4><p>Analyse construite sur l'export brut Google Search Console. Indicateurs : impressions, clics, CTR, position, et CTR médian par position.</p></div>
        <div class="divider"></div>
        <div class="col"><h4>Limites</h4><p>Les positions sont des moyennes GSC. Les signaux de cannibalisation doivent être validés manuellement avant tout déploiement.</p></div>
      </div>
    </section>
"""


def _render_letter(report: dict, site_name: str) -> str:
    summary = str(report.get("executive_summary") or "")
    clicks = _kpi_metric(report, "Clics totaux", format_number(_source_metric(report, "Clics totaux")))
    impressions = _kpi_metric(report, "Impressions", format_number(_source_metric(report, "Impressions totales")))
    priority_count = _kpi_metric(report, "Pages prioritaires", format_number(_source_metric(report, "Pages prioritaires")))
    query_count = _kpi_metric(report, "Requêtes exploitables", format_number(_source_metric(report, "Requêtes exploitables")))
    generated_at = str(report.get("generated_at") or "")
    return f"""
    <section class="page">
      {_runhead("II. Lettre d'analyse")}
      <header>
        <p class="eyebrow"><span class="num">II.</span> Lettre d'analyse</p>
        <h2 class="section-title" style="margin-top: 16px;"><em>L'enjeu n'est pas</em><br>de gagner en visibilité.</h2>
        <p class="lede" style="margin-top: 20px;">C'est de capter les clics que la visibilité actuelle laisse sur la table — avant tout effort de création.</p>
      </header>
      <div class="rule-short" style="margin: 12px 0;"></div>
      <div class="letter-body">
        <p><span class="drop">L</span>e site reçoit {_e(impressions)} impressions sur la période fournie, et transforme ce volume en {_e(clicks)} clics. Cette asymétrie n'est pas l'expression d'un manque de contenu : c'est le signe que <b>les pages déjà classées par Google n'obtiennent pas toujours le taux de clic attendu pour leur position</b>.</p>
        <p>{_e(summary)}</p>
        <p>{_e(priority_count)} pages prioritaires concentrent l'essentiel du potentiel à 30 jours. {_e(query_count)} requêtes exportées par Google montrent les intentions qu'il reste à couvrir à l'intérieur du contenu existant, avant de produire de nouveaux articles.</p>
        <p>Ce rapport sépare ce qui peut être fait <b>en semaine 1</b> des enrichissements à confirmer sur quatre à huit semaines, puis des décisions éditoriales plus structurantes.</p>
        <p style="color: var(--ink-mid); font-style: italic; font-size: 15px;">Bonne lecture.</p>
      </div>
      <div class="letter-sign">
        <div class="sign-mark">— Prospect&nbsp;Machine</div>
        <div class="sign-meta"><strong>Analyse SEO · Google Search Console</strong><br>Rapport n° {_e(_date_ref(generated_at))} · Émis le {_e(_date_label(generated_at))}</div>
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
        row_class = "ladder-row is-1" if index == 1 else "ladder-row"
        ladder.append(
            f'<div class="{row_class}">'
            f'<span class="ladder-num">{index}.</span>'
            f'<div class="ladder-body"><strong>{_e(item.get("title"))}</strong><p>{_e(item.get("why"))} {_e(item.get("action"))}</p></div>'
            f'<div class="ladder-meta"><span class="tag {"hot" if index == 1 else ""}">{_e(item.get("impact") or "à prioriser")}</span><span class="effort">{_e(item.get("effort") or "effort à qualifier")}</span></div>'
            "</div>"
        )
    if not ladder:
        ladder.append('<div class="empty-state">Aucune priorité mensuelle exploitable dans l\'export.</div>')
    return f"""
    <section class="page">
      {_runhead("III. État des lieux")}
      <header>
        <p class="eyebrow"><span class="num">III.</span> État des lieux</p>
        <h2 class="section-title"><em>Les chiffres</em> qui comptent,<br>et la décision qu'ils dictent.</h2>
      </header>
      <div class="diag-grid">
        <div class="diag-statement">
          <h3 class="diag-headline">Le site dispose déjà de la visibilité.<br><em>L'écart se gagne au clic</em>, pas à la création.</h3>
          <p>La marge la plus rapide à activer se trouve dans la réécriture de titres et de meta descriptions des pages les mieux exposées, avant tout effort éditorial.</p>
          <p>La synthèse de droite donne les indicateurs racines. La décision en bas de page ordonne les leviers du plus rentable en effort/impact au plus structurant.</p>
          <div class="rule-short" style="margin-top: 6px;"></div>
          <p class="smallcaps ink" style="text-transform: uppercase; letter-spacing: 0.16em; font-weight: 700; font-size: 11px; color: var(--ink);">Décision rapide — à lire en 30 secondes</p>
        </div>
        <div class="kpi-stack">
          {_render_kpi_row("Pages indexées analysées", _kpi_metric(report, "Pages analysées"), f'Dont {_kpi_metric(report, "Pages prioritaires")} prioritaires', "")}
          {_render_kpi_row("Impressions", _kpi_metric(report, "Impressions"), "visibilité brute", "is-accent")}
          {_render_kpi_row("Clics", _kpi_metric(report, "Clics totaux"), "période fournie", "")}
          {_render_kpi_row("CTR moyen", _kpi_metric(report, "Taux de clic"), "signal de clic", "is-hot")}
          {_render_kpi_row("Position moyenne", _kpi_metric(report, "Position moyenne"), "moyenne pondérée", "")}
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
    <section class="page">
      {_runhead("IV. L'écart")}
      <header>
        <p class="eyebrow"><span class="num">IV.</span> L'écart</p>
        <h2 class="section-title"><em>Position contre clic</em><br>— ce que dit le nuage.</h2>
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
    card_class = "page-card"
    if not compact and (index <= 2 or _priority_tone(page) == "high"):
        card_class += " is-top"
    if compact:
        card_class += " compact"
    axis_text = _axis_percent(axis_max)
    return f"""
      <article class="{card_class}">
        <div class="page-card-rank">{_roman_lower(index)}.</div>
        <div class="page-card-main">
          <div class="page-card-head">
            <div>
              <h3 class="page-card-title">{_e(_short_label(page))}</h3>
              <span class="page-card-url">{_e(compact_url_for_display(str(page.get('url') or '')))}</span>
            </div>
            <div class="page-card-tag"><span class="tag {tag_class}">{_e(priority_display_label(str(page.get("priority", "p3")), str(page.get("priority_label", ""))))}</span><span class="effort smallcaps">{_e(page.get("effort") or "à activer")}</span></div>
          </div>
          <div class="metric-row">
            <div class="metric"><span class="metric-label">Clics</span><span class="metric-value">{_e(clicks)}</span></div>
            <div class="metric"><span class="metric-label">Impressions</span><span class="metric-value">{_e(impressions)}</span></div>
            <div class="metric"><span class="metric-label">CTR</span><span class="metric-value">{_e(ctr)}</span></div>
            <div class="metric"><span class="metric-label">Position</span><span class="metric-value">{_e(str(position).replace(".", ","))}</span></div>
            <div class="metric delta"><span class="metric-label">{"Gain / mois" if compact else "Gain estimé / mois"}</span><span class="metric-value">{_e(_gain_label(gain).lstrip("+"))}</span></div>
          </div>
          <div class="page-card-body">
            <div class="page-card-col">
              {'' if compact else '<span class="field-label">Diagnostic</span>'}
              {'' if compact else f'<p class="field-text">{_e(page.get("diagnostic") or page.get("why") or "")}</p>'}
              <span class="field-label" style="margin-top: 8px;">Action</span>
              <p class="field-text">{_inline(page.get("recommendation") or "Action à confirmer avec la SERP cible.")}</p>
              {f'<div class="note-block"><b>SERP enrichie à confirmer.</b> Snippet à lire avant tout test.</div>' if page.get("serp_anomaly") else ''}
            </div>
            <div class="page-card-col">
              <span class="field-label">CTR actuel vs cible</span>
              <div class="ctr-row">
                <div class="ctr-row-stat"><span>0%</span><span><b>{_e(ctr)}</b> → <b>{format_percent(ctr_median(pos_value) * 0.65)} — {format_percent(ctr_p75(pos_value))}</b></span><span>{axis_text}</span></div>
                <div class="ctr-track"><div class="ctr-band" style="left:{target_low:.1f}%;right:{100 - target_high:.1f}%"></div><div class="ctr-now" style="width:{now_width:.1f}%"></div></div>
              </div>
              <p class="gain-line"><b>{_e(_gain_label(gain))}</b> clics / mois <em>· horizon 6–8 semaines</em></p>
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
    page_index = "1 / 3" if start == 0 else "2 / 3"
    heading = (
        '<h2 class="section-title"><em>Dix pages,</em><br>par ordre de récupération.</h2>'
        '<p class="lede">Pour chaque page : position observée, CTR actuel comparé à la fourchette attendue, action recommandée et gain mensuel estimé.</p>'
        if not compact
        else '<h2 class="section-title-sm" style="margin-top: 8px;"><em>Pages visibles, sous-cliquées</em> — angle ou contenu à clarifier.</h2>'
    )
    return f"""
    <section class="page">
      {_runhead(f"V. Pages prioritaires · {page_index}")}
      <header>
        <p class="eyebrow"><span class="num">V.</span> Pages prioritaires <span style="margin-left: 8px; color: var(--muted-soft);">— {label}</span></p>
        {heading}
      </header>
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
      <article class="snippet-block">
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
    <section class="page">
      {_runhead("VI. Réécriture des résultats Google")}
      <header>
        <p class="eyebrow"><span class="num">VI.</span> Réécriture des résultats Google</p>
        <h2 class="section-title"><em>Avant / après</em><br>— ce que Google montrera.</h2>
        <p class="lede">Les propositions conservent les pages sélectionnées par le pipeline et ciblent un meilleur taux de clic.</p>
      </header>
      {body}
      {_pagenum(site_name, 8)}
    </section>
"""


def _render_queries(report: dict, site_name: str) -> str:
    rows = []
    for row in list(report.get("top_query_opportunities") or [])[:15]:
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
    <section class="page">
      {_runhead("VII. Requêtes exploitables")}
      <header>
        <p class="eyebrow"><span class="num">VII.</span> Requêtes exploitables</p>
        <h2 class="section-title"><em>Quinze requêtes</em><br>à traiter dès maintenant.</h2>
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
    <section class="page">
      {_runhead("VIII. Pages en concurrence")}
      <header>
        <p class="eyebrow"><span class="num">VIII.</span> Pages en concurrence</p>
        <h2 class="section-title"><em>Clusters et variantes</em><br>— ce qui se chevauche.</h2>
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
    <section class="page">
      {_runhead("IX. Opportunités commerciales")}
      <header>
        <p class="eyebrow"><span class="num">IX.</span> Opportunités commerciales</p>
        <h2 class="section-title"><em>Pages à intention</em><br>business — affiliation et tests.</h2>
        <p class="lede">Hors top 10 prioritaire. À intégrer en relais des actions principales : chaque page demande un verdict d'expert, un tableau décisionnel et un prochain clic logique.</p>
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
    return f"""
    <section class="page">
      {_runhead("X. Plan d'exécution")}
      <header>
        <p class="eyebrow"><span class="num">X.</span> Plan d'exécution</p>
        <h2 class="section-title"><em>Quatre semaines</em><br>pour activer la marge.</h2>
      </header>
      <div class="plan-grid">{''.join(week_html)}</div>
      <header style="margin-top:14px"><p class="eyebrow smallcaps">Lectures à conserver à l'esprit</p></header>
      <div class="lectures"><div class="col"><h4>Ce que ce rapport dit</h4><ul><li>Le <b>potentiel théorique</b> est un ordre de grandeur, pas une promesse.</li><li>Les <b>positions</b> sont des moyennes GSC.</li><li>Les actions doivent être validées après mise en ligne.</li></ul></div><div class="col"><h4>Ce qu'il ne dit pas</h4><ul><li>Il ne remplace pas un audit technique complet.</li><li>Les signaux de cannibalisation nécessitent une validation manuelle.</li><li>Sans export précédent, il ne diagnostique pas une baisse.</li></ul></div></div>
      <div class="closing"><div><h3>Prochain rapport — dans 4 semaines.</h3><p>Relancer GSC avec un export de comparaison pour vérifier les effets page par page.</p></div><div class="closing-mark"><strong>Prospect Machine</strong>contact@prospect-machine.fr</div></div>
      {_pagenum(site_name, 12)}
    </section>
"""


def render_gsc_report(report: dict, *, lang: str = "fr") -> str:
    """Render a standalone HTML document using the GSC handoff design."""
    active_lang = sanitize_gsc_language(str(report.get("lang") or lang))
    _ = gsc_gettext(active_lang)
    site_name = _domain(report.get("site_name"))
    title = f"Rapport d'opportunités SEO — {site_name} · Prospect Machine"
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
  <meta charset="utf-8">
  <title>{_e(_(title))}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <style>{GSC_REPORT_STYLE}</style>
</head>
<body style="font-family: Inter">
  {_render_toolbar(report)}
  <div class="doc">
    {''.join(sections)}
  </div>
  <script>
    function exportPDF() {{
      window.print();
    }}
  </script>
</body>
</html>"""
