from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    AUDIT_MODE_CONFIGS,
    CONTENT_PATH_HINTS,
    DEFAULT_AUDIT_MODE,
    DEFAULT_DELAY,
    DEFAULT_MAX_PAGES,
    EDITORIAL_PATH_HINTS,
    EXCLUDED_CRAWL_EXTENSIONS,
    EXCLUDED_CRAWL_PATH_PREFIXES,
    NON_CONTENT_PATH_PREFIXES,
    UI_HEADING_PATTERNS,
)
from io_helpers import read_scored_csv, write_csv_rows, write_json_file
from models import AuditPage, AuditReport, QualifiedDomain
from utils import CLIError, clean_domain, contains_year_reference, fetch_limited_html, make_session, normalize_url

DATED_PATTERNS = [
    re.compile(r"\b20(?:1[8-9]|2[0-9])\b"),
    re.compile(
        r"\b(?:janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre)\s+20(?:1[8-9]|2[0-9])\b",
        re.I,
    ),
]


def audit_domains(
    input_csv: str | None,
    output_dir: str,
    top: int | None = None,
    min_score: int | None = None,
    delay: float = DEFAULT_DELAY,
    max_pages: int | None = None,
    max_depth: int | None = None,
    max_total_requests_per_domain: int | None = None,
    max_links_per_page: int | None = None,
    max_html_bytes: int | None = None,
    max_total_seconds_per_domain: float | None = None,
    overlap_enabled: bool | None = None,
    overlap_max_pages: int | None = None,
    mode: str = DEFAULT_AUDIT_MODE,
    site: str | None = None,
    session: requests.Session | None = None,
    excluded_path_prefixes: set[str] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[AuditReport]:
    mode_config = get_audit_mode_config(mode)
    selected = select_domains(input_csv=input_csv, top=top, min_score=min_score, site=site)
    if not selected:
        raise CLIError("Aucun domaine a auditer apres application des filtres.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    client = session or make_session()

    reports: list[AuditReport] = []
    resolved_max_pages = max_pages or mode_config.max_pages or DEFAULT_MAX_PAGES
    resolved_max_depth = max_depth if max_depth is not None else mode_config.max_depth
    resolved_max_requests = (
        max_total_requests_per_domain
        if max_total_requests_per_domain is not None
        else mode_config.max_total_requests_per_domain
    )
    resolved_max_links = max_links_per_page if max_links_per_page is not None else mode_config.max_links_per_page
    resolved_max_html_bytes = max_html_bytes if max_html_bytes is not None else mode_config.max_html_bytes
    resolved_max_seconds = (
        max_total_seconds_per_domain
        if max_total_seconds_per_domain is not None
        else mode_config.max_total_seconds_per_domain
    )
    resolved_overlap_enabled = mode_config.overlap_enabled if overlap_enabled is None else overlap_enabled
    resolved_overlap_max_pages = overlap_max_pages if overlap_max_pages is not None else mode_config.overlap_max_pages
    summary_rows: list[dict[str, int | str]] = []
    summary_fieldnames = [
        "domain",
        "pages_crawled",
        "observed_health_score",
        "missing_titles",
        "missing_meta_descriptions",
        "missing_h1",
        "thin_content_pages",
        "duplicate_title_groups",
        "duplicate_meta_description_groups",
        "possible_content_overlap_pairs",
        "probable_orphan_pages",
        "weak_internal_linking_pages",
        "deep_pages_detected",
        "dated_content_signals",
    ]
    total = len(selected)
    print(
        f"Audit de {total} domaine(s) | mode={mode} | max_pages={resolved_max_pages} | delay={delay}s"
    )

    for index, item in enumerate(selected, start=1):
        if cancel_callback is not None:
            cancel_callback()
        print(f"\n[{index}/{total}] Audit de {item.domain} (score={item.score})")
        start_url = item.domain if item.domain.startswith("http") else f"https://{item.domain}"
        pages = crawl_site(
            start_url,
            max_pages=resolved_max_pages,
            max_depth=resolved_max_depth,
            max_total_requests_per_domain=resolved_max_requests,
            max_links_per_page=resolved_max_links,
            max_html_bytes=resolved_max_html_bytes,
            max_total_seconds_per_domain=resolved_max_seconds,
            max_consecutive_errors=mode_config.max_consecutive_errors,
            delay=delay,
            timeout=mode_config.timeout,
            max_redirects=mode_config.max_redirects,
            session=client,
            progress_label=item.domain,
            excluded_path_prefixes=excluded_path_prefixes,
            cancel_callback=cancel_callback,
        )
        if not pages:
            report = AuditReport(
                domain=clean_domain(item.domain),
                audited_at=datetime.now().isoformat(timespec="seconds"),
                pages_crawled=0,
                observed_health_score=0,
                notes=[
                    "Aucune page HTML accessible n'a pu etre crawlee.",
                    "Ce resultat ne permet pas de conclure sur la qualite SEO du site.",
                ],
            )
        else:
            report = build_report(
                pages,
                clean_domain(item.domain),
                overlap_enabled=resolved_overlap_enabled,
                overlap_max_pages=resolved_overlap_max_pages,
            )

        report_path = output_path / f"{report.domain}.json"
        write_json_file(report_path, asdict(report))
        print(
            f"  -> {report.pages_crawled} pages crawllees | "
            f"observed_health_score={report.observed_health_score} | "
            f"json={report_path}"
        )
        reports.append(report)
        summary_rows.append(
            {
                "domain": report.domain,
                "pages_crawled": report.pages_crawled,
                "observed_health_score": report.observed_health_score,
                "missing_titles": report.summary.get("missing_titles", 0),
                "missing_meta_descriptions": report.summary.get("missing_meta_descriptions", 0),
                "missing_h1": report.summary.get("missing_h1", 0),
                "thin_content_pages": report.summary.get("thin_content_pages", 0),
                "duplicate_title_groups": report.summary.get("duplicate_title_groups", 0),
                "duplicate_meta_description_groups": report.summary.get("duplicate_meta_description_groups", 0),
                "possible_content_overlap_pairs": report.summary.get("possible_content_overlap_pairs", 0),
                "probable_orphan_pages": report.summary.get("probable_orphan_pages", 0),
                "weak_internal_linking_pages": report.summary.get("weak_internal_linking_pages", 0),
                "deep_pages_detected": report.summary.get("deep_pages_detected", 0),
                "dated_content_signals": report.summary.get("dated_content_signals", 0),
            }
        )

    write_csv_rows(
        output_path / "audit_summary.csv",
        summary_rows,
        fieldnames=summary_fieldnames,
    )
    if cancel_callback is not None:
        cancel_callback()
    return reports


def select_domains(
    input_csv: str | None,
    top: int | None,
    min_score: int | None,
    site: str | None,
) -> list[QualifiedDomain]:
    if site:
        return [QualifiedDomain(score=0, domain=site.strip())]
    if not input_csv:
        raise CLIError("Le module audit attend soit un CSV score, soit l'option --site.")

    items = read_scored_csv(input_csv)
    if min_score is not None:
        items = [item for item in items if item.score >= min_score]
    items.sort(key=lambda item: item.score, reverse=True)
    if top is not None:
        items = items[:top]
    return items


def crawl_site(
    start_url: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = 2,
    max_total_requests_per_domain: int = 35,
    max_links_per_page: int = 12,
    max_html_bytes: int = 700_000,
    max_total_seconds_per_domain: float = 20.0,
    max_consecutive_errors: int = 5,
    delay: float = DEFAULT_DELAY,
    timeout: int = 8,
    max_redirects: int = 5,
    session: requests.Session | None = None,
    progress_label: str = "",
    excluded_path_prefixes: set[str] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[AuditPage]:
    if not start_url.startswith(("http://", "https://")):
        start_url = f"https://{start_url}"
    start_url = normalize_url(start_url)
    base_domain = clean_domain(start_url)
    client = session or make_session()

    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    visited: set[str] = set()
    seen_or_queued: set[str] = {start_url}
    pages: list[AuditPage] = []
    started_at = time.monotonic()
    total_requests = 0
    consecutive_failures = 0

    if progress_label:
        print(f"  Crawl en cours sur {progress_label}...")

    while queue and len(visited) < max_pages:
        if crawl_budget_exceeded(started_at, total_requests, max_total_seconds_per_domain, max_total_requests_per_domain):
            break
        if cancel_callback is not None:
            cancel_callback()
        current_url, depth = queue.popleft()
        if depth > max_depth:
            continue
        current_url = normalize_url(current_url)
        if current_url in visited:
            continue
        visited.add(current_url)
        total_requests += 1
        page = crawl_page(
            current_url,
            session=client,
            timeout=timeout,
            max_html_bytes=max_html_bytes,
            max_links_per_page=max_links_per_page,
            max_redirects=max_redirects,
            excluded_path_prefixes=excluded_path_prefixes,
            cancel_callback=cancel_callback,
        )
        if page is None:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_errors:
                break
            continue
        page.depth = depth
        pages.append(page)
        if page.status_code and page.status_code >= 400:
            consecutive_failures += 1
        else:
            consecutive_failures = 0
        count = len(pages)
        if count <= 3 or count % 10 == 0:
            print(
                f"    [{count}/{max_pages}] depth={depth} "
                f"load={page.load_time:.2f}s {page.url}"
            )
        if depth < max_depth:
            for link in page.internal_links_out:
                if link not in visited and link not in seen_or_queued:
                    seen_or_queued.add(link)
                    queue.append((link, depth + 1))
        if consecutive_failures >= max_consecutive_errors:
            break
        if total_requests >= 5 and not pages:
            break
        if cancel_callback is not None:
            cancel_callback()
        time.sleep(delay)

    if progress_label:
        print(f"  Crawl termine pour {progress_label}: {len(pages)} pages")
    return pages


def crawl_page(
    url: str,
    session: requests.Session,
    timeout: int,
    max_html_bytes: int,
    max_links_per_page: int,
    max_redirects: int,
    excluded_path_prefixes: set[str] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> AuditPage | None:
    page = AuditPage(url=url)
    if cancel_callback is not None:
        cancel_callback()
    try:
        started_at = time.time()
        response = fetch_limited_html(
            session,
            url,
            timeout=timeout,
            max_html_bytes=max_html_bytes,
            max_redirects=max_redirects,
        )
        page.load_time = round(time.time() - started_at, 2)
        page.status_code = response.status_code
        if response.status_code >= 400:
            page.issues.append(f"HTTP {response.status_code} detecte sur la page")
            return page
        if response.skip_reason == "non_html":
            return None
        if response.skip_reason == "html_too_large":
            page.issues.append("HTML trop volumineux pour une analyse detaillee")
            return page
        if response.skip_reason == "too_many_redirects":
            page.issues.append("Trop de redirections detectees sur la page")
            return page
    except requests.Timeout:
        page.load_time = float(timeout)
        page.issues.append("Timeout detecte pendant le crawl")
        return page
    except requests.RequestException as exc:
        page.issues.append(f"Erreur reseau pendant le crawl: {str(exc)[:80]}")
        return page

    page.url = normalize_url(response.url)
    soup = BeautifulSoup(response.text, "html.parser")
    page.title = extract_title(soup)
    page.meta_description = extract_meta_description(soup)
    page.h1 = [node.get_text(" ", strip=True) for node in soup.find_all("h1")]
    page.has_structured_data = bool(soup.find("script", attrs={"type": "application/ld+json"}))
    page.canonical = extract_canonical(soup)
    page.meaningful_h1_count = compute_meaningful_h1_count(page.h1)
    text = extract_text_content(soup)
    page.word_count = len(text.split())
    page.dated_references = find_dated_references(text=text, title=page.title, url=page.url)
    page.content_like = compute_content_like(
        url=page.url,
        status_code=page.status_code,
        title=page.title,
        headings=page.h1,
        word_count=page.word_count,
        dated_references=page.dated_references,
    )
    page.overlap_fingerprint = build_overlap_fingerprint(page.title, page.h1)

    images = soup.find_all("img")
    page.images_total = len(images)
    page.images_without_alt = sum(1 for image in images if not image.get("alt", "").strip())

    base_domain = clean_domain(page.url)
    links: dict[str, int] = {}
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue
        absolute = normalize_url(urljoin(page.url, href))
        if should_crawl(absolute, base_domain, excluded_path_prefixes=excluded_path_prefixes):
            priority = crawl_link_priority(absolute, base_domain)
            if priority < 0:
                continue
            previous = links.get(absolute)
            if previous is None or priority > previous:
                links[absolute] = priority
    page.internal_links_out = [
        item[0]
        for item in sorted(links.items(), key=lambda item: (-item[1], item[0]))[:max_links_per_page]
    ]
    return page


def should_crawl(
    url: str,
    base_domain: str,
    excluded_path_prefixes: set[str] | None = None,
) -> bool:
    active_exclusions = excluded_path_prefixes or EXCLUDED_CRAWL_PATH_PREFIXES
    parsed = urlparse(url)
    if parsed.netloc and clean_domain(parsed.netloc) != clean_domain(base_domain):
        return False
    path = parsed.path.lower()
    if any(path.startswith(prefix) for prefix in active_exclusions):
        return False
    if any(path.endswith(ext) for ext in EXCLUDED_CRAWL_EXTENSIONS):
        return False
    if parsed.fragment:
        return False
    return True


def extract_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    return title_tag.get_text(" ", strip=True) if title_tag else ""


def extract_meta_description(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    return meta.get("content", "").strip() if meta else ""


def extract_canonical(soup: BeautifulSoup) -> str:
    canonical = soup.find("link", attrs={"rel": "canonical"})
    return canonical.get("href", "").strip() if canonical else ""


def extract_text_content(soup: BeautifulSoup) -> str:
    ignored_tags = {"script", "style", "nav", "footer", "header", "aside"}
    parts: list[str] = []
    for text_node in soup.find_all(string=True):
        if not str(text_node).strip():
            continue
        parent = text_node.parent
        skip = False
        while parent is not None:
            if getattr(parent, "name", None) in ignored_tags:
                skip = True
                break
            parent = parent.parent
        if not skip:
            parts.append(str(text_node).strip())
    return " ".join(parts)


def is_outdated_date_reference(value: str, reference_date: datetime | None = None) -> bool:
    year_match = re.search(r"\b(20\d{2})\b", value)
    if year_match is None:
        return False
    reference_year = (reference_date or datetime.now()).year
    return int(year_match.group(1)) < reference_year


def find_dated_references(
    text: str,
    title: str,
    url: str,
    reference_date: datetime | None = None,
) -> list[str]:
    found: list[str] = []
    active_reference_date = reference_date or datetime.now()
    excerpts = [title, url, text[:2000]]
    labels = [
        "Date visible dans le titre",
        "Date visible dans l'URL",
        "Date visible dans le contenu",
    ]
    for index, excerpt in enumerate(excerpts):
        for pattern in DATED_PATTERNS:
            for match in pattern.finditer(excerpt):
                value = match.group(0)
                if not is_outdated_date_reference(value, reference_date=active_reference_date):
                    continue
                label = f"{labels[index]}: {value}"
                if label not in found:
                    found.append(label)
    return found


def is_ui_like_text(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if not normalized:
        return False
    return any(
        normalized == pattern
        or normalized.startswith(f"{pattern} ")
        or normalized.endswith(f" {pattern}")
        for pattern in UI_HEADING_PATTERNS
    )


def path_looks_content_like(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.startswith(prefix) for prefix in CONTENT_PATH_HINTS)


def path_is_non_content(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.startswith(prefix) for prefix in NON_CONTENT_PATH_PREFIXES)


def is_content_like_page(page: AuditPage) -> bool:
    if page.content_like:
        return True
    return compute_content_like(
        url=page.url,
        status_code=page.status_code,
        title=page.title,
        headings=page.h1,
        word_count=page.word_count,
        dated_references=page.dated_references,
    )


def meaningful_h1_count(page: AuditPage) -> int:
    if page.meaningful_h1_count:
        return page.meaningful_h1_count
    return compute_meaningful_h1_count(page.h1)


def analyze_page_issues(pages: list[AuditPage]) -> None:
    for page in pages:
        if page.status_code and page.status_code >= 400:
            continue
        content_like = is_content_like_page(page)
        if not page.title:
            page.issues.append("Titre Google absent sur la page analysée")
        elif len(page.title) < 20:
            page.issues.append(f"Titre Google probablement trop court ({len(page.title)} caractères)")
        elif len(page.title) > 65:
            page.issues.append(f"Titre Google probablement trop long ({len(page.title)} caractères)")

        if not page.meta_description:
            page.issues.append("Description Google absente sur la page analysée")
        elif len(page.meta_description) < 70:
            page.issues.append(
                f"Description Google probablement trop courte ({len(page.meta_description)} caractères)"
            )
        elif len(page.meta_description) > 160:
            page.issues.append(
                f"Description Google probablement trop longue ({len(page.meta_description)} caractères)"
            )

        if not page.h1 and content_like:
            page.issues.append("Titre principal absent sur la page")
        elif meaningful_h1_count(page) > 2 and content_like:
            page.issues.append(f"{meaningful_h1_count(page)} titres principaux repérés sur la page")

        if content_like and page.word_count < 350:
            page.issues.append(f"Contenu à enrichir ({page.word_count} mots)")
        if content_like and page.images_without_alt >= 5:
            page.issues.append(f"{page.images_without_alt} image(s) sans texte alternatif repérée(s)")
        if page.load_time > 3:
            page.issues.append(f"Temps de chargement observé élevé ({page.load_time}s)")
        if content_like and page.depth > 3:
            page.issues.append(f"Page assez éloignée de l'accueil (niveau {page.depth})")
        if content_like and page.word_count > 1200 and not page.has_structured_data:
            page.issues.append("Balisage enrichi non détecté sur cette page")
        if content_like and page.dated_references:
            page.issues.append("Date visible à actualiser")


def detect_duplicates(pages: list[AuditPage]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    title_map: dict[str, list[str]] = defaultdict(list)
    meta_map: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        if page.status_code and page.status_code >= 400:
            continue
        if not (is_content_like_page(page) or urlparse(page.url).path in {"", "/"}):
            continue
        if page.title:
            title_map[page.title.lower().strip()].append(page.url)
        if page.meta_description:
            meta_map[page.meta_description.lower().strip()].append(page.url)
    duplicate_titles = {title: urls for title, urls in title_map.items() if len(urls) > 1}
    duplicate_metas = {meta: urls for meta, urls in meta_map.items() if len(urls) > 1}
    return duplicate_titles, duplicate_metas


def detect_possible_overlap(pages: list[AuditPage], threshold: float = 0.6) -> list[dict[str, str | float]]:
    content_pages = [page for page in pages if is_content_like_page(page)]
    overlaps: list[dict[str, str | float]] = []
    for index, page_a in enumerate(content_pages):
        text_a = overlap_fingerprint(page_a)
        if not text_a:
            continue
        tokens_a = set(text_a.split())
        for page_b in content_pages[index + 1 :]:
            text_b = overlap_fingerprint(page_b)
            if not text_b:
                continue
            if len(tokens_a.intersection(text_b.split())) < 2:
                continue
            similarity = SequenceMatcher(None, text_a, text_b).ratio()
            if similarity >= threshold:
                overlaps.append(
                    {
                        "page_1": page_a.url,
                        "page_2": page_b.url,
                        "title_1": page_a.title,
                        "title_2": page_b.title,
                        "similarity": round(similarity * 100, 1),
                        "note": "Deux contenus semblent répondre à un sujet très proche",
                    }
                )
    overlaps.sort(key=lambda item: item["similarity"], reverse=True)
    return overlaps


def overlap_fingerprint(page: AuditPage) -> str:
    if page.overlap_fingerprint:
        return page.overlap_fingerprint
    return build_overlap_fingerprint(page.title, page.h1)


def count_incoming_links(pages: list[AuditPage]) -> dict[str, int]:
    incoming: dict[str, int] = defaultdict(int)
    for page in pages:
        for link in page.internal_links_out:
            incoming[link] += 1
    return incoming


def detect_probable_orphans(pages: list[AuditPage]) -> list[str]:
    incoming_links = count_incoming_links(pages)
    orphans: list[str] = []
    for page in pages:
        if page.depth == 0 or not is_content_like_page(page):
            continue
        if incoming_links.get(page.url, 0) == 0 and (not page.status_code or page.status_code < 400):
            orphans.append(page.url)
    return sorted(orphans)


def detect_weak_internal_linking(
    pages: list[AuditPage],
    incoming_links: dict[str, int],
) -> list[str]:
    weak_pages: list[str] = []
    for page in pages:
        if not is_content_like_page(page):
            continue
        if page.depth >= 2 and incoming_links.get(page.url, 0) <= 1:
            weak_pages.append(page.url)
    return sorted(weak_pages)


def compute_observed_health_score(
    pages: list[AuditPage],
    possible_overlap: list[dict[str, str | float]],
    probable_orphans: list[str],
    duplicate_titles: dict[str, list[str]],
    duplicate_metas: dict[str, list[str]],
    weak_internal_linking: list[str],
) -> int:
    score = 100
    ok_pages = [page for page in pages if not page.status_code or page.status_code < 400]
    content_pages = [page for page in ok_pages if is_content_like_page(page)] or ok_pages
    total = len(content_pages)
    if total == 0:
        return 0

    missing_titles = sum(1 for page in content_pages if not page.title)
    missing_metas = sum(1 for page in content_pages if not page.meta_description)
    missing_h1 = sum(1 for page in content_pages if meaningful_h1_count(page) == 0)
    multiple_h1 = sum(1 for page in content_pages if meaningful_h1_count(page) > 2)
    thin_content = sum(1 for page in content_pages if page.word_count < 350)
    dated_content = sum(1 for page in content_pages if page.dated_references)
    images_without_alt = sum(1 for page in content_pages if page.images_without_alt >= 5)
    missing_structured_data = sum(1 for page in content_pages if page.word_count > 1200 and not page.has_structured_data)
    deep_pages = sum(1 for page in content_pages if page.depth > 3)
    crawl_errors = sum(1 for page in pages if page.status_code and page.status_code >= 400)

    score -= min(10, round(missing_titles / total * 18))
    score -= min(8, round(missing_metas / total * 14))
    score -= min(5, round(missing_h1 / total * 10))
    score -= min(22, round(thin_content / total * 30))
    score -= min(14, round(dated_content / total * 22))
    score -= min(3, round(images_without_alt / total * 8))
    score -= min(2, round(multiple_h1 / total * 6))
    score -= min(2, round(missing_structured_data / total * 6))
    score -= min(18, len(duplicate_titles) * 5)
    score -= min(14, len(duplicate_metas) * 4)
    score -= min(16, len(possible_overlap) * 4)
    score -= min(18, len(probable_orphans) * 4)
    score -= min(12, len(weak_internal_linking) * 2)
    score -= min(12, deep_pages * 3)
    score -= min(10, crawl_errors * 2)
    return max(0, min(100, score))


def build_report(
    pages: list[AuditPage],
    domain: str,
    overlap_enabled: bool = True,
    overlap_max_pages: int = 24,
) -> AuditReport:
    analyze_page_issues(pages)
    duplicate_titles, duplicate_metas = detect_duplicates(pages)
    possible_overlap = []
    if overlap_enabled:
        possible_overlap = detect_possible_overlap_bounded(pages, max_pages=overlap_max_pages)
    incoming_links = count_incoming_links(pages)
    probable_orphans = detect_probable_orphans(pages)
    weak_internal_linking = detect_weak_internal_linking(pages, incoming_links)
    dated_content = [{"url": page.url, "references": page.dated_references} for page in pages if page.dated_references]
    observed_health_score = compute_observed_health_score(
        pages,
        possible_overlap=possible_overlap,
        probable_orphans=probable_orphans,
        duplicate_titles=duplicate_titles,
        duplicate_metas=duplicate_metas,
        weak_internal_linking=weak_internal_linking,
    )

    ok_pages = [page for page in pages if not page.status_code or page.status_code < 400]
    content_pages = [page for page in ok_pages if is_content_like_page(page)]
    summary = {
        "pages_crawled": len(pages),
        "pages_ok": len(ok_pages),
        "pages_with_errors": len([page for page in pages if page.status_code and page.status_code >= 400]),
        "missing_titles": sum(1 for page in content_pages if not page.title),
        "duplicate_title_groups": len(duplicate_titles),
        "titles_too_short": sum(1 for page in content_pages if page.title and len(page.title) < 20),
        "titles_too_long": sum(1 for page in content_pages if len(page.title) > 65),
        "missing_meta_descriptions": sum(1 for page in content_pages if not page.meta_description),
        "duplicate_meta_description_groups": len(duplicate_metas),
        "meta_descriptions_too_short": sum(
            1 for page in content_pages if page.meta_description and len(page.meta_description) < 70
        ),
        "meta_descriptions_too_long": sum(1 for page in content_pages if len(page.meta_description) > 160),
        "missing_h1": sum(1 for page in content_pages if meaningful_h1_count(page) == 0),
        "multiple_h1": sum(1 for page in content_pages if meaningful_h1_count(page) > 2),
        "thin_content_pages": sum(1 for page in content_pages if page.word_count < 350),
        "images_without_alt": sum(page.images_without_alt for page in content_pages if page.images_without_alt >= 5),
        "missing_structured_data": sum(
            1 for page in content_pages if page.word_count > 1200 and not page.has_structured_data
        ),
        "dated_content_signals": len(dated_content),
        "deep_pages_detected": sum(1 for page in content_pages if page.depth > 3),
        "probable_orphan_pages": len(probable_orphans),
        "weak_internal_linking_pages": len(weak_internal_linking),
        "possible_content_overlap_pairs": len(possible_overlap),
        "content_like_pages": len(content_pages),
    }

    critical_findings = build_critical_findings(summary)
    business_priority_signals = build_business_priority_signals(summary)
    top_pages_to_rework = build_top_pages_to_rework(
        content_pages,
        incoming_links=incoming_links,
        probable_orphans=probable_orphans,
        weak_internal_linking=weak_internal_linking,
    )
    confidence_notes = build_confidence_notes(summary, possible_overlap)
    notes = [
        "Rapport fondé uniquement sur les pages réellement visitées pendant l'analyse.",
        "Les points remontés servent à repérer des opportunités d'amélioration, pas à rendre un verdict définitif.",
        "Les pages dites isolées ou peu soutenues sont estimées à partir des liens visibles pendant l'analyse.",
        "Les sujets trop proches signalent un risque de doublon, pas un problème confirmé à 100 %.",
    ]

    return AuditReport(
        domain=domain,
        audited_at=datetime.now().isoformat(timespec="seconds"),
        pages_crawled=len(pages),
        observed_health_score=observed_health_score,
        notes=notes,
        summary=summary,
        critical_findings=critical_findings,
        probable_orphan_pages=probable_orphans,
        possible_content_overlap=possible_overlap,
        duplicate_titles=duplicate_titles,
        duplicate_meta_descriptions=duplicate_metas,
        dated_content_signals=dated_content,
        business_priority_signals=business_priority_signals,
        top_pages_to_rework=top_pages_to_rework,
        confidence_notes=confidence_notes,
        pages=[serialize_audit_page(page) for page in pages],
    )


def build_critical_findings(summary: dict[str, int]) -> list[str]:
    findings: list[str] = []
    if summary["thin_content_pages"]:
        findings.append(
            f"{summary['thin_content_pages']} pages méritent d'être enrichies pour mieux répondre au sujet"
        )
    if summary["duplicate_title_groups"]:
        findings.append(
            f"{summary['duplicate_title_groups']} groupes de pages reprennent le même titre dans Google"
        )
    if summary["duplicate_meta_description_groups"]:
        findings.append(
            f"{summary['duplicate_meta_description_groups']} groupes de pages reprennent une description très proche sous Google"
        )
    if summary["dated_content_signals"]:
        findings.append(
            f"{summary['dated_content_signals']} pages affichent une date qui peut donner une impression de contenu ancien"
        )
    if summary["deep_pages_detected"]:
        findings.append(f"{summary['deep_pages_detected']} pages importantes semblent trop éloignées de l'accueil")
    if summary["probable_orphan_pages"]:
        findings.append(
            f"{summary['probable_orphan_pages']} pages paraissent difficiles à retrouver depuis le reste du site"
        )
    if summary["weak_internal_linking_pages"]:
        findings.append(
            f"{summary['weak_internal_linking_pages']} pages reçoivent trop peu de liens internes pour bien remonter"
        )
    if summary["possible_content_overlap_pairs"]:
        findings.append(
            f"{summary['possible_content_overlap_pairs']} paires de pages semblent répondre à la même intention"
        )
    return findings


def build_business_priority_signals(summary: dict[str, int]) -> list[dict[str, str | int]]:
    signals: list[dict[str, str | int]] = []
    priority_map = [
        ("thin_content_pages", "HIGH", "Pages à enrichir en priorité"),
        ("duplicate_title_groups", "HIGH", "Titres Google répétés sur plusieurs pages"),
        ("duplicate_meta_description_groups", "HIGH", "Descriptions Google répétées"),
        ("dated_content_signals", "HIGH", "Contenus qui paraissent datés"),
        ("probable_orphan_pages", "HIGH", "Pages difficiles à retrouver dans le site"),
        ("weak_internal_linking_pages", "MEDIUM", "Pages peu soutenues par les liens internes"),
        ("deep_pages_detected", "MEDIUM", "Pages trop éloignées de l'accueil"),
        ("possible_content_overlap_pairs", "MEDIUM", "Pages qui se concurrencent sur le même sujet"),
    ]
    for key, severity, label in priority_map:
        value = summary.get(key, 0)
        if value:
            signals.append({"key": key, "signal": label, "severity": severity, "count": value})
    return signals


def build_top_pages_to_rework(
    pages: list[AuditPage],
    incoming_links: dict[str, int],
    probable_orphans: list[str],
    weak_internal_linking: list[str],
) -> list[dict[str, str | int | list[str]]]:
    orphan_set = set(probable_orphans)
    weak_set = set(weak_internal_linking)
    ranked: list[dict[str, str | int | list[str]]] = []
    for page in pages:
        reasons: list[str] = []
        priority = 0
        if page.word_count < 350:
            priority += 4
            reasons.append("contenu à enrichir pour mieux répondre à la recherche")
        if page.dated_references:
            priority += 4
            reasons.append("date visible à actualiser")
        if page.url in orphan_set:
            priority += 4
            reasons.append("page difficile à retrouver dans le site")
        elif page.url in weak_set:
            priority += 2
            reasons.append("peu de liens internes vers cette page")
        if page.depth > 3:
            priority += 3
            reasons.append("page trop éloignée de l'accueil")
        if not page.meta_description:
            priority += 2
            reasons.append("description Google absente")
        if not page.title:
            priority += 2
            reasons.append("titre Google absent")
        if priority == 0:
            continue
        confidence = "medium"
        if page.url in orphan_set or page.dated_references or page.word_count < 220:
            confidence = "medium-high"
        ranked.append(
            {
                "url": page.url,
                "priority_score": priority,
                "word_count": page.word_count,
                "depth": page.depth,
                "incoming_links_observed": incoming_links.get(page.url, 0),
                "reasons": reasons,
                "confidence": confidence,
            }
        )
    ranked.sort(key=lambda item: (int(item["priority_score"]), int(item["word_count"]) * -1), reverse=True)
    return ranked[:5]


def build_confidence_notes(
    summary: dict[str, int],
    possible_overlap: list[dict[str, str | float]],
) -> list[str]:
    notes = [
        "Les constats ci-dessous servent surtout à prioriser les améliorations de contenu et de structure.",
    ]
    if summary.get("possible_content_overlap_pairs"):
        notes.append(
            "Les sujets proches ne sont remontés que sur des pages qui ressemblent à de vrais contenus."
        )
    if summary.get("probable_orphan_pages") or summary.get("weak_internal_linking_pages"):
        notes.append(
            "La lecture des liens internes peut être partielle si certaines zones n'étaient pas accessibles depuis la page d'accueil."
        )
    if not possible_overlap:
        notes.append("Aucun doublon de sujet marquant n'a été repéré parmi les contenus analysés.")
    return notes


def get_audit_mode_config(mode: str):
    try:
        return AUDIT_MODE_CONFIGS[mode]
    except KeyError as exc:
        raise CLIError(f"Mode audit inconnu: {mode}") from exc


def crawl_budget_exceeded(
    started_at: float,
    total_requests: int,
    max_total_seconds_per_domain: float,
    max_total_requests_per_domain: int,
) -> bool:
    if max_total_seconds_per_domain > 0 and (time.monotonic() - started_at) >= max_total_seconds_per_domain:
        return True
    return max_total_requests_per_domain > 0 and total_requests >= max_total_requests_per_domain


def crawl_link_priority(url: str, base_domain: str) -> int:
    parsed = urlparse(url)
    if parsed.netloc and clean_domain(parsed.netloc) != clean_domain(base_domain):
        return -100
    path = parsed.path.lower() or "/"
    if path_is_non_content(url):
        return -100
    score = 0
    if path in {"", "/"}:
        score += 6
    if any(path.startswith(prefix) for prefix in EDITORIAL_PATH_HINTS):
        score += 8
    if any(path.startswith(prefix) for prefix in CONTENT_PATH_HINTS):
        score += 6
    if contains_year_reference(path):
        score += 1
    if parsed.query:
        score -= 4
    if path.count("/") <= 2:
        score += 2
    return score


def compute_meaningful_h1_count(headings: list[str]) -> int:
    return len([heading for heading in headings if heading.strip() and not is_ui_like_text(heading)])


def compute_content_like(
    url: str,
    status_code: int,
    title: str,
    headings: list[str],
    word_count: int,
    dated_references: list[str],
) -> bool:
    if status_code and status_code >= 400:
        return False
    if path_is_non_content(url):
        return False
    heading = " ".join([title, *headings]).strip()
    if heading and is_ui_like_text(heading):
        return False
    if word_count >= 700:
        return True
    if word_count >= 350 and (dated_references or path_looks_content_like(url)):
        return True
    return path_looks_content_like(url) and word_count >= 80


def build_overlap_fingerprint(title: str, headings: list[str]) -> str:
    heading = " ".join([title, *headings]).strip().lower()
    if not heading or is_ui_like_text(heading):
        return ""
    cleaned = re.sub(r"[^a-z0-9àâçéèêëîïôûùüÿñæœ\s-]", " ", heading)
    tokens = [token for token in cleaned.split() if len(token) >= 4]
    if len(tokens) < 3:
        return ""
    return " ".join(tokens[:12])


def detect_possible_overlap_bounded(
    pages: list[AuditPage],
    threshold: float = 0.6,
    max_pages: int = 24,
) -> list[dict[str, str | float]]:
    content_pages = [page for page in pages if is_content_like_page(page)]
    if max_pages > 0 and len(content_pages) > max_pages:
        content_pages = sorted(content_pages, key=lambda page: (page.depth, -page.word_count, page.url))[:max_pages]
    return detect_possible_overlap(content_pages, threshold=threshold)


def serialize_audit_page(page: AuditPage) -> dict[str, object]:
    payload = asdict(page)
    payload.pop("content_like", None)
    payload.pop("meaningful_h1_count", None)
    payload.pop("overlap_fingerprint", None)
    return payload
