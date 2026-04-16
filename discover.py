from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections import deque
from math import ceil
from pathlib import Path
from typing import Callable
from unicodedata import normalize
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    DEFAULT_DELAY,
    DEFAULT_DISCOVER_PROVIDER,
    DISCOVER_HTTP_TIMEOUT,
    DISCOVER_RETRY_ATTEMPTS,
    DISCOVER_RETRY_BACKOFF,
    DISCOVERY_EXCLUDED_DOMAIN_PATTERNS,
    DISCOVERY_QUERY_STOPWORDS,
    QUERY_MODIFIER_HINTS,
    SEARCH_QUERY_TEMPLATES,
)
from io_helpers import append_csv_rows, discovery_rows, init_csv_file, write_csv_rows
from models import DomainDiscovery
from utils import (
    CLIError,
    clean_domain,
    decode_duckduckgo_target,
    is_big_site,
    is_hard_blocked_domain,
    make_session,
    utc_timestamp,
)


class SearchProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, limit: int, session: requests.Session) -> list[DomainDiscovery]:
        raise NotImplementedError


class AutoSearchProvider(SearchProvider):
    name = "auto"

    def __init__(self, providers: list[SearchProvider]) -> None:
        self.providers = providers

    def search(self, query: str, limit: int, session: requests.Session) -> list[DomainDiscovery]:
        messages: list[str] = []
        for provider in self.providers:
            try:
                results = provider.search(query=query, limit=limit, session=session)
            except CLIError as exc:
                messages.append(str(exc))
                continue
            if results:
                return results
            messages.append(
                f"Le provider '{provider.name}' n'a retourne aucun domaine exploitable pour '{query}'."
            )
        raise CLIError(" | ".join(messages))


class BingRssProvider(SearchProvider):
    name = "bingrss"
    search_url = "https://www.bing.com/search"

    def search(self, query: str, limit: int, session: requests.Session) -> list[DomainDiscovery]:
        last_error: requests.RequestException | None = None
        for attempt in range(DISCOVER_RETRY_ATTEMPTS):
            try:
                response = session.get(
                    self.search_url,
                    params={"q": query, "format": "rss"},
                    timeout=DISCOVER_HTTP_TIMEOUT,
                )
                response.raise_for_status()
                results = extract_bing_rss_results(
                    xml_payload=response.text,
                    query=query,
                    provider_name=self.name,
                    limit=limit,
                )
                if results:
                    return results
                break
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(DISCOVER_RETRY_BACKOFF * (attempt + 1))

        if last_error is not None:
            raise CLIError(
                f"Le provider '{self.name}' a echoue pour la requete '{query}'."
            ) from last_error
        return []


class BingHtmlProvider(SearchProvider):
    name = "binghtml"
    search_url = "https://www.bing.com/search"

    def search(self, query: str, limit: int, session: requests.Session) -> list[DomainDiscovery]:
        last_error: requests.RequestException | None = None
        for attempt in range(DISCOVER_RETRY_ATTEMPTS):
            try:
                response = session.get(
                    self.search_url,
                    params={"q": query},
                    timeout=DISCOVER_HTTP_TIMEOUT,
                )
                response.raise_for_status()
                results = extract_bing_html_results(
                    html=response.text,
                    query=query,
                    provider_name=self.name,
                    limit=limit,
                )
                if results:
                    return results
                break
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(DISCOVER_RETRY_BACKOFF * (attempt + 1))

        if last_error is not None:
            raise CLIError(
                f"Le provider '{self.name}' a echoue pour la requete '{query}'."
            ) from last_error
        return []


class DuckDuckGoHtmlProvider(SearchProvider):
    name = "duckduckgo"
    search_endpoints = (
        ("POST", "https://html.duckduckgo.com/html/"),
        ("GET", "https://html.duckduckgo.com/html/"),
        ("GET", "https://lite.duckduckgo.com/lite/"),
    )

    def search(self, query: str, limit: int, session: requests.Session) -> list[DomainDiscovery]:
        last_error: requests.RequestException | None = None
        for method, endpoint in self.search_endpoints:
            for attempt in range(DISCOVER_RETRY_ATTEMPTS):
                try:
                    response = self._perform_request(
                        session=session,
                        method=method,
                        endpoint=endpoint,
                        query=query,
                    )
                    response.raise_for_status()
                    results = extract_duckduckgo_results(
                        html=response.text,
                        query=query,
                        provider_name=self.name,
                        limit=limit,
                    )
                    if results:
                        return results
                    break
                except requests.RequestException as exc:
                    last_error = exc
                    time.sleep(DISCOVER_RETRY_BACKOFF * (attempt + 1))

        if last_error is not None:
            raise CLIError(
                f"Le provider '{self.name}' a echoue pour la requete '{query}'. "
                "Verifiez votre connexion reseau, reessayez avec moins de niches, "
                "ou augmentez le delai entre les requetes."
            ) from last_error

        return []

    def _perform_request(
        self,
        session: requests.Session,
        method: str,
        endpoint: str,
        query: str,
    ) -> requests.Response:
        if method == "POST":
            return session.post(endpoint, data={"q": query}, timeout=DISCOVER_HTTP_TIMEOUT)
        return session.get(f"{endpoint}?{urlencode({'q': query})}", timeout=DISCOVER_HTTP_TIMEOUT)


