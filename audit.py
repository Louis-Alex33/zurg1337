from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
import html as html_lib
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from audit_store import record_audit_report
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
from utils import CLIError, clean_domain, contains_year_reference, fetch_limited_html, make_cached_session, make_session, normalize_url

DATED_PATTERNS = [
    re.compile(r"\b20(?:1[8-9]|2[0-9])\b"),
    re.compile(
        r"\b(?:janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre)\s+20(?:1[8-9]|2[0-9])\b",
        re.I,
    ),
]

CRAWL_SOURCES = {"home", "sitemap", "mixed"}
GENERIC_ANCHOR_TEXTS = {
    "cliquez ici",
    "continuer",
    "decouvrir",
    "découvrir",
    "en savoir plus",
    "ici",
    "lire",
    "lire la suite",
    "lire plus",
    "more",
    "read more",
    "voir",
    "voir plus",
}


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
    crawl_source: str = "home",
    sitemap_max_urls: int | None = None,
    respect_robots: bool = True,
    html_output: str | None = None,
    history: bool = True,
    sqlite_index: str | None = None,
    cache_enabled: bool = False,
    cache_dir: str = ".cache/prospect_machine/http",
    cache_ttl_seconds: int = 604_800,
    mode: str = DEFAULT_AUDIT_MODE,
    site: str | None = None,
    session: requests.Session | None = None,
    excluded_path_prefixes: set[str] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[AuditReport]:
    mode_config = get_audit_mode_config(mode)
    if crawl_source not in CRAWL_SOURCES:
        raise CLIError(f"Source de crawl inconnue: {crawl_source}. Valeurs: home, sitemap, mixed.")
    selected = select_domains(input_csv=input_csv, top=top, min_score=min_score, site=site)
    if not selected:
        raise CLIError("Aucun domaine a auditer apres application des filtres.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if session is not None:
        client = session
    elif cache_enabled:
        client = make_cached_session(cache_dir=cache_dir, ttl_seconds=cache_ttl_seconds)
    else:
        client = make_session()

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
    resolved_sitemap_max_urls = sitemap_max_urls if sitemap_max_urls is not None else max(resolved_max_pages * 4, 40)
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
        "avg_page_health_score",
        "min_page_health_score",
        "noindex_pages",
        "canonical_missing_pages",
        "canonical_to_other_url_pages",
        "robots_blocked_pages",
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
        crawl_metadata: dict[str, object] = {}
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
            crawl_source=crawl_source,
            sitemap_max_urls=resolved_sitemap_max_urls,
            respect_robots=respect_robots,
            session=client,
            progress_label=item.domain,
            excluded_path_prefixes=excluded_path_prefixes,
            cancel_callback=cancel_callback,
            metadata=crawl_metadata,
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
                crawl_metadata=crawl_metadata,
            )
        else:
            report = build_report(
                pages,
                clean_domain(item.domain),
                overlap_enabled=resolved_overlap_enabled,
                overlap_max_pages=resolved_overlap_max_pages,
                crawl_metadata=crawl_metadata,
            )

        report_path = output_path / f"{report.domain}.json"
        write_json_file(report_path, asdict(report))
        report.history_path = ""
        if history:
            history_path = write_audit_history_report(output_path, report)
            report.history_path = str(history_path)
            write_json_file(report_path, asdict(report))
        if html_output:
            html_path = resolve_audit_html_path(html_output, output_path, report, single_report=len(selected) == 1)
            write_audit_html_report(report, html_path)
            report.html_path = str(html_path)
            write_json_file(report_path, asdict(report))
        index_path = sqlite_index or str(output_path / "audit_index.sqlite")
        record_audit_report(index_path, report)
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
                "avg_page_health_score": report.summary.get("avg_page_health_score", 0),
                "min_page_health_score": report.summary.get("min_page_health_score", 0),
                "noindex_pages": report.summary.get("noindex_pages", 0),
                "canonical_missing_pages": report.summary.get("canonical_missing_pages", 0),
                "canonical_to_other_url_pages": report.summary.get("canonical_to_other_url_pages", 0),
                "robots_blocked_pages": report.summary.get("robots_blocked_pages", 0),
            }
        )

    write_csv_rows(
        output_path / "audit_summary.csv",
        summary_rows,
        fieldnames=summary_fieldnames,
    )
    if html_output and len(reports) > 1:
        index_path = Path(html_output)
        write_audit_html_index(reports, index_path)
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


