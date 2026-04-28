from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from config import GSC_CANNIBAL_STOPWORDS, GSC_STRUCTURAL_SLUGS, GSC_TECHNICAL_URL_PATTERNS, GSC_TECHNICAL_URL_SUFFIXES
from io_helpers import ensure_parent_dir
from models import GSCPageAnalysis, GSCPageData, GSCQueryData
from scoring import gsc_score_ctr, gsc_score_decline, gsc_score_impressions, gsc_score_position, is_dead_gsc_page
from utils import CLIError, coerce_float, coerce_int

PAGINATION_RE = re.compile(r"/page/\d+/?$")
EXPECTED_CTR_BY_POSITION = {
    1: 0.30,
    2: 0.18,
    3: 0.12,
    4: 0.08,
    5: 0.06,
    6: 0.05,
    7: 0.04,
    8: 0.03,
    9: 0.025,
    10: 0.02,
    11: 0.015,
    12: 0.013,
    13: 0.011,
    14: 0.010,
    15: 0.009,
    16: 0.008,
    17: 0.007,
    18: 0.006,
    19: 0.005,
    20: 0.004,
}


def run_gsc_analysis(
    current_csv: str,
    previous_csv: str | None = None,
    queries_csv: str | None = None,
    output_csv: str = "gsc_report.csv",
    output_html: str | None = None,
    output_json: str | None = None,
    site_name: str = "",
    niche_stopwords: list[str] | None = None,
    auto_niche_stopwords: bool = False,
) -> list[GSCPageAnalysis]:
    current = parse_pages_csv(current_csv)
    previous = parse_pages_csv(previous_csv) if previous_csv else None
    effective_queries_csv = queries_csv
    if not effective_queries_csv and gsc_archive_contains(current_csv, "queries"):
        effective_queries_csv = current_csv
    extra_stopwords = {word.strip().lower() for word in niche_stopwords or [] if word.strip()}
    if auto_niche_stopwords:
        extra_stopwords.update(derive_auto_stopwords(current))
    possible_overlap = (
        detect_possible_query_overlap(
            current,
            parse_queries_csv(effective_queries_csv),
            extra_stopwords=extra_stopwords,
        )
        if effective_queries_csv
        else {}
    )
    results = analyze_pages(current=current, previous=previous, possible_overlap=possible_overlap)
    write_csv(results, output_csv)
    if output_json:
        write_json(results, output_json)
    if output_html:
        write_html(
            results,
            output_html,
            site_name=site_name,
            has_previous=bool(previous_csv),
            has_queries=bool(effective_queries_csv),
        )
    return results


def detect_delimiter(filepath: str) -> str:
    with Path(filepath).open("r", encoding="utf-8-sig") as handle:
        first_line = handle.readline()
    return "\t" if "\t" in first_line else ","


def detect_delimiter_from_text(text: str) -> str:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    return "\t" if "\t" in first_line else ","


def gsc_archive_contains(filepath: str | None, kind: str) -> bool:
    if not filepath or Path(filepath).suffix.lower() != ".zip":
        return False
    try:
        with ZipFile(filepath) as archive:
            return find_gsc_csv_member(archive, kind) is not None
    except (BadZipFile, FileNotFoundError):
        return False


def read_gsc_csv_text(filepath: str, kind: str) -> str:
    path = Path(filepath)
    if path.suffix.lower() != ".zip":
        return path.read_text(encoding="utf-8-sig")

    try:
        with ZipFile(path) as archive:
            member = find_gsc_csv_member(archive, kind)
            if not member:
                raise CLIError(f"Impossible de trouver le CSV {kind} dans l'export ZIP: {filepath}")
            return archive.read(member).decode("utf-8-sig", errors="replace")
    except BadZipFile as exc:
        raise CLIError(f"Export ZIP GSC illisible: {filepath}") from exc


def find_gsc_csv_member(archive: ZipFile, kind: str) -> str | None:
    for name in archive.namelist():
        normalized = normalize_archive_name(Path(name).name)
        if not normalized.endswith(".csv"):
            continue
        if kind == "pages" and ("pages" in normalized or "top pages" in normalized):
            return name
        if kind == "queries" and (
            "requete" in normalized
            or "requetes" in normalized
            or "queries" in normalized
            or "query" in normalized
        ):
            return name
    return None


