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
from typing import Any
from urllib.parse import unquote, urlparse
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
GENERIC_SNIPPET_PHRASES = (
    "guide clair",
    "conseils et points clés",
    "conseils et points cles",
    "points clés",
    "points cles",
    "points à vérifier",
    "points a verifier",
    "découvrez les informations essentielles",
    "decouvrez les informations essentielles",
    "conseils pour avancer plus simplement",
    "promesse plus concrète",
    "promesse plus concrete",
)
BUSINESS_HIGH_TERMS = (
    "raquette",
    "chaussure",
    "chaussures",
    "balle",
    "balles",
    "pressurisateur",
    "sac",
    "equipement",
    "équipement",
    "meilleur",
    "meilleure",
    "avis",
    "comparatif",
    "test",
    "acheter",
    "achat",
    "prix",
    "promo",
    "guide achat",
    "programme",
    "pdf",
    "formation",
    "partenariat",
)
BUSINESS_LOW_TERMS = (
    "joueur",
    "joueuse",
    "biographie",
    "age",
    "âge",
    "fortune",
    "actualite",
    "actualité",
    "news",
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
    mode: str = "executive",
    annexes_dir: str | None = None,
    site_context: str = "affiliate_media",
    export_csv: bool = False,
) -> list[GSCPageAnalysis]:
    if mode not in {"full", "executive"}:
        raise CLIError(f"Mode GSC inconnu: {mode}. Valeurs: full, executive.")
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
    cannibalization_groups = detect_cannibalization_groups(current, queries)
    possible_overlap = build_overlap_from_cannibalization_groups(cannibalization_groups)
    if not possible_overlap and queries:
        possible_overlap = detect_possible_query_overlap(
            current,
            queries,
            extra_stopwords=extra_stopwords,
        )
    results = analyze_pages(
        current=current,
        previous=previous,
        possible_overlap=possible_overlap,
        queries=queries,
        site_context=site_context,
    )
    apply_cannibalization_groups(results, cannibalization_groups)
    write_csv(results, output_csv)
    if mode == "executive" or export_csv:
        write_executive_exports(
            results=results,
            queries=queries,
            output_dir=annexes_dir or str(Path(output_csv).parent or "."),
            cannibalization_groups=cannibalization_groups,
        )
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
            mode=mode,
            report_mode=detect_report_mode({"current": current_csv, "previous": previous_csv}),
            cannibalization_groups=cannibalization_groups,
        )
    return results


def detect_delimiter(filepath: str) -> str:
    with Path(filepath).open("r", encoding="utf-8-sig") as handle:
        first_line = handle.readline()
    if "\t" in first_line:
        return "\t"
    if first_line.count(";") > first_line.count(","):
        return ";"
    return ","


def detect_delimiter_from_text(text: str) -> str:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if "\t" in first_line:
        return "\t"
    if first_line.count(";") > first_line.count(","):
        return ";"
    return ","


