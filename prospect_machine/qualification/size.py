from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BFS_MAX_PAGES = 50
_BFS_DEPTH = 2


@dataclass
class SizeResult:
    estimated_size: int = 0
    source: str = ""  # "sitemap" | "crawl"


async def fetch_size_signals(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int = 8,
) -> SizeResult:
    """Estimate site size via sitemap (preferred) or BFS crawl (fallback)."""

    result = await _try_sitemap_count(domain, session, timeout)
    if result is not None:
        return result

    result = await _try_bfs_crawl(domain, session, timeout)
    return result or SizeResult()


async def _try_sitemap_count(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int,
) -> SizeResult | None:
    url = f"https://{domain}/sitemap.xml"
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            ssl=False,
        ) as resp:
            if resp.status != 200:
                return None
            xml_text = await resp.text(errors="replace")
    except Exception as exc:
        logger.debug("size sitemap fetch %s: %s", url, exc)
        return None

    count = await _count_sitemap_urls(xml_text, domain, session, timeout)
    if count > 0:
        return SizeResult(estimated_size=count, source="sitemap")
    return None


async def _count_sitemap_urls(
    xml_text: str,
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int,
    _depth: int = 0,
) -> int:
    """Recursively count <loc> entries, following sitemap index links (max depth 2)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return 0

    # Detect sitemap index vs urlset by tag name.
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if tag == "sitemapindex" and _depth < 2:
        total = 0
        for sitemap_el in root.iter():
            loc_tag = sitemap_el.tag.split("}")[-1] if "}" in sitemap_el.tag else sitemap_el.tag
            if loc_tag == "loc" and sitemap_el.text:
                child_url = sitemap_el.text.strip()
                try:
                    async with session.get(
                        child_url,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        allow_redirects=True,
                        ssl=False,
                    ) as resp:
                        if resp.status == 200:
                            child_xml = await resp.text(errors="replace")
                            total += await _count_sitemap_urls(
                                child_xml, domain, session, timeout, _depth + 1
                            )
                except Exception as exc:
                    logger.debug("child sitemap %s: %s", child_url, exc)
        return total

    # urlset: count <loc> tags.
    count = 0
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local == "loc":
            count += 1
    return count


async def _try_bfs_crawl(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int,
) -> SizeResult | None:
    base = f"https://{domain}"
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(base, 0)])

    while queue and len(visited) < _BFS_MAX_PAGES:
        url, depth = queue.popleft()
        if url in visited or depth > _BFS_DEPTH:
            continue
        visited.add(url)
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    continue
                ct = resp.headers.get("content-type", "")
                if "html" not in ct:
                    continue
                html = await resp.text(errors="replace")
        except Exception as exc:
            logger.debug("bfs crawl %s: %s", url, exc)
            continue

        if depth < _BFS_DEPTH:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup.find_all("a", href=True):
                href = tag["href"].strip()
                absolute = urljoin(url, href)
                parsed = urlparse(absolute)
                # Only follow same-domain, HTML-like links.
                if parsed.netloc.replace("www.", "") != domain.replace("www.", ""):
                    continue
                if parsed.scheme not in {"http", "https"}:
                    continue
                if any(absolute.lower().endswith(ext) for ext in (".pdf", ".jpg", ".png", ".css", ".js")):
                    continue
                clean = absolute.split("#")[0]
                if clean not in visited:
                    queue.append((clean, depth + 1))

    count = len(visited)
    if count > 0:
        return SizeResult(estimated_size=count, source="crawl")
    return None