def normalize_archive_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_name.strip().lower()


def normalize_header(header: str) -> str:
    value = strip_accents(header).strip().lower().replace("\ufeff", "")
    mapping = {
        "average position": "position",
        "clics": "clicks",
        "clicks": "clicks",
        "ctr": "ctr",
        "impressions": "impressions",
        "page": "page",
        "pages": "page",
        "pages les plus populaires": "page",
        "position": "position",
        "position moyenne": "position",
        "query": "query",
        "requete": "query",
        "requete les plus frequentes": "query",
        "requete les plus fréquentes": "query",
        "requetes": "query",
        "requetes les plus frequentes": "query",
        "requêtes": "query",
        "top pages": "page",
        "top queries": "query",
        "url": "page",
    }
    return mapping.get(value, value)


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def parse_pages_csv(filepath: str | None) -> list[GSCPageData]:
    if not filepath:
        return []
    text = read_gsc_csv_text(filepath, "pages")
    delimiter = detect_delimiter_from_text(text)
    pages: list[GSCPageData] = []
    with io.StringIO(text) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise CLIError(f"CSV GSC vide ou illisible: {filepath}")
        headers = {normalize_header(name): name for name in reader.fieldnames}
        required = {"page", "clicks", "impressions", "ctr", "position"}
        if not required.issubset(headers):
            missing = ", ".join(sorted(required - set(headers)))
            raise CLIError(f"Colonnes manquantes dans {filepath}: {missing}")

        for row in reader:
            try:
                url = (row.get(headers["page"]) or "").strip()
                if not url or is_technical_url(url) or is_structural_url(url):
                    continue
                ctr = coerce_float(row.get(headers["ctr"]), default=0.0)
                if ctr > 1:
                    ctr = ctr / 100
                pages.append(
                    GSCPageData(
                        url=url,
                        clicks=coerce_int(row.get(headers["clicks"]), default=0),
                        impressions=coerce_int(row.get(headers["impressions"]), default=0),
                        ctr=ctr,
                        position=coerce_float(row.get(headers["position"]), default=0.0),
                    )
                )
            except ValueError:
                continue
    return pages


def parse_queries_csv(filepath: str | None) -> list[GSCQueryData]:
    if not filepath:
        return []
    text = read_gsc_csv_text(filepath, "queries")
    delimiter = detect_delimiter_from_text(text)
    queries: list[GSCQueryData] = []
    with io.StringIO(text) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise CLIError(f"CSV GSC vide ou illisible: {filepath}")
        headers = {normalize_header(name): name for name in reader.fieldnames}
        required = {"query", "clicks", "impressions", "ctr", "position"}
        if not required.issubset(headers):
            missing = ", ".join(sorted(required - set(headers)))
            raise CLIError(f"Colonnes manquantes dans {filepath}: {missing}")

        for row in reader:
            try:
                query = (row.get(headers["query"]) or "").strip()
                if not query:
                    continue
                ctr = coerce_float(row.get(headers["ctr"]), default=0.0)
                if ctr > 1:
                    ctr = ctr / 100
                queries.append(
                    GSCQueryData(
                        query=query,
                        clicks=coerce_int(row.get(headers["clicks"]), default=0),
                        impressions=coerce_int(row.get(headers["impressions"]), default=0),
                        ctr=ctr,
                        position=coerce_float(row.get(headers["position"]), default=0.0),
                    )
                )
            except ValueError:
                continue
    return queries


def is_technical_url(url: str) -> bool:
    lower = url.lower()
    if any(pattern in lower for pattern in GSC_TECHNICAL_URL_PATTERNS):
        return True
    if any(lower.endswith(suffix) for suffix in GSC_TECHNICAL_URL_SUFFIXES):
        return True
    return bool(PAGINATION_RE.search(lower))


def is_structural_url(url: str) -> bool:
    without_domain = url.replace("https://", "").replace("http://", "").rstrip("/")
    slug = without_domain.split("/")[-1].lower()
    return slug in GSC_STRUCTURAL_SLUGS


