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
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile

from config import GSC_CANNIBAL_STOPWORDS, GSC_STRUCTURAL_SLUGS, GSC_TECHNICAL_URL_PATTERNS, GSC_TECHNICAL_URL_SUFFIXES
from io_helpers import ensure_parent_dir
from labels import EMPTY_SECTION_MESSAGES, SECTION_INTROS, translate
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
    graphique_csv: str | None = None,
    pays_csv: str | None = None,
    appareils_csv: str | None = None,
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
    effective_graphique_csv = graphique_csv
    if not effective_graphique_csv and gsc_archive_contains(current_csv, "graphique"):
        effective_graphique_csv = current_csv
    effective_pays_csv = pays_csv
    if not effective_pays_csv and gsc_archive_contains(current_csv, "pays"):
        effective_pays_csv = current_csv
    effective_appareils_csv = appareils_csv
    if not effective_appareils_csv and gsc_archive_contains(current_csv, "appareils"):
        effective_appareils_csv = current_csv
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
            graphique_data=load_graphique(effective_graphique_csv),
            pays_data=load_pays(effective_pays_csv),
            appareils_data=load_appareils(effective_appareils_csv),
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
        if kind == "graphique" and (
            "graphique" in normalized
            or "dates" in normalized
            or "date" in normalized
            or "chart" in normalized
        ):
            return name
        if kind == "pays" and ("pays" in normalized or "country" in normalized or "countries" in normalized):
            return name
        if kind == "appareils" and (
            "appareil" in normalized
            or "appareils" in normalized
            or "device" in normalized
            or "devices" in normalized
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
        "appareil": "device",
        "appareils": "device",
        "country": "country",
        "clics": "clicks",
        "clicks": "clicks",
        "ctr": "ctr",
        "date": "date",
        "device": "device",
        "jour": "date",
        "impressions": "impressions",
        "page": "page",
        "pages": "page",
        "pages les plus populaires": "page",
        "pays": "country",
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


def load_graphique(filepath: str | None) -> list[dict[str, object]]:
    """Retourne les points du graphique GSC sous forme {date, clics, impressions}."""
    if not filepath:
        return []
    try:
        text = read_gsc_csv_text(str(filepath), "graphique")
    except (FileNotFoundError, CLIError):
        return []
    delimiter = detect_delimiter_from_text(text)
    rows: list[dict[str, object]] = []
    with io.StringIO(text) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            return []
        headers = {normalize_header(name): name for name in reader.fieldnames}
        if "date" not in headers or "clicks" not in headers:
            return []
        for row in reader:
            date_value = (row.get(headers["date"]) or "").strip()
            if not date_value:
                continue
            rows.append(
                {
                    "date": date_value,
                    "clics": coerce_int(row.get(headers["clicks"]), default=0),
                    "impressions": coerce_int(row.get(headers.get("impressions", "")), default=0),
                }
            )
    return rows[-90:]


def load_pays(filepath: str | None) -> list[dict[str, object]]:
    """Retourne liste de dicts {pays, clics, impressions, ctr, position}."""
    return _load_dimension(filepath, kind="pays", dimension_key="country", output_key="pays")[:5]


def load_appareils(filepath: str | None) -> list[dict[str, object]]:
    """Retourne liste de dicts {appareil, clics, impressions, ctr, position}."""
    return _load_dimension(filepath, kind="appareils", dimension_key="device", output_key="appareil")


def _load_dimension(
    filepath: str | None,
    kind: str,
    dimension_key: str,
    output_key: str,
) -> list[dict[str, object]]:
    if not filepath:
        return []
    try:
        text = read_gsc_csv_text(str(filepath), kind)
    except (FileNotFoundError, CLIError):
        return []
    delimiter = detect_delimiter_from_text(text)
    rows: list[dict[str, object]] = []
    with io.StringIO(text) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            return []
        headers = {normalize_header(name): name for name in reader.fieldnames}
        required = {dimension_key, "clicks", "impressions", "ctr", "position"}
        if not required.issubset(headers):
            return []
        for row in reader:
            label = (row.get(headers[dimension_key]) or "").strip()
            if not label:
                continue
            ctr = coerce_float(row.get(headers["ctr"]), default=0.0)
            if ctr > 1:
                ctr = ctr / 100
            rows.append(
                {
                    output_key: label,
                    "clics": coerce_int(row.get(headers["clicks"]), default=0),
                    "impressions": coerce_int(row.get(headers["impressions"]), default=0),
                    "ctr": ctr,
                    "position": coerce_float(row.get(headers["position"]), default=0.0),
                }
            )
    return sorted(rows, key=lambda row: int(row["clics"]), reverse=True)


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
        actions.append("Revoir title et méta description pour mieux convertir les impressions")
    if 4 <= analysis.position <= 10:
        actions.append("Densifier le contenu avec sections, FAQ et signaux de fraîcheur")
    elif 10 < analysis.position <= 20:
        actions.append("Renforcer fortement le contenu et le maillage interne")
    if analysis.click_delta is not None and analysis.click_delta < -10:
        actions.append("Vérifier la fraîcheur du contenu et les changements de SERP")
    if analysis.impressions > 500 and analysis.clicks < 10:
        actions.append("Tester un angle de title plus explicite sur l'intention")
    if analysis.possible_overlap_queries:
        actions.append(
            "Chevauchement page/requête possible à vérifier avant de conclure à une cannibalisation"
        )
    if not actions:
        actions.append("RAS prioritaire sur la période analysée")
    return list(dict.fromkeys(actions))


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
            f"+{ctr_gain} clics récupérables estimés sur la période analysée "
            f"si le CTR se rapproche de l’attendu à position {position_bucket}"
        )
    else:
        label = (
            f"+{position_gain} clics récupérables estimés sur la période analysée "
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


def build_report(
    pages_csv: str | Path | list[GSCPageAnalysis] | None = None,
    previous_csv: str | Path | None = None,
    queries_csv: str | Path | None = None,
    graphique_csv: str | Path | None = None,
    pays_csv: str | Path | None = None,
    appareils_csv: str | Path | None = None,
    *,
    site_name: str = "",
    has_previous: bool | None = None,
    has_queries: bool | None = None,
    graphique_data: list[dict[str, object]] | None = None,
    pays_data: list[dict[str, object]] | None = None,
    appareils_data: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if isinstance(pages_csv, list):
        results = pages_csv
    elif pages_csv:
        current = parse_pages_csv(str(pages_csv))
        queries = parse_queries_csv(str(queries_csv)) if queries_csv else []
        overlap = detect_possible_query_overlap(current, queries) if queries else {}
        previous = parse_pages_csv(str(previous_csv)) if previous_csv else None
        results = analyze_pages(current=current, previous=previous, possible_overlap=overlap)
    else:
        results = []

    graphique = graphique_data if graphique_data is not None else load_graphique(str(graphique_csv)) if graphique_csv else []
    pays = pays_data if pays_data is not None else load_pays(str(pays_csv)) if pays_csv else []
    appareils = appareils_data if appareils_data is not None else load_appareils(str(appareils_csv)) if appareils_csv else []

    title = f"Rapport SEO — {site_name}" if site_name else "Rapport SEO"
    total_clicks = sum(item.clicks for item in results)
    total_impressions = sum(item.impressions for item in results)
    avg_ctr = (total_clicks / total_impressions) if total_impressions else 0.0
    avg_position = (
        sum(item.position * item.impressions for item in results) / total_impressions
        if total_impressions
        else 0.0
    )
    total_recoverable = sum(item.estimated_recoverable_clicks or 0 for item in results)

    sections = assign_report_sections(results)
    return {
        "title": title,
        "site_name": site_name,
        "generated_at": datetime.now().strftime("%d/%m/%Y"),
        "period_label": "Période analysée: export Google Search Console fourni",
        "source_notes": [
            "Export Pages récent: obligatoire, c'est la photo actuelle.",
            (
                "Export Pages précédent: fourni, les pages à surveiller peuvent être comparées."
                if (has_previous if has_previous is not None else bool(previous_csv))
                else "Export Pages précédent: non fourni, la surveillance temporelle reste limitée."
            ),
            (
                "Export Requêtes: fourni, les conflits de mots-clés potentiels sont signalés."
                if (has_queries if has_queries is not None else bool(queries_csv))
                else "Export Requêtes: non fourni, le rapport reste centré sur les pages."
            ),
        ],
        "kpis": [
            {"label": "Clics totaux", "value": format_number(total_clicks)},
            {"label": "Impressions totales", "value": format_number(total_impressions)},
            {"label": "CTR moyen", "value": format_percent(avg_ctr)},
            {"label": "Position moyenne", "value": f"{avg_position:.1f}" if avg_position else "-"},
            {"label": translate("Pages analysées"), "value": format_number(len(results))},
            {"label": translate("Clics récupérables estimés"), "value": f"+{format_number(total_recoverable)}"},
        ],
        "sections": sections,
        "graphique_data": graphique,
        "pays_data": pays,
        "appareils_data": appareils,
    }


def assign_report_sections(results: list[GSCPageAnalysis]) -> list[dict[str, object]]:
    section_defs = [
        ("opportunites", translate("Pages à traiter en premier")),
        ("surveiller", translate("Pages qui perdent du terrain")),
        ("google", translate("Snippets à retravailler")),
        ("percee", translate("Pages proches d'un gain SEO")),
        ("traction", translate("Pages faibles à réévaluer")),
        ("conflits", translate("Chevauchements possibles")),
    ]
    buckets: dict[str, list[dict[str, object]]] = {section_id: [] for section_id, _ in section_defs}
    seen_urls: set[str] = set()
    ordered = sorted(
        results,
        key=lambda item: (item.estimated_recoverable_clicks or 0, item.score, item.impressions),
        reverse=True,
    )

    predicates = [
        ("opportunites", is_priority_opportunity),
        ("surveiller", is_declining_page),
        ("google", is_snippet_opportunity),
        ("percee", is_near_breakthrough),
        ("traction", is_weak_page),
        ("conflits", lambda item: bool(item.possible_overlap_queries)),
    ]
    for section_id, predicate in predicates:
        for item in ordered:
            if item.url in seen_urls or not predicate(item):
                continue
            buckets[section_id].append(page_to_report_dict(item))
            seen_urls.add(item.url)

    return [
        {
            "id": section_id,
            "title": title,
            "intro": SECTION_INTROS[title],
            "empty_message": EMPTY_SECTION_MESSAGES[title],
            "pages": buckets[section_id],
            "has_gain_note": section_id in {"opportunites", "google", "percee"},
        }
        for section_id, title in section_defs
    ]


def is_priority_opportunity(item: GSCPageAnalysis) -> bool:
    return item.priority in {"HIGH", "MEDIUM"} and bool(item.estimated_recoverable_clicks)


def is_declining_page(item: GSCPageAnalysis) -> bool:
    if is_weak_page(item):
        return False
    return (
        (item.click_delta is not None and item.click_delta < 0)
        or (item.impression_delta is not None and item.impression_delta < 0)
        or (item.position_delta is not None and item.position_delta > 1)
    )


def is_snippet_opportunity(item: GSCPageAnalysis) -> bool:
    return (
        item.impressions >= 100
        and bool(item.estimated_recoverable_clicks)
        and any("ctr" in action.lower() or "title" in action.lower() or "méta" in action.lower() for action in item.actions)
    )


def is_near_breakthrough(item: GSCPageAnalysis) -> bool:
    return 4 <= item.position <= 20 and item.impressions >= 50 and item.priority != "DEAD" and not is_snippet_opportunity(item)


def is_weak_page(item: GSCPageAnalysis) -> bool:
    return item.priority == "DEAD" or (item.impressions < 50 and item.clicks < 5)


def page_to_report_dict(item: GSCPageAnalysis) -> dict[str, object]:
    actions = [translate(action) for action in list(dict.fromkeys(item.actions))]
    return {
        "url": item.url,
        "slug": display_slug(item.url),
        "priority": item.priority.lower(),
        "priority_label": translate(item.priority),
        "metrics": {
            "Clics": format_number(item.clicks),
            "Impressions": format_number(item.impressions),
            "CTR": format_percent(item.ctr),
            "Position": f"{item.position:.1f}",
            "Gain estimé": f"+{format_number(item.estimated_recoverable_clicks)}" if item.estimated_recoverable_clicks else "-",
        },
        "actions": actions,
        "action_types": ",".join(action_types_for_page(item.actions)),
        "why": explain_reason(item),
        "overlap_queries": item.possible_overlap_queries[:4],
    }


def action_types_for_page(actions: list[str]) -> list[str]:
    types: list[str] = []
    joined = " ".join(actions).lower()
    if "title" in joined or "méta" in joined or "meta" in joined or "ctr" in joined:
        types.append("snippet")
    if "contenu" in joined or "faq" in joined or "fraîcheur" in joined or "fraicheur" in joined:
        types.append("contenu")
    if "maillage" in joined or "liens internes" in joined:
        types.append("liens")
    return list(dict.fromkeys(types)) or ["autre"]


def explain_reason(item: GSCPageAnalysis) -> str:
    reasons: list[str] = []
    if item.estimated_recoverable_clicks:
        reasons.append(item.impact_label.replace("clics récupérables estimés", "clics de gain estimé"))
    if 4 <= item.position <= 10:
        reasons.append("La page est déjà proche du haut de la première page Google.")
    elif 10 < item.position <= 20:
        reasons.append("La page est déjà visible: un contenu renforcé et de meilleurs liens internes peuvent faire levier.")
    if item.ctr < 0.02 and item.impressions >= 100:
        reasons.append("Elle apparaît souvent dans Google mais génère peu de clics.")
    if item.click_delta is not None and item.click_delta < 0:
        reasons.append("Elle perd des clics par rapport à la période précédente.")
    if item.possible_overlap_queries:
        reasons.append("Des requêtes proches semblent toucher plusieurs URLs.")
    return " ".join(reasons) or "Signal faible: garder en observation plutôt que traiter en urgence."


def display_slug(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return path if path != "/" else parsed.netloc or url


def format_number(value: int | float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def format_percent(value: float) -> str:
    return f"{value:.1%}".replace(".", ",")


def write_html(
    results: list[GSCPageAnalysis],
    output_path: str,
    site_name: str = "",
    has_previous: bool = False,
    has_queries: bool = False,
    graphique_data: list[dict[str, object]] | None = None,
    pays_data: list[dict[str, object]] | None = None,
    appareils_data: list[dict[str, object]] | None = None,
) -> Path:
    output_file = ensure_parent_dir(output_path)
    report = build_report(
        results,
        site_name=site_name,
        has_previous=has_previous,
        has_queries=has_queries,
        graphique_data=graphique_data,
        pays_data=pays_data,
        appareils_data=appareils_data,
    )
    html_doc = render_report(report)
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(html_doc)
    return output_file


def render_report(report: dict[str, object]) -> str:
    title = str(report["title"])
    sections = report.get("sections", [])
    nav = "".join(
        f"<a href='#{html.escape(str(section['id']))}'>{html.escape(nav_label(str(section['title'])))}</a>"
        for section in sections  # type: ignore[union-attr]
    )
    kpis = "".join(
        "<div class='kpi-card'>"
        f"<span>{html.escape(str(kpi['label']))}</span>"
        f"<strong>{html.escape(str(kpi['value']))}</strong>"
        "</div>"
        for kpi in report.get("kpis", [])  # type: ignore[union-attr]
    )
    source_notes = "".join(
        f"<li>{html.escape(str(note))}</li>" for note in report.get("source_notes", [])  # type: ignore[union-attr]
    )
    traffic_chart = render_traffic_chart(report.get("graphique_data", []))  # type: ignore[arg-type]
    traffic_section = (
        f"""
    <section class="report-panel chart-panel">
      <div class="section-heading">
        <h2>Trafic sur 90 jours</h2>
        <p>Évolution quotidienne des clics, si l'export Graphique est disponible.</p>
      </div>
      {traffic_chart}
    </section>
"""
        if traffic_chart
        else ""
    )
    sections_html = "".join(render_report_section(section) for section in sections)  # type: ignore[arg-type]
    origin_section = render_origin_section(
        report.get("pays_data", []),  # type: ignore[arg-type]
        report.get("appareils_data", []),  # type: ignore[arg-type]
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #FAFAF9;
      --card: #FFFFFF;
      --line: #E5E3DC;
      --soft: #F3F2EE;
      --primary: #1D4ED8;
      --text: #1C1C1A;
      --muted: #6B6B6A;
      --red-bg: #FEE2E2;
      --red-text: #991B1B;
      --amber-bg: #FEF3C7;
      --amber-text: #92400E;
      --green-bg: #D1FAE5;
      --green-text: #065F46;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, sans-serif;
      line-height: 1.5;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    a {{ color: var(--primary); overflow-wrap: anywhere; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    .report-header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 20px;
      align-items: start;
      margin-bottom: 22px;
    }}
    .brand-mark {{
      width: 44px;
      height: 44px;
      border-radius: 10px;
      background: var(--primary);
      color: white;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      margin-bottom: 14px;
    }}
    h1 {{ font-size: 2.25rem; line-height: 1.08; margin-bottom: 8px; letter-spacing: 0; }}
    .meta, .section-heading p, .source-list, .empty-state, .why, .footer-note {{ color: var(--muted); }}
    .btn-export {{
      border: 0;
      border-radius: 8px;
      background: var(--primary);
      color: white;
      cursor: pointer;
      font-weight: 700;
      padding: 11px 16px;
      white-space: nowrap;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(145px, 1fr));
      gap: 10px;
      margin: 18px 0;
    }}
    .kpi-card {{
      background: var(--soft);
      border-radius: 8px;
      padding: 14px;
      min-height: 86px;
    }}
    .kpi-card span {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 7px; }}
    .kpi-card strong {{ display: block; font-size: 24px; font-weight: 650; line-height: 1.1; }}
    .source-box {{
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 10px;
      padding: 14px 16px;
      margin-bottom: 18px;
    }}
    .source-list {{ margin: 0; padding-left: 18px; }}
    nav {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      background: rgba(250, 250, 249, 0.96);
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      padding: 12px 0;
      margin-bottom: 20px;
    }}
    nav a {{
      color: var(--text);
      text-decoration: none;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 0.9rem;
    }}
    .report-panel, .report-section {{
      margin-top: 22px;
      padding-top: 4px;
    }}
    .section-heading {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 12px;
    }}
    .section-heading h2 {{ margin-bottom: 4px; font-size: 1.45rem; }}
    .filter-bar {{
      display: flex;
      gap: 14px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 10px;
      padding: 10px;
      margin-bottom: 12px;
    }}
    .filter-group {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
    .filter-label {{ color: var(--muted); font-size: 12px; font-weight: 700; margin-right: 2px; }}
    .filter-btn {{
      border: 1px solid var(--line);
      background: var(--soft);
      border-radius: 8px;
      color: var(--text);
      cursor: pointer;
      padding: 7px 10px;
      font-size: 0.86rem;
    }}
    .filter-btn.is-active {{ background: var(--primary); border-color: var(--primary); color: white; }}
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
    }}
    .page-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: start;
    }}
    .card-head h3 {{ font-size: 1rem; line-height: 1.3; margin-bottom: 4px; overflow-wrap: anywhere; }}
    .badge {{
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .badge-high {{ background: var(--red-bg); color: var(--red-text); }}
    .badge-medium {{ background: var(--amber-bg); color: var(--amber-text); }}
    .badge-low, .badge-dead {{ background: var(--green-bg); color: var(--green-text); }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(5, minmax(72px, 1fr));
      gap: 8px;
    }}
    .metric {{ background: var(--soft); border-radius: 8px; padding: 8px; min-width: 0; }}
    .metric span {{ color: var(--muted); display: block; font-size: 11px; }}
    .metric strong {{ display: block; font-size: 0.95rem; line-height: 1.25; overflow-wrap: anywhere; }}
    .actions {{ margin: 0; padding-left: 18px; }}
    .actions li + li {{ margin-top: 5px; }}
    .why {{ font-style: italic; margin: 0; }}
    .query-note {{
      color: var(--amber-text);
      background: var(--amber-bg);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 0.9rem;
      margin: 0;
    }}
    .empty-state {{
      background: var(--card);
      border: 1px dashed var(--line);
      border-radius: 10px;
      padding: 18px;
    }}
    .reliability-note {{
      color: var(--muted);
      font-size: 0.9rem;
      margin: 12px 0 0;
    }}
    .chart-card, .origin-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 16px;
    }}
    .chart-svg {{ width: 100%; height: auto; display: block; }}
    .origin-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .bar-row {{ display: flex; gap: 10px; align-items: center; margin-top: 12px; }}
    .bar-label {{ width: 96px; font-size: 0.92rem; overflow-wrap: anywhere; }}
    .bar-track {{ flex: 1; background: var(--soft); border-radius: 4px; height: 8px; }}
    .bar-fill {{ height: 100%; background: var(--primary); border-radius: 4px; }}
    .bar-value {{ width: 92px; text-align: right; color: var(--muted); font-size: 0.88rem; }}
    .footer-note {{ margin-top: 28px; border-top: 1px solid var(--line); padding-top: 18px; }}
    @media (max-width: 820px) {{
      main {{ padding: 24px 14px 42px; }}
      .report-header {{ grid-template-columns: 1fr; }}
      .kpi-grid {{ grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }}
      .section-heading {{ display: block; }}
      .metric-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .bar-label, .bar-value {{ width: auto; min-width: 64px; }}
    }}
    @media print {{
      .btn-export,
      .filter-bar,
      nav,
      .no-print {{ display: none !important; }}
      @page {{
        size: A4;
        margin: 20mm 15mm;
      }}
      body {{
        font-size: 11pt;
        background: white !important;
        color: black !important;
      }}
      main {{ max-width: none; padding: 0; }}
      .page-card {{
        break-inside: avoid;
        page-break-inside: avoid;
        border: 1px solid #ccc !important;
        box-shadow: none !important;
      }}
      a[href]::after {{
        content: " (" attr(href) ")";
        font-size: 9pt;
        color: #666;
      }}
      .kpi-card {{
        background: #F5F5F5 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .page-card {{ display: block !important; }}
      .report-section {{ page-break-before: auto; }}
      .report-section:first-of-type {{ page-break-before: avoid; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="report-header">
      <div>
        <div class="brand-mark">SEO</div>
        <h1>{html.escape(title)}</h1>
        <p class="meta">Généré le {html.escape(str(report["generated_at"]))} · {html.escape(str(report["period_label"]))}</p>
      </div>
      <button onclick="exportPDF()" class="btn-export">Exporter en PDF</button>
    </header>

    <section class="kpi-grid" aria-label="Indicateurs clés">
      {kpis}
    </section>

    <section class="source-box">
      <ul class="source-list">{source_notes}</ul>
    </section>

    {traffic_section}

    <nav aria-label="Navigation du rapport">{nav}</nav>

    {sections_html}

    {origin_section}

    <p class="footer-note">Les gains sont des estimations sur la période analysée, pas des garanties.</p>
  </main>
  <script>
    function exportPDF() {{
      const original = document.title;
      document.title = 'Rapport_SEO_' + new Date().toISOString().slice(0,10);
      window.print();
      document.title = original;
    }}

    document.querySelectorAll('.filter-bar').forEach((bar) => {{
      bar.addEventListener('click', (event) => {{
        const button = event.target.closest('button[data-filter-kind]');
        if (!button) return;
        const section = button.closest('.report-section');
        const kind = button.dataset.filterKind;
        section.querySelectorAll(`button[data-filter-kind="${{kind}}"]`).forEach((item) => {{
          item.classList.toggle('is-active', item === button);
        }});
        applyFilters(section);
      }});
    }});

    function applyFilters(section) {{
      const priority = section.querySelector('[data-filter-kind="priority"].is-active')?.dataset.filterValue || 'all';
      const action = section.querySelector('[data-filter-kind="action"].is-active')?.dataset.filterValue || 'all';
      section.querySelectorAll('.page-card').forEach((card) => {{
        const priorityMatch = priority === 'all' || card.dataset.priority === priority;
        const actionValues = (card.dataset.actions || '').split(',');
        const actionMatch = action === 'all' || actionValues.includes(action);
        card.style.display = priorityMatch && actionMatch ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>"""


def nav_label(title: str) -> str:
    replacements = {
        "Opportunités prioritaires": "Opportunités",
        "Pages à surveiller": "À surveiller",
        "Résultats Google à améliorer": "Résultats Google",
        "Pages proches d'une percée": "Proches d'une percée",
        "Pages sans traction": "Sans traction",
        "Conflits de mots-clés": "Conflits",
    }
    return replacements.get(title, title)


def render_report_section(section: dict[str, object]) -> str:
    pages = section.get("pages", [])
    section_id = str(section["id"])
    cards = "".join(render_page_card(page) for page in pages)  # type: ignore[arg-type]
    body = (
        f"<div class='cards-grid'>{cards}</div>"
        if pages
        else f"<p class='empty-state'>{html.escape(str(section['empty_message']))}</p>"
    )
    gain_note = (
        "<p class='reliability-note'>Les gains estimés sont calculés sur la période exportée et supposent "
        "une amélioration de ~3 positions. Ils constituent un ordre de grandeur, pas une prévision.</p>"
        if section.get("has_gain_note")
        else ""
    )
    return f"""
    <section class="report-section" id="{html.escape(section_id)}">
      <div class="section-heading">
        <div>
          <h2>{html.escape(str(section["title"]))}</h2>
          <p>{html.escape(str(section["intro"]))}</p>
        </div>
      </div>
      {render_filter_bar(section_id)}
      {body}
      {gain_note}
    </section>
"""


def render_filter_bar(section_id: str) -> str:
    priorities = [("all", "Toutes"), ("high", "Haute"), ("medium", "Moyenne"), ("low", "Faible")]
    actions = [("all", "Toutes"), ("snippet", "Résultat Google"), ("contenu", "Enrichir le contenu"), ("liens", "Liens internes")]
    priority_buttons = "".join(
        filter_button(section_id, "priority", value, label, active=value == "all") for value, label in priorities
    )
    action_buttons = "".join(
        filter_button(section_id, "action", value, label, active=value == "all") for value, label in actions
    )
    return f"""
      <div class="filter-bar">
        <div class="filter-group"><span class="filter-label">Urgence</span>{priority_buttons}</div>
        <div class="filter-group"><span class="filter-label">Action</span>{action_buttons}</div>
      </div>
"""


def filter_button(section_id: str, kind: str, value: str, label: str, active: bool = False) -> str:
    active_class = " is-active" if active else ""
    return (
        f"<button class='filter-btn{active_class}' type='button' "
        f"data-section='{html.escape(section_id)}' data-filter-kind='{html.escape(kind)}' "
        f"data-filter-value='{html.escape(value)}'>{html.escape(label)}</button>"
    )


def render_page_card(page: dict[str, object]) -> str:
    metrics = "".join(
        "<div class='metric'>"
        f"<span>{html.escape(str(label))}</span>"
        f"<strong>{html.escape(str(value))}</strong>"
        "</div>"
        for label, value in page["metrics"].items()  # type: ignore[union-attr]
    )
    actions = "".join(f"<li>{html.escape(str(action))}</li>" for action in page.get("actions", []))  # type: ignore[arg-type]
    overlap = ""
    if page.get("overlap_queries"):
        queries = " · ".join(str(query) for query in page["overlap_queries"])  # type: ignore[index]
        overlap = f"<p class='query-note'>Requêtes à vérifier: {html.escape(queries)}</p>"
    return f"""
      <article class="page-card" data-priority="{html.escape(str(page["priority"]))}" data-actions="{html.escape(str(page["action_types"]))}">
        <div class="card-head">
          <div>
            <h3><a href="{html.escape(str(page["url"]))}">{html.escape(str(page["slug"]))}</a></h3>
          </div>
          <span class="badge badge-{html.escape(str(page["priority"]))}">{html.escape(str(page["priority_label"]))}</span>
        </div>
        <div class="metric-row">{metrics}</div>
        <div>
          <strong>{html.escape(translate("Action conseillée"))}</strong>
          <ul class="actions">{actions}</ul>
        </div>
        <p class="why">{html.escape(str(page["why"]))}</p>
        {overlap}
      </article>
"""


def render_traffic_chart(points: list[dict[str, object]]) -> str:
    if not points:
        return ""
    clicks = [int(point.get("clics", 0)) for point in points]
    if not clicks:
        return ""
    width = 900
    height = 220
    pad = 28
    max_clicks = max(clicks) or 1
    step = (width - pad * 2) / max(1, len(clicks) - 1)
    coords = []
    for index, value in enumerate(clicks):
        x = pad + index * step
        y = height - pad - ((height - pad * 2) * (value / max_clicks))
        coords.append(f"{x:.1f},{y:.1f}")
    first_label = html.escape(str(points[0].get("date", "")))
    last_label = html.escape(str(points[-1].get("date", "")))
    return f"""
      <div class="chart-card">
        <svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Clics quotidiens">
          <line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#E5E3DC" />
          <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#E5E3DC" />
          <polyline fill="none" stroke="#1D4ED8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" points="{' '.join(coords)}" />
          <text x="{pad}" y="{height - 6}" fill="#6B6B6A" font-size="12">{first_label}</text>
          <text x="{width - pad}" y="{height - 6}" fill="#6B6B6A" font-size="12" text-anchor="end">{last_label}</text>
          <text x="{pad}" y="18" fill="#6B6B6A" font-size="12">Max {format_number(max_clicks)} clics</text>
        </svg>
      </div>
"""


def render_origin_section(pays_data: list[dict[str, object]], appareils_data: list[dict[str, object]]) -> str:
    if not pays_data and not appareils_data:
        return ""
    country_bars = render_bar_rows(pays_data, "pays", mode="max") if pays_data else "<p class='empty-state'>Aucune donnée pays disponible.</p>"
    device_bars = (
        render_bar_rows(appareils_data, "appareil", mode="total")
        if appareils_data
        else "<p class='empty-state'>Aucune donnée appareil disponible.</p>"
    )
    return f"""
    <section class="report-panel">
      <div class="section-heading">
        <div>
          <h2>Origine du trafic</h2>
          <p>Répartition des clics par pays et par appareil.</p>
        </div>
      </div>
      <div class="origin-grid">
        <div class="origin-card">
          <h3>Par pays</h3>
          {country_bars}
        </div>
        <div class="origin-card">
          <h3>Par appareil</h3>
          {device_bars}
        </div>
      </div>
    </section>
"""


def render_bar_rows(rows: list[dict[str, object]], label_key: str, mode: str) -> str:
    if not rows:
        return ""
    total = sum(int(row.get("clics", 0)) for row in rows) or 1
    maximum = max((int(row.get("clics", 0)) for row in rows), default=1) or 1
    bars: list[str] = []
    for row in rows[:5]:
        clicks = int(row.get("clics", 0))
        width = (clicks / total * 100) if mode == "total" else (clicks / maximum * 100)
        suffix = f"{width:.0f}%" if mode == "total" else f"{format_number(clicks)} clics"
        bars.append(
            "<div class='bar-row'>"
            f"<span class='bar-label'>{html.escape(str(row.get(label_key, '')))}</span>"
            "<div class='bar-track'>"
            f"<div class='bar-fill' style='width: {max(1, min(100, width)):.0f}%'></div>"
            "</div>"
            f"<span class='bar-value'>{html.escape(suffix)}</span>"
            "</div>"
        )
    return "".join(bars)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GSC analysis helper")
    parser.add_argument("current", help="Export GSC pages - période récente")
    parser.add_argument("previous", nargs="?", help="Export GSC pages - période précédente")
    parser.add_argument("-q", "--queries", help="Export GSC requêtes")
    parser.add_argument("--graphique", help="Export GSC graphique")
    parser.add_argument("--pays", help="Export GSC pays")
    parser.add_argument("--appareils", help="Export GSC appareils")
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
