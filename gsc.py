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
GSC_CSV_KIND_ALIASES = {
    "pages": ("pages", "page", "top pages", "url"),
    "queries": ("requetes", "requete", "queries", "query", "top queries", "mots cles", "keywords"),
    "graphique": ("graphique", "date", "dates", "chart", "courbe"),
    "pays": ("pays", "country", "countries"),
    "appareils": ("appareil", "appareils", "device", "devices"),
    "filters": ("filtres", "filtre", "filters", "filter"),
}
GSC_KIND_DIMENSIONS = {
    "pages": "page",
    "queries": "query",
    "graphique": "date",
    "pays": "country",
    "appareils": "device",
    "filters": "filter",
}
QUERY_QUESTION_STARTERS = (
    "comment",
    "combien",
    "pourquoi",
    "quand",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "ou",
    "où",
)


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
    queries = parse_queries_csv(effective_queries_csv) if effective_queries_csv else []
    possible_overlap = (
        detect_possible_query_overlap(
            current,
            queries,
            extra_stopwords=extra_stopwords,
        )
        if queries
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
            has_queries=bool(queries),
            queries_data=queries,
            graphique_data=load_graphique(effective_graphique_csv),
            pays_data=load_pays(effective_pays_csv),
            appareils_data=load_appareils(effective_appareils_csv),
            filters_data=load_filters(current_csv),
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
    candidates: list[tuple[int, str]] = []
    for name in archive.namelist():
        if not normalize_archive_name(Path(name).name).endswith(".csv"):
            continue
        score = score_gsc_csv_member(archive, name, kind)
        if score > 0:
            candidates.append((score, name))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def score_gsc_csv_member(archive: ZipFile, name: str, kind: str) -> int:
    normalized_names = normalize_archive_name_variants(Path(name).name)
    score = 0
    aliases = GSC_CSV_KIND_ALIASES.get(kind, ())
    if any(alias in normalized for alias in aliases for normalized in normalized_names):
        score += 40
    headers = read_gsc_member_headers(archive, name)
    normalized_headers = {normalize_header(header) for header in headers}
    dimension = GSC_KIND_DIMENSIONS.get(kind, "")
    metric_headers = {"clicks", "impressions", "ctr", "position"}
    if dimension and dimension in normalized_headers:
        score += 70
    if kind in {"pages", "queries", "pays", "appareils"} and metric_headers.issubset(normalized_headers):
        score += 25
    if kind == "graphique" and {"date", "clicks"}.issubset(normalized_headers):
        score += 30
    if kind == "filters" and {"filter", "value"}.issubset(normalized_headers):
        score += 80
    if kind == "pages" and "query" in normalized_headers:
        score -= 60
    if kind == "queries" and "page" in normalized_headers:
        score -= 60
    return score


def read_gsc_member_headers(archive: ZipFile, name: str) -> list[str]:
    try:
        text = archive.read(name).decode("utf-8-sig", errors="replace")
    except (KeyError, UnicodeDecodeError):
        return []
    if not text.strip():
        return []
    delimiter = detect_delimiter_from_text(text)
    with io.StringIO(text) as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            return next(reader)
        except StopIteration:
            return []


def normalize_archive_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\s_]+", " ", ascii_name).strip().lower()


def normalize_archive_name_variants(name: str) -> set[str]:
    variants = {name}
    for encoding in ("cp437", "latin1"):
        try:
            variants.add(name.encode(encoding, errors="ignore").decode("utf-8", errors="ignore"))
        except UnicodeError:
            pass
    try:
        variants.add(name.encode("utf-8", errors="ignore").decode("latin1", errors="ignore"))
    except UnicodeError:
        pass
    return {normalize_archive_name(variant) for variant in variants if variant}


def normalize_header(header: str) -> str:
    value = re.sub(r"\s+", " ", strip_accents(header).strip().lower().replace("\ufeff", ""))
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
        "filtre": "filter",
        "filter": "filter",
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
        "valeur": "value",
        "value": "value",
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


