from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import aiohttp

from prospect_machine.qualification.contact import ContactResult, fetch_contact_signals
from prospect_machine.qualification.editorial import EditorialResult, fetch_editorial_signals
from prospect_machine.qualification.size import SizeResult, fetch_size_signals

logger = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = 10
_DEFAULT_TIMEOUT = 10

# Headers that look like a real browser to avoid trivial bot blocks.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


@dataclass
class DomainSignals:
    domain: str
    # Contact
    has_contact_page: bool = False
    contact_page_url: str = ""
    contact_emails: list[str] = field(default_factory=list)
    contact_names: list[str] = field(default_factory=list)
    # Editorial
    last_post_date: date | None = None
    last_post_source: str = ""
    # Size
    estimated_size: int = 0
    size_source: str = ""
    # Error tracking
    error: str = ""


def run_qualification(
    domains: list[str],
    concurrency: int = _DEFAULT_CONCURRENCY,
    timeout: int = _DEFAULT_TIMEOUT,
    lang: str = "fr",
) -> list[DomainSignals]:
    """Synchronous entry point — runs the async qualification loop in a new event loop."""
    return asyncio.run(_qualify_all(domains, concurrency, timeout, lang))


async def _qualify_all(
    domains: list[str],
    concurrency: int,
    timeout: int,
    lang: str,
) -> list[DomainSignals]:
    semaphore = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(ssl=False, limit=concurrency)
    async with aiohttp.ClientSession(
        headers=_HEADERS,
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout + 5),
    ) as session:
        tasks = [
            _qualify_domain(domain, session, semaphore, timeout, lang)
            for domain in domains
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    signals_list: list[DomainSignals] = []
    for domain, result in zip(domains, results):
        if isinstance(result, Exception):
            logger.warning("qualification error domain=%s error=%s", domain, result)
            signals_list.append(DomainSignals(domain=domain, error=str(result)))
        else:
            signals_list.append(result)
    return signals_list


async def _qualify_domain(
    domain: str,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    timeout: int,
    lang: str,
) -> DomainSignals:
    async with semaphore:
        logger.debug("qualifying domain=%s", domain)
        contact_task = asyncio.create_task(
            fetch_contact_signals(domain, session, timeout=timeout, lang=lang)
        )
        editorial_task = asyncio.create_task(
            fetch_editorial_signals(domain, session, timeout=timeout)
        )
        size_task = asyncio.create_task(
            fetch_size_signals(domain, session, timeout=timeout)
        )

        contact_res, editorial_res, size_res = await asyncio.gather(
            contact_task, editorial_task, size_task, return_exceptions=True
        )

        signals = DomainSignals(domain=domain)

        if isinstance(contact_res, ContactResult):
            signals.has_contact_page = contact_res.has_contact_page
            signals.contact_page_url = contact_res.contact_page_url
            signals.contact_emails = contact_res.emails
            signals.contact_names = contact_res.names
        elif isinstance(contact_res, Exception):
            logger.debug("contact signals error domain=%s: %s", domain, contact_res)

        if isinstance(editorial_res, EditorialResult):
            signals.last_post_date = editorial_res.last_post_date
            signals.last_post_source = editorial_res.source
        elif isinstance(editorial_res, Exception):
            logger.debug("editorial signals error domain=%s: %s", domain, editorial_res)

        if isinstance(size_res, SizeResult):
            signals.estimated_size = size_res.estimated_size
            signals.size_source = size_res.source
        elif isinstance(size_res, Exception):
            logger.debug("size signals error domain=%s: %s", domain, size_res)

        return signals


def signals_to_row(s: DomainSignals) -> dict[str, Any]:
    """Convert DomainSignals to a flat dict suitable for CSV/SQLite storage."""
    return {
        "domain": s.domain,
        "has_contact_page": "yes" if s.has_contact_page else "",
        "contact_page_url": s.contact_page_url,
        "contact_emails": " | ".join(s.contact_emails),
        "contact_names": " | ".join(s.contact_names),
        "last_post_date": s.last_post_date.isoformat() if s.last_post_date else "",
        "last_post_source": s.last_post_source,
        "estimated_size": s.estimated_size,
        "size_source": s.size_source,
        "error": s.error,
    }
