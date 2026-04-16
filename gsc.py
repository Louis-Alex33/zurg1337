from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

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
    extra_stopwords = {word.strip().lower() for word in niche_stopwords or [] if word.strip()}
    if auto_niche_stopwords:
        extra_stopwords.update(derive_auto_stopwords(current))
    possible_overlap = (
        detect_possible_query_overlap(
            current,
            parse_queries_csv(queries_csv),
            extra_stopwords=extra_stopwords,
        )
        if queries_csv
        else {}
    )
    results = analyze_pages(current=current, previous=previous, possible_overlap=possible_overlap)
    write_csv(results, output_csv)
    if output_json:
        write_json(results, output_json)
    if output_html:
        write_html(results, output_html, site_name=site_name)
    return results


def detect_delimiter(filepath: str) -> str:
    with Path(filepath).open("r", encoding="utf-8-sig") as handle:
        first_line = handle.readline()
    return "\t" if "\t" in first_line else ","


def normalize_header(header: str) -> str:
    value = header.strip().lower().replace("\ufeff", "")
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


def parse_pages_csv(filepath: str | None) -> list[GSCPageData]:
    if not filepath:
        return []
    delimiter = detect_delimiter(filepath)
    pages: list[GSCPageData] = []
    with Path(filepath).open("r", encoding="utf-8-sig") as handle:
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
    delimiter = detect_delimiter(filepath)
    queries: list[GSCQueryData] = []
    with Path(filepath).open("r", encoding="utf-8-sig") as handle:
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


def write_html(results: list[GSCPageAnalysis], output_path: str, site_name: str = "") -> Path:
    output_file = ensure_parent_dir(output_path)
    high = [item for item in results if item.priority == "HIGH"]
    medium = [item for item in results if item.priority == "MEDIUM"]
    dead = [item for item in results if item.priority == "DEAD"]
    overlap = [item for item in results if item.possible_overlap_queries]
    total_recoverable = sum(item.estimated_recoverable_clicks or 0 for item in results)
    title = f"Rapport GSC - {site_name}" if site_name else "Rapport GSC"

    def render_rows(items: list[GSCPageAnalysis]) -> str:
        rows: list[str] = []
        for item in items:
            rows.append(
                "<tr>"
                f"<td><a href='{item.url}'>{item.url}</a></td>"
                f"<td>{item.priority}</td>"
                f"<td>{item.score}</td>"
                f"<td>{item.position:.1f}</td>"
                f"<td>{item.ctr:.1%}</td>"
                f"<td>{item.clicks}</td>"
                f"<td>{item.impressions}</td>"
                f"<td>{item.estimated_recoverable_clicks or ''}</td>"
                f"<td>{item.impact_label}</td>"
                "</tr>"
            )
        return "\n".join(rows)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #17212b; background: #f7f7f2; }}
    h1, h2 {{ color: #17313e; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: white; border: 1px solid #d8ddd3; border-radius: 10px; padding: 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ padding: 10px; border: 1px solid #d8ddd3; text-align: left; vertical-align: top; }}
    th {{ background: #ecf0e3; }}
    a {{ color: #0b5c76; }}
    .note {{ background: #fff9e8; border-left: 4px solid #c38b00; padding: 12px 16px; margin-bottom: 24px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="note">
    Les estimations ci-dessous portent sur la periode analysee dans les exports fournis.
    Les cas de chevauchement page/requete sont des heuristiques de verification, pas une preuve de cannibalisation.
  </div>
  <div class="grid">
    <div class="card"><strong>{len(results)}</strong><br>Pages analysees</div>
    <div class="card"><strong>{len(high)}</strong><br>Priorite haute</div>
    <div class="card"><strong>{len(medium)}</strong><br>Priorite moyenne</div>
    <div class="card"><strong>{len(dead)}</strong><br>Pages a reevaluer</div>
    <div class="card"><strong>{len(overlap)}</strong><br>Chevauchements possibles</div>
    <div class="card"><strong>+{total_recoverable}</strong><br>Clics recuperables estimes</div>
  </div>
  <h2>Pages a traiter en priorite</h2>
  <table>
    <tr>
      <th>URL</th>
      <th>Priorite</th>
      <th>Score</th>
      <th>Position</th>
      <th>CTR</th>
      <th>Clics</th>
      <th>Impressions</th>
      <th>Clics recuperables</th>
      <th>Lecture commerciale prudente</th>
    </tr>
    {render_rows(high + medium)}
  </table>
</body>
</html>"""
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(html)
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