def load_filters(filepath: str | None) -> dict[str, str]:
    if not filepath:
        return {}
    try:
        text = read_gsc_csv_text(str(filepath), "filters")
    except (FileNotFoundError, CLIError):
        return {}
    delimiter = detect_delimiter_from_text(text)
    filters: dict[str, str] = {}
    with io.StringIO(text) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            return {}
        headers = {normalize_header(name): name for name in reader.fieldnames}
        if "filter" not in headers or "value" not in headers:
            return {}
        for row in reader:
            label = (row.get(headers["filter"]) or "").strip()
            value = (row.get(headers["value"]) or "").strip()
            if label and value:
                filters[strip_accents(label).strip().lower()] = value.replace("\xa0", " ")
    return filters


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
    queries_data: list[GSCQueryData] | None = None,
    graphique_data: list[dict[str, object]] | None = None,
    pays_data: list[dict[str, object]] | None = None,
    appareils_data: list[dict[str, object]] | None = None,
    filters_data: dict[str, str] | None = None,
) -> dict[str, object]:
    if isinstance(pages_csv, list):
        results = pages_csv
        queries = queries_data or []
    elif pages_csv:
        current = parse_pages_csv(str(pages_csv))
        effective_queries_csv = (
            str(queries_csv)
            if queries_csv
            else str(pages_csv)
            if gsc_archive_contains(str(pages_csv), "queries")
            else ""
        )
        queries = queries_data if queries_data is not None else parse_queries_csv(effective_queries_csv) if effective_queries_csv else []
        overlap = detect_possible_query_overlap(current, queries) if queries else {}
        previous = parse_pages_csv(str(previous_csv)) if previous_csv else None
        results = analyze_pages(current=current, previous=previous, possible_overlap=overlap)
    else:
        results = []
        queries = queries_data or []

    graphique = graphique_data if graphique_data is not None else load_graphique(str(graphique_csv)) if graphique_csv else []
    pays = pays_data if pays_data is not None else load_pays(str(pays_csv)) if pays_csv else []
    appareils = appareils_data if appareils_data is not None else load_appareils(str(appareils_csv)) if appareils_csv else []
    filters = (
        filters_data
        if filters_data is not None
        else load_filters(str(pages_csv))
        if pages_csv and not isinstance(pages_csv, list)
        else {}
    )

    domain = site_name or infer_domain_from_results(results)
    title = "Plan d’action SEO basé sur Google Search Console"
    total_clicks = sum(item.clicks for item in results)
    total_impressions = sum(item.impressions for item in results)
    avg_ctr = (total_clicks / total_impressions) if total_impressions else 0.0
    avg_position = (
        sum(item.position * item.impressions for item in results) / total_impressions
        if total_impressions
        else 0.0
    )
    total_recoverable = sum(item.estimated_recoverable_clicks or 0 for item in results)

    priority_count = sum(1 for item in results if item.priority in {"HIGH", "MEDIUM"} and not is_dead_gsc_page(item))
    snippet_count = sum(1 for item in results if is_snippet_opportunity(item))
    sections = assign_report_sections(results)
    has_query_export = has_queries if has_queries is not None else bool(queries)
    return {
        "title": title,
        "subtitle": "Opportunités de croissance, pages prioritaires et actions recommandées",
        "site_name": domain,
        "generated_at": datetime.now().strftime("%d/%m/%Y"),
        "period_label": build_period_label(filters),
        "executive_summary": build_executive_summary(results, priority_count, snippet_count, bool(queries)),
        "monthly_priorities": build_monthly_priorities(results, queries),
        "source_notes": [
            "Analyse basée sur les données Google Search Console exportées.",
            (
                "Export Pages précédent: fourni, les variations peuvent être contextualisées."
                if (has_previous if has_previous is not None else bool(previous_csv))
                else "Export Pages précédent: non fourni, la lecture reste centrée sur la période actuelle."
            ),
            (
                "Export Requêtes: fourni et exploité pour qualifier les intentions de recherche."
                if has_query_export
                else "Export Requêtes: non fourni, les recommandations s’appuient surtout sur les pages."
            ),
        ],
        "kpis": [
            {"label": "Pages analysées", "value": format_number(len(results))},
            {"label": "Clics totaux", "value": format_number(total_clicks)},
            {"label": "Impressions totales", "value": format_number(total_impressions)},
            {"label": "CTR moyen", "value": format_percent(avg_ctr)},
            {"label": "Position moyenne", "value": f"{avg_position:.1f}" if avg_position else "-"},
            {"label": "Pages prioritaires", "value": format_number(priority_count)},
            {"label": "Snippets à retravailler", "value": format_number(snippet_count)},
            {"label": "Clics récupérables estimés", "value": f"+{format_number(total_recoverable)}"},
        ],
        "sections": sections,
        "priority_pages": build_priority_page_cards(results)[:10],
        "snippet_pages": build_snippet_cards(results)[:8],
        "breakthrough_pages": build_breakthrough_cards(results)[:10],
        "query_sections": build_query_sections(queries, results),
        "appendix_pages": [page_to_appendix_row(item) for item in results],
        "appendix_queries": [query_to_appendix_row(query, results) for query in queries],
        "has_queries": bool(queries),
        "graphique_data": graphique,
        "pays_data": pays,
        "appareils_data": appareils,
        "filters": filters,
    }


def infer_domain_from_results(results: list[GSCPageAnalysis]) -> str:
    for item in results:
        parsed = urlparse(item.url)
        if parsed.netloc:
            return parsed.netloc.replace("www.", "")
    return "Domaine non précisé"


def build_period_label(filters: dict[str, str]) -> str:
    date_value = filters.get("date")
    if date_value:
        return f"Période analysée: {date_value}"
    return "Période analysée: export Google Search Console fourni"


def build_executive_summary(
    results: list[GSCPageAnalysis],
    priority_count: int,
    snippet_count: int,
    has_queries: bool,
) -> str:
    if not results:
        return "L’export fourni ne contient pas assez de pages exploitables pour établir une priorisation fiable."
    high_impression_low_ctr = sum(1 for item in results if item.impressions >= 100 and item.ctr < 0.02)
    near_top = sum(1 for item in results if 4 <= item.position <= 12 and item.impressions >= 50)
    if high_impression_low_ctr >= max(1, len(results) * 0.15):
        base = (
            "Le site dispose déjà de pages visibles dans Google, mais plusieurs pages génèrent beaucoup "
            "d’impressions sans obtenir un taux de clic satisfaisant. La priorité est donc d’améliorer "
            "les pages déjà exposées avant de produire davantage de contenus."
        )
    elif near_top:
        base = (
            "Le site possède des pages déjà placées près des premières positions. Le meilleur levier à court "
            "terme consiste à renforcer ces pages avec un contenu plus complet, de meilleurs liens internes "
            "et des réponses plus nettes aux intentions de recherche."
        )
    elif priority_count:
        base = (
            "L’export fait ressortir quelques opportunités ciblées plutôt qu’un problème généralisé. "
            "Le plan d’action doit rester sélectif pour concentrer l’effort sur les pages avec un potentiel mesurable."
        )
    else:
        base = (
            "Aucun signal critique ne ressort massivement de l’export. Le rapport sert surtout à identifier "
            "des ajustements progressifs et à poser une base de suivi dans Google Search Console."
        )
    query_note = (
        " Les requêtes fournies permettent aussi d’affiner les angles éditoriaux et les questions à intégrer."
        if has_queries
        else " L’absence de l’export Requêtes limite l’analyse fine de l’intention de recherche."
    )
    snippet_note = (
        f" {format_count(snippet_count, 'snippet ressort', 'snippets ressortent')} comme candidats à une réécriture prioritaire."
        if snippet_count
        else ""
    )
    return base + query_note + snippet_note