class StaticSearchProvider(SearchProvider):
    name = "static"

    def __init__(self, fixtures: dict[str, list[DomainDiscovery]]) -> None:
        self.fixtures = fixtures

    def search(self, query: str, limit: int, session: requests.Session) -> list[DomainDiscovery]:
        return self.fixtures.get(query, [])[:limit]


def build_queries(niches: list[str], query_mode: str = "auto") -> list[str]:
    queries: list[str] = []
    for niche in niches:
        niche = sanitize_discovery_niche(niche)
        if not niche:
            continue
        if query_mode not in {"auto", "exact", "expand"}:
            raise CLIError(f"Mode de requete inconnu: {query_mode}")

        use_exact = query_mode == "exact" or (
            query_mode == "auto" and should_use_exact_query(niche)
        )
        if use_exact:
            candidate = normalize_query(niche)
            if candidate:
                queries.append(candidate)
            continue
        for template in SEARCH_QUERY_TEMPLATES:
            candidate = normalize_query(template.format(niche=niche).strip())
            if candidate:
                queries.append(candidate)
    seen: set[str] = set()
    deduped: list[str] = []
    for query in queries:
        if query in seen:
            continue
        seen.add(query)
        deduped.append(query)
    return deduped


def get_provider(name: str) -> SearchProvider:
    duckduckgo = DuckDuckGoHtmlProvider()
    binghtml = BingHtmlProvider()
    bingrss = BingRssProvider()
    providers: dict[str, SearchProvider] = {
        DEFAULT_DISCOVER_PROVIDER: AutoSearchProvider([binghtml, bingrss, duckduckgo]),
        "auto": AutoSearchProvider([binghtml, bingrss, duckduckgo]),
        "binghtml": binghtml,
        "bingrss": bingrss,
        "duckduckgo": duckduckgo,
    }
    provider = providers.get(name)
    if provider is None:
        supported = ", ".join(sorted(providers))
        raise CLIError(f"Provider inconnu '{name}'. Providers disponibles: {supported}")
    return provider


