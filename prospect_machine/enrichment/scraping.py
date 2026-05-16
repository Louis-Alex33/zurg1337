from __future__ import annotations

from .base import EmailFinder, EmailResult


class ScrapingEmailFinder(EmailFinder):
    """Returns the first email already present in DomainSignals.contact_emails.

    No network I/O — the data was fetched during QualificationStep.
    Accepts an optional pre-loaded list of emails so the step can inject them.
    """

    def __init__(self, emails: list[str] | None = None) -> None:
        self._emails: list[str] = emails or []

    def find(self, domain: str) -> EmailResult:
        if not self._emails:
            return EmailResult()
        return EmailResult(
            email=self._emails[0],
            source="scrape",
            confidence=0.9,
        )