def build_monthly_priorities(results: list[GSCPageAnalysis], queries: list[GSCQueryData]) -> list[dict[str, str]]:
    snippet_count = sum(1 for item in results if is_snippet_opportunity(item))
    near_count = sum(1 for item in results if is_near_breakthrough(item) or 4 <= item.position <= 12)
    query_count = len([query for query in queries if query.impressions >= 50])
    priorities = [
        {
            "title": "Améliorer les snippets des pages à fortes impressions",
            "why": (
                f"{format_count(snippet_count, 'page est déjà visible mais sous-cliquée', 'pages sont déjà visibles mais sous-cliquées')}."
                if snippet_count
                else "Les pages visibles doivent donner une raison plus claire de cliquer."
            ),
            "action": "Réécrire les titles, les meta descriptions et l’angle d’entrée des pages prioritaires.",
            "impact": "Potentiel d’amélioration du CTR sans attendre une progression de position.",
        },
        {
            "title": "Renforcer les pages proches du haut des résultats",
            "why": (
                f"{format_count(near_count, 'page est déjà en page 1 ou au début de la page 2', 'pages sont déjà en page 1 ou au début de la page 2')}."
                if near_count
                else "Les pages avec une base SEO existante sont souvent plus rentables à améliorer que des contenus neufs."
            ),
            "action": "Enrichir le contenu, ajouter une FAQ, mettre à jour les informations et renforcer le maillage interne.",
            "impact": "Gain potentiel plus rapide car les pages ont déjà une visibilité Google.",
        },
        {
            "title": "Exploiter les requêtes sous-utilisées",
            "why": (
                f"{format_count(query_count, 'requête exploitable révèle une intention précise', 'requêtes exploitables révèlent des intentions précises')}."
                if queries
                else "Cette piste sera à confirmer dès qu’un export Requêtes sera disponible."
            ),
            "action": "Ajouter des sections ciblées dans les pages existantes ou créer des contenus satellites lorsque l’intention est distincte.",
            "impact": "Potentiel de trafic plus qualifié, à valider après mise en ligne et suivi GSC.",
        },
    ]
    priorities.sort(
        key=lambda item: (
            0 if "snippets" in item["title"].lower() and snippet_count else 1,
            0 if "haut" in item["title"].lower() and near_count else 1,
        )
    )
    return priorities[:3]


def format_count(count: int, singular: str, plural: str) -> str:
    return f"{format_number(count)} {singular if count == 1 else plural}"


def build_priority_page_cards(results: list[GSCPageAnalysis]) -> list[dict[str, object]]:
    ordered = sorted(
        [item for item in results if not is_weak_page(item)],
        key=lambda item: (item.estimated_recoverable_clicks or 0, item.score, item.impressions),
        reverse=True,
    )
    return [page_to_report_dict(item) for item in ordered if item.priority in {"HIGH", "MEDIUM"} or item.estimated_recoverable_clicks]


def build_snippet_cards(results: list[GSCPageAnalysis]) -> list[dict[str, object]]:
    return [snippet_to_report_dict(item) for item in sorted(results, key=lambda row: row.impressions, reverse=True) if is_snippet_opportunity(item)]


def build_breakthrough_cards(results: list[GSCPageAnalysis]) -> list[dict[str, object]]:
    candidates = [
        item
        for item in results
        if 4 <= item.position <= 20 and item.impressions >= 50 and item.priority != "DEAD"
    ]
    return [page_to_breakthrough_dict(item) for item in sorted(candidates, key=lambda row: (row.position, -row.impressions))]


def build_query_sections(queries: list[GSCQueryData], results: list[GSCPageAnalysis]) -> list[dict[str, object]]:
    if not queries:
        return []
    under_clicked = sorted(
        [query for query in queries if query.impressions >= 50 and query.ctr < expected_ctr_for_position(query.position) * 0.65],
        key=lambda query: (query.impressions, -query.clicks),
        reverse=True,
    )[:10]
    near_gain = sorted(
        [query for query in queries if 3.5 <= query.position <= 12 and query.impressions >= 30],
        key=lambda query: (query.position, -query.impressions),
    )[:10]
    existing = sorted(
        [query for query in queries if query.position <= 20 and query.impressions >= 20],
        key=lambda query: (query.impressions, -query.position),
        reverse=True,
    )[:10]
    new_content = sorted(
        [query for query in queries if should_consider_new_content(query, results)],
        key=lambda query: (query.impressions, query.position),
        reverse=True,
    )[:10]
    return [
        {
            "id": "queries-impressions",
            "title": "Top requêtes avec beaucoup d’impressions et peu de clics",
            "rows": [query_to_report_dict(query, results, forced_recommendation="à utiliser dans un title/meta") for query in under_clicked],
        },
        {
            "id": "queries-gain",
            "title": "Top requêtes déjà proches d’un gain",
            "rows": [query_to_report_dict(query, results, forced_recommendation="à intégrer dans une page existante") for query in near_gain],
        },
        {
            "id": "queries-existing",
            "title": "Requêtes à intégrer dans les pages existantes",
            "rows": [query_to_report_dict(query, results, forced_recommendation="à intégrer dans une page existante") for query in existing],
        },
        {
            "id": "queries-new",
            "title": "Requêtes pouvant justifier un nouveau contenu",
            "rows": [query_to_report_dict(query, results, forced_recommendation="à considérer comme nouveau contenu") for query in new_content],
        },
    ]


def expected_ctr_for_position(position: float) -> float:
    return EXPECTED_CTR_BY_POSITION.get(max(1, min(20, round(position))), 0.004)


def should_consider_new_content(query: GSCQueryData, results: list[GSCPageAnalysis]) -> bool:
    if query.impressions < 20 or query.position <= 8:
        return False
    query_tokens = query_token_set(query.query)
    if not query_tokens:
        return False
    page_token_sets = [extract_slug_keywords(item.url, stopwords=set(GSC_CANNIBAL_STOPWORDS)) for item in results]
    best_overlap = max((len(query_tokens & tokens) / max(1, len(query_tokens)) for tokens in page_token_sets), default=0)
    return best_overlap < 0.45 or query.position > 18


def query_token_set(query: str) -> set[str]:
    stopwords = {word.lower() for word in GSC_CANNIBAL_STOPWORDS}
    return {
        strip_accents(word).lower()
        for word in re.findall(r"[\w'-]+", query)
        if len(word) > 3 and strip_accents(word).lower() not in stopwords
    }