def write_audit_history_report(output_path: Path, report: AuditReport) -> Path:
    timestamp = report.audited_at.replace(":", "-")
    history_path = output_path / report.domain / f"{timestamp}.json"
    report.history_path = str(history_path)
    write_json_file(history_path, asdict(report))
    return history_path


def resolve_audit_html_path(
    html_output: str,
    output_path: Path,
    report: AuditReport,
    single_report: bool,
) -> Path:
    requested = Path(html_output)
    if single_report:
        return requested
    return output_path / "html" / f"{report.domain}.html"


def write_audit_html_index(reports: list[AuditReport], output_path: Path) -> Path:
    rows = []
    for report in reports:
        link = report.html_path or f"html/{report.domain}.html"
        if report.html_path:
            try:
                link = str(Path(report.html_path).relative_to(output_path.parent))
            except ValueError:
                link = report.html_path
        rows.append(
            "<tr>"
            f"<td>{html_lib.escape(report.domain)}</td>"
            f"<td>{report.pages_crawled}</td>"
            f"<td>{report.observed_health_score}/100</td>"
            f"<td><a href='{html_lib.escape(link)}'>Rapport HTML</a></td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='4'>Aucun rapport.</td></tr>"
    html = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Audit SEO - index</title>
  <style>{audit_html_styles()}</style>
</head>
<body>
  <main>
    <h1>Index des audits SEO</h1>
    <table>
      <thead><tr><th>Domaine</th><th>Pages</th><th>Score</th><th>Rapport</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </main>
</body>
</html>"""
    output_file = write_text_file(output_path, html)
    return output_file


def write_audit_html_report(report: AuditReport, output_path: Path) -> Path:
    summary = report.summary
    top_pages = report.top_pages_to_rework[:8]
    signals = report.business_priority_signals[:8]
    technical = report.technical_checks
    page_rows = []
    for page in report.pages[:80]:
        page_rows.append(
            "<tr>"
            f"<td><a href='{html_lib.escape(str(page.get('url') or '#'))}'>{html_lib.escape(short_url(str(page.get('url') or '')))}</a></td>"
            f"<td>{html_lib.escape(str(page.get('page_type') or '-'))}</td>"
            f"<td>{html_lib.escape(str(page.get('page_health_score') or 0))}/100</td>"
            f"<td>{html_lib.escape(str(page.get('word_count') or 0))}</td>"
            f"<td>{html_lib.escape(' | '.join(str(item) for item in (page.get('issues') or [])[:4]))}</td>"
            "</tr>"
        )
    top_page_items = "".join(
        f"<li><a href='{html_lib.escape(str(item.get('url') or '#'))}'>{html_lib.escape(short_url(str(item.get('url') or '')))}</a>"
        f" <span>{html_lib.escape(str(item.get('page_health_score') or '-'))}/100</span></li>"
        for item in top_pages
    ) or "<li>Aucune page prioritaire nette.</li>"
    signal_items = "".join(
        f"<li><strong>{html_lib.escape(str(item.get('signal') or 'Signal'))}</strong> "
        f"<span>{html_lib.escape(str(item.get('count') or 0))}</span></li>"
        for item in signals
    ) or "<li>Aucun signal prioritaire net.</li>"
    technical_items = "".join(
        f"<li><strong>{html_lib.escape(key.replace('_', ' '))}</strong> <span>{html_lib.escape(str(value))}</span></li>"
        for key, value in technical.items()
    ) or "<li>Aucun signal technique net.</li>"
    metadata_items = "".join(
        f"<li><strong>{html_lib.escape(str(key).replace('_', ' '))}</strong> <span>{html_lib.escape(str(value))}</span></li>"
        for key, value in report.crawl_metadata.items()
    ) or "<li>Métadonnées non disponibles.</li>"
    html = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Audit SEO - {html_lib.escape(report.domain)}</title>
  <style>{audit_html_styles()}</style>
</head>
<body>
  <main>
    <header class="hero">
      <p>Audit SEO autonome</p>
      <h1>{html_lib.escape(report.domain)}</h1>
      <strong>{report.observed_health_score}/100</strong>
      <span>{report.pages_crawled} pages crawlées · {html_lib.escape(report.audited_at)}</span>
    </header>
    <section class="grid">
      <article><h2>Synthèse</h2><ul>
        <li><strong>Pages de contenu</strong> <span>{summary.get('content_like_pages', 0)}</span></li>
        <li><strong>Score moyen page</strong> <span>{summary.get('avg_page_health_score', 0)}/100</span></li>
        <li><strong>Score page min</strong> <span>{summary.get('min_page_health_score', 0)}/100</span></li>
        <li><strong>Pages légères</strong> <span>{summary.get('thin_content_pages', 0)}</span></li>
      </ul></article>
      <article><h2>Signaux prioritaires</h2><ul>{signal_items}</ul></article>
      <article><h2>Technique</h2><ul>{technical_items}</ul></article>
      <article><h2>Crawl</h2><ul>{metadata_items}</ul></article>
    </section>
    <section>
      <h2>Pages à revoir en priorité</h2>
      <ul class="top-pages">{top_page_items}</ul>
    </section>
    <section>
      <h2>Pages analysées</h2>
      <table>
        <thead><tr><th>URL</th><th>Type</th><th>Score</th><th>Mots</th><th>Points relevés</th></tr></thead>
        <tbody>{"".join(page_rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""
    output_file = write_text_file(output_path, html)
    return output_file


def write_text_file(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def audit_html_styles() -> str:
    return """
    body { margin: 0; font-family: Arial, sans-serif; color: #17212b; background: #f6f7f4; }
    main { max-width: 1120px; margin: 0 auto; padding: 32px; }
    .hero { padding: 28px; background: #17313e; color: white; border-radius: 8px; margin-bottom: 24px; }
    .hero p { margin: 0 0 8px; text-transform: uppercase; letter-spacing: .08em; font-size: 12px; }
    .hero h1 { margin: 0 0 12px; font-size: 34px; }
    .hero strong { display: block; font-size: 42px; margin-bottom: 4px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    article, section { margin-bottom: 20px; }
    article { background: white; border: 1px solid #dde3db; border-radius: 8px; padding: 16px; }
    h2 { font-size: 18px; margin: 0 0 12px; }
    ul { padding-left: 18px; }
    li { margin: 7px 0; }
    li span { color: #53605a; }
    table { width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde3db; }
    th, td { padding: 10px; border-bottom: 1px solid #e8ece5; text-align: left; vertical-align: top; }
    th { background: #eef2ea; }
    a { color: #0b5c76; }
    """


def short_url(url: str, max_length: int = 78) -> str:
    cleaned = url.replace("https://", "").replace("http://", "").rstrip("/")
    return cleaned if len(cleaned) <= max_length else cleaned[: max_length - 1].rstrip("/") + "…"


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
    crawl_source: str = "home",
    sitemap_max_urls: int = 120,
    respect_robots: bool = True,
    session: requests.Session | None = None,
    progress_label: str = "",
    excluded_path_prefixes: set[str] | None = None,
    cancel_callback: Callable[[], None] | None = None,
    metadata: dict[str, object] | None = None,
) -> list[AuditPage]:
    if not start_url.startswith(("http://", "https://")):
        start_url = f"https://{start_url}"
    start_url = normalize_url(start_url)
    base_domain = clean_domain(start_url)
    client = session or make_session()

    robots_rules = fetch_robots_rules(start_url, client, timeout=timeout) if respect_robots else default_robots_rules()
    sitemap_urls: list[str] = []
    if crawl_source in {"sitemap", "mixed"}:
        sitemap_urls = discover_sitemap_urls(
            start_url,
            session=client,
            timeout=timeout,
            max_urls=sitemap_max_urls,
            max_redirects=max_redirects,
            robots_rules=robots_rules,
            excluded_path_prefixes=excluded_path_prefixes,
        )
    seed_urls = build_seed_urls(start_url, sitemap_urls=sitemap_urls, crawl_source=crawl_source)
    if metadata is not None:
        metadata.update(
            {
                "crawl_source": crawl_source,
                "seed_urls_count": len(seed_urls),
                "sitemap_urls_found": len(sitemap_urls),
                "robots_txt_available": bool(robots_rules.get("available")),
                "robots_txt_status": robots_rules.get("status_code", 0),
                "robots_disallow_rules": len(robots_rules.get("disallow", [])),
            }
        )

    queue: deque[tuple[str, int]] = deque((url, 0) for url in seed_urls)
    visited: set[str] = set()
    seen_or_queued: set[str] = set(seed_urls)
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
        if respect_robots and not robots_can_fetch(robots_rules, current_url):
            page = AuditPage(
                url=current_url,
                requested_url=current_url,
                depth=depth,
                robots_allowed=False,
                page_type=classify_page_type(current_url),
                page_health_score=0,
                issues=["URL bloquée par robots.txt, non crawlée"],
            )
            pages.append(page)
            continue
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


def default_robots_rules() -> dict[str, object]:
    return {"available": False, "status_code": 0, "disallow": [], "sitemaps": [], "error": ""}


def fetch_robots_rules(start_url: str, session: requests.Session, timeout: int = 8) -> dict[str, object]:
    parsed = urlparse(start_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rules = default_robots_rules()
    try:
        response = session.get(robots_url, timeout=timeout, allow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        rules["error"] = str(exc)[:120]
        return rules
    rules["status_code"] = response.status_code
    if response.status_code >= 400:
        return rules
    rules["available"] = True
    parsed_rules = parse_robots_txt(getattr(response, "text", ""))
    rules["disallow"] = parsed_rules["disallow"]
    rules["sitemaps"] = parsed_rules["sitemaps"]
    return rules


def parse_robots_txt(text: str) -> dict[str, list[str]]:
    disallow: list[str] = []
    sitemaps: list[str] = []
    active_agents: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            active_agents = [item.strip().lower() for item in value.split(",") if item.strip()]
            continue
        if key == "sitemap" and value:
            sitemaps.append(value)
            continue
        if key == "disallow" and ("*" in active_agents or not active_agents):
            if value:
                disallow.append(value)
    return {"disallow": disallow, "sitemaps": sitemaps}


def robots_can_fetch(rules: dict[str, object], url: str) -> bool:
    disallow = [str(item).strip() for item in rules.get("disallow", []) if str(item).strip()]
    if not disallow:
        return True
    path = urlparse(url).path or "/"
    return not any(path.startswith(rule) for rule in disallow)


def discover_sitemap_urls(
    start_url: str,
    session: requests.Session,
    timeout: int,
    max_urls: int,
    max_redirects: int,
    robots_rules: dict[str, object] | None = None,
    excluded_path_prefixes: set[str] | None = None,
) -> list[str]:
    parsed = urlparse(start_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    base_domain = clean_domain(start_url)
    candidates = [
        str(item)
        for item in (robots_rules or {}).get("sitemaps", [])
        if str(item).startswith(("http://", "https://"))
    ]
    candidates.extend(f"{base}{path}" for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"))
    seen_sitemaps: set[str] = set()
    discovered: list[str] = []
    queue: deque[str] = deque(dict.fromkeys(candidates))

    while queue and len(discovered) < max_urls:
        sitemap_url = queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = session.get(sitemap_url, timeout=timeout, allow_redirects=True)
        except Exception:  # noqa: BLE001
            continue
        if response.status_code >= 400 or len(getattr(response, "history", [])) > max_redirects:
            continue
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            continue
        locs = [node.text.strip() for node in root.findall(".//{*}loc") if node.text and node.text.strip()]
        if root.tag.endswith("sitemapindex"):
            for loc in locs:
                if loc not in seen_sitemaps:
                    queue.append(loc)
            continue
        for loc in locs:
            normalized = normalize_url(loc)
            if clean_domain(normalized) != base_domain:
                continue
            if not should_crawl(normalized, base_domain, excluded_path_prefixes=excluded_path_prefixes):
                continue
            if normalized not in discovered:
                discovered.append(normalized)
            if len(discovered) >= max_urls:
                break
    discovered.sort(key=lambda url: (-crawl_link_priority(url, base_domain), url))
    return discovered[:max_urls]


def build_seed_urls(start_url: str, sitemap_urls: list[str], crawl_source: str) -> list[str]:
    if crawl_source == "home":
        return [start_url]
    if crawl_source == "sitemap":
        return sitemap_urls or [start_url]
    seeds = [start_url]
    seeds.extend(url for url in sitemap_urls if url != start_url)
    return seeds


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
    page = AuditPage(url=url, requested_url=url)
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
        page.redirect_count = getattr(response, "redirect_count", 0)
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
    page.canonical = normalize_canonical(extract_canonical(soup), page.url)
    page.canonical_status = compute_canonical_status(page.url, page.canonical)
    page.meta_robots = extract_meta_robots(soup)
    page.is_noindex = "noindex" in page.meta_robots.lower()
    page.meaningful_h1_count = compute_meaningful_h1_count(page.h1)
    text = extract_text_content(soup)
    page.word_count = len(text.split())
    page.page_type = classify_page_type(page.url, title=page.title, headings=page.h1)
    page.dated_references = find_dated_references(text=text, title=page.title, url=page.url)
    page.content_like = compute_content_like(
        url=page.url,
        status_code=page.status_code,
        title=page.title,
        headings=page.h1,
        word_count=page.word_count,
        dated_references=page.dated_references,
    )
    h2 = [node.get_text(" ", strip=True) for node in soup.find_all("h2")[:5]]
    page.overlap_fingerprint = build_overlap_fingerprint(page.title, page.h1 + h2, text_excerpt=text[:1200])

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
            anchor_text = normalize_anchor_text(link.get_text(" ", strip=True))
            if not anchor_text:
                page.empty_internal_anchor_count += 1
            elif anchor_text in GENERIC_ANCHOR_TEXTS:
                page.generic_internal_anchor_count += 1
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


def normalize_canonical(canonical: str, page_url: str) -> str:
    if not canonical:
        return ""
    return normalize_url(urljoin(page_url, canonical))


def compute_canonical_status(page_url: str, canonical: str) -> str:
    if not canonical:
        return "missing"
    normalized_page = normalize_url(page_url)
    normalized_canonical = normalize_url(canonical)
    if clean_domain(normalized_page) != clean_domain(normalized_canonical):
        return "cross_domain"
    if normalized_page == normalized_canonical:
        return "self"
    return "different_url"


def extract_meta_robots(soup: BeautifulSoup) -> str:
    directives: list[str] = []
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").strip().lower()
        if name not in {"robots", "googlebot", "bingbot"}:
            continue
        content = (meta.get("content") or "").strip()
        if content:
            directives.append(content)
    return ", ".join(dict.fromkeys(directives))


def normalize_anchor_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def classify_page_type(url: str, title: str = "", headings: list[str] | None = None) -> str:
    path = urlparse(url).path.lower().rstrip("/")
    if path in {"", "/"}:
        return "homepage"
    if path_is_non_content(url):
        if any(path.startswith(prefix) for prefix in ("/category", "/tag")):
            return "taxonomy"
        if path.startswith("/author"):
            return "author"
        if any(path.startswith(prefix) for prefix in ("/legal", "/mentions-legales", "/privacy", "/terms")):
            return "legal"
        if path.startswith("/contact"):
            return "contact"
        return "utility"
    if any(path.startswith(prefix) for prefix in ("/product", "/products", "/produit", "/boutique", "/shop")):
        return "product"
    if any(path.startswith(prefix) for prefix in ("/service", "/services", "/offre", "/offres")):
        return "service"
    if path_looks_content_like(url) or contains_year_reference(path):
        return "article"
    heading = " ".join([title, *(headings or [])]).lower()
    if any(word in heading for word in ("guide", "comparatif", "test", "avis", "conseil")):
        return "article"
    return "page"


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
        if not page.robots_allowed:
            page.page_health_score = 0
            continue
        if page.status_code and page.status_code >= 400:
            continue
        content_like = is_content_like_page(page)
        if page.redirect_count:
            page.issues.append(f"{page.redirect_count} redirection(s) observée(s) avant la page finale")
        if page.is_noindex and content_like:
            page.issues.append("Page de contenu marquée noindex")
        if content_like and page.canonical_status == "missing":
            page.issues.append("Canonical absente sur cette page de contenu")
        elif content_like and page.canonical_status == "cross_domain":
            page.issues.append("Canonical vers un autre domaine")
        elif content_like and page.canonical_status == "different_url":
            page.issues.append("Canonical vers une autre URL du site")
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
        if content_like and page.generic_internal_anchor_count >= 5:
            page.issues.append(f"{page.generic_internal_anchor_count} ancres internes génériques repérées")


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
    noindex_pages = sum(1 for page in content_pages if page.is_noindex)
    canonical_missing = sum(1 for page in content_pages if page.canonical_status == "missing")
    canonical_to_other = sum(1 for page in content_pages if page.canonical_status in {"different_url", "cross_domain"})
    robots_blocked = sum(1 for page in pages if not page.robots_allowed)
    generic_anchor_pages = sum(1 for page in content_pages if page.generic_internal_anchor_count >= 5)

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
    score -= min(18, noindex_pages * 6)
    score -= min(8, canonical_missing * 2)
    score -= min(16, canonical_to_other * 5)
    score -= min(12, robots_blocked * 4)
    score -= min(6, generic_anchor_pages * 2)
    return max(0, min(100, score))


def assign_page_health_scores(
    pages: list[AuditPage],
    incoming_links: dict[str, int],
    probable_orphans: list[str],
    weak_internal_linking: list[str],
) -> None:
    orphan_set = set(probable_orphans)
    weak_set = set(weak_internal_linking)
    for page in pages:
        page.page_health_score = compute_page_health_score(
            page,
            incoming_links=incoming_links,
            is_orphan=page.url in orphan_set,
            is_weak=page.url in weak_set,
        )


def compute_page_health_score(
    page: AuditPage,
    incoming_links: dict[str, int],
    is_orphan: bool = False,
    is_weak: bool = False,
) -> int:
    if not page.robots_allowed:
        return 0
    if page.status_code and page.status_code >= 400:
        return max(0, 55 - min(35, page.status_code - 400))

    score = 100
    content_like = is_content_like_page(page)
    if not page.title:
        score -= 14
    elif len(page.title) < 20 or len(page.title) > 65:
        score -= 5
    if not page.meta_description:
        score -= 12
    elif len(page.meta_description) < 70 or len(page.meta_description) > 160:
        score -= 4
    if content_like and meaningful_h1_count(page) == 0:
        score -= 8
    elif content_like and meaningful_h1_count(page) > 2:
        score -= 3
    if content_like and page.word_count < 350:
        score -= 18
    if content_like and page.dated_references:
        score -= 12
    if content_like and page.is_noindex:
        score -= 25
    if content_like and page.canonical_status == "missing":
        score -= 6
    elif content_like and page.canonical_status == "different_url":
        score -= 10
    elif content_like and page.canonical_status == "cross_domain":
        score -= 18
    if content_like and is_orphan:
        score -= 16
    elif content_like and is_weak:
        score -= 8
    if content_like and incoming_links.get(page.url, 0) == 0 and page.depth > 0:
        score -= 6
    if content_like and page.depth > 3:
        score -= 8
    if content_like and page.images_without_alt >= 5:
        score -= 3
    if content_like and page.word_count > 1200 and not page.has_structured_data:
        score -= 4
    if page.load_time > 3:
        score -= 4
    if page.redirect_count:
        score -= min(8, page.redirect_count * 3)
    if content_like and page.generic_internal_anchor_count >= 5:
        score -= min(6, page.generic_internal_anchor_count // 2)
    return max(0, min(100, score))


def build_report(
    pages: list[AuditPage],
    domain: str,
    overlap_enabled: bool = True,
    overlap_max_pages: int = 24,
    crawl_metadata: dict[str, object] | None = None,
) -> AuditReport:
    analyze_page_issues(pages)
    duplicate_titles, duplicate_metas = detect_duplicates(pages)
    possible_overlap = []
    if overlap_enabled:
        possible_overlap = detect_possible_overlap_bounded(pages, max_pages=overlap_max_pages)
    incoming_links = count_incoming_links(pages)
    probable_orphans = detect_probable_orphans(pages)
    weak_internal_linking = detect_weak_internal_linking(pages, incoming_links)
    assign_page_health_scores(pages, incoming_links, probable_orphans, weak_internal_linking)
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
    health_scores = [page.page_health_score for page in content_pages or ok_pages if page.robots_allowed]
    technical_checks = build_technical_checks(pages, content_pages)
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
        "avg_page_health_score": round(sum(health_scores) / len(health_scores)) if health_scores else 0,
        "min_page_health_score": min(health_scores) if health_scores else 0,
        "noindex_pages": technical_checks["noindex_pages"],
        "canonical_missing_pages": technical_checks["canonical_missing_pages"],
        "canonical_to_other_url_pages": technical_checks["canonical_to_other_url_pages"],
        "canonical_cross_domain_pages": technical_checks["canonical_cross_domain_pages"],
        "redirected_pages": technical_checks["redirected_pages"],
        "robots_blocked_pages": technical_checks["robots_blocked_pages"],
        "generic_anchor_pages": technical_checks["generic_anchor_pages"],
    }

    critical_findings = build_critical_findings(summary)
    business_priority_signals = build_business_priority_signals(summary)
    top_pages_to_rework = build_top_pages_to_rework(
        content_pages,
        incoming_links=incoming_links,
        probable_orphans=probable_orphans,
        weak_internal_linking=weak_internal_linking,
    )
    internal_linking_opportunities = build_internal_linking_opportunities(
        content_pages,
        weak_internal_linking=weak_internal_linking,
        probable_orphans=probable_orphans,
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
        technical_checks=technical_checks,
        internal_linking_opportunities=internal_linking_opportunities,
        crawl_metadata=crawl_metadata or {},
        pages=[serialize_audit_page(page) for page in pages],
    )


def build_critical_findings(summary: dict[str, int]) -> list[str]:
    findings: list[str] = []
    if summary.get("noindex_pages"):
        findings.append(f"{summary['noindex_pages']} pages de contenu sont marquées noindex")
    if summary.get("canonical_to_other_url_pages"):
        findings.append(f"{summary['canonical_to_other_url_pages']} pages ont une canonical vers une autre URL")
    if summary.get("robots_blocked_pages"):
        findings.append(f"{summary['robots_blocked_pages']} URLs détectées sont bloquées par robots.txt")
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
        ("noindex_pages", "HIGH", "Pages importantes marquées noindex"),
        ("canonical_to_other_url_pages", "HIGH", "Canonicals à vérifier"),
        ("robots_blocked_pages", "HIGH", "Pages bloquées par robots.txt"),
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


def build_technical_checks(pages: list[AuditPage], content_pages: list[AuditPage]) -> dict[str, int]:
    return {
        "noindex_pages": sum(1 for page in content_pages if page.is_noindex),
        "canonical_missing_pages": sum(1 for page in content_pages if page.canonical_status == "missing"),
        "canonical_to_other_url_pages": sum(1 for page in content_pages if page.canonical_status == "different_url"),
        "canonical_cross_domain_pages": sum(1 for page in content_pages if page.canonical_status == "cross_domain"),
        "redirected_pages": sum(1 for page in pages if page.redirect_count),
        "robots_blocked_pages": sum(1 for page in pages if not page.robots_allowed),
        "generic_anchor_pages": sum(1 for page in content_pages if page.generic_internal_anchor_count >= 5),
    }


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
        if page.is_noindex:
            priority += 5
            reasons.append("page marquée noindex")
        if page.canonical_status in {"different_url", "cross_domain"}:
            priority += 4
            reasons.append("canonical à vérifier")
        if page.generic_internal_anchor_count >= 5:
            priority += 1
            reasons.append("ancres internes trop génériques")
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
                "page_health_score": page.page_health_score,
                "page_type": page.page_type,
                "incoming_links_observed": incoming_links.get(page.url, 0),
                "reasons": reasons,
                "confidence": confidence,
            }
        )
    ranked.sort(key=lambda item: (int(item["priority_score"]), int(item["word_count"]) * -1), reverse=True)
    return ranked[:5]


def build_internal_linking_opportunities(
    pages: list[AuditPage],
    weak_internal_linking: list[str],
    probable_orphans: list[str],
) -> list[dict[str, object]]:
    targets = [url for url in [*probable_orphans, *weak_internal_linking] if url]
    if not targets:
        return []
    source_candidates = [
        page
        for page in pages
        if page.url not in targets and page.word_count >= 500 and page.page_health_score >= 65
    ]
    source_candidates.sort(key=lambda page: (-page.word_count, page.depth, page.url))
    opportunities: list[dict[str, object]] = []
    for target in targets[:6]:
        sources = [page.url for page in source_candidates if target not in page.internal_links_out][:3]
        if not sources:
            continue
        opportunities.append(
            {
                "target_url": target,
                "suggested_source_urls": sources,
                "reason": "Renforcer cette page avec des liens depuis des contenus déjà visibles dans le crawl.",
            }
        )
    return opportunities


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


def build_overlap_fingerprint(title: str, headings: list[str], text_excerpt: str = "") -> str:
    heading = " ".join([title, *headings, text_excerpt]).strip().lower()
    visible_heading = " ".join([title, *headings]).strip().lower()
    if not heading or (visible_heading and is_ui_like_text(visible_heading)):
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