def discover_domains(
    niches: list[str],
    limit: int,
    output: str,
    provider_name: str = DEFAULT_DISCOVER_PROVIDER,
    delay: float = DEFAULT_DELAY,
    query_mode: str = "auto",
    session: requests.Session | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[DomainDiscovery]:
    if not niches:
        raise CLIError("Aucune niche fournie. Utilisez par exemple --niches 'padel,yoga,velo'.")
    if limit <= 0:
        raise CLIError("--limit doit etre superieur a 0.")

    provider = get_provider(provider_name)
    queries = build_queries(niches, query_mode=query_mode)
    client = session or make_session()
    fieldnames = ["domain", "source_query", "source_provider", "first_seen", "title", "snippet"]
    init_csv_file(output, fieldnames)
    per_query_limit = max(5, ceil(limit / max(1, len(queries))) * 2)
    failures: list[str] = []
    query_queue: deque[str] = deque(queries)
    seen_queries: set[str] = set()

    discovered_by_domain: dict[str, DomainDiscovery] = {}
    query_index = 0
    print(
        f"Discover lance | provider={provider_name} | queries={len(queries)} | "
        f"limit={limit} | per_query_limit={per_query_limit}"
    )
    while query_queue:
        if cancel_callback is not None:
            cancel_callback()
        query = query_queue.popleft()
        if query in seen_queries:
            continue
        seen_queries.add(query)
        query_index += 1
        print(
            f"[{query_index}/{len(queries)}] Requete en cours: '{query}' | "
            f"deja trouves={len(discovered_by_domain)}/{limit}"
        )
        try:
            batch = provider.search(query=query, limit=per_query_limit, session=client)
            if cancel_callback is not None:
                cancel_callback()
        except CLIError as exc:
            failures.append(str(exc))
            print(f"Warning: echec sur '{query}' | {exc}")
            maybe_enqueue_topic_fallbacks(query, query_mode, query_queue, seen_queries)
            if query_queue:
                if cancel_callback is not None:
                    cancel_callback()
                time.sleep(max(delay, 1.5))
            continue
        print(f"  -> {len(batch)} resultats bruts pour '{query}'")
        if not batch:
            maybe_enqueue_topic_fallbacks(query, query_mode, query_queue, seen_queries)
            print(f"  -> aucun domaine exploitable pour '{query}'")
        added_count = 0
        for item in batch:
            if not should_keep_discovery_item(item):
                continue
            if item.domain in discovered_by_domain:
                continue
            discovered_by_domain[item.domain] = item
            append_csv_rows(output, discovery_rows([item]), fieldnames=fieldnames)
            added_count += 1
            if len(discovered_by_domain) >= limit:
                break
        print(
            f"  -> {added_count} nouveaux domaines gardes | "
            f"total={len(discovered_by_domain)}/{limit}"
        )
        if len(discovered_by_domain) >= limit:
            break
        if query_queue:
            if cancel_callback is not None:
                cancel_callback()
            time.sleep(delay)

    discovered = list(discovered_by_domain.values())[:limit]
    if cancel_callback is not None:
        cancel_callback()
    if not discovered:
        raise CLIError(
            "Aucun domaine trouve. Verifiez les niches, le provider choisi, "
            "ou essayez une niche plus specifique. "
            f"Echecs observes: {len(failures)}."
        )

    write_csv_rows(
        output,
        discovery_rows(discovered),
        fieldnames=fieldnames,
    )
    print(f"Discover termine | {len(discovered)} domaines exportes vers {output}")
    return discovered


def import_domains_from_file(
    input_path: str,
    output: str,
    source_query: str = "manual",
    source_provider: str = "manual",
) -> list[DomainDiscovery]:
    file_path = Path(input_path)
    if not file_path.exists():
        raise CLIError(f"Fichier introuvable: {input_path}")

    first_seen = utc_timestamp()
    imported_by_domain: dict[str, DomainDiscovery] = {}
    fieldnames = ["domain", "source_query", "source_provider", "first_seen", "title", "snippet"]
    init_csv_file(output, fieldnames)
    with file_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            domain = clean_domain(line)
            if not domain or is_big_site(domain):
                continue
            if domain in imported_by_domain:
                continue
            imported_by_domain[domain] = DomainDiscovery(
                domain=domain,
                source_query=source_query,
                source_provider=source_provider,
                first_seen=first_seen,
                title="",
                snippet="",
            )
            append_csv_rows(output, discovery_rows([imported_by_domain[domain]]), fieldnames=fieldnames)

    imported = list(imported_by_domain.values())
    if not imported:
        raise CLIError(
            "Aucun domaine exploitable trouve dans le fichier. "
            "Verifiez le format: un domaine ou une URL par ligne."
        )

    write_csv_rows(
        output,
        discovery_rows(imported),
        fieldnames=fieldnames,
    )
    return imported


def discovery_to_console_rows(items: list[DomainDiscovery]) -> list[str]:
    rows: list[str] = []
    for item in items[:10]:
        rows.append(
            f"- {item.domain} | query='{item.source_query}' | provider={item.source_provider} | "
            f"title='{item.title[:60]}'"
        )
    return rows


def infer_domain_from_result_url(url: str) -> str:
    return clean_domain(urlparse(url).netloc or url)


def normalize_query(query: str) -> str:
    words = query.split()
    deduped_words: list[str] = []
    seen: set[str] = set()
    for word in words:
        normalized = word.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped_words.append(word)
    return " ".join(deduped_words).strip()


def sanitize_discovery_niche(value: str) -> str:
    cleaned = value.strip()
    lower = cleaned.lower()
    prefixes = (
        "niche =",
        "niche:",
        "niches =",
        "niches:",
        "query =",
        "query:",
        "requete =",
        "requete:",
        "requêtes =",
        "requêtes:",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned


def niche_contains_modifier(niche: str) -> bool:
    words = {_normalize_query_token(word) for word in niche.split()}
    return any(word in QUERY_MODIFIER_HINTS for word in words)


def should_use_exact_query(niche: str) -> bool:
    return niche_contains_modifier(niche) or contains_search_operators(niche)


def contains_search_operators(niche: str) -> bool:
    lowered = niche.lower()
    operator_hints = (
        "site:",
        "intitle:",
        "inbody:",
        "inurl:",
        "filetype:",
        "after:",
        "before:",
        '"',
        "'",
        "(",
        ")",
    )
    return any(hint in lowered for hint in operator_hints)


def _normalize_query_token(token: str) -> str:
    normalized = normalize("NFKD", token).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip(" '\"()[]{}.,;:!?")
    return normalized


def maybe_enqueue_topic_fallbacks(
    query: str,
    query_mode: str,
    query_queue: deque[str],
    seen_queries: set[str],
) -> None:
    if query_mode != "auto":
        return
    if contains_search_operators(query):
        return
    if not niche_contains_modifier(query):
        return

    fallback_queries = build_topic_fallback_queries(query)
    new_queries = [candidate for candidate in fallback_queries if candidate not in seen_queries and candidate not in query_queue]
    if not new_queries:
        return
    print(f"Info: fallback requetes pour '{query}': {', '.join(new_queries)}")
    query_queue.extend(new_queries)


def build_topic_fallback_queries(query: str) -> list[str]:
    topic = extract_query_topic(query)
    if not topic:
        return []
    return build_queries([topic], query_mode="expand")


def extract_query_topic(query: str) -> str:
    kept_words: list[str] = []
    for raw_word in query.split():
        token = _normalize_query_token(raw_word)
        if not token:
            continue
        if token in QUERY_MODIFIER_HINTS or token in DISCOVERY_QUERY_STOPWORDS:
            continue
        if contains_operator_token(raw_word):
            continue
        kept_words.append(raw_word.strip(" '\"()[]{}.,;:!?"))
    normalized_topic = normalize_query(" ".join(kept_words))
    return normalized_topic


def contains_operator_token(token: str) -> bool:
    lowered = token.lower()
    return any(
        hint in lowered
        for hint in ("site:", "intitle:", "inbody:", "inurl:", "filetype:", "after:", "before:")
    )


def extract_duckduckgo_results(
    html: str,
    query: str,
    provider_name: str,
    limit: int,
) -> list[DomainDiscovery]:
    soup = BeautifulSoup(html, "html.parser")
    structured = extract_structured_results(soup, query=query, provider_name=provider_name, limit=limit)
    if structured:
        return structured[:limit]
    return extract_fallback_anchor_results(soup, query=query, provider_name=provider_name, limit=limit)


def extract_structured_results(
    soup: BeautifulSoup,
    query: str,
    provider_name: str,
    limit: int,
) -> list[DomainDiscovery]:
    selectors = [".result", ".web-result", "article"]
    first_seen = utc_timestamp()
    results_by_domain: dict[str, DomainDiscovery] = {}

    for selector in selectors:
        for block in soup.select(selector):
            link = (
                block.select_one(".result__a")
                or block.select_one("a.result-link")
                or block.select_one("h2 a")
                or block.select_one("a[data-testid='result-title-a']")
            )
            if link is None:
                continue
            discovery = discovery_from_link(
                href=link.get("href", ""),
                title=link.get_text(" ", strip=True),
                snippet=extract_snippet(block),
                query=query,
                provider_name=provider_name,
                first_seen=first_seen,
            )
            if discovery is None or discovery.domain in results_by_domain:
                continue
            results_by_domain[discovery.domain] = discovery
            if len(results_by_domain) >= limit:
                return list(results_by_domain.values())
    return list(results_by_domain.values())


def extract_fallback_anchor_results(
    soup: BeautifulSoup,
    query: str,
    provider_name: str,
    limit: int,
) -> list[DomainDiscovery]:
    first_seen = utc_timestamp()
    results_by_domain: dict[str, DomainDiscovery] = {}
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not looks_like_search_result_href(href):
            continue
        title = link.get_text(" ", strip=True)
        if len(title) < 8:
            continue
        discovery = discovery_from_link(
            href=href,
            title=title,
            snippet="",
            query=query,
            provider_name=provider_name,
            first_seen=first_seen,
        )
        if discovery is None or discovery.domain in results_by_domain:
            continue
        results_by_domain[discovery.domain] = discovery
        if len(results_by_domain) >= limit:
            break
    return list(results_by_domain.values())


def discovery_from_link(
    href: str,
    title: str,
    snippet: str,
    query: str,
    provider_name: str,
    first_seen: str,
) -> DomainDiscovery | None:
    raw_url = decode_duckduckgo_target(href)
    domain = clean_domain(raw_url)
    if not domain or domain.endswith("duckduckgo.com") or is_big_site(domain) or is_hard_blocked_domain(domain):
        return None
    if is_excluded_discovery_domain(domain):
        return None
    if not looks_relevant_for_query(domain=domain, title=title, snippet=snippet, query=query):
        return None
    return DomainDiscovery(
        domain=domain,
        source_query=query,
        source_provider=provider_name,
        first_seen=first_seen,
        title=title,
        snippet=snippet,
    )


def extract_snippet(block) -> str:
    snippet_node = (
        block.select_one(".result__snippet")
        or block.select_one(".result-snippet")
        or block.select_one(".snippet")
        or block.select_one(".result__extras__url")
    )
    return snippet_node.get_text(" ", strip=True) if snippet_node else ""


def should_keep_discovery_item(item: DomainDiscovery) -> bool:
    domain = clean_domain(item.domain)
    if not domain or is_big_site(domain) or is_hard_blocked_domain(domain) or is_excluded_discovery_domain(domain):
        return False
    return looks_relevant_for_query(domain=domain, title=item.title, snippet=item.snippet, query=item.source_query)


def is_excluded_discovery_domain(domain: str) -> bool:
    normalized_domain = clean_domain(domain)
    return any(pattern in normalized_domain for pattern in DISCOVERY_EXCLUDED_DOMAIN_PATTERNS)


def looks_relevant_for_query(domain: str, title: str, snippet: str, query: str) -> bool:
    core_terms = extract_query_core_terms(query)
    if not core_terms:
        return True
    haystack = normalize_match_text(" ".join([domain, title, snippet]))
    return any(term in haystack for term in core_terms)


def extract_query_core_terms(query: str) -> list[str]:
    core_terms: list[str] = []
    for raw_word in query.split():
        token = normalize_match_text(raw_word)
        if not token or token in QUERY_MODIFIER_HINTS or token in DISCOVERY_QUERY_STOPWORDS:
            continue
        if len(token) < 3:
            continue
        if token not in core_terms:
            core_terms.append(token)
    return core_terms


def normalize_match_text(value: str) -> str:
    ascii_value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().split())


def looks_like_search_result_href(href: str) -> bool:
    if not href:
        return False
    lower = href.lower()
    if "duckduckgo.com/l/?" in lower and "uddg=" in lower:
        return True
    if lower.startswith("http://") or lower.startswith("https://"):
        blocked_hosts = (
            "bing.com",
            "duckduckgo.com",
            "start.duckduckgo.com",
        )
        return not any(host in lower for host in blocked_hosts)
    return False


def extract_bing_rss_results(
    xml_payload: str,
    query: str,
    provider_name: str,
    limit: int,
) -> list[DomainDiscovery]:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError:
        return []

    first_seen = utc_timestamp()
    results_by_domain: dict[str, DomainDiscovery] = {}
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        description = (item.findtext("description") or "").strip()
        discovery = discovery_from_link(
            href=link,
            title=title,
            snippet=description,
            query=query,
            provider_name=provider_name,
            first_seen=first_seen,
        )
        if discovery is None or discovery.domain in results_by_domain:
            continue
        results_by_domain[discovery.domain] = discovery
        if len(results_by_domain) >= limit:
            break
    return list(results_by_domain.values())


def extract_bing_html_results(
    html: str,
    query: str,
    provider_name: str,
    limit: int,
) -> list[DomainDiscovery]:
    soup = BeautifulSoup(html, "html.parser")
    first_seen = utc_timestamp()
    results_by_domain: dict[str, DomainDiscovery] = {}

    for block in soup.select("li.b_algo, .b_algo, main article"):
        link = (
            block.select_one("h2 a")
            or block.select_one("a[h]")
            or block.select_one("a")
        )
        if link is None:
            continue
        href = link.get("href", "").strip()
        title = link.get_text(" ", strip=True)
        snippet_node = (
            block.select_one(".b_caption p")
            or block.select_one(".b_snippet")
            or block.select_one("p")
        )
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        discovery = discovery_from_link(
            href=href,
            title=title,
            snippet=snippet,
            query=query,
            provider_name=provider_name,
            first_seen=first_seen,
        )
        if discovery is None or discovery.domain in results_by_domain:
            continue
        results_by_domain[discovery.domain] = discovery
        if len(results_by_domain) >= limit:
            return list(results_by_domain.values())

    return list(results_by_domain.values())