def query_to_report_dict(
    query: GSCQueryData,
    results: list[GSCPageAnalysis],
    forced_recommendation: str = "",
) -> dict[str, object]:
    recommendation = forced_recommendation or classify_query_recommendation(query, results)
    return {
        "query": query.query,
        "clicks": format_number(query.clicks),
        "impressions": format_number(query.impressions),
        "ctr": format_percent(query.ctr),
        "position": f"{query.position:.1f}",
        "recommendation": recommendation,
    }


def query_to_appendix_row(query: GSCQueryData, results: list[GSCPageAnalysis]) -> dict[str, object]:
    row = query_to_report_dict(query, results)
    return {
        "Requête": row["query"],
        "Clics": row["clicks"],
        "Impressions": row["impressions"],
        "CTR": row["ctr"],
        "Position": row["position"],
        "Recommandation": row["recommendation"],
    }


def classify_query_recommendation(query: GSCQueryData, results: list[GSCPageAnalysis]) -> str:
    lowered = query.query.strip().lower()
    if lowered.startswith(QUERY_QUESTION_STARTERS) or len(lowered.split()) >= 5:
        return "à traiter en FAQ"
    if query.ctr < expected_ctr_for_position(query.position) * 0.65 and query.position <= 12:
        return "à utiliser dans un title/meta"
    if should_consider_new_content(query, results):
        return "à considérer comme nouveau contenu"
    return "à intégrer dans une page existante"


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
    actions = precise_actions_for_page(item)
    action_types = action_types_for_page(actions)
    return {
        "url": item.url,
        "slug": display_slug(item.url),
        "priority": priority_css_class(item),
        "priority_label": client_priority_label(item),
        "diagnostic": diagnostic_for_page(item),
        "metrics": {
            "Clics": format_number(item.clicks),
            "Impressions": format_number(item.impressions),
            "CTR": format_percent(item.ctr),
            "Position": f"{item.position:.1f}",
            "Gain estimé": f"+{format_number(item.estimated_recoverable_clicks)}" if item.estimated_recoverable_clicks else "à confirmer",
        },
        "actions": actions,
        "action_types": ",".join(css_action_type(value) for value in action_types),
        "action_type_labels": action_types,
        "effort": effort_for_page(item),
        "impact": impact_for_page(item),
        "why": explain_reason(item),
        "overlap_queries": item.possible_overlap_queries[:4],
    }


def action_types_for_page(actions: list[str]) -> list[str]:
    types: list[str] = []
    joined = " ".join(actions).lower()
    if "title" in joined or "méta" in joined or "meta" in joined or "ctr" in joined:
        types.append("Snippet")
    if "contenu" in joined or "faq" in joined or "fraîcheur" in joined or "fraicheur" in joined:
        types.append("Contenu")
    if "maillage" in joined or "liens internes" in joined:
        types.append("Maillage interne")
    if "technique" in joined or "redirection" in joined or "supprimer" in joined:
        types.append("Technique")
    if "cannibalisation" in joined or "chevauchement" in joined:
        types.append("Cannibalisation")
    return list(dict.fromkeys(types)) or ["Contenu"]


def css_action_type(label: str) -> str:
    return strip_accents(label).lower().replace(" ", "-")


def client_priority_label(item: GSCPageAnalysis) -> str:
    if item.priority == "HIGH":
        return "Priorité 1"
    if item.priority == "MEDIUM":
        return "Priorité 2"
    if item.priority == "DEAD":
        return "À arbitrer"
    return "Priorité 3"


def priority_css_class(item: GSCPageAnalysis) -> str:
    if item.priority == "HIGH":
        return "p1"
    if item.priority == "MEDIUM":
        return "p2"
    if item.priority == "DEAD":
        return "dead"
    return "p3"


def effort_for_page(item: GSCPageAnalysis) -> str:
    if is_dead_gsc_page(item) or item.possible_overlap_queries:
        return "Élevé"
    if 4 <= item.position <= 10 and is_snippet_opportunity(item):
        return "Faible"
    if item.position <= 20:
        return "Moyen"
    return "Moyen"


def diagnostic_for_page(item: GSCPageAnalysis) -> str:
    if is_dead_gsc_page(item):
        return "La page ne capte presque pas de trafic et doit être arbitrée plutôt qu’optimisée à l’aveugle."
    if is_snippet_opportunity(item):
        return "La page reçoit beaucoup d’impressions mais son CTR reste faible par rapport à sa visibilité."
    if 4 <= item.position <= 10:
        return "La page est déjà proche des premières positions et peut progresser avec un renforcement ciblé."
    if 10 < item.position <= 20:
        return "La page est visible mais manque probablement de profondeur ou de soutien interne pour passer un cap."
    if item.possible_overlap_queries:
        return "Plusieurs URLs semblent répondre à des requêtes proches, à vérifier avant optimisation."
    return "La page présente un signal utile mais moins urgent que les priorités principales."


def impact_for_page(item: GSCPageAnalysis) -> str:
    if item.impact_label:
        return item.impact_label
    if is_snippet_opportunity(item):
        return "Hausse potentielle du CTR, à confirmer après mise en ligne et suivi dans GSC."
    if item.position <= 20:
        return "Potentiel de gain progressif si la page gagne en pertinence et en liens internes."
    return "Impact à confirmer: le signal actuel reste limité."


