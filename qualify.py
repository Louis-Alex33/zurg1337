from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Callable, Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    APP_PATH_HINTS,
    BLOG_PATH_HINTS,
    CMS_SIGNATURES,
    DEFAULT_DELAY,
    DEFAULT_QUALIFY_MODE,
    DOCS_PATH_HINTS,
    EDITORIAL_PATH_HINTS,
    MARKETPLACE_PATH_HINTS,
    QUALIFY_MODE_CONFIGS,
    SITEMAP_CANDIDATES,
    SOCIAL_HOST_HINTS,
)
from io_helpers import qualified_rows, read_discovery_csv, write_csv_rows, write_json_file
from models import DomainDiscovery, QualificationSignals, QualifiedDomain
from scoring import score_qualification
from utils import (
    CLIError,
    absolute_url,
    clean_domain,
    contains_year_reference,
    fetch_limited_html,
    is_hard_blocked_domain,
    make_session,
)


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def qualify_domains(
    input_csv: str,
    output: str,
    json_output: str | None = None,
    delay: float = DEFAULT_DELAY,
    check_sitemap: bool | None = None,
    mode: str = DEFAULT_QUALIFY_MODE,
    max_html_bytes: int | None = None,
    max_total_seconds_per_domain: float | None = None,
    max_total_requests_per_domain: int | None = None,
    max_sitemap_urls: int | None = None,
    max_nested_sitemaps: int | None = None,
    session: requests.Session | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[QualifiedDomain]:
    mode_config = get_qualify_mode_config(mode)
    discoveries = read_discovery_csv(input_csv)
    client = session or make_session()
    qualified: list[QualifiedDomain] = []
    fieldnames = [
        "score",
        "domain",
        "cms",
        "estimated_pages",
        "hard_blocked",
        "size_score",
        "rejected",
        "rejection_reason",
        "rejection_confidence",
        "has_blog",
        "has_dated_content",
        "dated_urls_count",
        "contact_found",
        "social_links",
        "issues",
        "title",
        "notes",
        "sitemap_available",
        "source_query",
        "source_provider",
        "first_seen",
        "is_editorial_candidate",
        "is_app_like",
        "app_signal",
        "is_docs_like",
        "docs_signal",
        "is_marketplace_like",
        "marketplace_signal",
        "refresh_repair_fit",
        "site_type_note",
        "nav_link_ratio",
        "content_link_ratio",
        "editorial_word_count",
    ]
    resolved_check_sitemap = mode_config.check_sitemap if check_sitemap is None else check_sitemap
    resolved_max_html_bytes = max_html_bytes or mode_config.max_html_bytes
    resolved_max_total_seconds = max_total_seconds_per_domain or mode_config.max_total_seconds_per_domain
    resolved_max_total_requests = max_total_requests_per_domain or mode_config.max_total_requests_per_domain
    resolved_max_sitemap_urls = max_sitemap_urls if max_sitemap_urls is not None else mode_config.max_sitemap_urls
    resolved_max_nested_sitemaps = (
        max_nested_sitemaps if max_nested_sitemaps is not None else mode_config.max_nested_sitemaps
    )

    for discovery in discoveries:
        if cancel_callback is not None:
            cancel_callback()
        signals = collect_signals(
            discovery,
            client,
            check_sitemap=resolved_check_sitemap,
            homepage_timeout=mode_config.homepage_timeout,
            max_html_bytes=resolved_max_html_bytes,
            max_total_seconds_per_domain=resolved_max_total_seconds,
            max_total_requests_per_domain=resolved_max_total_requests,
            max_sitemap_urls=resolved_max_sitemap_urls,
            max_nested_sitemaps=resolved_max_nested_sitemaps,
            max_redirects=mode_config.max_redirects,
            cancel_callback=cancel_callback,
        )
        score = score_qualification(signals)
        qualified.append(
            QualifiedDomain(
                score=score,
                domain=signals.domain,
                cms=signals.cms,
                estimated_pages=signals.estimated_pages,
                hard_blocked=signals.hard_blocked,
                size_score=signals.size_score,
                rejected=signals.rejected,
                rejection_reason=signals.rejection_reason,
                rejection_confidence=signals.rejection_confidence,
                has_blog=signals.has_blog,
                has_dated_content=signals.has_dated_content,
                dated_urls_count=signals.dated_urls_count,
                contact_found=signals.contact_found,
                social_links=signals.social_links,
                issues=signals.issues,
                title=signals.title,
                notes=signals.notes,
                sitemap_available=signals.sitemap_available,
                source_query=signals.source_query,
                source_provider=signals.source_provider,
                first_seen=signals.first_seen,
                is_editorial_candidate=signals.is_editorial_candidate,
                is_app_like=signals.is_app_like,
                app_signal=signals.app_signal,
                is_docs_like=signals.is_docs_like,
                docs_signal=signals.docs_signal,
                is_marketplace_like=signals.is_marketplace_like,
                marketplace_signal=signals.marketplace_signal,
                refresh_repair_fit=signals.refresh_repair_fit,
                site_type_note=signals.site_type_note,
                nav_link_ratio=signals.nav_link_ratio,
                content_link_ratio=signals.content_link_ratio,
                editorial_word_count=signals.editorial_word_count,
            )
        )
        if cancel_callback is not None:
            cancel_callback()
        time.sleep(delay)

    qualified.sort(key=lambda item: item.score, reverse=True)

    write_csv_rows(output, qualified_rows(qualified), fieldnames=fieldnames)
    write_json_file(json_output or output.replace(".csv", ".json"), qualified_rows(qualified))
    return qualified


def collect_signals(
    discovery: DomainDiscovery,
    session: requests.Session,
    check_sitemap: bool = True,
    homepage_timeout: int = 8,
    max_html_bytes: int = 650_000,
    max_total_seconds_per_domain: float = 8.0,
    max_total_requests_per_domain: int = 2,
    max_sitemap_urls: int = 0,
    max_nested_sitemaps: int = 0,
    max_redirects: int = 4,
    cancel_callback: Callable[[], None] | None = None,
) -> QualificationSignals:
    homepage_url = f"https://{discovery.domain}"
    resource_state = {"started_at": time.monotonic(), "requests": 0}
    signals = QualificationSignals(
        domain=discovery.domain,
        source_query=discovery.source_query,
        source_provider=discovery.source_provider,
        first_seen=discovery.first_seen,
        title=discovery.title,
        notes="",
        hard_blocked=is_hard_blocked_domain(discovery.domain),
    )
    if signals.hard_blocked:
        signals.rejected = True
        signals.rejection_reason = "hard_blocked_domain"
        signals.rejection_confidence = "high"
        signals.notes = "Domaine bloque avant qualification pour eviter les tres gros sites hors cible."
        return signals
    if cancel_callback is not None:
        cancel_callback()
    response = fetch_homepage(
        discovery.domain,
        session,
        timeout=homepage_timeout,
        max_html_bytes=max_html_bytes,
        max_total_requests_per_domain=max_total_requests_per_domain,
        max_redirects=max_redirects,
        resource_state=resource_state,
        cancel_callback=cancel_callback,
    )
    if response is None or response.status_code >= 400 or response.skip_reason:
        signals.notes = build_homepage_failure_note(response)
        signals.issues.append(build_homepage_failure_issue(response))
        signals.size_score = compute_size_score(signals)
        signals.rejected, signals.rejection_reason, signals.rejection_confidence = should_reject(signals)
        return signals

    soup = BeautifulSoup(response.text, "html.parser")
    html = response.text.lower()
    homepage_url = response.url
    signals.title = extract_title(soup) or discovery.title
    signals.cms = detect_cms(html)
    signals.has_blog = detect_blog_presence(soup, html, homepage_url)
    signals.estimated_pages = estimate_site_size(soup, discovery.domain)
    signals.social_links = detect_social_links(soup)
    signals.contact_found = detect_contact(soup, response.text)
    signals.issues = detect_homepage_issues(soup)
    signals.has_dated_content = detect_dated_content(signals.title, soup.get_text(" ", strip=True)[:3000])
    signals.notes = build_notes(response)
    signals.editorial_word_count = extract_editorial_word_count(soup=soup)

    site_type = classify_site_type(
        soup=soup,
        html=html,
        homepage_url=homepage_url,
        has_blog=signals.has_blog,
        has_dated_content=signals.has_dated_content,
        editorial_word_count=signals.editorial_word_count,
    )
    signals.is_editorial_candidate = site_type["is_editorial_candidate"]
    signals.is_app_like = site_type["is_app_like"]
    signals.app_signal = site_type["app_signal"]
    signals.is_docs_like = site_type["is_docs_like"]
    signals.docs_signal = site_type["docs_signal"]
    signals.is_marketplace_like = site_type["is_marketplace_like"]
    signals.marketplace_signal = site_type["marketplace_signal"]
    signals.refresh_repair_fit = site_type["refresh_repair_fit"]
    signals.site_type_note = site_type["site_type_note"]
    signals.nav_link_ratio = site_type["nav_link_ratio"]
    signals.content_link_ratio = site_type["content_link_ratio"]

    if check_sitemap:
        if cancel_callback is not None:
            cancel_callback()
        if qualify_budget_exceeded(
            resource_state,
            max_total_seconds_per_domain=max_total_seconds_per_domain,
            max_total_requests_per_domain=max_total_requests_per_domain,
        ):
            signals.notes = append_note(signals.notes, "Budget machine atteint avant l'inspection du sitemap.")
        else:
            sitemap = inspect_sitemap(
                discovery.domain,
                session,
                timeout=homepage_timeout,
                max_html_bytes=max_html_bytes,
                max_total_seconds_per_domain=max_total_seconds_per_domain,
                max_total_requests_per_domain=max_total_requests_per_domain,
                max_sitemap_urls=max_sitemap_urls,
                max_nested_sitemaps=max_nested_sitemaps,
                max_redirects=max_redirects,
                resource_state=resource_state,
                cancel_callback=cancel_callback,
            )
            signals.sitemap_available = sitemap["found"]
            signals.dated_urls_count = sitemap["dated_urls_count"]
            signals.has_dated_content = signals.has_dated_content or sitemap["dated_urls_count"] > 0
            if sitemap["estimated_pages"] > signals.estimated_pages:
                signals.estimated_pages = sitemap["estimated_pages"]
    signals.size_score = compute_size_score(signals)
    signals.rejected, signals.rejection_reason, signals.rejection_confidence = should_reject(signals)
    if not signals.rejected and signals.rejection_confidence == "low":
        signals.notes = append_note(signals.notes, borderline_rejection_note(signals.rejection_reason))
    return signals


def compute_size_score(signals: QualificationSignals) -> int:
    score = 0
    pages = signals.estimated_pages

    if pages >= 5000:
        score += 50
    elif pages >= 2000:
        score += 25
    elif pages >= 1000:
        score += 15
    elif pages >= 400:
        score += 5

    if signals.dated_urls_count >= 100:
        score += 20
    elif signals.dated_urls_count >= 30:
        score += 10

    if signals.is_editorial_candidate and pages >= 1000:
        score += 10
    if signals.has_blog and pages >= 2000:
        score += 10

    return min(score, 100)


def should_reject(signals: QualificationSignals) -> tuple[bool, str, str]:
    """Retourne (rejected, reason, confidence)."""
    candidates: list[tuple[str, str]] = []
    if signals.hard_blocked:
        candidates.append(("hard_blocked_domain", "high"))
    if signals.size_score >= 80:
        candidates.append(("site_too_large", "high" if signals.size_score >= 90 else "medium"))
    if signals.is_app_like:
        if signals.app_signal >= 5 and signals.editorial_word_count < 400:
            confidence = "high"
        elif signals.app_signal >= 4:
            confidence = "medium"
        else:
            confidence = "low"
        candidates.append(("app_like_site", confidence))
    if signals.is_docs_like:
        if signals.docs_signal >= 5 and signals.editorial_word_count < 400:
            confidence = "high"
        elif signals.docs_signal >= 4:
            confidence = "medium"
        else:
            confidence = "low"
        candidates.append(("docs_like_site", confidence))
    if signals.is_marketplace_like and not signals.is_editorial_candidate:
        if signals.marketplace_signal >= 5:
            confidence = "high"
        elif signals.marketplace_signal >= 4:
            confidence = "medium"
        else:
            confidence = "low"
        candidates.append(("marketplace_like_site", confidence))
    if not candidates:
        return False, "", ""

    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    reason, confidence = max(candidates, key=lambda item: confidence_rank[item[1]])
    return confidence in {"medium", "high"}, reason, confidence


def fetch_homepage(
    domain: str,
    session: requests.Session,
    timeout: int,
    max_html_bytes: int,
    max_total_requests_per_domain: int,
    max_redirects: int,
    resource_state: dict[str, float | int],
    cancel_callback: Callable[[], None] | None = None,
) -> object | None:
    last_response = None
    for candidate in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
        if cancel_callback is not None:
            cancel_callback()
        if not consume_request_budget(resource_state, max_total_requests_per_domain):
            break
        try:
            response = fetch_limited_html(
                session,
                candidate,
                timeout=timeout,
                max_html_bytes=max_html_bytes,
                max_redirects=max_redirects,
            )
            last_response = response
            if response.status_code >= 400:
                continue
            if response.skip_reason == "non_html":
                continue
            if response.skip_reason:
                return response
            return response
        except requests.RequestException:
            continue
    return last_response


def extract_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    return title_tag.get_text(" ", strip=True) if title_tag else ""


def detect_cms(html: str) -> str:
    for needle, cms_name in CMS_SIGNATURES:
        if needle in html:
            return cms_name
    return ""


def detect_blog_presence(soup: BeautifulSoup, html: str, homepage_url: str) -> bool:
    if any(hint in html for hint in BLOG_PATH_HINTS):
        return True
    for link in soup.find_all("a", href=True):
        href = absolute_url(homepage_url, link["href"])
        parsed = urlparse(href)
        if any(parsed.path.lower().startswith(hint) for hint in BLOG_PATH_HINTS):
            return True
    return False


def estimate_site_size(soup: BeautifulSoup, domain: str) -> int:
    paths = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue
        parsed = urlparse(href)
        if parsed.netloc and clean_domain(parsed.netloc) != domain:
            continue
        path = parsed.path.rstrip("/")
        if path and path != "/":
            paths.add(path)
    return len(paths)


def detect_social_links(soup: BeautifulSoup) -> list[str]:
    found: list[str] = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip().lower()
        for host, label in SOCIAL_HOST_HINTS.items():
            if host in href and label not in found:
                found.append(label)
    return found


def detect_contact(soup: BeautifulSoup, html: str) -> str:
    emails = [email for email in EMAIL_RE.findall(html) if not is_noise_email(email)]
    if emails:
        return emails[0]
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text(" ", strip=True).lower()
        if "contact" in href.lower() or "contact" in text:
            return "Page contact detectee"
    return ""


def is_noise_email(email: str) -> bool:
    lower = email.lower()
    return any(part in lower for part in ("example", "wixpress", "wordpress", "sentry"))


def detect_homepage_issues(soup: BeautifulSoup) -> list[str]:
    issues: list[str] = []
    if not extract_title(soup):
        issues.append("Homepage sans title")

    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta is None or not meta.get("content", "").strip():
        issues.append("Homepage sans meta description")

    h1_tags = soup.find_all("h1")
    if not h1_tags:
        issues.append("Homepage sans H1")
    elif len(h1_tags) > 1:
        issues.append("Homepage avec plusieurs H1")

    images = soup.find_all("img")
    images_without_alt = sum(1 for image in images if not image.get("alt", "").strip())
    if images_without_alt >= 3:
        issues.append(f"{images_without_alt} images sans alt sur la homepage")

    if soup.find("script", attrs={"type": "application/ld+json"}) is None:
        issues.append("Pas de donnees structurees visibles sur la homepage")

    return issues


def detect_dated_content(title: str, body_excerpt: str) -> bool:
    return contains_year_reference(title) or contains_year_reference(body_excerpt)


def build_notes(response: requests.Response) -> str:
    final_url = response.url
    if clean_domain(final_url) != clean_domain(response.request_url):
        return f"Redirection vers {final_url}"
    return ""


def classify_site_type(
    soup: BeautifulSoup,
    html: str,
    homepage_url: str,
    has_blog: bool,
    has_dated_content: bool,
    editorial_word_count: int,
) -> dict[str, bool | float | str | int]:
    link_signals = collect_link_signals(soup, homepage_url)
    nav_ratio = round(link_signals["nav_links"] / max(1, link_signals["internal_links"]), 2)
    content_ratio = round(link_signals["content_links"] / max(1, link_signals["internal_links"]), 2)

    editorial_signal = 0
    if has_blog:
        editorial_signal += 2
    if has_dated_content:
        editorial_signal += 1
    if link_signals["editorial_links"] >= 2:
        editorial_signal += 2
    elif link_signals["editorial_links"] == 1:
        editorial_signal += 1
    if editorial_word_count >= 450:
        editorial_signal += 2
    elif editorial_word_count >= 220:
        editorial_signal += 1
    if content_ratio >= 0.3:
        editorial_signal += 1

    app_signal = link_signals["app_links"] + count_keyword_hits(html, APP_PATH_HINTS)
    docs_signal = link_signals["docs_links"] + count_keyword_hits(html, DOCS_PATH_HINTS)
    marketplace_signal = link_signals["marketplace_links"] + count_keyword_hits(html, MARKETPLACE_PATH_HINTS)

    is_app_like = app_signal >= 3 and nav_ratio >= 0.35 and editorial_word_count < 900
    is_docs_like = docs_signal >= 3 and editorial_word_count < 1200
    is_marketplace_like = marketplace_signal >= 3
    is_editorial_candidate = editorial_signal >= 3 and not is_app_like and not is_docs_like

    if is_app_like or is_docs_like:
        refresh_repair_fit = "low_fit"
    elif is_marketplace_like and not is_editorial_candidate:
        refresh_repair_fit = "mixed_fit"
    elif is_editorial_candidate:
        refresh_repair_fit = "good_fit"
    else:
        refresh_repair_fit = "review_fit"

    reasons: list[str] = []
    if is_editorial_candidate:
        reasons.append("presence editoriale exploitable pour un refresh")
    if is_app_like:
        reasons.append("navigation orientee app/login/dashboard")
    if is_docs_like:
        reasons.append("empreinte docs/support dominante")
    if is_marketplace_like:
        reasons.append("structure marketplace ou catalogue")
    if not reasons:
        reasons.append("signaux mitiges, a verifier manuellement")

    return {
        "is_editorial_candidate": is_editorial_candidate,
        "is_app_like": is_app_like,
        "app_signal": app_signal,
        "is_docs_like": is_docs_like,
        "docs_signal": docs_signal,
        "is_marketplace_like": is_marketplace_like,
        "marketplace_signal": marketplace_signal,
        "refresh_repair_fit": refresh_repair_fit,
        "site_type_note": "; ".join(reasons),
        "nav_link_ratio": nav_ratio,
        "content_link_ratio": content_ratio,
    }


def collect_link_signals(soup: BeautifulSoup, homepage_url: str) -> dict[str, int]:
    domain = clean_domain(homepage_url)
    signals = {
        "internal_links": 0,
        "nav_links": 0,
        "content_links": 0,
        "editorial_links": 0,
        "app_links": 0,
        "docs_links": 0,
        "marketplace_links": 0,
    }
    for link in soup.find_all("a", href=True):
        href = absolute_url(homepage_url, link.get("href", ""))
        parsed = urlparse(href)
        if parsed.netloc and clean_domain(parsed.netloc) != domain:
            continue
        path = (parsed.path or "/").lower()
        if path == "/":
            continue
        signals["internal_links"] += 1
        if link.find_parent(["nav", "header", "footer", "aside"]) is not None:
            signals["nav_links"] += 1
        else:
            signals["content_links"] += 1
        if any(path.startswith(hint) for hint in EDITORIAL_PATH_HINTS):
            signals["editorial_links"] += 1
        if any(path.startswith(hint) for hint in APP_PATH_HINTS):
            signals["app_links"] += 1
        if any(path.startswith(hint) for hint in DOCS_PATH_HINTS):
            signals["docs_links"] += 1
        if any(path.startswith(hint) for hint in MARKETPLACE_PATH_HINTS):
            signals["marketplace_links"] += 1
    return signals


def extract_editorial_word_count(html: str | None = None, soup: BeautifulSoup | None = None) -> int:
    if soup is None:
        if html is None:
            return 0
        soup = BeautifulSoup(html, "html.parser")
    main = soup.find(["main", "article"]) or soup.body or soup
    return len(_visible_text_segments(main).split())


def count_keyword_hits(html: str, keywords: Iterable[str]) -> int:
    hits = 0
    for keyword in keywords:
        if keyword in html:
            hits += 1
    return hits


def inspect_sitemap(
    domain: str,
    session: requests.Session,
    timeout: int,
    max_html_bytes: int,
    max_total_seconds_per_domain: float,
    max_total_requests_per_domain: int,
    max_sitemap_urls: int,
    max_nested_sitemaps: int,
    max_redirects: int,
    resource_state: dict[str, float | int],
    cancel_callback: Callable[[], None] | None = None,
) -> dict[str, int | bool]:
    sitemap_urls: list[str] = []
    for candidate in SITEMAP_CANDIDATES:
        for prefix in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
            sitemap_urls.append(f"{prefix}{candidate}")
    if max_sitemap_urls > 0:
        sitemap_urls = sitemap_urls[:max_sitemap_urls]

    discovered_urls: list[str] = []
    for sitemap_url in sitemap_urls:
        if cancel_callback is not None:
            cancel_callback()
        if qualify_budget_exceeded(
            resource_state,
            max_total_seconds_per_domain=max_total_seconds_per_domain,
            max_total_requests_per_domain=max_total_requests_per_domain,
        ):
            break
        if not consume_request_budget(resource_state, max_total_requests_per_domain):
            break
        try:
            response = session.get(sitemap_url, timeout=timeout, allow_redirects=True)
            if response.status_code >= 400:
                continue
            if len(response.history) > max_redirects:
                continue
            header_length = response.headers.get("content-length", "").strip()
            if header_length.isdigit() and int(header_length) > max_html_bytes:
                continue
            root = ET.fromstring(response.content)
            namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            nested_sitemaps = [node.text or "" for node in root.findall(".//sm:sitemap/sm:loc", namespace)]
            if nested_sitemaps:
                for nested_url in nested_sitemaps[: max(0, max_nested_sitemaps)]:
                    if cancel_callback is not None:
                        cancel_callback()
                    if qualify_budget_exceeded(
                        resource_state,
                        max_total_seconds_per_domain=max_total_seconds_per_domain,
                        max_total_requests_per_domain=max_total_requests_per_domain,
                    ):
                        break
                    if not consume_request_budget(resource_state, max_total_requests_per_domain):
                        break
                    try:
                        nested_response = session.get(nested_url, timeout=timeout, allow_redirects=True)
                        if len(nested_response.history) > max_redirects:
                            continue
                        nested_length = nested_response.headers.get("content-length", "").strip()
                        if nested_length.isdigit() and int(nested_length) > max_html_bytes:
                            continue
                        nested_root = ET.fromstring(nested_response.content)
                        discovered_urls.extend(
                            node.text or ""
                            for node in nested_root.findall(".//sm:url/sm:loc", namespace)
                            if node.text
                        )
                        if max_sitemap_urls > 0 and len(discovered_urls) >= max_sitemap_urls:
                            discovered_urls = discovered_urls[:max_sitemap_urls]
                            break
                    except (requests.RequestException, ET.ParseError):
                        continue
                estimated_pages = len(discovered_urls)
                if nested_sitemaps and discovered_urls and max_nested_sitemaps:
                    explored = min(max_nested_sitemaps, len(nested_sitemaps))
                    estimated_pages += max(0, len(nested_sitemaps) - explored) * max(1, len(discovered_urls) // explored)
                return {
                    "found": True,
                    "estimated_pages": estimated_pages,
                    "dated_urls_count": count_dated_urls(discovered_urls),
                }

            discovered_urls.extend(
                node.text or ""
                for node in root.findall(".//sm:url/sm:loc", namespace)
                if node.text
            )
            if max_sitemap_urls > 0:
                discovered_urls = discovered_urls[:max_sitemap_urls]
            return {
                "found": True,
                "estimated_pages": len(discovered_urls),
                "dated_urls_count": count_dated_urls(discovered_urls),
            }
        except (requests.RequestException, ET.ParseError):
            continue

    return {"found": False, "estimated_pages": 0, "dated_urls_count": 0}


def count_dated_urls(urls: Iterable[str]) -> int:
    count = 0
    for url in urls:
        if contains_year_reference(url):
            count += 1
    return count


def get_qualify_mode_config(mode: str):
    try:
        return QUALIFY_MODE_CONFIGS[mode]
    except KeyError as exc:
        raise CLIError(f"Mode qualify inconnu: {mode}") from exc


def consume_request_budget(resource_state: dict[str, float | int], max_total_requests_per_domain: int) -> bool:
    requests_count = int(resource_state.get("requests", 0))
    if max_total_requests_per_domain > 0 and requests_count >= max_total_requests_per_domain:
        return False
    resource_state["requests"] = requests_count + 1
    return True


def qualify_budget_exceeded(
    resource_state: dict[str, float | int],
    max_total_seconds_per_domain: float,
    max_total_requests_per_domain: int,
) -> bool:
    elapsed = time.monotonic() - float(resource_state.get("started_at", time.monotonic()))
    if max_total_seconds_per_domain > 0 and elapsed >= max_total_seconds_per_domain:
        return True
    return max_total_requests_per_domain > 0 and int(resource_state.get("requests", 0)) >= max_total_requests_per_domain


def build_homepage_failure_note(response: object | None) -> str:
    if response is None:
        return "Homepage inaccessible ou non HTML"
    skip_reason = getattr(response, "skip_reason", "")
    if skip_reason == "html_too_large":
        return "Homepage HTML trop lourde pour une qualification rapide"
    if skip_reason == "too_many_redirects":
        return "Homepage ignorée après trop de redirections"
    if skip_reason == "non_html":
        return "Homepage non HTML"
    status_code = getattr(response, "status_code", 0)
    if status_code >= 400:
        return f"Homepage inaccessible (HTTP {status_code})"
    return "Homepage inaccessible ou non HTML"


def build_homepage_failure_issue(response: object | None) -> str:
    if response is None:
        return "Homepage inaccessible"
    skip_reason = getattr(response, "skip_reason", "")
    if skip_reason == "html_too_large":
        return "Homepage HTML trop lourde"
    if skip_reason == "too_many_redirects":
        return "Homepage avec trop de redirections"
    if skip_reason == "non_html":
        return "Homepage non HTML"
    status_code = getattr(response, "status_code", 0)
    if status_code >= 400:
        return f"Homepage inaccessible (HTTP {status_code})"
    return "Homepage inaccessible"


def append_note(current: str, extra: str) -> str:
    if not current:
        return extra
    return f"{current} {extra}"


def borderline_rejection_note(reason: str) -> str:
    notes = {
        "app_like_site": "Signaux app-like borderline, review recommandee.",
        "docs_like_site": "Signaux docs-like borderline, review recommandee.",
        "marketplace_like_site": "Signaux marketplace-like borderline, review recommandee.",
    }
    return notes.get(reason, "Signaux borderline, review recommandee.")


def _visible_text_segments(root: BeautifulSoup) -> str:
    ignored_tags = {"script", "style", "noscript", "form", "nav", "header", "footer", "aside"}
    parts: list[str] = []
    for text_node in root.find_all(string=True):
        if not str(text_node).strip():
            continue
        parent = text_node.parent
        skip = False
        while parent is not None:
            parent_name = getattr(parent, "name", None)
            if parent_name in ignored_tags:
                skip = True
                break
            if parent is root:
                break
            parent = parent.parent
        if not skip:
            parts.append(str(text_node).strip())
    return " ".join(parts)