def extract_slug_keywords(url: str, stopwords: set[str] | frozenset[str] = frozenset()) -> set[str]:
    path = url.replace("https://", "").replace("http://", "").split("?")[0]
    parts = path.replace("/", " ").replace("-", " ").replace("_", " ").split()
    return {
        word.lower()
        for word in parts
        if len(word) > 4 and word.lower() not in stopwords
    }


def derive_auto_stopwords(pages: list[GSCPageData], threshold: float = 0.6) -> set[str]:
    """Retourne les mots apparaissant dans >= threshold des URLs du corpus."""
    if not pages:
        return set()

    token_counts: dict[str, int] = defaultdict(int)
    for page in pages:
        for token in extract_slug_keywords(page.url):
            token_counts[token] += 1

    page_count = len(pages)
    return {
        token
        for token, count in token_counts.items()
        if page_count and (count / page_count) >= threshold
    }


def detect_possible_query_overlap(
    pages: list[GSCPageData],
    queries: list[GSCQueryData],
    extra_stopwords: set[str] = frozenset(),
) -> dict[str, list[str]]:
    stopwords = {word.lower() for word in GSC_CANNIBAL_STOPWORDS}
    stopwords.update(word.lower() for word in extra_stopwords)
    page_keywords = {
        page.url: extract_slug_keywords(page.url, stopwords=stopwords)
        for page in pages
        if page.position <= 40
    }
    possible_overlap: dict[str, list[str]] = defaultdict(list)
    query_impressions = {query.query: query.impressions for query in queries}

    for query in queries:
        words = query.query.lower().split()
        if len(words) < 2 or query.impressions < 10 or query.position > 20:
            continue
        significant_words = {
            word for word in words if len(word) > 4 and word not in stopwords
        }
        if not significant_words:
            continue
        min_overlap = 2 if len(significant_words) >= 3 else 1
        matching_pages = [
            url for url, keywords in page_keywords.items() if len(significant_words & keywords) >= min_overlap
        ]
        if len(matching_pages) >= 2:
            for url in matching_pages:
                possible_overlap[url].append(query.query)

    return {
        url: sorted(set(queries_for_url), key=lambda query: query_impressions.get(query, 0), reverse=True)
        for url, queries_for_url in possible_overlap.items()
    }


def analyze_pages(
    current: list[GSCPageData],
    previous: list[GSCPageData] | None,
    possible_overlap: dict[str, list[str]],
) -> list[GSCPageAnalysis]:
    previous_map = {page.url: page for page in previous or []}
    max_impressions = max((page.impressions for page in current), default=1)
    results: list[GSCPageAnalysis] = []

    for page in current:
        analysis = GSCPageAnalysis(
            url=page.url,
            clicks=page.clicks,
            impressions=page.impressions,
            ctr=page.ctr,
            position=page.position,
            possible_overlap_queries=possible_overlap.get(page.url, []),
        )
        previous_page = previous_map.get(page.url)
        if previous_page:
            analysis.prev_clicks = previous_page.clicks
            analysis.prev_impressions = previous_page.impressions
            analysis.prev_position = previous_page.position
            analysis.click_delta = page.clicks - previous_page.clicks
            analysis.impression_delta = page.impressions - previous_page.impressions
            analysis.position_delta = round(page.position - previous_page.position, 1)

        analysis.score = round(
            gsc_score_position(page.position)
            + gsc_score_impressions(page.impressions, max_impressions)
            + gsc_score_ctr(page.ctr, page.position)
            + gsc_score_decline(analysis.click_delta, analysis.impression_delta),
            1,
        )
        analysis.category = categorize_page(analysis)
        analysis.priority = priority_for_page(analysis)
        analysis.actions = suggest_actions(analysis)
        analysis.estimated_recoverable_clicks, analysis.impact_label = estimate_recoverable_clicks(analysis)
        results.append(analysis)

    results.sort(key=lambda item: (0 if item.priority == "DEAD" else 1, -item.score))
    return results