def precise_actions_for_page(item: GSCPageAnalysis) -> list[str]:
    actions: list[str] = []
    keyword = keyword_phrase_from_url(item.url)
    if is_dead_gsc_page(item):
        return [
            "vérifier si la page répond encore à une intention utile",
            "fusionner avec une page plus forte si le sujet est déjà couvert",
            "prévoir une redirection 301 ou un retrait propre si la page n’a plus de rôle",
        ]
    if is_snippet_opportunity(item):
        actions.extend(
            [
                f"réécrire le title autour de l’intention « {keyword} »",
                "clarifier la promesse dès la meta description",
                "aligner l’introduction avec la question principale de l’internaute",
            ]
        )
    if 4 <= item.position <= 10:
        actions.extend(
            [
                "ajouter une FAQ courte sur les questions récurrentes du sujet",
                "mettre à jour les informations clés et les exemples",
                "ajouter des liens internes depuis les pages thématiquement proches",
            ]
        )
    elif 10 < item.position <= 20:
        actions.extend(
            [
                "enrichir la page avec une structure plus complète",
                "créer des liens internes depuis les contenus déjà visibles",
                "traiter les sous-intentions manquantes dans des sections dédiées",
            ]
        )
    if item.click_delta is not None and item.click_delta < -10:
        actions.append("contrôler la fraîcheur du contenu et les changements visibles dans les résultats Google")
    if item.possible_overlap_queries:
        actions.append("vérifier manuellement la cannibalisation possible avant de modifier les pages")
    return list(dict.fromkeys(actions)) or ["garder la page en suivi et réévaluer lors du prochain export GSC"]


def keyword_phrase_from_url(url: str) -> str:
    slug = display_slug(url).strip("/")
    if not slug:
        return "la requête principale"
    last_segment = slug.split("/")[-1]
    words = [word for word in re.split(r"[-_]+", last_segment) if word and not word.isdigit()]
    return " ".join(words[:6]) or "la requête principale"


def snippet_to_report_dict(item: GSCPageAnalysis) -> dict[str, object]:
    keyword = keyword_phrase_from_url(item.url)
    title_keyword = keyword[:1].upper() + keyword[1:]
    return {
        "url": item.url,
        "slug": display_slug(item.url),
        "problem": "Beaucoup d’impressions, mais le résultat affiché ne donne probablement pas assez envie de cliquer.",
        "intent": probable_intent_from_keyword(keyword),
        "angle": f"Répondre clairement à l’intention « {keyword} » avec une promesse plus concrète.",
        "title_example": f"{title_keyword} : guide clair, conseils et points clés",
        "meta_example": (
            f"Découvrez les informations essentielles sur {keyword}, les points à vérifier et les conseils "
            "pour avancer plus simplement."
        ),
        "metrics": f"{format_number(item.impressions)} impressions · CTR {format_percent(item.ctr)} · position {item.position:.1f}",
    }


def probable_intent_from_keyword(keyword: str) -> str:
    lower = keyword.lower()
    if any(word in lower for word in ("prix", "tarif", "meilleur", "avis", "comparatif")):
        return "Comparaison ou décision d’achat"
    if any(word in lower for word in ("comment", "guide", "niveau", "points", "inscription")):
        return "Recherche d’explication pratique"
    return "Recherche d’information sur le sujet"


def page_to_breakthrough_dict(item: GSCPageAnalysis) -> dict[str, object]:
    return {
        "url": item.url,
        "slug": display_slug(item.url),
        "position": f"{item.position:.1f}",
        "impressions": format_number(item.impressions),
        "clicks": format_number(item.clicks),
        "action": main_action_for_page(item),
        "effort": effort_for_page(item),
        "impact": impact_for_page(item),
    }


def main_action_for_page(item: GSCPageAnalysis) -> str:
    if is_snippet_opportunity(item):
        return "Retravailler le snippet"
    if 4 <= item.position <= 10:
        return "Renforcer contenu, FAQ et maillage interne"
    if item.possible_overlap_queries:
        return "Vérifier la cannibalisation possible"
    return "Enrichir la page et créer des liens internes"


def page_to_appendix_row(item: GSCPageAnalysis) -> dict[str, object]:
    return {
        "URL": item.url,
        "Priorité": client_priority_label(item),
        "Clics": format_number(item.clicks),
        "Impressions": format_number(item.impressions),
        "CTR": format_percent(item.ctr),
        "Position": f"{item.position:.1f}",
        "Gain estimé": f"+{format_number(item.estimated_recoverable_clicks)}" if item.estimated_recoverable_clicks else "",
        "Action principale": main_action_for_page(item),
    }


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
    queries_data: list[GSCQueryData] | None = None,
    graphique_data: list[dict[str, object]] | None = None,
    pays_data: list[dict[str, object]] | None = None,
    appareils_data: list[dict[str, object]] | None = None,
    filters_data: dict[str, str] | None = None,
) -> Path:
    output_file = ensure_parent_dir(output_path)
    report = build_report(
        results,
        site_name=site_name,
        has_previous=has_previous,
        has_queries=has_queries,
        queries_data=queries_data,
        graphique_data=graphique_data,
        pays_data=pays_data,
        appareils_data=appareils_data,
        filters_data=filters_data,
    )
    html_doc = render_report(report)
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(html_doc)
    return output_file


