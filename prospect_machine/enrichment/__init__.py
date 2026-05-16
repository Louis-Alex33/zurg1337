from __future__ import annotations

from .base import EmailFinder, EmailResult
from .scraping import ScrapingEmailFinder
from .hunter import HunterEmailFinder
from .chained import ChainedEmailFinder

__all__ = [
    "EmailFinder",
    "EmailResult",
    "ScrapingEmailFinder",
    "HunterEmailFinder",
    "ChainedEmailFinder",
]