def categorize_page(analysis: GSCPageAnalysis) -> str:
    if is_dead_gsc_page(analysis):
        return "MORT - fusionner, rediriger ou supprimer"
    if analysis.score >= 60:
        return "PRIORITE HAUTE"
    if analysis.score >= 40:
        return "PRIORITE MOYENNE"
    if analysis.score >= 20:
        return "A SURVEILLER"
    return "OK"


def priority_for_page(analysis: GSCPageAnalysis) -> str:
    if is_dead_gsc_page(analysis):
        return "DEAD"
    if analysis.score >= 60:
        return "HIGH"
    if analysis.score >= 40:
        return "MEDIUM"
    return "LOW"


def suggest_actions(analysis: GSCPageAnalysis) -> list[str]:
    actions: list[str] = []
    if is_dead_gsc_page(analysis):
        return [
            "Verifier si cette page peut etre fusionnee avec une page plus forte",
            "Sinon envisager une redirection 301 ou un retrait propre",
        ]

    position_bucket = max(1, min(10, round(analysis.position)))
    expected_ctr = EXPECTED_CTR_BY_POSITION.get(position_bucket, 0.015)
    if analysis.ctr < expected_ctr * 0.6:
        actions.append("Revoir title et meta description pour mieux convertir les impressions")
    if 4 <= analysis.position <= 10:
        actions.append("Densifier le contenu avec sections, FAQ et signaux de fraicheur")
    elif 10 < analysis.position <= 20:
        actions.append("Renforcer fortement le contenu et le maillage interne")
    if analysis.click_delta is not None and analysis.click_delta < -10:
        actions.append("Verifier la fraicheur du contenu et les changements de SERP")
    if analysis.impressions > 500 and analysis.clicks < 10:
        actions.append("Tester un angle de title plus explicite sur l'intention")
    if analysis.possible_overlap_queries:
        actions.append(
            "Chevauchement page/requete possible a verifier avant de conclure a une cannibalisation"
        )
    if not actions:
        actions.append("RAS prioritaire sur la periode analysee")
    return actions


def estimate_recoverable_clicks(analysis: GSCPageAnalysis) -> tuple[int | None, str]:
    if is_dead_gsc_page(analysis) or analysis.impressions < 10:
        return None, ""

    position_bucket = max(1, min(20, round(analysis.position)))
    expected_ctr = EXPECTED_CTR_BY_POSITION.get(position_bucket, 0.004)
    ctr_gain = 0
    if analysis.ctr < expected_ctr * 0.9:
        ctr_gain = round(analysis.impressions * (expected_ctr - analysis.ctr))

    target_position = max(1, analysis.position - 3)
    target_bucket = max(1, min(20, round(target_position)))
    target_ctr = EXPECTED_CTR_BY_POSITION.get(target_bucket, 0.004)
    position_gain = round(analysis.impressions * max(0, target_ctr - analysis.ctr))

    best_gain = max(ctr_gain, position_gain)
    if best_gain <= 0:
        return None, ""

    if ctr_gain >= position_gain and ctr_gain > 0:
        label = (
            f"+{ctr_gain} clics recuperables estimes sur la periode analysee "
            f"si le CTR se rapproche de l'attendu a position {position_bucket}"
        )
    else:
        label = (
            f"+{position_gain} clics recuperables estimes sur la periode analysee "
            f"si la page gagne environ 3 positions"
        )
    return best_gain, label