def detect_csv_dialect(path: str | Path) -> csv.Dialect:
    sample = Path(path).read_text(encoding="utf-8-sig", errors="replace")[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        class FallbackDialect(csv.excel):
            delimiter = detect_delimiter_from_text(sample)

        return FallbackDialect


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("\xa0", " ").replace("%", "").strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    if not cleaned:
        return 0.0
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        left, right = cleaned.rsplit(",", 1)
        if len(right) == 3 and left and left.replace("-", "").isdigit():
            cleaned = left + right
        else:
            cleaned = f"{left}.{right}"
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_ctr(value: Any) -> float:
    if value is None:
        return 0.0
    raw = str(value)
    number = parse_number(value)
    if "%" in raw:
        return number
    if number <= 1:
        return number * 100
    return number


def calculate_ctr(clicks: Any, impressions: Any) -> float:
    impression_count = parse_number(impressions)
    if impression_count <= 0:
        return 0.0
    return (parse_number(clicks) / impression_count) * 100


def calculate_ctr_ratio(clicks: Any, impressions: Any) -> float:
    return calculate_ctr(clicks, impressions) / 100


def format_ctr(value: float, decimals: int | None = None) -> str:
    percent = float(value)
    resolved_decimals = decimals if decimals is not None else 2
    return f"{percent:.{resolved_decimals}f} %".replace(".", ",")


def format_ctr_ratio(value: float, decimals: int | None = None) -> str:
    return format_ctr(float(value) * 100, decimals=decimals)


def load_gsc_csv(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    source = Path(path)
    if not source.exists():
        raise CLIError(f"Fichier GSC introuvable: {path}")
    dialect = detect_csv_dialect(source)
    rows: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            return []
        for row in reader:
            rows.append(dict(row))
    return normalize_gsc_columns(rows)


def normalize_gsc_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            normalized_key = normalize_header(str(key or ""))
            if normalized_key in {"clicks", "impressions"}:
                normalized[normalized_key] = int(round(parse_number(value)))
            elif normalized_key == "ctr":
                normalized[normalized_key] = parse_ctr(value)
            elif normalized_key == "position":
                normalized[normalized_key] = round(parse_number(value), 3)
            elif normalized_key in {"page", "query", "country", "device", "date"}:
                normalized[normalized_key] = str(value or "").strip()
            elif normalized_key:
                normalized[normalized_key] = value
        if any(normalized.get(key) for key in ("page", "query", "country", "device", "date")):
            normalized.setdefault("clicks", 0)
            normalized.setdefault("impressions", 0)
            normalized["ctr"] = calculate_ctr_ratio(normalized.get("clicks"), normalized.get("impressions"))
            normalized.setdefault("position", 0.0)
            normalized_rows.append(normalized)
    return normalized_rows


def compare_gsc_periods(
    before_df: list[dict[str, Any]],
    after_df: list[dict[str, Any]],
    key_column: str,
) -> list[dict[str, Any]]:
    before = aggregate_gsc_rows(before_df, key_column)
    after = aggregate_gsc_rows(after_df, key_column)
    keys = set(before) | set(after)
    comparisons: list[dict[str, Any]] = []
    for key in sorted(keys):
        old = before.get(key, empty_gsc_metric())
        new = after.get(key, empty_gsc_metric())
        clicks_delta = int(new["clicks"] - old["clicks"])
        impressions_delta = int(new["impressions"] - old["impressions"])
        item = {
            key_column: key,
            "key": key,
            "status": "new" if key not in before else "lost" if key not in after else "existing",
            "clicks_before": int(old["clicks"]),
            "clicks_after": int(new["clicks"]),
            "clicks_delta": clicks_delta,
            "clicks_delta_pct": pct_delta(old["clicks"], new["clicks"]),
            "impressions_before": int(old["impressions"]),
            "impressions_after": int(new["impressions"]),
            "impressions_delta": impressions_delta,
            "impressions_delta_pct": pct_delta(old["impressions"], new["impressions"]),
            "ctr_before": round(float(old["ctr"]), 4),
            "ctr_after": round(float(new["ctr"]), 4),
            "ctr_delta": round(float(new["ctr"] - old["ctr"]), 4),
            "position_before": round(float(old["position"]), 2),
            "position_after": round(float(new["position"]), 2),
            "position_delta": round(float(new["position"] - old["position"]), 2),
        }
        comparisons.append(item)
    comparisons.sort(key=lambda row: (int(row["clicks_delta"]), int(row["impressions_delta"])))
    return comparisons


def aggregate_gsc_rows(rows: list[dict[str, Any]], key_column: str) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        key = str(row.get(key_column) or "").strip()
        if key_column == "page":
            key = normalize_url_for_matching(key)
        if not key:
            continue
        current = grouped.setdefault(
            key,
            {
                "clicks": 0.0,
                "impressions": 0.0,
                "ctr": 0.0,
                "position": 0.0,
                "position_weight": 0.0,
            },
        )
        clicks = parse_number(row.get("clicks"))
        impressions = parse_number(row.get("impressions"))
        current["clicks"] += clicks
        current["impressions"] += impressions
        current["position"] += parse_number(row.get("position")) * max(impressions, 1.0)
        current["position_weight"] += max(impressions, 1.0)
    for value in grouped.values():
        value["ctr"] = value["clicks"] / value["impressions"] if value["impressions"] else 0.0
        value["position"] = value["position"] / value["position_weight"] if value["position_weight"] else 0.0
    return grouped


def empty_gsc_metric() -> dict[str, float]:
    return {"clicks": 0.0, "impressions": 0.0, "ctr": 0.0, "position": 0.0}


def pct_delta(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return round(((after - before) / before) * 100, 1)


def summarize_gsc_losses(gsc_data: dict[str, Any]) -> dict[str, Any]:
    pages = list(gsc_data.get("pages") or [])
    queries = list(gsc_data.get("queries") or [])
    countries = list(gsc_data.get("countries") or [])
    devices = list(gsc_data.get("devices") or [])
    page_totals = summarize_comparison_totals(pages)
    return {
        **page_totals,
        "top_losing_pages": top_losses(pages),
        "top_losing_queries": top_losses(queries),
        "top_losing_countries": top_losses(countries),
        "top_losing_devices": top_losses(devices),
        "has_pages": bool(pages),
        "has_queries": bool(queries),
        "has_countries": bool(countries),
        "has_devices": bool(devices),
    }


def summarize_comparison_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    clicks_before = sum(int(row.get("clicks_before") or 0) for row in rows)
    clicks_after = sum(int(row.get("clicks_after") or 0) for row in rows)
    impressions_before = sum(int(row.get("impressions_before") or 0) for row in rows)
    impressions_after = sum(int(row.get("impressions_after") or 0) for row in rows)
    return {
        "clicks_before": clicks_before,
        "clicks_after": clicks_after,
        "click_loss": max(0, clicks_before - clicks_after),
        "click_loss_pct": pct_loss(clicks_before, clicks_after),
        "impressions_before": impressions_before,
        "impressions_after": impressions_after,
        "impression_loss": max(0, impressions_before - impressions_after),
        "impression_loss_pct": pct_loss(impressions_before, impressions_after),
        "ctr_before": round(clicks_before / impressions_before, 4) if impressions_before else 0.0,
        "ctr_after": round(clicks_after / impressions_after, 4) if impressions_after else 0.0,
    }


def pct_loss(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return round(max(0.0, ((before - after) / before) * 100), 1)


def top_losses(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    losing = [row for row in rows if int(row.get("clicks_delta") or 0) < 0 or int(row.get("impressions_delta") or 0) < 0]
    losing.sort(key=lambda row: (int(row.get("clicks_delta") or 0), int(row.get("impressions_delta") or 0)))
    return losing[:limit]


def normalize_url_for_matching(url: str) -> str:
    if not url:
        return ""
    candidate = str(url).strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = unquote(parsed.path or "/")
    path = re.sub(r"/+", "/", path).rstrip("/") or "/"
    path = path.lower()
    return f"{host}{path}"


def path_for_matching(url: str) -> str:
    normalized = normalize_url_for_matching(url)
    if "/" not in normalized:
        return "/"
    return normalized[normalized.find("/") :] or "/"


def match_gsc_page_to_crawl(gsc_url: str, crawl_pages: list[Any]) -> dict[str, Any]:
    gsc_normalized = normalize_url_for_matching(gsc_url)
    gsc_path = path_for_matching(gsc_url)
    indexes = build_crawl_match_indexes(crawl_pages)
    for match_type, index_name in (
        ("final_url", "final"),
        ("requested_url", "requested"),
        ("canonical", "canonical"),
    ):
        page = indexes[index_name].get(gsc_normalized)
        if page is not None:
            return {"matched": True, "match_type": match_type, "page": page}
    path_matches = indexes["path"].get(gsc_path, [])
    if len(path_matches) == 1:
        return {"matched": True, "match_type": "path", "page": path_matches[0]}
    return {"matched": False, "match_type": "unmatched", "page": None}


def build_crawl_match_indexes(crawl_pages: list[Any]) -> dict[str, Any]:
    indexes: dict[str, Any] = {"final": {}, "requested": {}, "canonical": {}, "path": defaultdict(list)}
    for page in crawl_pages:
        requested = page_value(page, "requested_url") or page_value(page, "url")
        final = page_value(page, "final_url") or page_value(page, "url")
        canonical = page_value(page, "canonical")
        requested_normalized = normalize_url_for_matching(str(requested or ""))
        final_normalized = normalize_url_for_matching(str(final or ""))
        canonical_normalized = normalize_url_for_matching(str(canonical or "")) if canonical else ""
        path_normalized = path_for_matching(str(final or requested or ""))
        set_page_value(page, "requested_url_normalized", requested_normalized)
        set_page_value(page, "final_url_normalized", final_normalized)
        set_page_value(page, "canonical_url_normalized", canonical_normalized)
        set_page_value(page, "path_normalized", path_normalized)
        if final_normalized:
            indexes["final"][final_normalized] = page
        if requested_normalized:
            indexes["requested"][requested_normalized] = page
        if canonical_normalized:
            indexes["canonical"][canonical_normalized] = page
        if path_normalized:
            indexes["path"][path_normalized].append(page)
    return indexes


def page_value(page: Any, field: str) -> Any:
    if isinstance(page, dict):
        return page.get(field)
    return getattr(page, field, None)


def set_page_value(page: Any, field: str, value: Any) -> None:
    if isinstance(page, dict):
        page[field] = value
    elif hasattr(page, field):
        setattr(page, field, value)


def resolve_gsc_export_paths(
    *,
    gsc_folder: str | None = None,
    pages_before: str | None = None,
    pages_after: str | None = None,
    queries_before: str | None = None,
    queries_after: str | None = None,
    countries_before: str | None = None,
    countries_after: str | None = None,
    devices_before: str | None = None,
    devices_after: str | None = None,
    dates: str | None = None,
) -> dict[str, str]:
    paths = {
        "pages_before": pages_before,
        "pages_after": pages_after,
        "queries_before": queries_before,
        "queries_after": queries_after,
        "countries_before": countries_before,
        "countries_after": countries_after,
        "devices_before": devices_before,
        "devices_after": devices_after,
        "dates": dates,
    }
    if gsc_folder:
        folder = Path(gsc_folder)
        conventions = {
            "pages_before": "pages_before.csv",
            "pages_after": "pages_after.csv",
            "queries_before": "queries_before.csv",
            "queries_after": "queries_after.csv",
            "countries_before": "countries_before.csv",
            "countries_after": "countries_after.csv",
            "devices_before": "devices_before.csv",
            "devices_after": "devices_after.csv",
            "dates": "dates.csv",
        }
        for key, filename in conventions.items():
            candidate = folder / filename
            if not paths.get(key) and candidate.exists():
                paths[key] = str(candidate)
    return {key: str(value) for key, value in paths.items() if value}


def resolve_gsc_standalone_inputs(
    *,
    current: str | None = None,
    previous: str | None = None,
    queries: str | None = None,
    graphique: str | None = None,
    pays: str | None = None,
    appareils: str | None = None,
    gsc_folder: str | None = None,
) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "current": current,
        "previous": previous,
        "queries": queries,
        "graphique": graphique,
        "pays": pays,
        "appareils": appareils,
    }
    if not gsc_folder:
        return values
    folder = Path(gsc_folder)
    candidates = {
        "current": ("pages_after.csv", "pages_current.csv", "pages_recent.csv", "Pages.csv"),
        "previous": ("pages_before.csv", "pages_old.csv", "pages_previous.csv"),
        "queries": ("queries_after.csv", "queries_current.csv", "queries.csv", "Requêtes.csv", "Requetes.csv"),
        "graphique": ("dates.csv", "graphique.csv", "Graphique.csv"),
        "pays": ("countries_after.csv", "pays.csv", "Pays.csv"),
        "appareils": ("devices_after.csv", "appareils.csv", "Appareils.csv"),
    }
    for key, names in candidates.items():
        if values.get(key):
            continue
        for name in names:
            candidate = folder / name
            if candidate.exists():
                values[key] = str(candidate)
                break
    if not values.get("current"):
        zips = sorted(folder.glob("*.zip"))
        if zips:
            values["current"] = str(zips[0])
    return values


def load_gsc_period_exports(paths: dict[str, str]) -> dict[str, Any]:
    data: dict[str, Any] = {"paths": paths}
    pairs = {
        "pages": ("pages_before", "pages_after", "page"),
        "queries": ("queries_before", "queries_after", "query"),
        "countries": ("countries_before", "countries_after", "country"),
        "devices": ("devices_before", "devices_after", "device"),
    }
    for output_key, (before_key, after_key, dimension) in pairs.items():
        before_path = paths.get(before_key)
        after_path = paths.get(after_key)
        if before_path and after_path:
            data[output_key] = compare_gsc_periods(load_gsc_csv(before_path), load_gsc_csv(after_path), dimension)
        else:
            data[output_key] = []
    data["dates"] = load_gsc_csv(paths.get("dates")) if paths.get("dates") else []
    data["summary"] = summarize_gsc_losses(data)
    return data


def detect_traffic_drop_start_date(date_rows: list[dict[str, Any]]) -> str:
    if len(date_rows) < 6:
        return ""
    ordered = sorted(date_rows, key=lambda row: str(row.get("date") or ""))
    midpoint = max(2, len(ordered) // 2)
    baseline_rows = ordered[:midpoint]
    baseline = sum(int(row.get("clicks") or 0) for row in baseline_rows) / max(1, len(baseline_rows))
    if baseline <= 0:
        return ""
    for row in ordered[midpoint:]:
        if int(row.get("clicks") or 0) <= baseline * 0.75:
            return str(row.get("date") or "")
    return ""


def query_intent_type(query: str, brand_terms: list[str] | None = None) -> str:
    cleaned = query.lower()
    if any(term and term.lower() in cleaned for term in brand_terms or []):
        return "branded"
    if any(term in cleaned for term in ("price", "pricing", "quote", "supplier", "manufacturer", "wholesale", "buy", "oem", "odm", "private label")):
        return "commercial"
    if any(cleaned.startswith(prefix) for prefix in ("how ", "what ", "why ", "best ", "guide ", *QUERY_QUESTION_STARTERS)):
        return "informational"
    return "unknown"


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
        "countries": "country",
        "clics": "clicks",
        "clicks": "clicks",
        "ctr": "ctr",
        "date": "date",
        "device": "device",
        "devices": "device",
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
                clicks = coerce_int(row.get(headers["clicks"]), default=0)
                impressions = coerce_int(row.get(headers["impressions"]), default=0)
                ctr = calculate_ctr_ratio(clicks, impressions)
                pages.append(
                    GSCPageData(
                        url=url,
                        clicks=clicks,
                        impressions=impressions,
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
                clicks = coerce_int(row.get(headers["clicks"]), default=0)
                impressions = coerce_int(row.get(headers["impressions"]), default=0)
                ctr = calculate_ctr_ratio(clicks, impressions)
                queries.append(
                    GSCQueryData(
                        query=query,
                        clicks=clicks,
                        impressions=impressions,
                        ctr=ctr,
                        position=coerce_float(row.get(headers["position"]), default=0.0),
                        target_url=(row.get(headers["page"]) or "").strip() if "page" in headers else "",
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
            clicks = coerce_int(row.get(headers["clicks"]), default=0)
            impressions = coerce_int(row.get(headers["impressions"]), default=0)
            ctr = calculate_ctr_ratio(clicks, impressions)
            rows.append(
                {
                    output_key: label,
                    "clics": clicks,
                    "impressions": impressions,
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
    parsed = urlparse(url if "://" in url else f"https://{url}")
    path = parsed.path or url
    parts = path.replace("/", " ").replace("-", " ").replace("_", " ").split()
    return {
        word.lower()
        for word in parts
        if (len(word) > 4 or re.fullmatch(r"p\d{2,4}", word.lower())) and word.lower() not in stopwords
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


def detect_cannibalization_groups(
    pages: list[GSCPageData],
    queries: list[GSCQueryData],
) -> list[dict[str, Any]]:
    stopwords = {word.lower() for word in GSC_CANNIBAL_STOPWORDS}
    candidates = [page for page in pages if page.impressions >= 20 and page.position <= 35]
    raw_token_map = {page.url: extract_slug_keywords(page.url, stopwords=stopwords) for page in candidates}
    token_frequency: dict[str, int] = defaultdict(int)
    for tokens in raw_token_map.values():
        for token in tokens:
            token_frequency[token] += 1
    common_tokens = {
        token
        for token, count in token_frequency.items()
        if len(candidates) >= 5 and count / max(1, len(candidates)) >= 0.45
    }
    token_map = {
        url: {token for token in tokens if token not in common_tokens}
        for url, tokens in raw_token_map.items()
    }
    query_tokens = [(query, query_token_set(query.query)) for query in queries if query.impressions >= 10 and query.position <= 25]
    groups: list[dict[str, Any]] = []
    used_urls: set[str] = set()

    for page in sorted(candidates, key=lambda item: item.impressions, reverse=True):
        if page.url in used_urls:
            continue
        tokens = token_map.get(page.url, set())
        if len(tokens) < 2:
            continue
        related: list[GSCPageData] = [page]
        for other in candidates:
            if other.url == page.url or other.url in used_urls:
                continue
            other_tokens = token_map.get(other.url, set())
            shared = tokens & other_tokens
            similarity = len(shared) / max(1, min(len(tokens), len(other_tokens)))
            tournament_group = "tournoi" in shared and (
                bool(re.search(r"p\d{2,4}", page.url.lower()))
                or bool(re.search(r"p\d{2,4}", other.url.lower()))
                or "organisation-tournoi" in page.url.lower()
                or "organisation-tournoi" in other.url.lower()
            )
            if (len(shared) >= 2 and similarity >= 0.45) or tournament_group:
                related.append(other)
        if len(related) < 2:
            continue
        combined_tokens = set().union(*(token_map.get(item.url, set()) for item in related))
        shared_queries = [
            query.query
            for query, tokens_for_query in query_tokens
            if len(tokens_for_query & combined_tokens) >= max(1, min(2, len(tokens_for_query)))
        ][:8]
        if not shared_queries and len(combined_tokens) < 3:
            continue
        topic = build_cannibalization_topic(combined_tokens, shared_queries)
        known_cluster = known_cannibalization_cluster([item.url for item in related])
        confidence = (
            "high"
            if len(shared_queries) >= 3 and len(related) >= 3
            else "medium"
            if shared_queries or known_cluster
            else "low"
        )
        if confidence == "low":
            continue
        group_id = f"can-{len(groups) + 1:02d}"
        urls = [item.url for item in related]
        groups.append(
            {
                "group_id": group_id,
                "topic": topic,
                "urls": urls,
                "shared_queries": shared_queries,
                "confidence": confidence,
                "recommendation": cannibalization_recommendation(topic, urls),
            }
        )
        used_urls.update(urls)
    return groups


def known_cannibalization_cluster(urls: list[str]) -> bool:
    joined = " ".join(strip_accents(url).lower() for url in urls)
    if len(urls) >= 3 and "tournoi" in joined and re.search(r"p\d{2,4}", joined):
        return True
    if len(urls) >= 2 and "chaussures" in joined and "padel" in joined:
        return True
    if len(urls) >= 2 and "raquette" in joined and "padel" in joined:
        return True
    return False


def build_cannibalization_topic(tokens: set[str], shared_queries: list[str]) -> str:
    if shared_queries:
        first = shared_queries[0].strip()
        return first[:80]
    ordered = sorted(tokens, key=lambda token: (-len(token), token))[:3]
    return " ".join(ordered) if ordered else "cluster à valider"


def cannibalization_recommendation(topic: str, urls: list[str]) -> str:
    if any("tournoi" in url for url in urls):
        return "Clarifier une page mère sur les tournois et des pages filles par niveau, avec ancres internes spécifiques."
    return f"Clarifier le rôle de chaque page du cluster « {topic} » et éviter que deux URLs ciblent la même intention principale."


def build_overlap_from_cannibalization_groups(groups: list[dict[str, Any]]) -> dict[str, list[str]]:
    overlap: dict[str, list[str]] = {}
    for group in groups:
        queries = [str(query) for query in group.get("shared_queries") or []]
        for url in group.get("urls") or []:
            overlap[str(url)] = queries
    return overlap


def apply_cannibalization_groups(results: list[GSCPageAnalysis], groups: list[dict[str, Any]]) -> None:
    by_url = {item.url: item for item in results}
    for group in groups:
        urls = [str(url) for url in group.get("urls") or []]
        shared_queries = [str(query) for query in group.get("shared_queries") or []]
        for url in urls:
            item = by_url.get(url)
            if not item:
                continue
            item.cannibalization_group_id = str(group.get("group_id") or "")
            item.urls_in_group = [other for other in urls if other != url]
            item.shared_queries = shared_queries
            item.cannibalization_confidence = str(group.get("confidence") or "")
            item.cannibalization_recommendation = str(group.get("recommendation") or "")
            item.action_type = action_type_for_analysis(item)
            item.recommendation = specific_recommendation_for_page(item)


def analyze_pages(
    current: list[GSCPageData],
    previous: list[GSCPageData] | None,
    possible_overlap: dict[str, list[str]],
    queries: list[GSCQueryData] | None = None,
    site_context: str = "affiliate_media",
) -> list[GSCPageAnalysis]:
    previous_map = {page.url: page for page in previous or []}
    max_impressions = max((page.impressions for page in current), default=1)
    results: list[GSCPageAnalysis] = []
    query_rows = queries or []

    for page in current:
        main_query = find_main_query_for_page(page, query_rows)
        page_type = classify_page_type(page.url, main_query.query if main_query else "")
        business_value, business_reason, monetization = estimate_business_value(
            page.url,
            title="",
            queries=[main_query.query] if main_query else [],
            page_type=page_type,
            site_context=site_context,
        )
        analysis = GSCPageAnalysis(
            url=page.url,
            clicks=page.clicks,
            impressions=page.impressions,
            ctr=page.ctr,
            position=page.position,
            possible_overlap_queries=possible_overlap.get(page.url, []),
            page_type=page_type,
            business_value=business_value,
            business_reason=business_reason,
            monetization_possible=monetization,
            main_query=main_query.query if main_query else keyword_phrase_from_url(page.url),
        )
        previous_page = previous_map.get(page.url)
        if previous_page:
            analysis.prev_clicks = previous_page.clicks
            analysis.prev_impressions = previous_page.impressions
            analysis.prev_position = previous_page.position
            analysis.click_delta = page.clicks - previous_page.clicks
            analysis.impression_delta = page.impressions - previous_page.impressions
            analysis.position_delta = round(page.position - previous_page.position, 1)

        legacy_score = round(
            gsc_score_position(page.position)
            + gsc_score_impressions(page.impressions, max_impressions)
            + gsc_score_ctr(page.ctr, page.position)
            + gsc_score_decline(analysis.click_delta, analysis.impression_delta),
            1,
        )
        analysis.actions = suggest_actions(analysis)
        analysis.estimated_recoverable_clicks, analysis.impact_label = estimate_recoverable_clicks(analysis)
        analysis.opportunity_score = seo_opportunity_score(analysis, max_impressions=max_impressions)
        analysis.score = max(legacy_score, float(analysis.opportunity_score))
        analysis.category = categorize_page(analysis)
        analysis.priority = priority_for_page(analysis)
        analysis.priority_label = priority_label_for_score(analysis)
        analysis.action_type = action_type_for_analysis(analysis)
        analysis.recommendation = specific_recommendation_for_page(analysis)
        results.append(analysis)

    results.sort(key=lambda item: (0 if item.priority == "DEAD" else 1, -item.opportunity_score, -item.score))
    return results


def find_main_query_for_page(page: GSCPageData, queries: list[GSCQueryData]) -> GSCQueryData | None:
    if not queries:
        return None
    page_url = normalize_url_for_query_match(page.url)
    page_queries = [
        query
        for query in queries
        if query.target_url and normalize_url_for_query_match(query.target_url) == page_url
    ]
    if not page_queries:
        return None
    return max(page_queries, key=lambda query: (query.impressions, query.clicks, -query.position))


def normalize_url_for_query_match(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.rstrip("/") or "/"
        return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), path=path).geturl()
    return value.rstrip("/")


def classify_page_type(url: str, main_query: str = "") -> str:
    text = strip_accents(f"{url} {main_query}").lower()
    if any(term in text for term in ("comparatif", "meilleur", "avis", "test-", "/test", "guide-achat")):
        return "commercial"
    if any(term in text for term in ("comment", "tenir", "changer", "nettoyer", "regle", "technique", "service", "vollee")):
        return "practical guide"
    if any(term in text for term in ("raquette", "chaussure", "balle", "pressurisateur", "sac", "equipement")):
        return "equipment"
    if any(term in text for term in ("tournoi", "p100", "p250", "p500", "niveau", "points")):
        return "cluster guide"
    if any(term in text for term in ("joueur", "joueuse", "biographie", "actualite", "news")):
        return "low business editorial"
    return "editorial"


def estimate_business_value(
    url: str,
    title: str = "",
    queries: list[str] | None = None,
    page_type: str = "",
    site_context: str = "affiliate_media",
) -> tuple[str, str, str]:
    haystack = strip_accents(" ".join([url, title, page_type, " ".join(queries or [])])).lower()
    commercial_modifiers = ("meilleur", "meilleure", "avis", "comparatif", "test", "acheter", "achat", "prix", "promo", "choisir")
    if page_type == "practical guide" and not any(term in haystack for term in commercial_modifiers):
        return "medium", "Guide pratique pouvant pousser vers une ressource ou un produit.", "produit numérique"
    if any(term in haystack for term in BUSINESS_HIGH_TERMS):
        monetization = "affiliation"
        if any(term in haystack for term in ("programme", "pdf", "formation")):
            monetization = "produit numérique"
        return "high", "Intention produit, comparatif, test ou achat possible.", monetization
    if any(term in haystack for term in BUSINESS_LOW_TERMS):
        return "low", "Sujet éloigné d'une monétisation directe.", "none"
    if any(term in haystack for term in ("tournoi", "club", "terrain", "local", "partenaire")):
        return "medium", "Potentiel de cluster, partenariat ou lead indirect.", "lead"
    if any(term in haystack for term in ("comment", "technique", "guide", "regle", "niveau")):
        return "medium", "Guide pratique pouvant pousser vers une ressource ou un produit.", "produit numérique"
    return "low", "Valeur business à confirmer manuellement.", "none"


def seo_opportunity_score(analysis: GSCPageAnalysis, max_impressions: int) -> int:
    if is_dead_gsc_page(analysis):
        return 0
    impressions_score = min(20.0, (analysis.impressions / max(1, max_impressions)) * 20.0)
    expected_ctr = expected_ctr_for_position(analysis.position)
    ctr_gap_score = 0.0
    if expected_ctr:
        ctr_gap_score = max(0.0, min(20.0, ((expected_ctr - analysis.ctr) / expected_ctr) * 20.0))
    if 4 <= analysis.position <= 12:
        position_score = 20.0
    elif 12 < analysis.position <= 15:
        position_score = 14.0
    elif 2 <= analysis.position < 4:
        position_score = 9.0
    elif 15 < analysis.position <= 25:
        position_score = 6.0
    else:
        position_score = 0.0
    business_score = {"high": 25.0, "medium": 10.0, "low": 0.0}.get(analysis.business_value, 0.0)
    query_score = 5.0 if analysis.main_query and analysis.main_query != "la requête principale" else 0.0
    monetization_score = 15.0 if analysis.monetization_possible != "none" else 0.0
    gain_score = 5.0 if analysis.estimated_recoverable_clicks else 0.0
    action_score = 0.0
    if is_snippet_opportunity(analysis):
        action_score += 10.0
    if 4 <= analysis.position <= 15:
        action_score += 10.0
    if analysis.impressions < 50:
        impressions_score = max(0.0, impressions_score - 20.0)
        ctr_gap_score *= 0.4
    if analysis.position > 30 and analysis.business_value != "high":
        position_score = max(0.0, position_score - 20.0)
    low_business_penalty = 15.0 if analysis.business_value == "low" else 0.0
    cannibalization_penalty = 10.0 if analysis.cannibalization_confidence == "high" else 0.0
    score = (
        impressions_score
        + ctr_gap_score
        + position_score
        + business_score
        + query_score
        + monetization_score
        + gain_score
        + action_score
        - low_business_penalty
        - cannibalization_penalty
    )
    return int(round(max(0.0, min(100.0, score))))


def calculate_opportunity_score(page: GSCPageAnalysis, max_impressions: int = 1) -> int:
    return seo_opportunity_score(page, max_impressions=max_impressions)


def priority_label_for_score(analysis: GSCPageAnalysis) -> str:
    score = analysis.opportunity_score
    if is_dead_gsc_page(analysis) or score < 20:
        return "Ignore" if is_dead_gsc_page(analysis) else "Watch"
    if score >= 75:
        return "P1"
    if score >= 55:
        return "P2"
    if score >= 35:
        return "P3"
    return "Watch"


def action_type_for_analysis(analysis: GSCPageAnalysis) -> str:
    if analysis.cannibalization_group_id:
        return "cannibalization"
    if analysis.business_value == "high":
        return "business page"
    if is_snippet_opportunity(analysis):
        return "snippet"
    if 4 <= analysis.position <= 12:
        return "content refresh"
    if 12 < analysis.position <= 20:
        return "internal linking"
    if analysis.position > 20 and analysis.business_value == "high":
        return "content refresh"
    return "technical check" if is_dead_gsc_page(analysis) else "content refresh"


def specific_recommendation_for_page(analysis: GSCPageAnalysis) -> str:
    return generate_page_recommendation(
        page=analysis.url,
        main_queries=[analysis.main_query] if analysis.main_query else [],
        page_type=analysis.page_type,
        business_value=analysis.business_value,
        analysis=analysis,
    )


def generate_page_recommendation(
    page: str,
    main_queries: list[str] | None,
    page_type: str,
    business_value: str,
    analysis: GSCPageAnalysis | None = None,
) -> str:
    query = (main_queries or [keyword_phrase_from_url(page)])[0] or keyword_phrase_from_url(page)
    lower = strip_accents(f"{page} {query} {page_type}").lower()
    if "tournoi-padel-p100" in lower:
        return "Ajouter un bloc « Quel niveau pour jouer un P100 ? », un tableau points / inscription / classement, puis une FAQ sur les cuts, le partenaire, le prix d'inscription et la préparation du premier tournoi."
    if "tournoi-padel-p500" in lower:
        return "Clarifier le nombre de points, le niveau attendu et les conditions d'inscription, puis ajouter des liens vers les pages P100, P250 et le guide global des tournois."
    if "tournoi" in lower and re.search(r"p\d{2,4}", lower):
        level = (re.search(r"p\d{2,4}", lower) or re.search(r"p\d{2,4}", query.lower()))
        label = level.group(0).upper() if level else "ce niveau"
        return f"Structurer la page {label} autour du niveau attendu, des points, du format, des conditions d'inscription et des liens vers le guide global des tournois."
    if "tenir-raquette-padel" in lower:
        return "Ajouter des visuels de prise, une section sur la prise continentale, les erreurs fréquentes et des liens vers coups de base, service et raquette débutant."
    if "pressurisateur" in lower:
        return "Renforcer l'intention achat : critères de choix, modèles recommandés, limites réelles, puis liens vers balles padel et comparaisons Decathlon/Amazon si pertinentes."
    if "chaussures-padel" in lower and "test-chaussures" not in lower:
        return "Structurer la page autour des critères d'achat : semelle, maintien, amorti, surface et morphologie, puis lier vers les tests chaussures Kuikma, Asics, Nox et Joma."
    if "raquette-padel" in lower and "/test-" not in lower:
        return "Recentrer la page sur l'aide au choix : tableau par niveau, forme, mousse, poids et budget, puis liens vers les tests et comparatifs raquettes."
    if "/test-" in lower or "test-" in lower:
        return "Ajouter un verdict en haut de page, les profils de joueurs concernés, les limites du produit et des liens vers la page catégorie ou le comparatif correspondant."
    if "sac-padel" in lower or "balles-padel" in lower:
        return "Transformer la page en aide au choix avec critères d'achat, cas d'usage, erreurs fréquentes et liens vers les tests ou produits associés."
    action_type = analysis.action_type if analysis is not None else ""
    if action_type == "cannibalization":
        return analysis.cannibalization_recommendation or "Clarifier le rôle de chaque URL du cluster avant d'optimiser les contenus."
    if action_type == "snippet":
        return f"Réécrire le title autour de « {query} », puis faire porter la meta sur le bénéfice exact de la page et les éléments consultables dès l'arrivée."
    if action_type == "internal linking":
        return f"Créer des liens internes vers cette page depuis les contenus du même cluster avec des ancres proches de « {query} », puis renforcer les sections qui répondent aux sous-intentions visibles."
    if business_value == "high":
        return "Ajouter critères de décision, limites, comparaisons et liens de monétisation utiles afin de transformer la visibilité Google en clics business qualifiés."
    return "Garder en suivi GSC et prioriser seulement si les impressions ou la position progressent."


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
    score = analysis.opportunity_score or int(round(analysis.score))
    if score >= 60:
        return "HIGH"
    if score >= 40:
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
            "Chevauchement page/requête possible à vérifier avant de conclure à des pages en concurrence"
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
            f"si le taux de clic se rapproche de l’attendu à position {position_bucket}"
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
        "priority_label",
        "score",
        "seo_opportunity_score",
        "category",
        "url",
        "clicks",
        "impressions",
        "ctr",
        "position",
        "business_value",
        "business_reason",
        "monetization_possible",
        "main_query",
        "action_type",
        "recommendation",
        "prev_clicks",
        "prev_impressions",
        "prev_position",
        "click_delta",
        "impression_delta",
        "position_delta",
        "estimated_recoverable_clicks",
        "impact_label",
        "possible_overlap_queries",
        "cannibalization_group_id",
        "urls_in_group",
        "shared_queries",
        "cannibalization_confidence",
        "actions",
    ]
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "priority": item.priority,
                    "priority_label": item.priority_label,
                    "score": item.score,
                    "seo_opportunity_score": item.opportunity_score,
                    "category": item.category,
                    "url": item.url,
                    "clicks": item.clicks,
                    "impressions": item.impressions,
                    "ctr": format_ctr_ratio(item.ctr),
                    "position": f"{item.position:.1f}",
                    "business_value": item.business_value,
                    "business_reason": item.business_reason,
                    "monetization_possible": item.monetization_possible,
                    "main_query": item.main_query,
                    "action_type": item.action_type,
                    "recommendation": item.recommendation,
                    "prev_clicks": item.prev_clicks or "",
                    "prev_impressions": item.prev_impressions or "",
                    "prev_position": f"{item.prev_position:.1f}" if item.prev_position is not None else "",
                    "click_delta": item.click_delta if item.click_delta is not None else "",
                    "impression_delta": item.impression_delta if item.impression_delta is not None else "",
                    "position_delta": item.position_delta if item.position_delta is not None else "",
                    "estimated_recoverable_clicks": item.estimated_recoverable_clicks or "",
                    "impact_label": item.impact_label,
                    "possible_overlap_queries": " | ".join(item.possible_overlap_queries),
                    "cannibalization_group_id": item.cannibalization_group_id,
                    "urls_in_group": " | ".join(item.urls_in_group),
                    "shared_queries": " | ".join(item.shared_queries),
                    "cannibalization_confidence": item.cannibalization_confidence,
                    "actions": " | ".join(item.actions),
                }
            )
    return output_file


def write_json(results: list[GSCPageAnalysis], output_path: str) -> Path:
    output_file = ensure_parent_dir(output_path)
    payload: list[dict[str, object]] = []
    for item in results:
        row = asdict(item)
        row["ctr"] = format_ctr_ratio(item.ctr)
        payload.append(row)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return output_file


def write_executive_exports(
    *,
    results: list[GSCPageAnalysis],
    queries: list[GSCQueryData],
    output_dir: str,
    cannibalization_groups: list[dict[str, Any]],
) -> list[Path]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    page_rows = [pages_opportunity_export_row(item) for item in results]
    query_rows = [queries_opportunity_export_row(query, results) for query in queries]
    snippet_rows = [snippet_export_row(item) for item in results if is_snippet_opportunity(item)]
    cannibalization_rows = [cannibalization_export_row(group) for group in cannibalization_groups]
    paths = [
        write_dict_csv(folder / "pages_opportunities.csv", page_rows),
        write_dict_csv(folder / "queries_opportunities.csv", query_rows),
        write_dict_csv(folder / "snippets_rewrite.csv", snippet_rows),
        write_dict_csv(folder / "cannibalization_groups.csv", cannibalization_rows),
        write_dict_csv(folder / "full_pages_export.csv", page_rows),
        write_dict_csv(folder / "full_queries_export.csv", query_rows),
        write_dict_csv(folder / "pages_full_export.csv", page_rows),
        write_dict_csv(folder / "queries_full_export.csv", query_rows),
        write_dict_csv(folder / "snippets_full_export.csv", snippet_rows),
        write_dict_csv(folder / "opportunities_full_export.csv", page_rows),
    ]
    return paths


def write_dict_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    output_file = ensure_parent_dir(str(path))
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_file


def pages_opportunity_export_row(item: GSCPageAnalysis) -> dict[str, object]:
    return {
        "url": item.url,
        "clicks": item.clicks,
        "impressions": item.impressions,
        "ctr_recalculated": format_ctr_ratio(item.ctr),
        "position": f"{item.position:.2f}",
        "business_value": item.business_value,
        "opportunity_score": item.opportunity_score,
        "priority": item.priority_label,
        "action_type": item.action_type,
        "estimated_gain": item.estimated_recoverable_clicks or 0,
        "main_query": item.main_query,
        "recommendation": item.recommendation,
    }


def queries_opportunity_export_row(query: GSCQueryData, results: list[GSCPageAnalysis]) -> dict[str, object]:
    recommendation = classify_query_recommendation(query, results)
    target = best_target_url_for_query(query, results)
    return {
        "query": query.query,
        "clicks": query.clicks,
        "impressions": query.impressions,
        "ctr_recalculated": format_ctr_ratio(query.ctr),
        "position": f"{query.position:.2f}",
        "intent": probable_intent_from_keyword(query.query),
        "recommendation": recommendation,
        "target_url": target,
        "should_create_new_content": "yes" if should_consider_new_content(query, results) else "no",
    }


def snippet_export_row(item: GSCPageAnalysis) -> dict[str, object]:
    snippet = generate_snippet_recommendation(
        page=item.url,
        main_query=item.main_query or keyword_phrase_from_url(item.url),
        page_type=item.page_type,
        business_value=item.business_value,
        intent=probable_intent_from_keyword(item.main_query),
        gsc_data=asdict(item),
    )
    return {
        "url": item.url,
        "main_query": item.main_query,
        "current_title": "",
        "suggested_title": snippet["title"],
        "suggested_meta": snippet["meta"],
        "reason": snippet["reason"],
    }


def cannibalization_export_row(group: dict[str, Any]) -> dict[str, object]:
    return {
        "group_id": group.get("group_id", ""),
        "topic": group.get("topic", ""),
        "urls": " | ".join(str(url) for url in group.get("urls") or []),
        "shared_queries": " | ".join(str(query) for query in group.get("shared_queries") or []),
        "confidence": group.get("confidence", ""),
        "recommendation": group.get("recommendation", ""),
    }


def best_target_url_for_query(query: GSCQueryData, results: list[GSCPageAnalysis]) -> str:
    query_slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(query.query).lower()).strip("-")
    if query_slug:
        exact_matches = [
            item.url
            for item in results
            if query_slug in re.sub(r"[^a-z0-9]+", "-", strip_accents(urlparse(item.url).path).lower())
        ]
        if exact_matches:
            return sorted(exact_matches, key=len)[0]
    tokens = query_token_set(query.query)
    if not tokens:
        return ""
    best: tuple[float, str] | None = None
    for item in results:
        page_tokens = extract_slug_keywords(item.url, stopwords=set(GSC_CANNIBAL_STOPWORDS))
        overlap = len(tokens & page_tokens)
        score = overlap * 100 + item.impressions / 100 - item.position
        if overlap <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, item.url)
    return best[1] if best else ""


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
    mode: str = "executive",
    report_mode: str | None = None,
    cannibalization_groups: list[dict[str, Any]] | None = None,
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
        results = analyze_pages(current=current, previous=previous, possible_overlap=overlap, queries=queries)
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
    detected_report_mode = report_mode or detect_report_mode({"previous": previous_csv})
    period_note = (
        "Before/After traffic comparison: export précédent fourni, les variations peuvent être contextualisées."
        if detected_report_mode == "before_after_comparison"
        else "Current period analysis: aucun export précédent fourni, ce rapport identifie des opportunités sur la visibilité actuelle."
    )
    previous_note = (
        "Export Pages précédent: fourni, les variations peuvent être contextualisées."
        if (has_previous if has_previous is not None else bool(previous_csv))
        else "Export Pages précédent: non fourni, la lecture reste centrée sur la période actuelle."
    )

    priority_count = sum(1 for item in results if item.priority in {"HIGH", "MEDIUM"} and not is_dead_gsc_page(item))
    snippet_count = sum(1 for item in results if is_snippet_opportunity(item))
    query_opportunities_count = len([query for query in queries if query.impressions >= 30 and query.position <= 20])
    sections = assign_report_sections(results)
    has_query_export = has_queries if has_queries is not None else bool(queries)
    priority_pages = build_priority_page_cards(results)[:10]
    priority_page_urls = {normalize_url_for_query_match(str(page.get("url", ""))) for page in priority_pages}
    snippet_pages = build_snippet_cards(results, excluded_urls=priority_page_urls)[:10]
    estimated_gain_note = (
        "Estimation basée sur un alignement CTR médian pour la position actuelle. "
        "Non garanti — à valider après mise en ligne et suivi GSC sur 30-60 jours."
    )
    return {
        "title": "GSC SEO Opportunity Report" if mode == "executive" else title,
        "subtitle": "Opportunités de croissance, pages prioritaires et actions recommandées",
        "site_name": domain,
        "generated_at": datetime.now().strftime("%d/%m/%Y"),
        "period_label": build_period_label(filters),
        "mode": mode,
        "report_mode": detected_report_mode,
        "report_mode_label": report_mode_label(detected_report_mode),
        "executive_summary": build_executive_summary(results, priority_count, snippet_count, bool(queries)),
        "estimated_gain_value": f"+{format_number(total_recoverable)} clics potentiels",
        "estimated_gain_note": estimated_gain_note,
        "monthly_priorities": build_monthly_priorities(results, queries),
        "source_notes": [
            "Analyse basée sur les données Google Search Console exportées.",
            period_note if mode == "executive" else previous_note,
            (
                "Sans export précédent, ce rapport ne diagnostique pas une baisse de trafic."
                if detected_report_mode == "current_period_only"
                else "Les baisses et gains doivent être lus comme des variations entre les deux exports fournis."
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
            {"label": "Taux de clic moyen", "value": format_percent(avg_ctr)},
            {"label": "Position moyenne", "value": f"{avg_position:.1f}" if avg_position else "-"},
            {"label": "Pages prioritaires", "value": format_number(priority_count)},
            {"label": translate("Snippets à retravailler"), "value": format_number(snippet_count)},
            {"label": "Requêtes exploitables", "value": format_number(query_opportunities_count)},
            {"label": "Gain de trafic estimé", "value": "Voir note"},
        ],
        "sections": sections,
        "priority_pages": priority_pages,
        "snippet_pages": snippet_pages,
        "snippet_section_note": (
            "Les résultats Google des pages prioritaires sont détaillés dans la section ci-dessus. "
            "Cette section liste uniquement les pages hors Top 10 prioritaire."
        ),
        "breakthrough_pages": build_breakthrough_cards(results)[:10],
        "query_sections": build_query_sections(queries, results),
        "top_query_opportunities": build_top_query_opportunities(queries, results, limit=20),
        "business_opportunities": build_business_opportunities(results)[:10],
        "appendix_pages": [page_to_appendix_row(item) for item in results],
        "appendix_queries": [query_to_appendix_row(query, results) for query in queries],
        "annex_files": [
            "pages_opportunities.csv",
            "queries_opportunities.csv",
            "snippets_rewrite.csv",
            "cannibalization_groups.csv",
            "full_pages_export.csv",
            "full_queries_export.csv",
            "pages_full_export.csv",
            "queries_full_export.csv",
            "snippets_full_export.csv",
            "opportunities_full_export.csv",
        ],
        "cannibalization_groups": cannibalization_groups or [],
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


def detect_report_mode(gsc_inputs: dict[str, Any]) -> str:
    if gsc_inputs.get("previous") or gsc_inputs.get("pages_before"):
        return "before_after_comparison"
    return "current_period_only"


def report_mode_label(value: str) -> str:
    if value == "before_after_comparison":
        return "Before/After comparison"
    return "Current period only"


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
        f" {format_count(snippet_count, 'résultat Google ressort', 'résultats Google ressortent')} comme candidats à une réécriture prioritaire."
        if snippet_count
        else ""
    )
    return (
        base
        + query_note
        + snippet_note
        + " Les gains estimés sont des ordres de grandeur, pas des promesses de trafic."
    )


def build_monthly_priorities(results: list[GSCPageAnalysis], queries: list[GSCQueryData]) -> list[dict[str, str]]:
    snippet_count = sum(1 for item in results if is_snippet_opportunity(item))
    near_count = sum(1 for item in results if is_near_breakthrough(item) or 4 <= item.position <= 12)
    query_count = len([query for query in queries if query.impressions >= 50])
    priorities = [
        {
            "title": "Améliorer les résultats Google des pages à fortes impressions",
            "why": (
                f"{format_count(snippet_count, 'page est déjà visible mais sous-cliquée', 'pages sont déjà visibles mais sous-cliquées')}."
                if snippet_count
                else "Les pages visibles doivent donner une raison plus claire de cliquer."
            ),
            "action": "Réécrire les titles, les meta descriptions et l’angle d’entrée des pages prioritaires.",
            "impact": "Potentiel d’amélioration du taux de clic sans attendre une progression de position.",
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
        key=lambda item: (item.opportunity_score, business_sort_weight(item.business_value), item.estimated_recoverable_clicks or 0, item.impressions),
        reverse=True,
    )
    return [page_to_report_dict(item) for item in ordered if item.priority in {"HIGH", "MEDIUM"} or item.estimated_recoverable_clicks]


def business_sort_weight(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def build_snippet_cards(
    results: list[GSCPageAnalysis],
    excluded_urls: set[str] | None = None,
) -> list[dict[str, object]]:
    excluded = excluded_urls or set()
    return [
        snippet_to_report_dict(item)
        for item in sorted(results, key=lambda row: row.impressions, reverse=True)
        if is_snippet_opportunity(item) and normalize_url_for_query_match(item.url) not in excluded
    ]


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


def build_top_query_opportunities(
    queries: list[GSCQueryData],
    results: list[GSCPageAnalysis],
    limit: int = 20,
) -> list[dict[str, object]]:
    candidates = [query for query in queries if query.impressions >= 20 and query.position <= 30]
    candidates.sort(
        key=lambda query: (
            query.impressions,
            -query.clicks,
            -abs(query.position - 10) if query.position <= 20 else -query.position,
        ),
        reverse=True,
    )
    rows: list[dict[str, object]] = []
    for query in candidates[:limit]:
        recommendation = classify_query_recommendation(query, results)
        rows.append(
            {
                "query": query.query,
                "clicks": format_number(query.clicks),
                "impressions": format_number(query.impressions),
                "ctr": format_percent(query.ctr),
                "position": f"{query.position:.1f}",
                "intent": probable_intent_from_keyword(query.query),
                "recommendation": recommendation,
                "target_url": best_target_url_for_query(query, results),
                "should_create_new_content": "oui" if should_consider_new_content(query, results) else "non",
            }
        )
    return rows


def build_business_opportunities(results: list[GSCPageAnalysis]) -> list[dict[str, object]]:
    high_value = [item for item in results if item.business_value == "high" and not is_dead_gsc_page(item)]
    high_value.sort(key=lambda item: (item.opportunity_score, item.impressions, item.estimated_recoverable_clicks or 0), reverse=True)
    return [page_to_report_dict(item) for item in high_value]


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
        if (len(word) > 3 or re.fullmatch(r"p\d{2,4}", strip_accents(word).lower()))
        and strip_accents(word).lower() not in stopwords
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
        translate("CTR"): row["ctr"],
        "Position": row["position"],
        "Recommandation": row["recommendation"],
    }


def classify_query_recommendation(query: GSCQueryData, results: list[GSCPageAnalysis]) -> str:
    lowered = query.query.strip().lower()
    if query.impressions < 20 or query.position > 40:
        return "à ignorer / faible valeur"
    if lowered.startswith(QUERY_QUESTION_STARTERS) or len(lowered.split()) >= 5:
        return "FAQ"
    if query.ctr < expected_ctr_for_position(query.position) * 0.65 and query.position <= 12:
        return "résultat Google"
    if should_consider_new_content(query, results):
        return "nouveau contenu"
    if 8 < query.position <= 20:
        return "maillage interne"
    return "section à ajouter"


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
    action_types = [action_label_from_type(item.action_type)] if item.action_type else action_types_for_page(actions)
    return {
        "url": item.url,
        "slug": display_slug(item.url),
        "priority": priority_css_class(item),
        "priority_label": item.priority_label or client_priority_label(item),
        "diagnostic": diagnostic_for_page(item),
        "metrics": {
            "Clics": format_number(item.clicks),
            "Impressions": format_number(item.impressions),
            translate("CTR"): format_percent(item.ctr),
            "Position": f"{item.position:.1f}",
            "Gain estimé": f"+{format_number(item.estimated_recoverable_clicks)}" if item.estimated_recoverable_clicks else "à confirmer",
        },
        "business_value": item.business_value,
        "business_reason": item.business_reason,
        "monetization_possible": item.monetization_possible,
        "opportunity_score": item.opportunity_score,
        "main_query": item.main_query,
        "recommendation": item.recommendation,
        "actions": actions,
        "action_types": ",".join(css_action_type(value) for value in action_types),
        "action_type_labels": action_types,
        "effort": effort_for_page(item),
        "impact": impact_for_page(item),
        "why": explain_reason(item),
        "overlap_queries": item.possible_overlap_queries[:4],
        "cannibalization": {
            "group_id": item.cannibalization_group_id,
            "urls": item.urls_in_group,
            "shared_queries": item.shared_queries,
            "confidence": item.cannibalization_confidence,
            "recommendation": item.cannibalization_recommendation,
        },
    }


def action_types_for_page(actions: list[str]) -> list[str]:
    types: list[str] = []
    joined = " ".join(actions).lower()
    if "title" in joined or "méta" in joined or "meta" in joined or "ctr" in joined:
        types.append(translate("Snippet"))
    if "contenu" in joined or "faq" in joined or "fraîcheur" in joined or "fraicheur" in joined:
        types.append("Contenu")
    if "maillage" in joined or "liens internes" in joined:
        types.append("Maillage interne")
    if "technique" in joined or "redirection" in joined or "supprimer" in joined:
        types.append("Technique")
    if "cannibalisation" in joined or "chevauchement" in joined:
        types.append("⚠ Pages en compétition")
    return list(dict.fromkeys(types)) or ["Contenu"]


def action_label_from_type(action_type: str) -> str:
    labels = {
        "snippet": translate("Snippet"),
        "content refresh": "Contenu",
        "internal linking": "Maillage interne",
        "business page": "Page business",
        "new content": "Nouveau contenu",
        "cannibalization": "⚠ Pages en compétition",
        "technical check": "Technique",
    }
    return labels.get(action_type, "Contenu")


def css_action_type(label: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "", strip_accents(label).lower().replace(" ", "-"))


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
        return "La page reçoit beaucoup d’impressions mais son taux de clic reste faible par rapport à sa visibilité."
    if 4 <= item.position <= 10:
        return "La page est déjà proche des premières positions et peut progresser avec un renforcement ciblé."
    if 10 < item.position <= 20:
        return "La page est visible mais manque probablement de profondeur ou de soutien interne pour passer un cap."
    if item.possible_overlap_queries:
        return "Plusieurs URLs semblent répondre à des requêtes proches, à vérifier avant optimisation."
    return "La page présente un signal utile mais moins urgent que les priorités principales."


def impact_for_page(item: GSCPageAnalysis) -> str:
    if item.estimated_recoverable_clicks:
        return f"+{format_number(item.estimated_recoverable_clicks)} clics récupérables estimés"
    if is_snippet_opportunity(item):
        return "Hausse potentielle du taux de clic"
    if item.position <= 20:
        return "Potentiel de progression SEO"
    return "Impact à confirmer: le signal actuel reste limité."


def precise_actions_for_page(item: GSCPageAnalysis) -> list[str]:
    primary = specific_recommendation_for_page(item)
    actions: list[str] = [primary]
    if is_dead_gsc_page(item):
        return [
            "vérifier si la page répond encore à une intention utile",
            "fusionner avec une page plus forte si le sujet est déjà couvert",
            "prévoir une redirection 301 ou un retrait propre si la page n’a plus de rôle",
        ]
    if item.click_delta is not None and item.click_delta < -10:
        actions.append("contrôler la fraîcheur du contenu et les changements visibles dans les résultats Google")
    return (list(dict.fromkeys(actions)) or ["garder la page en suivi et réévaluer lors du prochain export GSC"])[:5]


def keyword_phrase_from_url(url: str) -> str:
    slug = display_slug(url).strip("/")
    if not slug:
        return "la requête principale"
    last_segment = slug.split("/")[-1]
    words = [word for word in re.split(r"[-_]+", last_segment) if word and not word.isdigit()]
    return " ".join(words[:6]) or "la requête principale"


def snippet_to_report_dict(item: GSCPageAnalysis) -> dict[str, object]:
    keyword = item.main_query or keyword_phrase_from_url(item.url)
    recommendation = generate_snippet_recommendation(
        page=item.url,
        main_query=keyword,
        page_type=item.page_type,
        business_value=item.business_value,
        intent=probable_intent_from_keyword(keyword),
        gsc_data={"clicks": item.clicks, "impressions": item.impressions, "ctr": item.ctr, "position": item.position},
    )
    return {
        "url": item.url,
        "slug": display_slug(item.url),
        "main_query": keyword,
        "problem": snippet_problem_for_page(item),
        "intent": probable_intent_from_keyword(keyword),
        "angle": recommendation["reason"],
        "title_example": recommendation["title"],
        "meta_example": recommendation["meta"],
        "position": item.position,
        "metrics": f"{format_number(item.impressions)} impressions · taux de clic {format_percent(item.ctr)} · position {item.position:.1f}",
    }


def generate_snippet_recommendation(
    page: str,
    main_query: str,
    page_type: str = "",
    business_value: str = "",
    gsc_data: dict[str, Any] | None = None,
    intent: str = "",
) -> dict[str, str]:
    query = clean_query_for_snippet(main_query or keyword_phrase_from_url(page))
    lower = strip_accents(f"{page} {query} {page_type} {business_value} {intent}").lower()
    if "p100" in lower or "p250" in lower or "p500" in lower:
        level = "P100" if "p100" in lower else "P250" if "p250" in lower else "P500"
        title = f"Tournoi {level} padel : niveau, points et inscription"
        meta = f"Comprenez le niveau requis en {level}, les points à gagner, les règles d'inscription et les repères pour préparer votre tournoi."
    elif "par 4" in lower or "par-4" in lower:
        title = "Par 4 au padel : réussir le smash qui sort du terrain"
        meta = "Placement, hauteur de balle, timing et erreurs fréquentes : les repères pour tenter un par 4 plus proprement en match."
    elif "tenir" in lower and "raquette" in lower:
        title = "Comment tenir sa raquette de padel sans se crisper"
        meta = "Placement de la main, prise continentale, erreurs fréquentes : les bases pour mieux tenir votre raquette et gagner en contrôle."
    elif "agustin" in lower or "tapia" in lower:
        title = "Agustín Tapia : profil, palmarès et style de jeu"
        meta = "Découvrez le parcours d'Agustín Tapia, son style sur le circuit pro, ses forces en match et les repères clés pour suivre sa carrière."
    elif "pressurisateur" in lower:
        title = "Meilleur pressurisateur de balles de padel : comparatif"
        meta = "Comparez les pressurisateurs utiles pour prolonger la durée de vie des balles, avec critères d'achat, limites et conseils pratiques."
    elif "chaussure" in lower:
        title = "Chaussures de padel : modèles, critères et erreurs à éviter"
        meta = "Semelle, maintien, confort, surface de jeu : les critères à vérifier avant de choisir une paire de chaussures de padel."
    elif any(term in lower for term in ("meilleur", "comparatif", "avis", "test", "raquette", "chaussure", "balle", "sac")):
        title = title_case_snippet(f"{query} : critères, avis et choix utiles")
        meta = f"Comparez les options autour de {query}, avec les critères de choix, les limites à connaître et les profils pour lesquels elles conviennent."
    elif lower.startswith("comment") or "comment " in lower:
        title = title_case_snippet(f"{query} : méthode simple et erreurs à éviter")
        meta = f"Retrouvez les gestes, repères et erreurs fréquentes pour {query.replace('comment ', '')}, avec une approche concrète à appliquer sur le terrain."
    elif "tournoi" in lower:
        title = title_case_snippet(f"{query} : règles, niveau et inscription")
        meta = f"Faites le point sur {query} : format, niveau attendu, inscription, points et repères utiles avant de vous engager."
    else:
        title = title_case_snippet(f"{query} : repères pratiques et erreurs à éviter")
        meta = f"Comprenez {query} avec une réponse structurée, des exemples concrets et les critères utiles pour décider quoi faire ensuite."
    title = sanitize_snippet_text(trim_to_length(title, 60))
    meta = sanitize_snippet_text(trim_to_length(meta, 160))
    if len(meta) < 120:
        meta = sanitize_snippet_text(f"{meta} Une synthèse pratique pour décider quoi faire ensuite.")
    return {
        "title": title,
        "meta": meta,
        "reason": f"Faire correspondre le résultat Google à l'intention « {query} » avec un angle précis et vérifiable.",
    }


def clean_query_for_snippet(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", query.replace("-", " ")).strip(" /")
    return cleaned or "la requête principale"


def title_case_snippet(value: str) -> str:
    return value[:1].upper() + value[1:]


def trim_to_length(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    shortened = value[: max_length + 1].rsplit(" ", 1)[0].rstrip(" :,-")
    return shortened or value[:max_length].rstrip()


def sanitize_snippet_text(value: str) -> str:
    cleaned = value
    replacements = {
        "conseils et points clés": "repères pratiques",
        "conseils et points cles": "repères pratiques",
        "guide clair": "réponse précise",
        "points clés": "repères utiles",
        "points cles": "repères utiles",
        "points à vérifier": "critères utiles",
        "points a verifier": "critères utiles",
        "Découvrez les informations essentielles": "Retrouvez les informations utiles",
        "conseils pour avancer plus simplement": "repères pour décider quoi faire ensuite",
        "promesse plus concrète": "angle plus précis",
        "promesse plus concrete": "angle plus précis",
    }
    for bad, good in replacements.items():
        cleaned = re.sub(re.escape(bad), good, cleaned, flags=re.I)
    return cleaned


def snippet_problem_for_page(item: GSCPageAnalysis) -> str:
    expected = expected_ctr_for_position(item.position)
    if item.ctr < expected * 0.6:
        return "Cette page reçoit déjà beaucoup d'impressions, mais son taux de clic reste faible pour sa position."
    return "La page est visible dans Google : le résultat affiché peut être rendu plus spécifique à l'intention principale."


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
        return "Améliorer le résultat Google"
    if 4 <= item.position <= 10:
        return "Renforcer contenu, FAQ et maillage interne"
    if item.possible_overlap_queries:
        return "Vérifier les pages en concurrence"
    return "Enrichir la page et créer des liens internes"


def page_to_appendix_row(item: GSCPageAnalysis) -> dict[str, object]:
    return {
        "URL": item.url,
        "Priorité": client_priority_label(item),
        "Clics": format_number(item.clicks),
        "Impressions": format_number(item.impressions),
        translate("CTR"): format_percent(item.ctr),
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
    percent = float(value) * 100
    decimals = 2 if 0 < percent < 1 else 1
    return f"{percent:.{decimals}f} %".replace(".", ",")


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
    mode: str = "executive",
    report_mode: str | None = None,
    cannibalization_groups: list[dict[str, Any]] | None = None,
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
        mode=mode,
        report_mode=report_mode,
        cannibalization_groups=cannibalization_groups,
    )
    html_doc = render_report(report)
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(html_doc)
    return output_file


def render_executive_report(report: dict[str, object]) -> str:
    title = str(report["title"])
    kpis = "".join(render_kpi_card(kpi) for kpi in report.get("kpis", []))  # type: ignore[arg-type]
    estimate_box = render_estimate_box(report)
    priorities = render_monthly_priorities(report.get("monthly_priorities", []))  # type: ignore[arg-type]
    priority_cards = render_priority_page_cards(report.get("priority_pages", []))  # type: ignore[arg-type]
    queries = render_executive_query_opportunities(report.get("top_query_opportunities", []))  # type: ignore[arg-type]
    snippets = render_snippet_section(  # type: ignore[arg-type]
        report.get("snippet_pages", []),
        str(report.get("snippet_section_note") or ""),
    )
    business = render_business_section(report.get("business_opportunities", []))  # type: ignore[arg-type]
    cannibalization = render_cannibalization_groups_section(report.get("cannibalization_groups", []))  # type: ignore[arg-type]
    annexes = render_annex_links(report.get("annex_files", []))  # type: ignore[arg-type]
    source_notes = "".join(f"<li>{html.escape(str(note))}</li>" for note in report.get("source_notes", []))  # type: ignore[union-attr]
    mode_label = str(report.get("report_mode_label") or "Current period only")
    nav = "".join(
        f"<a href='#{anchor}'>{label}</a>"
        for anchor, label in [
            ("synthese", "Synthèse"),
            ("priorites", "Priorités"),
            ("pages-prioritaires", "Pages"),
            ("requetes", "Requêtes"),
            ("snippets", "Résultats Google"),
            ("cannibalisation", "Pages en concurrence"),
            ("business", "Business"),
            ("plan", "30 jours"),
            ("methodologie", "Méthode"),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg:#F7F7F4; --surface:#FFFFFF; --ink:#171717; --muted:#666A70; --border:#E2E0D8;
      --accent:#124E78; --accent-soft:#EAF3F8; --high:#9F1239; --medium:#A16207; --low:#166534;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:13px/1.58 Georgia, "Times New Roman", serif; }}
    h1,h2,h3,.kpi-label,.kpi-value,.cover-meta-label,.cover-meta-value,.priority-number,.priority-badge,.metric,.data-label,nav,.btn-export {{ font-family:"Helvetica Neue", Arial, sans-serif; letter-spacing:0; }}
    h1 {{ font-size:48px; line-height:1.05; margin:0 0 18px; }}
    h2 {{ font-size:22px; margin:0 0 8px; }}
    h3 {{ font-size:15px; margin:0 0 10px; }}
    a {{ color:var(--accent); overflow-wrap:anywhere; }}
    .report-container {{ max-width:880px; margin:0 auto; padding:0 30px 54px; }}
    .cover-page {{ min-height:100vh; margin:0 -30px; padding:62px 48px; color:#fff; background:#124E78; display:flex; flex-direction:column; justify-content:space-between; break-after:page; page-break-after:always; }}
    .cover-label,.cover-footer {{ opacity:.78; font:700 12px/1.4 "Helvetica Neue", Arial, sans-serif; text-transform:uppercase; }}
    .cover-subtitle {{ max-width:560px; font-size:18px; opacity:.86; margin:0 0 34px; }}
    .mode-badge {{ display:inline-block; padding:6px 12px; border:1px solid rgba(255,255,255,.35); border-radius:999px; font:700 12px/1 "Helvetica Neue", Arial, sans-serif; margin-bottom:22px; }}
    .cover-meta {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; border-top:1px solid rgba(255,255,255,.24); padding-top:26px; }}
    .cover-meta-label {{ display:block; opacity:.65; font-size:11px; text-transform:uppercase; margin-bottom:5px; }}
    .cover-meta-value {{ font-weight:700; overflow-wrap:anywhere; }}
    .btn-export {{ background:#fff; color:var(--accent); border:0; border-radius:8px; padding:10px 14px; font-weight:700; cursor:pointer; margin-top:24px; }}
    nav {{ position:sticky; top:0; background:rgba(247,247,244,.96); border-bottom:1px solid var(--border); padding:12px 0; display:flex; gap:8px; flex-wrap:wrap; z-index:3; }}
    nav a {{ color:var(--ink); text-decoration:none; background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:7px 10px; font-weight:700; font-size:12px; }}
    .source-box,.report-section {{ margin-top:34px; padding-top:26px; border-top:2px solid var(--accent); }}
    .source-box {{ background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--accent); border-radius:0 8px 8px 0; padding:15px 18px; }}
    .source-list {{ margin:0; padding-left:18px; color:var(--muted); }}
    .section-header {{ margin-bottom:18px; }}
    .section-intro,.reliability-note,.page-constat,.why {{ color:var(--muted); }}
    .kpi-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:18px 0; }}
    .kpi-card,.page-card,.snippet-card,.appendix-card,.query-card {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:18px; break-inside:avoid; page-break-inside:avoid; margin-bottom:14px; }}
    .kpi-label,.metric-label,.data-label,.mini-label,.constat-label,.actions-label {{ display:block; color:var(--muted); font-size:10px; font-weight:800; text-transform:uppercase; margin-bottom:4px; }}
    .kpi-value {{ font-size:24px; font-weight:800; }}
    .executive-summary {{ background:var(--accent-soft); border-left:4px solid var(--accent); border-radius:0 8px 8px 0; padding:16px 18px; }}
    .estimate-box {{ margin-top:18px; background:#FFF7ED; color:#1F2937; border:1px solid #FDBA74; border-left:4px solid #D97706; border-radius:0 8px 8px 0; padding:14px 16px; }}
    .estimate-box strong {{ display:block; font:800 18px/1.2 "Helvetica Neue", Arial, sans-serif; margin-bottom:5px; }}
    .estimate-box p {{ margin:0; color:#4B5563; }}
    .priorities-list {{ display:flex; flex-direction:column; gap:0; }}
    .priority-item {{ display:flex; gap:20px; padding:18px 0; border-bottom:1px solid var(--border); break-inside:avoid; }}
    .priority-number {{ min-width:54px; color:#8DB4C9; font-size:42px; font-weight:900; line-height:1; }}
    .priority-meta {{ display:flex; flex-direction:column; gap:5px; color:var(--muted); }}
    .page-card-header,.card-head {{ display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:12px; }}
    .page-slug {{ display:block; font:700 14px/1.3 "Helvetica Neue", Arial, sans-serif; overflow-wrap:anywhere; }}
    .page-url {{ display:block; font-size:11px; margin-top:3px; }}
    .priority-badge {{ white-space:nowrap; border-radius:999px; padding:4px 10px; font-size:11px; font-weight:800; }}
    .priority-badge--high {{ color:var(--high); background:#FFF1F2; border:1px solid #FECDD3; }}
    .priority-badge--medium {{ color:var(--medium); background:#FEFCE8; border:1px solid #FDE68A; }}
    .priority-badge--low,.priority-badge--dead {{ color:var(--low); background:#F0FDF4; border:1px solid #BBF7D0; }}
    .page-metrics,.data-grid {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:0; border:1px solid #ECEAE4; border-radius:8px; overflow:hidden; margin:12px 0; }}
    .metric,.data-item {{ padding:10px; background:#FAFAF8; border-right:1px solid #ECEAE4; min-width:0; }}
    .metric:last-child,.data-item:last-child {{ border-right:0; }}
    .metric-value,.data-value {{ display:block; overflow-wrap:anywhere; font-weight:700; }}
    .position-bar {{ display:flex; align-items:center; gap:10px; margin:-4px 0 14px; }}
    .position-bar-label {{ color:var(--muted); font:800 10px/1.2 "Helvetica Neue", Arial, sans-serif; text-transform:uppercase; min-width:150px; }}
    .position-bar-track {{ flex:1; height:7px; background:var(--border); border-radius:999px; overflow:hidden; }}
    .position-bar-fill {{ height:100%; border-radius:999px; }}
    .position-bar-value {{ color:var(--muted); font:800 12px/1 "Helvetica Neue", Arial, sans-serif; min-width:30px; text-align:right; }}
    .actions-list,.actions {{ margin:0; padding-left:18px; }}
    .actions-list li,.actions li {{ margin-bottom:5px; }}
    .insight-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; border-top:1px solid var(--border); margin-top:12px; padding-top:12px; }}
    .chip-row {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .type-tag,.chip {{ display:inline-block; border-radius:999px; padding:3px 8px; background:var(--accent-soft); color:var(--accent); font:700 11px/1.3 "Helvetica Neue", Arial, sans-serif; }}
    .business-note {{ margin:10px 0 0; color:var(--muted); }}
    .annex-list {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
    .annex-item {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px; font-family:"Helvetica Neue", Arial, sans-serif; font-weight:700; }}
    .compact-table {{ width:100%; border-collapse:collapse; background:var(--surface); border:1px solid var(--border); border-radius:8px; overflow:hidden; font-family:"Helvetica Neue", Arial, sans-serif; font-size:11px; }}
    .compact-table th,.compact-table td {{ border-bottom:1px solid var(--border); padding:7px 8px; text-align:left; vertical-align:top; }}
    .compact-table th {{ background:var(--accent-soft); color:var(--accent); font-size:10px; text-transform:uppercase; }}
    .compact-table tr:last-child td {{ border-bottom:0; }}
    .compact-table .url-cell {{ overflow-wrap:anywhere; max-width:220px; }}
    .empty-state {{ background:var(--surface); border:1px dashed var(--border); border-radius:8px; padding:14px; color:var(--muted); }}
    @media print {{
      @page {{ size:A4; margin:14mm 13mm; }}
      nav,.btn-export,.no-print {{ display:none!important; }}
      body {{ background:#fff; font-size:11.5px; }}
      .report-container {{ max-width:none; padding:0; }}
      .cover-page {{ margin:0; min-height:267mm; background:#124E78!important; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
      .report-section {{ break-before:auto; page-break-before:auto; }}
      .page-card,.snippet-card,.appendix-card,.query-card,.priority-item {{ break-inside:avoid; page-break-inside:avoid; }}
      .compact-table tr {{ break-inside:avoid; page-break-inside:avoid; }}
      .kpi-grid {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
      h1 {{ font-size:42px; }}
    }}
    @media (max-width:760px) {{
      .cover-meta,.kpi-grid,.insight-grid,.annex-list {{ grid-template-columns:1fr; }}
      .page-metrics,.data-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .page-card-header,.priority-item {{ flex-direction:column; }}
    }}
  </style>
</head>
<body>
  <main class="report-container">
    <section class="cover-page">
      <div>
        <div class="cover-label">Rapport SEO · Google Search Console</div>
        <span class="mode-badge">{html.escape(mode_label)}</span>
        <h1>GSC SEO Opportunity Report</h1>
        <p class="cover-subtitle">Basé sur les données Google Search Console exportées.</p>
        <div class="cover-meta">
          <div><span class="cover-meta-label">Domaine</span><span class="cover-meta-value">{html.escape(str(report.get("site_name") or "Non précisé"))}</span></div>
          <div><span class="cover-meta-label">Période analysée</span><span class="cover-meta-value">{html.escape(str(report.get("period_label", "")).replace("Période analysée: ", ""))}</span></div>
          <div><span class="cover-meta-label">Date de génération</span><span class="cover-meta-value">{html.escape(str(report.get("generated_at") or ""))}</span></div>
        </div>
        {estimate_box}
        <button onclick="exportPDF()" class="btn-export no-print">Exporter en PDF</button>
      </div>
      <div class="cover-footer">Current period only = opportunités actuelles. Before/After = comparaison entre deux exports.</div>
    </section>
    <section class="source-box"><ul class="source-list">{source_notes}</ul></section>
    <nav aria-label="Navigation du rapport">{nav}</nav>
    <section class="report-section" id="synthese">
      <div class="section-header"><h2>Synthèse exécutive</h2><p class="section-intro">Les chiffres et décisions à retenir avant l’exécution.</p></div>
      <section class="kpi-grid">{kpis}</section>
      {estimate_box}
      <div class="executive-summary"><p>{html.escape(str(report.get("executive_summary", "")))}</p></div>
    </section>
    <section class="report-section" id="priorites"><div class="section-header"><h2>Les 3 priorités du mois</h2></div>{priorities}</section>
    <section class="report-section" id="pages-prioritaires"><div class="section-header"><h2>Top 10 pages prioritaires</h2><p class="section-intro">Maximum 10 pages dans le PDF principal, classées par potentiel SEO et valeur business.</p></div>{priority_cards}</section>
    <section class="report-section" id="requetes"><div class="section-header"><h2>Top 20 requêtes à exploiter</h2><p class="section-intro">Regroupées par intention d’action : résultat Google, FAQ, section, contenu, maillage ou faible valeur.</p></div>{queries}</section>
    {snippets}
    {cannibalization}
    <section class="report-section" id="business"><div class="section-header"><h2>Business opportunities</h2><p class="section-intro">Pages à forte valeur business : équipement, comparatifs, tests, affiliation, leads ou produits numériques.</p></div>{business}</section>
    {render_action_plan_section()}
    {render_methodology_section(str(report.get("report_mode") or "current_period_only"))}
    {annexes}
  </main>
  <script>
    function exportPDF() {{
      const original = document.title;
      document.title = 'GSC_Opportunity_Report_' + new Date().toISOString().slice(0,10);
      window.print();
      document.title = original;
    }}
  </script>
</body>
</html>"""


def render_report(report: dict[str, object]) -> str:
    if report.get("mode") == "executive":
        return render_executive_report(report)
    title = str(report["title"])
    nav_items = [
        ("synthese", "Synthèse"),
        ("priorites", "Priorités"),
        ("pages-prioritaires", "Pages"),
        ("requetes", "Requêtes"),
        ("snippets", "Résultats Google"),
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
      --color-bg: #FAFAF8;
      --color-surface: #FFFFFF;
      --color-border: #E8E5DE;
      --color-border-light: #F0EDE6;
      --color-text-primary: #1A1A18;
      --color-text-secondary: #6B6B68;
      --color-text-muted: #9B9B98;
      --color-accent: #1E40AF;
      --color-accent-light: #EFF3FF;
      --color-accent-mid: #BFCBF5;
      --color-high: #991B1B;
      --color-high-bg: #FEF2F2;
      --color-high-border: #FECACA;
      --color-medium: #92400E;
      --color-medium-bg: #FFFBEB;
      --color-medium-border: #FDE68A;
      --color-low: #065F46;
      --color-low-bg: #F0FDF4;
      --color-low-border: #A7F3D0;
      --color-positive: #059669;
      --color-positive-bg: #ECFDF5;
      --color-warning: #D97706;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      background: var(--color-bg);
      color: var(--color-text-primary);
      font-family: Georgia, "Times New Roman", serif;
      font-size: 13px;
      line-height: 1.7;
    }}
    .report-container {{
      max-width: 860px;
      margin: 0 auto;
      padding: 0 32px 64px;
    }}
    a {{ color: var(--color-accent); overflow-wrap: anywhere; word-break: break-word; }}
    h1, h2, h3, h4, p {{ margin-top: 0; }}
    h1, h2, h3, h4, .label, .badge, .stat-label, .section-title,
    .cover-label, .cover-meta-label, .cover-meta-value, .btn-export,
    .kpi-label, .kpi-value, .section-tag, .page-slug, .priority-badge,
    .metric-label, .metric-value, .constat-label, .actions-label,
    .effort-tag, .type-tag, .priority-number, .position-bar-label,
    .position-bar-value, .mini-label, .data-label, .query-card h3,
    .appendix-card h3 {{
      font-family: "Helvetica Neue", Arial, sans-serif;
      letter-spacing: 0;
    }}
    p, li, .page-description, .constat, .page-constat {{ font-family: Georgia, serif; }}
    h1 {{ font-size: 32px; font-weight: 700; line-height: 1.2; }}
    h2 {{ font-size: 22px; font-weight: 600; line-height: 1.3; margin-bottom: 4px; }}
    h3 {{ font-size: 16px; font-weight: 600; }}
    h4 {{
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-text-secondary);
    }}
    .btn-export {{
      border: 0;
      border-radius: 8px;
      background: rgba(255,255,255,0.16);
      color: #FFFFFF;
      cursor: pointer;
      font-weight: 700;
      padding: 11px 16px;
      white-space: nowrap;
      align-self: flex-start;
      border: 1px solid rgba(255,255,255,0.25);
    }}
    .cover-page {{
      background: var(--color-accent);
      color: #FFFFFF;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 64px 48px;
      margin: 0 -32px;
      page-break-after: always;
      break-after: page;
    }}
    .cover-label {{
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0;
      opacity: 0.7;
      margin-bottom: 24px;
    }}
    .cover-title {{
      font-size: 52px;
      font-weight: 700;
      line-height: 1.1;
      color: #FFFFFF;
      margin: 0 0 16px;
    }}
    .cover-subtitle {{
      font-size: 18px;
      opacity: 0.8;
      font-family: Georgia, serif;
      max-width: 480px;
      margin: 0 0 48px;
    }}
    .cover-meta {{
      display: flex;
      gap: 40px;
      border-top: 1px solid rgba(255,255,255,0.2);
      padding-top: 32px;
      flex-wrap: wrap;
    }}
    .cover-meta-item {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 140px;
    }}
    .cover-meta-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
      opacity: 0.6;
    }}
    .cover-meta-value {{
      font-size: 15px;
      font-weight: 600;
      overflow-wrap: anywhere;
    }}
    .cover-footer {{
      font-size: 12px;
      opacity: 0.5;
      border-top: 1px solid rgba(255,255,255,0.15);
      padding-top: 16px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin: 24px 0;
    }}
    .kpi-card {{
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 10px;
      padding: 16px 18px;
      min-height: 98px;
    }}
    .kpi-card--warning {{ background: var(--color-medium-bg); border-color: var(--color-medium-border); }}
    .kpi-card--positive {{ background: var(--color-positive-bg); border-color: #6EE7B7; }}
    .kpi-card--accent {{ background: var(--color-accent-light); border-color: var(--color-accent-mid); }}
    .kpi-label {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-text-secondary);
      margin-bottom: 6px;
    }}
    .kpi-value {{
      font-size: 26px;
      font-weight: 700;
      color: var(--color-text-primary);
      line-height: 1.1;
    }}
    .kpi-note {{ font-size: 11px; color: var(--color-text-muted); margin-top: 3px; }}
    .executive-summary {{
      background: var(--color-accent-light);
      border-left: 3px solid var(--color-accent);
      padding: 16px 20px;
      border-radius: 0 8px 8px 0;
      margin-top: 8px;
    }}
    .executive-summary p {{
      margin: 0;
      font-size: 13px;
      line-height: 1.7;
      color: var(--color-text-primary);
    }}
    .report-panel, .report-section, .source-box {{
      margin-top: 56px;
      padding-top: 32px;
      border-top: 2px solid var(--color-accent);
    }}
    .report-section + .report-section,
    .report-panel + .report-section,
    .report-section + .report-panel {{
      margin-top: 64px;
    }}
    .source-box {{
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-left: 3px solid var(--color-accent);
      padding: 16px 20px;
      border-radius: 0 8px 8px 0;
    }}
    .source-list {{ margin: 0; padding-left: 18px; color: var(--color-text-secondary); }}
    nav {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      background: rgba(250, 250, 248, 0.96);
      border-top: 1px solid var(--color-border);
      border-bottom: 1px solid var(--color-border);
      padding: 12px 0;
      margin: 24px 0 0;
    }}
    nav a {{
      color: var(--color-text-primary);
      text-decoration: none;
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-weight: 600;
    }}
    .section-header {{ margin-bottom: 24px; }}
    .section-tag {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-accent);
      background: var(--color-accent-light);
      padding: 3px 10px;
      border-radius: 20px;
      margin-bottom: 8px;
    }}
    .section-title {{ margin: 0 0 8px; color: var(--color-text-primary); }}
    .section-intro {{
      color: var(--color-text-secondary);
      font-size: 13px;
      margin: 0 0 24px;
      max-width: 600px;
    }}
    .cards-grid, .priority-list, .data-card-list {{
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}
    .page-card, .snippet-card, .query-card, .appendix-card, .origin-card, .chart-card {{
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      padding: 24px 28px;
      margin-bottom: 20px;
      position: relative;
      overflow: hidden;
      min-width: 0;
    }}
    .page-card::before, .snippet-card::before {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      bottom: 0;
      width: 4px;
    }}
    .page-card--high::before {{ background: var(--color-high); }}
    .page-card--medium::before {{ background: var(--color-warning); }}
    .page-card--low::before, .page-card--dead::before {{ background: var(--color-low); }}
    .snippet-card::before {{ background: var(--color-accent); }}
    .page-card-header, .card-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .page-slug {{
      font-family: "Helvetica Neue", monospace;
      font-size: 15px;
      font-weight: 600;
      color: var(--color-text-primary);
      display: block;
      overflow-wrap: anywhere;
    }}
    .page-url, .url-full {{
      font-size: 11px;
      color: var(--color-accent);
      text-decoration: none;
      display: block;
      margin-top: 2px;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .priority-badge, .badge {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
      padding: 4px 12px;
      border-radius: 20px;
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .priority-badge--high, .badge-p1 {{
      background: var(--color-high-bg);
      color: var(--color-high);
      border: 1px solid var(--color-high-border);
    }}
    .priority-badge--medium, .badge-p2 {{
      background: var(--color-medium-bg);
      color: var(--color-medium);
      border: 1px solid var(--color-medium-border);
    }}
    .priority-badge--low, .priority-badge--dead, .badge-p3, .badge-dead {{
      background: var(--color-low-bg);
      color: var(--color-low);
      border: 1px solid var(--color-low-border);
    }}
    .page-metrics, .metric-row {{
      display: flex;
      gap: 0;
      background: var(--color-bg);
      border: 1px solid var(--color-border-light);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 20px;
    }}
    .metric {{
      flex: 1;
      padding: 12px 16px;
      border-right: 1px solid var(--color-border-light);
      text-align: center;
      min-width: 0;
      background: transparent;
    }}
    .metric:last-child {{ border-right: none; }}
    .metric--warning {{ background: var(--color-medium-bg); }}
    .metric--positive {{ background: var(--color-positive-bg); }}
    .metric-label, .metric span {{
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-text-muted);
      display: block;
      margin-bottom: 4px;
    }}
    .metric-value, .metric strong {{
      font-size: 18px;
      font-weight: 700;
      color: var(--color-text-primary);
      display: block;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }}
    .metric--warning .metric-value, .metric--warning strong {{ color: var(--color-warning); }}
    .metric--positive .metric-value, .metric--positive strong {{ color: var(--color-positive); }}
    .position-bar {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin: -8px 0 18px;
    }}
    .position-bar-label {{
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-text-muted);
      min-width: 120px;
    }}
    .position-bar-track {{
      flex: 1;
      height: 6px;
      background: var(--color-border);
      border-radius: 3px;
      overflow: hidden;
    }}
    .position-bar-fill {{
      height: 100%;
      border-radius: 3px;
      background: var(--color-positive);
    }}
    .position-bar-value {{
      font-size: 12px;
      font-weight: 600;
      color: var(--color-text-secondary);
      min-width: 28px;
      text-align: right;
    }}
    .page-constat {{
      font-size: 13px;
      color: var(--color-text-secondary);
      line-height: 1.6;
      font-style: italic;
      margin-bottom: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--color-border-light);
    }}
    .constat-label, .mini-label {{
      font-style: normal;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-text-muted);
      display: block;
      margin-bottom: 4px;
    }}
    .actions-label {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-text-secondary);
      margin-bottom: 10px;
    }}
    .actions, .actions-list {{
      margin: 0;
      padding-left: 20px;
      list-style: none;
    }}
    .actions li, .actions-list li {{
      position: relative;
      padding-left: 16px;
      margin-bottom: 6px;
      font-size: 13px;
      color: var(--color-text-primary);
      line-height: 1.5;
    }}
    .actions li::before, .actions-list li::before {{
      content: "→";
      position: absolute;
      left: 0;
      color: var(--color-accent);
      font-style: normal;
      font-family: sans-serif;
    }}
    .insight-grid {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--color-border-light);
    }}
    .insight {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      min-width: 0;
    }}
    .insight strong {{
      font-size: 13px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .chip, .type-tag {{
      font-size: 11px;
      font-family: "Helvetica Neue", Arial, sans-serif;
      background: var(--color-accent-light);
      color: var(--color-accent);
      padding: 3px 10px;
      border-radius: 20px;
      font-weight: 500;
    }}
    .why {{ font-style: italic; margin: 0; color: var(--color-text-secondary); }}
    .query-note {{
      color: var(--color-medium);
      background: var(--color-medium-bg);
      border: 1px solid var(--color-medium-border);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      margin: 0;
    }}
    .priorities-list {{
      display: flex;
      flex-direction: column;
      gap: 0;
    }}
    .priority-item {{
      display: flex;
      gap: 28px;
      padding: 28px 0;
      border-bottom: 1px solid var(--color-border-light);
      align-items: flex-start;
    }}
    .priority-item:last-child {{ border-bottom: none; }}
    .priority-number {{
      font-size: 48px;
      font-weight: 800;
      color: var(--color-accent-mid);
      line-height: 1;
      min-width: 64px;
      letter-spacing: 0;
    }}
    .priority-body h3 {{
      font-size: 16px;
      font-weight: 600;
      margin: 0 0 12px;
      color: var(--color-text-primary);
    }}
    .priority-meta {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .priority-meta span {{
      font-size: 13px;
      color: var(--color-text-secondary);
      line-height: 1.5;
    }}
    .priority-meta strong {{
      color: var(--color-text-primary);
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    .empty-state {{
      background: var(--color-surface);
      border: 1px dashed var(--color-border);
      border-radius: 10px;
      padding: 18px;
      color: var(--color-text-secondary);
    }}
    .query-card h3, .appendix-card h3 {{ margin: 0 0 10px; color: var(--color-text-primary); }}
    .data-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 0;
      border: 1px solid var(--color-border-light);
      border-radius: 8px;
      overflow: hidden;
      margin: 12px 0;
    }}
    .data-item {{
      padding: 10px 12px;
      border-right: 1px solid var(--color-border-light);
      background: var(--color-bg);
    }}
    .data-item:last-child {{ border-right: none; }}
    .data-label {{
      display: block;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--color-text-muted);
      margin-bottom: 4px;
    }}
    .data-value {{
      display: block;
      font-size: 13px;
      color: var(--color-text-primary);
      overflow-wrap: anywhere;
    }}
    .reliability-note {{
      color: var(--color-text-muted);
      font-size: 12px;
      margin: 12px 0 0;
    }}
    .chart-svg {{ width: 100%; height: auto; display: block; }}
    .origin-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .bar-row {{ display: flex; gap: 10px; align-items: center; margin-top: 12px; }}
    .bar-label {{ width: 96px; font-size: 12px; overflow-wrap: anywhere; }}
    .bar-track {{ flex: 1; background: var(--color-border-light); border-radius: 4px; height: 8px; }}
    .bar-fill {{ height: 100%; background: var(--color-accent); border-radius: 4px; }}
    .bar-value {{ width: 92px; text-align: right; color: var(--color-text-muted); font-size: 12px; }}
    .footer-note {{
      margin-top: 56px;
      border-top: 1px solid var(--color-border);
      padding-top: 18px;
      color: var(--color-text-muted);
    }}
    @media (max-width: 820px) {{
      .report-container {{ padding: 0 18px 42px; }}
      .cover-page {{ margin: 0 -18px; padding: 48px 28px; }}
      .cover-title {{ font-size: 40px; }}
      .cover-meta {{ gap: 18px; }}
      .insight {{ grid-template-columns: 1fr; }}
      .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .page-card-header, .card-head, .priority-item {{ flex-direction: column; }}
      .page-metrics, .metric-row, .data-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric, .data-item {{ border-right: 0; border-bottom: 1px solid var(--color-border-light); }}
      .bar-label, .bar-value {{ width: auto; min-width: 64px; }}
    }}
    @media print {{
      .btn-export,
      nav,
      .no-print {{ display: none !important; }}
      @page {{
        size: A4;
        margin: 16mm 14mm;
      }}
      * {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      body {{
        font-size: 12px;
        background: var(--color-bg) !important;
        color: var(--color-text-primary) !important;
      }}
      .report-container {{ max-width: none; padding: 0; }}
      .cover-page {{
        background: #1E40AF !important;
        color: #FFFFFF !important;
        min-height: 265mm;
        margin: 0;
        page-break-after: always;
        break-after: page;
      }}
      .cover-title {{ font-size: 44px; color: #FFFFFF !important; }}
      .page-card, .priority-item, .snippet-card, .report-panel, .report-section, .kpi-grid {{
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .page-card::before {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .priority-badge--high, .priority-badge--medium, .priority-badge--low,
      .kpi-card--warning, .kpi-card--positive, .kpi-card--accent,
      .metric--warning, .metric--positive, .executive-summary, .type-tag {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .page-url::after, a[href]::after {{ content: none; }}
      .kpi-value {{ font-size: 22px; }}
      .page-card {{ display: block !important; }}
      .report-section, .report-panel {{ break-before: auto; page-break-before: auto; }}
      .appendix {{ break-inside: auto; page-break-inside: auto; }}
    }}
  </style>
</head>
<body>
  <main class="report-container">
    <section class="cover-page">
      <div class="cover-content">
        <div class="cover-label">Rapport SEO · Google Search Console</div>
        <h1 class="cover-title">Audit SEO GSC</h1>
        <p class="cover-subtitle">Plan d'action basé sur les données Google Search Console</p>
        <div class="cover-meta">
          <div class="cover-meta-item">
            <span class="cover-meta-label">Domaine analysé</span>
            <span class="cover-meta-value">{html.escape(str(report.get("site_name") or "Non précisé"))}</span>
          </div>
          <div class="cover-meta-item">
            <span class="cover-meta-label">Période</span>
            <span class="cover-meta-value">{html.escape(str(report.get("period_label", "")).replace("Période analysée: ", ""))}</span>
          </div>
          <div class="cover-meta-item">
            <span class="cover-meta-label">Généré le</span>
            <span class="cover-meta-value">{html.escape(str(report["generated_at"]))}</span>
          </div>
        </div>
        <button onclick="exportPDF()" class="btn-export no-print">Exporter en PDF</button>
      </div>
      <div class="cover-footer">Analyse basée sur les données Google Search Console exportées.</div>
    </section>

    <section class="source-box">
      <ul class="source-list">{source_notes}</ul>
    </section>

    <nav aria-label="Navigation du rapport">{nav}</nav>

    <section class="report-section" id="synthese">
      <div class="section-header"><h2 class="section-title">Synthèse exécutive</h2><p class="section-intro">Les indicateurs à retenir avant d’entrer dans le détail.</p></div>
      <section class="kpi-grid" aria-label="Indicateurs clés">{kpis}</section>
      <div class="executive-summary"><p>{html.escape(str(report.get("executive_summary", "")))}</p></div>
    </section>

    <section class="report-section priorities-section" id="priorites">
      <div class="section-header"><h2 class="section-title">Les 3 priorités du mois</h2><p class="section-intro">Un plan d’action volontairement court pour décider vite.</p></div>
      {priorities}
    </section>

    <section class="report-section" id="pages-prioritaires">
      <div class="section-header"><div class="section-tag">Priorité 1</div><h2 class="section-title">Top pages à traiter en premier</h2><p class="section-intro">Les pages avec le meilleur rapport visibilité, effort et potentiel.</p></div>
      {priority_cards}
      <p class="reliability-note">Les clics récupérables estimés sont un ordre de grandeur, pas une promesse. À confirmer après mise en ligne et suivi dans Google Search Console.</p>
    </section>

    <section class="report-section" id="requetes">
      <div class="section-header"><h2 class="section-title">Exploitation des requêtes</h2><p class="section-intro">Une sélection limitée aux requêtes utiles pour orienter les titles, FAQ et contenus.</p></div>
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
    label = str(kpi.get("label", ""))
    value = str(kpi.get("value", ""))
    label_lower = strip_accents(label).lower()
    classes = ["kpi-card"]
    note = ""
    if "ctr" in label_lower or "taux de clic" in label_lower:
        classes.append("kpi-card--warning")
        note = "<div class='kpi-note'>À surveiller selon la position moyenne</div>"
    elif "prioritaires" in label_lower:
        classes.append("kpi-card--accent")
    elif "recuperables" in label_lower or "gain" in label_lower or value.startswith("+"):
        classes.append("kpi-card--positive")
        note = "<div class='kpi-note'>estimation qualifiée</div>"
    return (
        f"<div class='{' '.join(classes)}'>"
        f"<div class='kpi-label'>{html.escape(label)}</div>"
        f"<div class='kpi-value'>{html.escape(value)}</div>"
        f"{note}"
        "</div>"
    )


def render_estimate_box(report: dict[str, object]) -> str:
    value = str(report.get("estimated_gain_value") or "")
    note = str(report.get("estimated_gain_note") or "")
    if not value and not note:
        return ""
    return (
        "<div class='estimate-box'>"
        f"<strong>Gain de trafic estimé : {html.escape(value)}</strong>"
        f"<p>{html.escape(note)}</p>"
        "</div>"
    )


def render_monthly_priorities(items: list[dict[str, str]]) -> str:
    if not items:
        return render_empty_state()
    cards = []
    for index, item in enumerate(items[:3], start=1):
        cards.append(
            "<article class='priority-item'>"
            f"<div class='priority-number'>{index:02d}</div>"
            "<div class='priority-body'>"
            f"<h3>{html.escape(item.get('title', ''))}</h3>"
            "<div class='priority-meta'>"
            f"<span class='priority-why'><strong>Pourquoi :</strong> {html.escape(item.get('why', ''))}</span>"
            f"<span class='priority-action'><strong>Action :</strong> {html.escape(item.get('action', ''))}</span>"
            f"<span class='priority-impact'><strong>Impact :</strong> {html.escape(item.get('impact', ''))}</span>"
            "</div>"
            "</div>"
            "</article>"
        )
    return f"<div class='priorities-list'>{''.join(cards)}</div>"


def render_priority_page_cards(pages: list[dict[str, object]]) -> str:
    if not pages:
        return render_empty_state()
    return f"<div class='cards-grid'>{''.join(render_client_page_card(page) for page in pages)}</div>"


def render_client_page_card(page: dict[str, object]) -> str:
    position = parse_position_value(dict(page.get("metrics", {})).get("Position", ""))
    priority_class = page_priority_class(str(page.get("priority", "p3")))
    metrics = "".join(
        f"<div class='metric {metric_state_class(str(label))}'>"
        f"<span class='metric-label'>{html.escape(str(label))}</span>"
        f"<span class='metric-value'>{html.escape(str(value))}</span>"
        "</div>"
        for label, value in dict(page.get("metrics", {})).items()
    )
    action_labels = "".join(f"<span class='type-tag'>{html.escape(str(label))}</span>" for label in page.get("action_type_labels", []))  # type: ignore[arg-type]
    business = (
        "<div class='insight'><span class='mini-label'>Valeur business</span>"
        f"<strong>{html.escape(str(page.get('business_value', '')))} · {html.escape(str(page.get('monetization_possible', '')))}</strong></div>"
    )
    recommendation = (
        "<div class='page-constat'><span class='constat-label'>Action recommandée spécifique</span>"
        f"{html.escape(str(page.get('recommendation', '')))}</div>"
        if page.get("recommendation")
        else ""
    )
    return f"""
      <article class="page-card page-card--{priority_class}">
        <div class="page-card-header">
          <div class="page-info">
            <span class="page-slug">{html.escape(str(page.get("slug", "")))}</span>
            <a class="page-url" href="{html.escape(str(page.get("url", "")))}">{html.escape(str(page.get("url", "")))} ↗</a>
          </div>
          <span class="priority-badge priority-badge--{priority_class}">{html.escape(priority_display_label(str(page.get("priority", "p3")), str(page.get("priority_label", ""))))}</span>
        </div>
        <div class="page-metrics">{metrics}</div>
        {render_position_bar(position)}
        <div class="page-constat"><span class="constat-label">Constat</span>{html.escape(str(page.get("diagnostic", "")))}</div>
        {recommendation}
        <div class="insight-grid">
          <div class="insight"><span class="mini-label">Effort estimé</span><strong>{html.escape(str(page.get("effort", "")))}</strong></div>
          {business}
          <div class="insight"><span class="mini-label">Type d'action</span><div class="chip-row">{action_labels}</div></div>
          <div class="insight"><span class="mini-label">Impact attendu</span><strong>{html.escape(str(page.get("impact", "")))}</strong></div>
        </div>
      </article>
"""


def render_data_item(label: str, value: object) -> str:
    return (
        "<div class='data-item'>"
        f"<span class='data-label'>{html.escape(str(label))}</span>"
        f"<span class='data-value'>{html.escape(str(value))}</span>"
        "</div>"
    )


def metric_state_class(label: str) -> str:
    label_normalized = strip_accents(label).lower()
    if "ctr" in label_normalized or "taux de clic" in label_normalized:
        return "metric--warning"
    if "gain" in label_normalized:
        return "metric--positive"
    return ""


def page_priority_class(priority: str) -> str:
    if priority == "p1":
        return "high"
    if priority == "p2":
        return "medium"
    if priority == "dead":
        return "dead"
    return "low"


def priority_display_label(priority: str, fallback: str) -> str:
    if priority == "p1":
        return "Priorité haute"
    if priority == "p2":
        return "Priorité moyenne"
    if priority == "dead":
        return "À arbitrer"
    return fallback or "Priorité faible"


def parse_position_value(value: object) -> float:
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 20.0


def format_position_value(position: float) -> str:
    return f"{position:.1f}".replace(".", ",")


def position_fill_width(position: float) -> float:
    return max(0.0, min(100.0, ((20.0 - position) / 19.0) * 100.0))


def position_bar_color(position: float) -> str:
    if position <= 3:
        return "#059669"
    if position <= 10:
        return "#D97706"
    return "#991B1B"


def render_position_bar(position: float) -> str:
    position_width = position_fill_width(position)
    position_color = position_bar_color(position)
    return f"""
        <div class="position-bar">
          <div class="position-bar-label">Position actuelle dans Google</div>
          <div class="position-bar-track"><div class="position-bar-fill" style="width: {position_width:.0f}%; background: {position_color}"></div></div>
          <span class="position-bar-value">{html.escape(format_position_value(position))}</span>
        </div>
"""


def render_query_sections(sections: list[dict[str, object]], has_queries: bool) -> str:
    if not has_queries:
        return render_empty_state("Export Requêtes non fourni ou non exploitable dans l’export fourni.")
    rendered = []
    for section in sections:
        rows = section.get("rows", [])
        rendered.append(
            "<div class='query-card'>"
            f"<h3>{html.escape(str(section.get('title', '')))}</h3>"
            f"{render_query_table(rows)}"
            "</div>"
        )
    return "".join(rendered)


def render_executive_query_opportunities(rows: list[dict[str, object]]) -> str:
    if not rows:
        return render_empty_state("Export Requêtes non fourni ou aucune requête exploitable détectée.")
    table_rows = []
    for row in rows[:20]:
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('recommendation', '')))}</td>"
            f"<td>{html.escape(str(row.get('query', '')))}</td>"
            f"<td>{html.escape(str(row.get('clicks', '')))}</td>"
            f"<td>{html.escape(str(row.get('impressions', '')))}</td>"
            f"<td>{html.escape(str(row.get('ctr', '')))}</td>"
            f"<td>{html.escape(str(row.get('position', '')))}</td>"
            f"<td class='url-cell'>{html.escape(str(row.get('target_url', '') or 'à valider'))}</td>"
            "</tr>"
        )
    return (
        "<table class='compact-table'><thead><tr>"
        "<th>Action</th><th>Requête</th><th>Clics</th><th>Impr.</th><th>Taux de clic</th><th>Pos.</th><th>Cible</th>"
        "</tr></thead><tbody>"
        f"{''.join(table_rows)}"
        "</tbody></table>"
    )


def render_query_table(rows: object) -> str:
    if not rows:
        return render_empty_state()
    typed_rows = list(rows)  # type: ignore[arg-type]
    cards = []
    for row in typed_rows:
        cards.append(
            "<article class='appendix-card'>"
            f"<h3>{html.escape(str(row.get('query', '')))}</h3>"
            "<div class='data-grid'>"
            f"{render_data_item('Clics', row.get('clicks', ''))}"
            f"{render_data_item('Impressions', row.get('impressions', ''))}"
            f"{render_data_item('Taux de clic', row.get('ctr', ''))}"
            f"{render_data_item('Position', row.get('position', ''))}"
            f"{render_data_item('Recommandation', row.get('recommendation', ''))}"
            "</div>"
            "</article>"
        )
    return f"<div class='data-card-list'>{''.join(cards)}</div>"


def render_snippet_section(snippets: list[dict[str, object]], note: str = "") -> str:
    body = (
        f"<div class='cards-grid'>{''.join(render_snippet_card(item) for item in snippets)}</div>"
        if snippets
        else render_empty_state()
    )
    note_html = f"<p class='reliability-note'>{html.escape(note)}</p>" if note else ""
    return f"""
    <section class="report-section" id="snippets">
      <div class="section-header"><h2 class="section-title">Résultats Google à améliorer</h2><p class="section-intro">Des propositions concrètes pour rendre les titres et descriptions Google plus cliquables.</p></div>
      {note_html}
      {body}
    </section>
"""


def render_snippet_card(item: dict[str, object]) -> str:
    position = parse_position_value(item.get("position", ""))
    return f"""
      <article class="snippet-card">
        <div class="page-card-header">
          <div class="page-info">
            <span class="page-slug">{html.escape(str(item.get("slug", "")))}</span>
            <a class="page-url" href="{html.escape(str(item.get("url", "")))}">{html.escape(str(item.get("url", "")))} ↗</a>
          </div>
          <span class="priority-badge priority-badge--medium">Résultat Google</span>
        </div>
        <p class="small-note">{html.escape(str(item.get("metrics", "")))}</p>
        {render_position_bar(position)}
        <div class="page-constat"><span class="constat-label">Problème</span>{html.escape(str(item.get("problem", "")))}</div>
        <div class="data-grid">
          {render_data_item("Intention", item.get("intent", ""))}
          {render_data_item("Angle", item.get("angle", ""))}
          {render_data_item("Title", item.get("title_example", ""))}
          {render_data_item("Meta", item.get("meta_example", ""))}
        </div>
      </article>
"""


def render_breakthrough_section(pages: list[dict[str, object]]) -> str:
    if not pages:
        body = render_empty_state()
    else:
        body_cards = "".join(
            "<article class='appendix-card'>"
            f"<h3><a href='{html.escape(str(row.get('url', '')))}'>{html.escape(str(row.get('slug', '')))}</a></h3>"
            "<div class='data-grid'>"
            f"{render_data_item('Position', row.get('position', ''))}"
            f"{render_data_item('Impressions', row.get('impressions', ''))}"
            f"{render_data_item('Clics', row.get('clicks', ''))}"
            f"{render_data_item('Effort', row.get('effort', ''))}"
            f"{render_data_item('Impact', row.get('impact', ''))}"
            "</div>"
            f"<div class='page-constat'><span class='constat-label'>Action principale</span>{html.escape(str(row.get('action', '')))}</div>"
            "</article>"
            for row in pages
        )
        body = f"<div class='data-card-list'>{body_cards}</div>"
    return f"""
    <section class="report-section" id="renforcer">
      <div class="section-header"><h2 class="section-title">Pages déjà visibles à renforcer</h2><p class="section-intro">Ces pages ont déjà une base SEO: les améliorer est souvent plus rentable que repartir de zéro.</p></div>
      {body}
    </section>
"""


def render_business_section(pages: list[dict[str, object]]) -> str:
    if not pages:
        return render_empty_state("Aucune page high business value ne ressort clairement dans cet export.")
    rows = []
    for page in pages[:10]:
        action = ", ".join(page.get("action_type_labels", [])) if isinstance(page.get("action_type_labels"), list) else ""
        rows.append(
            "<tr>"
            f"<td class='url-cell'><a href='{html.escape(str(page.get('url', '')))}'>{html.escape(str(page.get('slug', '')))}</a></td>"
            f"<td>{html.escape(str(page.get('business_value', '')))}</td>"
            f"<td>{html.escape(str(page.get('monetization_possible', '')))}</td>"
            f"<td>{html.escape(str(page.get('opportunity_score', '')))}</td>"
            f"<td>{html.escape(str(page.get('main_query', '')))}</td>"
            f"<td>{html.escape(action)}</td>"
            f"<td>{html.escape(str(page.get('recommendation', '')))}</td>"
            "</tr>"
        )
    return (
        "<table class='compact-table'><thead><tr>"
        "<th>Page</th><th>Valeur</th><th>Monétisation</th><th>Score</th><th>Requête</th><th>Action</th><th>Recommandation</th>"
        "</tr></thead><tbody>"
        f"{''.join(rows)}"
        "</tbody></table>"
    )


def render_cannibalization_groups_section(groups: list[dict[str, Any]]) -> str:
    visible_groups = [group for group in groups if str(group.get("confidence") or "") in {"medium", "high"}][:5]
    if not visible_groups:
        body = render_empty_state("Aucun groupe de pages en concurrence suffisamment fiable à afficher dans le PDF client.")
    else:
        cards = []
        for group in visible_groups:
            urls = [str(url) for url in group.get("urls") or []][:8]
            shared = [str(query) for query in group.get("shared_queries") or []][:6]
            url_items = "".join(f"<li>{html.escape(url)}</li>" for url in urls)
            shared_label = " · ".join(shared) if shared else "à valider avec l'export Requêtes"
            cards.append(
                "<article class='appendix-card'>"
                f"<h3>{html.escape(str(group.get('topic') or group.get('group_id') or 'Cluster à valider'))}</h3>"
                "<div class='data-grid'>"
                f"{render_data_item('Groupe', group.get('group_id', ''))}"
                f"{render_data_item('Signal', confidence_label(group.get('confidence', '')))}"
                f"{render_data_item('Requêtes partagées', shared_label)}"
                f"{render_data_item('URLs', len(urls))}"
                f"{render_data_item('Action', 'clarification du cluster')}"
                "</div>"
                f"<ul class='actions'>{url_items}</ul>"
                f"<p class='business-note'>{html.escape(str(group.get('recommendation') or 'Clarifier les rôles des URLs avant optimisation.'))}</p>"
                "</article>"
            )
        body = f"<div class='data-card-list'>{''.join(cards)}</div>"
    return f"""
    <section class="report-section" id="cannibalisation">
      <div class="section-header"><h2>Pages en concurrence</h2><p class="section-intro">Seulement les groupes précis et exploitables. Les signaux faibles restent dans les CSV.</p></div>
      {body}
    </section>
"""


def confidence_label(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "high":
        return "Signal fort"
    if normalized == "medium":
        return "Signal à vérifier"
    return str(value or "")


def render_action_plan_section() -> str:
    weeks = [
        ("Semaine 1", "Réécrire les 5 résultats Google prioritaires, corriger titres/descriptions et valider les requêtes principales."),
        ("Semaine 2", "Enrichir les 3 pages proches du top 10, ajouter une FAQ utile et renforcer les introductions."),
        ("Semaine 3", "Créer les liens internes depuis les pages visibles et optimiser les ancres autour des intentions cibles."),
        ("Semaine 4", "Suivre taux de clic, position et clics dans GSC, puis ajuster les pages dont le signal ne bouge pas."),
    ]
    body = "".join(
        "<article class='appendix-card'>"
        f"<h3>{html.escape(week)}</h3>"
        f"<p>{html.escape(action)}</p>"
        "</article>"
        for week, action in weeks
    )
    return f"""
    <section class="report-section" id="plan">
      <div class="section-header"><h2>Plan d'action 30 jours</h2><p class="section-intro">Un déroulé court pour transformer le rapport en exécution.</p></div>
      <div class="data-card-list">{body}</div>
    </section>
"""


def render_traffic_section(traffic_chart: str) -> str:
    return f"""
    <section class="report-section chart-panel">
      <div class="section-header"><h2 class="section-title">Évolution du trafic</h2><p class="section-intro">Évolution quotidienne des clics, si l’export Graphique est disponible.</p></div>
      {traffic_chart}
    </section>
"""


def render_methodology_section(report_mode: str = "current_period_only") -> str:
    items = [
        "Les gains de trafic estimés sont des ordres de grandeur, pas des promesses.",
        "Les positions sont des moyennes Google Search Console.",
        "Les priorités sont calculées selon impressions, taux de clic, position et potentiel d’amélioration.",
        "Les signaux de pages en concurrence doivent être vérifiés manuellement.",
        "Les résultats sont à confirmer après mise en ligne et suivi dans GSC.",
    ]
    if report_mode == "current_period_only":
        items.append("Aucun export précédent n’a été fourni: le rapport ne diagnostique pas une baisse de trafic.")
    else:
        items.append("La comparaison Before/After dépend strictement des deux exports fournis et de leurs périodes.")
    body = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"""
    <section class="report-section" id="methodologie">
      <div class="section-header"><h2 class="section-title">Comment lire ce rapport</h2><p class="section-intro">Les règles de lecture pour éviter les mauvaises interprétations.</p></div>
      <ul class="actions">{body}</ul>
    </section>
"""


def render_appendices(pages: list[dict[str, object]], queries: list[dict[str, object]]) -> str:
    pages_table = render_appendix_table(pages)
    queries_table = render_appendix_table(queries) if queries else render_empty_state("Aucun export Requêtes exploitable dans cette analyse.")
    return f"""
    <section class="report-section appendix" id="annexes">
      <div class="section-header"><h2 class="section-title">Annexes</h2><p class="section-intro">Données complètes et limites méthodologiques.</p></div>
      <h3>Tableau complet des pages analysées</h3>
      {pages_table}
      <h3>Tableau complet des requêtes</h3>
      {queries_table}
      <h3>Détails méthodologiques et limites</h3>
      <ul class="actions">
        <li>Google Search Console agrège les positions et les taux de clic: ce ne sont pas des mesures page par page en temps réel.</li>
        <li>Le rapport ne remplace pas une vérification SERP, une analyse de contenu ni un crawl technique complet.</li>
        <li>Les estimations de clics récupérables donnent un ordre de grandeur sur la période exportée.</li>
      </ul>
    </section>
"""


def render_annex_links(files: list[str]) -> str:
    items = "".join(f"<div class='annex-item'>{html.escape(str(filename))}</div>" for filename in files)
    return f"""
    <section class="report-section appendix" id="annexes">
      <div class="section-header"><h2>Annexes séparées</h2><p class="section-intro">Les tableaux complets sont fournis en annexes CSV. Le PDF principal reste volontairement court pour la décision.</p></div>
      <div class="annex-list">{items}</div>
    </section>
"""


def render_appendix_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return render_empty_state()
    headers = list(rows[0].keys())
    cards = []
    for row in rows:
        title_key = "URL" if "URL" in row else "Requête" if "Requête" in row else headers[0]
        title = row.get(title_key, "")
        details = "".join(render_data_item(header, row.get(header, "")) for header in headers if header != title_key)
        cards.append(
            "<article class='appendix-card'>"
            f"<h3>{html.escape(str(title))}</h3>"
            f"<div class='data-grid'>{details}</div>"
            "</article>"
        )
    return f"<div class='data-card-list'>{''.join(cards)}</div>"


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
      <div class="section-header">
        <h2 class="section-title">{html.escape(str(section["title"]))}</h2>
        <p class="section-intro">{html.escape(str(section["intro"]))}</p>
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
    return render_client_page_card(page)


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
    <section class="report-section">
      <div class="section-header"><h2 class="section-title">Origine du trafic</h2><p class="section-intro">Répartition des clics par pays et par appareil.</p></div>
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
    parser.add_argument("--gsc-folder", help="Dossier avec exports GSC")
    parser.add_argument("--mode", choices=["executive", "full"], default="executive")
    parser.add_argument("--site-context", default="affiliate_media")
    parser.add_argument("--export-csv", default="true", choices=["true", "false"])
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
