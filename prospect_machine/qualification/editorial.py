from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_RSS_PATHS = ["/feed", "/rss.xml", "/feed.xml", "/atom.xml"]

# ISO-8601 date pattern (YYYY-MM-DD) — no trailing \b so it also matches YYYY-MM-DDTHH:MM:SSZ.
_ISO_DATE_RE = re.compile(r"(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
# RFC-2822 date pattern (Mon, 01 Jan 2024)
_RFC_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d{2})\b",
    re.IGNORECASE,
)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class EditorialResult:
    last_post_date: date | None = None
    source: str = ""  # "sitemap" | "rss" | "home_scrape"


async def fetch_editorial_signals(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int = 8,
) -> EditorialResult:
    """Detect last publication date via sitemap, RSS, then home page scraping."""

    # 1 — sitemap.xml
    result = await _try_sitemap(domain, session, timeout)
    if result is not None:
        return result

    # 2 — RSS feeds
    result = await _try_rss(domain, session, timeout)
    if result is not None:
        return result

    # 3 — home page scraping
    result = await _try_home_scrape(domain, session, timeout)
    if result is not None:
        return result

    return EditorialResult()


async def _try_sitemap(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int,
) -> EditorialResult | None:
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
        logger.debug("sitemap fetch %s: %s", url, exc)
        return None

    best = _extract_lastmod_from_sitemap_xml(xml_text)
    if best is not None:
        return EditorialResult(last_post_date=best, source="sitemap")
    return None


def _extract_lastmod_from_sitemap_xml(xml_text: str) -> date | None:
    """Return the most recent lastmod date found in sitemap XML (index or urlset)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    # Strip XML namespace for simpler tag matching.
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    ns_prefix = f"{{{ns}}}" if ns else ""

    dates: list[date] = []

    def _collect(element: ET.Element) -> None:
        for child in element:
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if local == "lastmod" and child.text:
                d = _parse_iso_date(child.text.strip())
                if d:
                    dates.append(d)
            _collect(child)

    _collect(root)
    return max(dates) if dates else None


async def _try_rss(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int,
) -> EditorialResult | None:
    for path in _RSS_PATHS:
        url = f"https://{domain}{path}"
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    continue
                xml_text = await resp.text(errors="replace")
                best = _extract_date_from_rss(xml_text)
                if best is not None:
                    return EditorialResult(last_post_date=best, source="rss")
        except Exception as exc:
            logger.debug("rss probe %s: %s", url, exc)
            continue
    return None


def _extract_date_from_rss(xml_text: str) -> date | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    dates: list[date] = []

    def _scan(element: ET.Element) -> None:
        local = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        if local in {"pubDate", "updated", "published"} and element.text:
            d = _parse_rfc_or_iso_date(element.text.strip())
            if d:
                dates.append(d)
        for child in element:
            _scan(child)

    _scan(root)
    return max(dates) if dates else None


async def _try_home_scrape(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int,
) -> EditorialResult | None:
    url = f"https://{domain}"
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            ssl=False,
        ) as resp:
            if resp.status != 200:
                return None
            html = await resp.text(errors="replace")
    except Exception as exc:
        logger.debug("home scrape %s: %s", url, exc)
        return None

    # Look for ISO dates in <time datetime="...">, meta tags, and visible text.
    soup = BeautifulSoup(html, "html.parser")
    dates: list[date] = []

    for tag in soup.find_all("time"):
        dt_attr = tag.get("datetime", "")
        d = _parse_iso_date(dt_attr)
        if d:
            dates.append(d)

    for match in _ISO_DATE_RE.finditer(soup.get_text(" ", strip=True)[:5000]):
        d = _parse_iso_date(match.group(0))
        if d:
            dates.append(d)

    if dates:
        return EditorialResult(last_post_date=max(dates), source="home_scrape")
    return None


def _parse_iso_date(value: str) -> date | None:
    m = _ISO_DATE_RE.search(value)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_rfc_or_iso_date(value: str) -> date | None:
    d = _parse_iso_date(value)
    if d:
        return d
    m = _RFC_DATE_RE.search(value)
    if m:
        try:
            return date(int(m.group(3)), _MONTH_MAP[m.group(2).lower()[:3]], int(m.group(1)))
        except (ValueError, KeyError):
            pass
    return None