def render_report(report: dict[str, object]) -> str:
    title = str(report["title"])
    nav_items = [
        ("synthese", "Synthèse"),
        ("priorites", "Priorités"),
        ("pages-prioritaires", "Pages"),
        ("requetes", "Requêtes"),
        ("snippets", "Snippets"),
        ("renforcer", "À renforcer"),
        ("methodologie", "Méthode"),
        ("annexes", "Annexes"),
    ]
    nav = "".join(f"<a href='#{anchor}'>{label}</a>" for anchor, label in nav_items)
    kpis = "".join(render_kpi_card(kpi) for kpi in report.get("kpis", []))  # type: ignore[arg-type]
    source_notes = "".join(f"<li>{html.escape(str(note))}</li>" for note in report.get("source_notes", []))  # type: ignore[union-attr]
    traffic_chart = render_traffic_chart(report.get("graphique_data", []))  # type: ignore[arg-type]
    traffic_section = render_traffic_section(traffic_chart) if traffic_chart else ""
    origin_section = render_origin_section(
        report.get("pays_data", []),  # type: ignore[arg-type]
        report.get("appareils_data", []),  # type: ignore[arg-type]
    )
    priority_cards = render_priority_page_cards(report.get("priority_pages", []))  # type: ignore[arg-type]
    snippets = render_snippet_section(report.get("snippet_pages", []))  # type: ignore[arg-type]
    query_sections = render_query_sections(report.get("query_sections", []), bool(report.get("has_queries")))  # type: ignore[arg-type]
    breakthrough = render_breakthrough_section(report.get("breakthrough_pages", []))  # type: ignore[arg-type]
    priorities = render_monthly_priorities(report.get("monthly_priorities", []))  # type: ignore[arg-type]
    appendices = render_appendices(
        report.get("appendix_pages", []),  # type: ignore[arg-type]
        report.get("appendix_queries", []),  # type: ignore[arg-type]
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #F7F8FA;
      --card: #FFFFFF;
      --line: #DDE3EA;
      --soft: #EEF3F7;
      --primary: #155E75;
      --accent: #7C3AED;
      --text: #172026;
      --muted: #5C6873;
      --red-bg: #FFE5E1;
      --red-text: #9F2B1D;
      --amber-bg: #FFF2CC;
      --amber-text: #7A4B00;
      --green-bg: #DDF7EA;
      --green-text: #086142;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, sans-serif;
      line-height: 1.5;
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 30px 20px 56px; }}
    a {{ color: var(--primary); overflow-wrap: anywhere; word-break: break-word; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ font-size: 2.35rem; line-height: 1.08; margin-bottom: 10px; letter-spacing: 0; max-width: 820px; }}
    h2 {{ font-size: 1.45rem; line-height: 1.2; letter-spacing: 0; }}
    h3 {{ letter-spacing: 0; }}
    .report-header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 20px;
      align-items: start;
      margin-bottom: 24px;
      padding: 34px;
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 8px;
    }}
    .eyebrow {{ color: var(--primary); font-size: 0.78rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 10px; }}
    .subtitle {{ font-size: 1.1rem; color: var(--muted); max-width: 820px; margin-bottom: 18px; }}
    .cover-meta {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 20px; }}
    .cover-meta div {{ background: var(--soft); border-radius: 8px; padding: 12px; min-width: 0; }}
    .cover-meta span, .kpi-card span, .mini-label {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 5px; }}
    .cover-meta strong {{ display: block; overflow-wrap: anywhere; }}
    .meta, .section-heading p, .source-list, .empty-state, .why, .footer-note, .small-note {{ color: var(--muted); }}
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
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 10px;
      margin: 18px 0;
    }}
    .kpi-card {{
      background: var(--soft);
      border-radius: 8px;
      padding: 14px;
      min-height: 86px;
    }}
    .kpi-card strong {{ display: block; font-size: 24px; font-weight: 650; line-height: 1.1; }}
    .report-panel, .report-section, .source-box {{
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 8px;
      padding: 22px;
      margin-top: 20px;
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
    .section-heading {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 12px;
    }}
    .section-heading h2 {{ margin-bottom: 4px; font-size: 1.45rem; }}
    .summary-copy {{ font-size: 1.05rem; max-width: 880px; margin-bottom: 0; }}
    .cards-grid, .priority-list {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
    }}
    .priority-item, .page-card, .snippet-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
    }}
    .priority-item {{ background: #FBFCFE; }}
    .priority-item h3 {{ font-size: 1rem; margin-bottom: 8px; }}
    .priority-item p {{ margin-bottom: 8px; }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: start;
    }}
    .card-head h3 {{ font-size: 1rem; line-height: 1.3; margin-bottom: 4px; overflow-wrap: anywhere; }}
    .url-full {{ color: var(--muted); font-size: 0.88rem; line-height: 1.35; overflow-wrap: anywhere; word-break: break-word; }}
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
    .badge-p1 {{ background: var(--red-bg); color: var(--red-text); }}
    .badge-p2 {{ background: var(--amber-bg); color: var(--amber-text); }}
    .badge-p3, .badge-dead {{ background: var(--green-bg); color: var(--green-text); }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(94px, 1fr));
      gap: 8px;
    }}
    .metric {{ background: var(--soft); border-radius: 8px; padding: 8px; min-width: 0; }}
    .metric span {{ color: var(--muted); display: block; font-size: 11px; }}
    .metric strong {{ display: block; font-size: 0.95rem; line-height: 1.25; overflow-wrap: anywhere; }}
    .actions {{ margin: 0; padding-left: 18px; }}
    .actions li + li {{ margin-top: 5px; }}
    .insight-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .insight {{ background: var(--soft); border-radius: 8px; padding: 10px; }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .chip {{ border: 1px solid var(--line); background: var(--soft); border-radius: 999px; padding: 4px 8px; font-size: 12px; color: var(--text); }}
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
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 9px 8px; text-align: left; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ color: var(--muted); font-size: 12px; }}
    .table-wrap {{ overflow-x: auto; }}
    .appendix table {{ font-size: 0.88rem; }}
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
      .cover-meta, .insight-grid {{ grid-template-columns: 1fr; }}
      .kpi-grid {{ grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }}
      .cards-grid, .priority-list {{ grid-template-columns: 1fr; }}
      .section-heading {{ display: block; }}
      .metric-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .bar-label, .bar-value {{ width: auto; min-width: 64px; }}
    }}
    @media print {{
      .btn-export,
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
      .page-card, .priority-item, .snippet-card, .report-panel, .report-section {{
        break-inside: avoid;
        page-break-inside: avoid;
        border: 1px solid #ccc !important;
        box-shadow: none !important;
      }}
      a[href]::after {{ content: ""; }}
      .kpi-card, .metric, .insight {{
        background: #F5F5F5 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .page-card {{ display: block !important; }}
      .report-section, .report-panel {{ page-break-before: auto; }}
      .appendix {{ break-inside: auto; page-break-inside: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="report-header">
      <div>
        <p class="eyebrow">Audit SEO GSC</p>
        <h1>{html.escape(title)}</h1>
        <p class="subtitle">{html.escape(str(report.get("subtitle", "")))}</p>
        <div class="cover-meta">
          <div><span>Domaine analysé</span><strong>{html.escape(str(report.get("site_name") or "Non précisé"))}</strong></div>
          <div><span>Période analysée</span><strong>{html.escape(str(report.get("period_label", "")).replace("Période analysée: ", ""))}</strong></div>
          <div><span>Date de génération</span><strong>{html.escape(str(report["generated_at"]))}</strong></div>
        </div>
      </div>
      <button onclick="exportPDF()" class="btn-export">Exporter en PDF</button>
    </header>

    <section class="source-box">
      <ul class="source-list">{source_notes}</ul>
    </section>

    <nav aria-label="Navigation du rapport">{nav}</nav>

    <section class="report-panel" id="synthese">
      <div class="section-heading"><div><h2>Synthèse exécutive</h2><p>Les indicateurs à retenir avant d’entrer dans le détail.</p></div></div>
      <section class="kpi-grid" aria-label="Indicateurs clés">{kpis}</section>
      <p class="summary-copy">{html.escape(str(report.get("executive_summary", "")))}</p>
    </section>

    <section class="report-panel" id="priorites">
      <div class="section-heading"><div><h2>Les 3 priorités du mois</h2><p>Un plan d’action volontairement court pour décider vite.</p></div></div>
      {priorities}
    </section>

    <section class="report-section" id="pages-prioritaires">
      <div class="section-heading"><div><h2>Top pages à traiter en premier</h2><p>Les pages avec le meilleur rapport visibilité, effort et potentiel.</p></div></div>
      {priority_cards}
      <p class="reliability-note">Les clics récupérables estimés sont un ordre de grandeur, pas une promesse. À confirmer après mise en ligne et suivi dans Google Search Console.</p>
    </section>

    <section class="report-section" id="requetes">
      <div class="section-heading"><div><h2>Exploitation des requêtes</h2><p>Une sélection limitée aux requêtes utiles pour orienter les titles, FAQ et contenus.</p></div></div>
      {query_sections}
    </section>

    {snippets}
    {breakthrough}
    {traffic_section}
    {origin_section}
    {render_methodology_section()}
    {appendices}

    <p class="footer-note">Analyse basée sur les données Google Search Console exportées. Les recommandations doivent être priorisées avec la connaissance métier du site.</p>
  </main>
  <script>
    function exportPDF() {{
      const original = document.title;
      document.title = 'Rapport_SEO_' + new Date().toISOString().slice(0,10);
      window.print();
      document.title = original;
    }}
  </script>
</body>
</html>"""


def render_kpi_card(kpi: dict[str, object]) -> str:
    return (
        "<div class='kpi-card'>"
        f"<span>{html.escape(str(kpi.get('label', '')))}</span>"
        f"<strong>{html.escape(str(kpi.get('value', '')))}</strong>"
        "</div>"
    )


def render_monthly_priorities(items: list[dict[str, str]]) -> str:
    if not items:
        return render_empty_state()
    cards = []
    for index, item in enumerate(items[:3], start=1):
        cards.append(
            "<article class='priority-item'>"
            f"<h3>Priorité {index} — {html.escape(item.get('title', ''))}</h3>"
            f"<p><strong>Pourquoi :</strong> {html.escape(item.get('why', ''))}</p>"
            f"<p><strong>Action :</strong> {html.escape(item.get('action', ''))}</p>"
            f"<p><strong>Impact :</strong> {html.escape(item.get('impact', ''))}</p>"
            "</article>"
        )
    return f"<div class='priority-list'>{''.join(cards)}</div>"


def render_priority_page_cards(pages: list[dict[str, object]]) -> str:
    if not pages:
        return render_empty_state()
    return f"<div class='cards-grid'>{''.join(render_client_page_card(page) for page in pages)}</div>"


def render_client_page_card(page: dict[str, object]) -> str:
    metrics = "".join(
        "<div class='metric'>"
        f"<span>{html.escape(str(label))}</span>"
        f"<strong>{html.escape(str(value))}</strong>"
        "</div>"
        for label, value in dict(page.get("metrics", {})).items()
    )
    actions = "".join(f"<li>{html.escape(str(action))}</li>" for action in page.get("actions", []))  # type: ignore[arg-type]
    action_labels = "".join(f"<span class='chip'>{html.escape(str(label))}</span>" for label in page.get("action_type_labels", []))  # type: ignore[arg-type]
    overlap = ""
    if page.get("overlap_queries"):
        queries = " · ".join(str(query) for query in page["overlap_queries"])  # type: ignore[index]
        overlap = f"<p class='query-note'>Cannibalisation à vérifier sur: {html.escape(queries)}</p>"
    return f"""
      <article class="page-card">
        <div class="card-head">
          <div>
            <h3>Page : {html.escape(str(page.get("slug", "")))}</h3>
            <a class="url-full" href="{html.escape(str(page.get("url", "")))}">{html.escape(str(page.get("url", "")))}</a>
          </div>
          <span class="badge badge-{html.escape(str(page.get("priority", "p3")))}">{html.escape(str(page.get("priority_label", "")))}</span>
        </div>
        <div class="metric-row">{metrics}</div>
        <p><strong>Constat :</strong> {html.escape(str(page.get("diagnostic", "")))}</p>
        <div>
          <strong>Action recommandée</strong>
          <ul class="actions">{actions}</ul>
        </div>
        <div class="insight-grid">
          <div class="insight"><span class="mini-label">Effort estimé</span><strong>{html.escape(str(page.get("effort", "")))}</strong></div>
          <div class="insight"><span class="mini-label">Type d’action</span><div class="chip-row">{action_labels}</div></div>
          <div class="insight"><span class="mini-label">Impact attendu</span><strong>{html.escape(str(page.get("impact", "")))}</strong></div>
        </div>
        {overlap}
      </article>
"""


def render_query_sections(sections: list[dict[str, object]], has_queries: bool) -> str:
    if not has_queries:
        return render_empty_state("Export Requêtes non fourni ou non exploitable dans l’export fourni.")
    rendered = []
    for section in sections:
        rows = section.get("rows", [])
        rendered.append(
            "<div class='report-panel'>"
            f"<h3>{html.escape(str(section.get('title', '')))}</h3>"
            f"{render_query_table(rows)}"
            "</div>"
        )
    return "".join(rendered)


def render_query_table(rows: object) -> str:
    if not rows:
        return render_empty_state()
    typed_rows = list(rows)  # type: ignore[arg-type]
    body = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('query', '')))}</td>"
        f"<td>{html.escape(str(row.get('clicks', '')))}</td>"
        f"<td>{html.escape(str(row.get('impressions', '')))}</td>"
        f"<td>{html.escape(str(row.get('ctr', '')))}</td>"
        f"<td>{html.escape(str(row.get('position', '')))}</td>"
        f"<td>{html.escape(str(row.get('recommendation', '')))}</td>"
        "</tr>"
        for row in typed_rows
    )
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Requête</th><th>Clics</th><th>Impressions</th><th>CTR</th><th>Position</th><th>Recommandation</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


def render_snippet_section(snippets: list[dict[str, object]]) -> str:
    body = (
        f"<div class='cards-grid'>{''.join(render_snippet_card(item) for item in snippets)}</div>"
        if snippets
        else render_empty_state()
    )
    return f"""
    <section class="report-section" id="snippets">
      <div class="section-heading"><div><h2>Snippets à retravailler</h2><p>Des propositions concrètes pour rendre les résultats Google plus cliquables.</p></div></div>
      {body}
    </section>
"""


def render_snippet_card(item: dict[str, object]) -> str:
    return f"""
      <article class="snippet-card">
        <h3>{html.escape(str(item.get("slug", "")))}</h3>
        <a class="url-full" href="{html.escape(str(item.get("url", "")))}">{html.escape(str(item.get("url", "")))}</a>
        <p class="small-note">{html.escape(str(item.get("metrics", "")))}</p>
        <p><strong>Problème :</strong> {html.escape(str(item.get("problem", "")))}</p>
        <p><strong>Intention probable :</strong> {html.escape(str(item.get("intent", "")))}</p>
        <p><strong>Angle recommandé :</strong> {html.escape(str(item.get("angle", "")))}</p>
        <p><strong>Exemple de title :</strong> {html.escape(str(item.get("title_example", "")))}</p>
        <p><strong>Exemple de meta :</strong> {html.escape(str(item.get("meta_example", "")))}</p>
      </article>
"""


def render_breakthrough_section(pages: list[dict[str, object]]) -> str:
    if not pages:
        body = render_empty_state()
    else:
        body_rows = "".join(
            "<tr>"
            f"<td><a href='{html.escape(str(row.get('url', '')))}'>{html.escape(str(row.get('slug', '')))}</a></td>"
            f"<td>{html.escape(str(row.get('position', '')))}</td>"
            f"<td>{html.escape(str(row.get('impressions', '')))}</td>"
            f"<td>{html.escape(str(row.get('clicks', '')))}</td>"
            f"<td>{html.escape(str(row.get('action', '')))}</td>"
            f"<td>{html.escape(str(row.get('effort', '')))}</td>"
            f"<td>{html.escape(str(row.get('impact', '')))}</td>"
            "</tr>"
            for row in pages
        )
        body = (
            "<div class='table-wrap'><table><thead><tr>"
            "<th>URL</th><th>Position</th><th>Impressions</th><th>Clics</th><th>Action principale</th><th>Effort</th><th>Impact</th>"
            f"</tr></thead><tbody>{body_rows}</tbody></table></div>"
        )
    return f"""
    <section class="report-section" id="renforcer">
      <div class="section-heading"><div><h2>Pages déjà visibles à renforcer</h2><p>Ces pages ont déjà une base SEO: les améliorer est souvent plus rentable que repartir de zéro.</p></div></div>
      {body}
    </section>
"""


def render_traffic_section(traffic_chart: str) -> str:
    return f"""
    <section class="report-panel chart-panel">
      <div class="section-heading">
        <div><h2>Évolution du trafic</h2><p>Évolution quotidienne des clics, si l’export Graphique est disponible.</p></div>
      </div>
      {traffic_chart}
    </section>
"""


def render_methodology_section() -> str:
    items = [
        "Les clics récupérables sont des estimations, pas des promesses.",
        "Les positions sont des moyennes Google Search Console.",
        "Les priorités sont calculées selon impressions, CTR, position et potentiel d’amélioration.",
        "Les signaux de cannibalisation doivent être vérifiés manuellement.",
        "Les résultats sont à confirmer après mise en ligne et suivi dans GSC.",
    ]
    body = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"""
    <section class="report-panel" id="methodologie">
      <div class="section-heading"><div><h2>Comment lire ce rapport</h2><p>Les règles de lecture pour éviter les mauvaises interprétations.</p></div></div>
      <ul class="actions">{body}</ul>
    </section>
"""


def render_appendices(pages: list[dict[str, object]], queries: list[dict[str, object]]) -> str:
    pages_table = render_appendix_table(pages)
    queries_table = render_appendix_table(queries) if queries else render_empty_state("Aucun export Requêtes exploitable dans cette analyse.")
    return f"""
    <section class="report-section appendix" id="annexes">
      <div class="section-heading"><div><h2>Annexes</h2><p>Données complètes et limites méthodologiques.</p></div></div>
      <h3>Tableau complet des pages analysées</h3>
      {pages_table}
      <h3>Tableau complet des requêtes</h3>
      {queries_table}
      <h3>Détails méthodologiques et limites</h3>
      <ul class="actions">
        <li>Google Search Console agrège les positions et les CTR: ce ne sont pas des mesures page par page en temps réel.</li>
        <li>Le rapport ne remplace pas une vérification SERP, une analyse de contenu ni un crawl technique complet.</li>
        <li>Les estimations de clics récupérables donnent un ordre de grandeur sur la période exportée.</li>
      </ul>
    </section>
"""


def render_appendix_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return render_empty_state()
    headers = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(header, '')))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def render_empty_state(message: str = "Aucun signal prioritaire détecté sur cette catégorie dans l’export fourni.") -> str:
    return f"<p class='empty-state'>{html.escape(message)}</p>"


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