def write_csv(results: list[GSCPageAnalysis], output_path: str) -> Path:
    output_file = ensure_parent_dir(output_path)
    fieldnames = [
        "priority",
        "score",
        "category",
        "url",
        "clicks",
        "impressions",
        "ctr",
        "position",
        "prev_clicks",
        "prev_impressions",
        "prev_position",
        "click_delta",
        "impression_delta",
        "position_delta",
        "estimated_recoverable_clicks",
        "impact_label",
        "possible_overlap_queries",
        "actions",
    ]
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "priority": item.priority,
                    "score": item.score,
                    "category": item.category,
                    "url": item.url,
                    "clicks": item.clicks,
                    "impressions": item.impressions,
                    "ctr": f"{item.ctr:.2%}",
                    "position": f"{item.position:.1f}",
                    "prev_clicks": item.prev_clicks or "",
                    "prev_impressions": item.prev_impressions or "",
                    "prev_position": f"{item.prev_position:.1f}" if item.prev_position is not None else "",
                    "click_delta": item.click_delta if item.click_delta is not None else "",
                    "impression_delta": item.impression_delta if item.impression_delta is not None else "",
                    "position_delta": item.position_delta if item.position_delta is not None else "",
                    "estimated_recoverable_clicks": item.estimated_recoverable_clicks or "",
                    "impact_label": item.impact_label,
                    "possible_overlap_queries": " | ".join(item.possible_overlap_queries),
                    "actions": " | ".join(item.actions),
                }
            )
    return output_file


def write_json(results: list[GSCPageAnalysis], output_path: str) -> Path:
    output_file = ensure_parent_dir(output_path)
    payload: list[dict[str, object]] = []
    for item in results:
        row = asdict(item)
        row["ctr"] = f"{item.ctr:.2%}"
        payload.append(row)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return output_file


