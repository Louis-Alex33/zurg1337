from __future__ import annotations

import logging

from .base import EmailFinder, EmailResult
from .hunter import HunterEmailFinder
from .scraping import ScrapingEmailFinder

logger = logging.getLogger(__name__)


class ChainedEmailFinder(EmailFinder):
    """Tries ScrapingEmailFinder first, falls back to HunterEmailFinder if empty.

    The source field on the returned EmailResult traces which finder produced it.
    """

    def __init__(
        self,
        scraping: ScrapingEmailFinder | None = None,
        hunter: HunterEmailFinder | None = None,
    ) -> None:
        self._scraping = scraping or ScrapingEmailFinder()
        self._hunter = hunter or HunterEmailFinder()

    def find(self, domain: str) -> EmailResult:
        result = self._scraping.find(domain)
        if result.email:
            logger.debug("chained finder: scrape hit domain=%s email=%s", domain, result.email)
            return result

        logger.debug("chained finder: scrape miss, trying hunter domain=%s", domain)
        result = self._hunter.find(domain)
        if result.email:
            logger.debug("chained finder: hunter hit domain=%s email=%s", domain, result.email)
        return result