def write_html(
    results: list[GSCPageAnalysis],
    output_path: str,
    site_name: str = "",
    has_previous: bool = False,
    has_queries: bool = False,
) -> Path:
    output_file = ensure_parent_dir(output_path)
    high = [item for item in results if item.priority == "HIGH"]
    medium = [item for item in results if item.priority == "MEDIUM"]
    dead = [item for item in results if item.priority == "DEAD"]
    overlap = [item for item in results if item.possible_overlap_queries]
    total_recoverable = sum(item.estimated_recoverable_clicks or 0 for item in results)
    declining = [
        item
        for item in results
        if (item.click_delta is not None and item.click_delta < 0)
        or (item.impression_delta is not None and item.impression_delta < 0)
        or (item.position_delta is not None and item.position_delta > 1)
    ]
    ctr_opportunities = [
        item
        for item in results
        if item.impressions >= 100
        and item.estimated_recoverable_clicks
        and any("CTR" in action or "title" in action.lower() for action in item.actions)
    ]
    near_page_one = [
        item
        for item in results
        if 4 <= item.position <= 20 and item.impressions >= 50 and item.priority != "DEAD"
    ]
    title = f"Plan d'action GSC - {site_name}" if site_name else "Plan d'action GSC"

    def metric_delta(item: GSCPageAnalysis) -> str:
        parts: list[str] = []
        if item.click_delta is not None:
            parts.append(f"Clics: {item.click_delta:+d}")
        if item.impression_delta is not None:
            parts.append(f"Impr.: {item.impression_delta:+d}")
        if item.position_delta is not None:
            direction = "moins bien" if item.position_delta > 0 else "mieux"
            parts.append(f"Position: {item.position_delta:+.1f} ({direction})")
        return " | ".join(parts) if parts else "Pas de comparaison fournie"

    def action_summary(item: GSCPageAnalysis) -> str:
        if item.actions:
            return item.actions[0]
        return "Verifier la page et choisir l'action editoriale la plus simple"

    def explain_reason(item: GSCPageAnalysis) -> str:
        reasons: list[str] = []
        if item.estimated_recoverable_clicks:
            reasons.append(item.impact_label)
        if 4 <= item.position <= 10:
            reasons.append("La page est deja proche du haut de page 1.")
        elif 10 < item.position <= 20:
            reasons.append("La page est en page 2 ou bas de page 1: le contenu et le maillage peuvent faire levier.")
        if item.ctr < 0.02 and item.impressions >= 100:
            reasons.append("Beaucoup d'impressions, mais peu de clics: le snippet merite d'etre retravaille.")
        if item.click_delta is not None and item.click_delta < 0:
            reasons.append("La page perd des clics par rapport a la periode precedente.")
        if item.possible_overlap_queries:
            reasons.append("Plusieurs pages semblent toucher des requetes proches: a verifier avant modification.")
        return " ".join(reasons) or "Signal faible: garder en surveillance plutot que traiter en priorite."

    def render_rows(items: list[GSCPageAnalysis], limit: int = 12) -> str:
        rows: list[str] = []
        for item in items[:limit]:
            actions = "".join(f"<li>{html.escape(action)}</li>" for action in item.actions[:3])
            overlap_note = (
                f"<p class='mini-note'>Requetes a verifier: {html.escape(' | '.join(item.possible_overlap_queries[:4]))}</p>"
                if item.possible_overlap_queries
                else ""
            )
            rows.append(
                "<tr>"
                f"<td><a href='{html.escape(item.url)}'>{html.escape(item.url)}</a></td>"
                f"<td><span class='pill pill-{html.escape(item.priority.lower())}'>{html.escape(item.priority)}</span></td>"
                f"<td><strong>{html.escape(action_summary(item))}</strong><ul>{actions}</ul>{overlap_note}</td>"
                f"<td>{html.escape(explain_reason(item))}</td>"
                f"<td>{item.position:.1f}</td>"
                f"<td>{item.ctr:.1%}</td>"
                f"<td>{item.clicks}</td>"
                f"<td>{item.impressions}</td>"
                f"<td>{item.estimated_recoverable_clicks or '-'}</td>"
                f"<td>{html.escape(metric_delta(item))}</td>"
                "</tr>"
            )
        return "\n".join(rows) or "<tr><td colspan='10'>Aucun element prioritaire dans cette section.</td></tr>"

    def render_section(title_text: str, intro: str, items: list[GSCPageAnalysis]) -> str:
        return f"""
  <section class="report-section">
    <h2>{html.escape(title_text)}</h2>
    <p class="section-intro">{html.escape(intro)}</p>
    <table>
      <tr>
        <th>Page</th>
        <th>Priorite</th>
        <th>Action conseillee</th>
        <th>Pourquoi cette page ressort</th>
        <th>Pos.</th>
        <th>CTR</th>
        <th>Clics</th>
        <th>Impr.</th>
        <th>Clics recup.</th>
        <th>Evolution</th>
      </tr>
      {render_rows(items)}
    </table>
  </section>
"""

    source_notes = [
        "Export Pages recent: obligatoire, c'est la photo actuelle.",
        "Export Pages precedent: fourni, donc les pertes et progressions sont comparees."
        if has_previous
        else "Export Pages precedent: non fourni, donc le rapport ne juge pas les pertes dans le temps.",
        "Export Requetes: fourni, donc le rapport signale les chevauchements possibles."
        if has_queries
        else "Export Requetes: non fourni, donc le rapport reste centre sur les pages.",
    ]
    priority_items = sorted(
        high + medium,
        key=lambda item: (item.estimated_recoverable_clicks or 0, item.score),
        reverse=True,
    )
    declining = sorted(
        declining,
        key=lambda item: (
            item.click_delta if item.click_delta is not None else 0,
            item.impression_delta if item.impression_delta is not None else 0,
        ),
    )
    ctr_opportunities = sorted(
        ctr_opportunities,
        key=lambda item: item.estimated_recoverable_clicks or 0,
        reverse=True,
    )
    near_page_one = sorted(near_page_one, key=lambda item: (item.position, -item.impressions))

    html_doc = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{ --ink: #18212f; --muted: #64748b; --line: #dbe3ea; --soft: #f6f8fb; --blue: #1d4ed8; --green: #047857; --amber: #92400e; --red: #991b1b; }}
    body {{ font-family: Inter, Arial, sans-serif; margin: 0; color: var(--ink); background: #eef3f7; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1 {{ margin: 0 0 10px; font-size: 2.4rem; line-height: 1; color: #0f172a; }}
    h2 {{ margin: 0 0 8px; color: #0f172a; }}
    a {{ color: var(--blue); word-break: break-word; }}
    .hero {{ background: white; border: 1px solid var(--line); border-radius: 8px; padding: 24px; margin-bottom: 18px; }}
    .lede {{ color: var(--muted); max-width: 760px; line-height: 1.55; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 12px; margin: 18px 0; }}
    .card {{ background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    .card strong {{ display: block; font-size: 1.7rem; color: #0f172a; }}
    .note {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 14px 16px; margin: 16px 0 0; }}
    .source-list {{ margin: 10px 0 0; padding-left: 20px; color: var(--muted); }}
    .report-section {{ background: white; border: 1px solid var(--line); border-radius: 8px; padding: 20px; margin-top: 18px; overflow-x: auto; }}
    .section-intro {{ color: var(--muted); margin: 0 0 14px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1080px; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 0.92rem; }}
    th {{ background: var(--soft); color: #334155; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    ul {{ margin: 8px 0 0; padding-left: 18px; color: var(--muted); }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 0.75rem; font-weight: 700; }}
    .pill-high {{ background: #fee2e2; color: var(--red); }}
    .pill-medium {{ background: #fef3c7; color: var(--amber); }}
    .pill-low {{ background: #dbeafe; color: var(--blue); }}
    .pill-dead {{ background: #e5e7eb; color: #374151; }}
    .mini-note {{ margin: 8px 0 0; color: var(--amber); font-size: 0.84rem; }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>{html.escape(title)}</h1>
      <p class="lede">Ce rapport transforme les exports Google Search Console en liste de pages a traiter. Il sert a reperer les pages proches d'un gain, les pertes a verifier et les snippets qui recoivent des impressions sans convertir en clics.</p>
      <div class="grid">
        <div class="card"><strong>{len(results)}</strong>Pages analysees</div>
        <div class="card"><strong>{len(high)}</strong>Actions prioritaires</div>
        <div class="card"><strong>{len(declining)}</strong>Pages en baisse</div>
        <div class="card"><strong>{len(ctr_opportunities)}</strong>Snippets a retravailler</div>
        <div class="card"><strong>{len(overlap)}</strong>Chevauchements a verifier</div>
        <div class="card"><strong>+{total_recoverable}</strong>Clics recuperables estimes</div>
      </div>
      <div class="note">
        Les gains sont des ordres de grandeur sur la periode exportee, pas une promesse. Les chevauchements sont des signaux de verification, pas une preuve automatique de cannibalisation.
        <ul class="source-list">
          {''.join(f'<li>{html.escape(note)}</li>' for note in source_notes)}
        </ul>
      </div>
    </section>

    {render_section("1. Pages a traiter en premier", "Commence ici: ce sont les pages avec le meilleur compromis volume, position et gain estime.", priority_items)}
    {render_section("2. Pages qui perdent du terrain", "A utiliser seulement si tu as fourni un export precedent. Ces pages meritent une verification de fraicheur, SERP, contenu et maillage.", declining)}
    {render_section("3. Snippets a retravailler", "Pages avec impressions mais CTR sous l'attendu. Souvent: title, meta description, angle ou promesse trop floue.", ctr_opportunities)}
    {render_section("4. Pages proches d'un gain SEO", "Pages deja positionnees entre 4 et 20: enrichissement, maillage interne et mise a jour peuvent etre plus rentables qu'une creation de contenu.", near_page_one)}
    {render_section("5. Pages faibles a reevaluer", "Pages sans traction suffisante: verifier si elles doivent etre fusionnees, redirigees ou laissees hors priorite.", dead)}
    {render_section("6. Chevauchements possibles", "A regarder manuellement avant de parler de cannibalisation. Le rapport signale seulement des requetes qui semblent toucher plusieurs URLs.", overlap)}
  </main>
</body>
</html>"""
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(html_doc)
    return output_file


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GSC analysis helper")
    parser.add_argument("current", help="Export GSC pages - periode recente")
    parser.add_argument("previous", nargs="?", help="Export GSC pages - periode precedente")
    parser.add_argument("-q", "--queries", help="Export GSC requetes")
    parser.add_argument("-o", "--output", default="gsc_report.csv", help="CSV de sortie")
    parser.add_argument("--html", dest="html_output", help="Rapport HTML")
    parser.add_argument("--json", dest="json_output", help="Rapport JSON")
    parser.add_argument("--site", default="", help="Nom du site pour le rapport")
    parser.add_argument(
        "--niche-stopwords",
        type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
    )
    parser.add_argument("--auto-niche-stopwords", action="store_true")
    return parser
