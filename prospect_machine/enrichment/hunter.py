from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

import requests

from .base import EmailFinder, EmailResult

logger = logging.getLogger(__name__)

_HUNTER_API_URL = "https://api.hunter.io/v2/domain-search"
_CACHE_DB = Path("data/hunter_cache.db")
_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _init_cache(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hunter_cache (
            domain      TEXT PRIMARY KEY,
            email       TEXT NOT NULL,
            confidence  REAL NOT NULL,
            fetched_at  INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


class HunterEmailFinder(EmailFinder):
    """Calls the Hunter.io domain-search API with a local SQLite cache (TTL 30 days).

    - Requires HUNTER_API_KEY env var; logs a warning and returns empty if absent.
    - On HTTP 429 or quota errors: logs a warning, returns empty, does not raise.
    """

    def __init__(self, cache_db: Path = _CACHE_DB) -> None:
        self._api_key: str = os.environ.get("HUNTER_API_KEY", "")
        self._cache_db = cache_db
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = _init_cache(self._cache_db)
        return self._conn

    def _get_cached(self, domain: str) -> EmailResult | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT email, confidence, fetched_at FROM hunter_cache WHERE domain = ?",
            (domain,),
        ).fetchone()
        if row is None:
            return None
        email, confidence, fetched_at = row
        if time.time() - fetched_at > _CACHE_TTL_SECONDS:
            conn.execute("DELETE FROM hunter_cache WHERE domain = ?", (domain,))
            conn.commit()
            return None
        if not email:
            return EmailResult()
        return EmailResult(email=email, source="hunter", confidence=confidence)

    def _set_cache(self, domain: str, result: EmailResult) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO hunter_cache (domain, email, confidence, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (domain, result.email, result.confidence, int(time.time())),
        )
        conn.commit()

    def find(self, domain: str) -> EmailResult:
        if not self._api_key:
            logger.warning("HUNTER_API_KEY not set — skipping Hunter lookup for %s", domain)
            return EmailResult()

        cached = self._get_cached(domain)
        if cached is not None:
            logger.debug("hunter cache hit domain=%s", domain)
            return cached

        try:
            resp = requests.get(
                _HUNTER_API_URL,
                params={"domain": domain, "api_key": self._api_key},
                timeout=10,
            )
        except requests.RequestException as exc:
            logger.warning("hunter request error domain=%s: %s", domain, exc)
            return EmailResult()

        if resp.status_code == 429:
            logger.warning("hunter quota exceeded (429) domain=%s", domain)
            return EmailResult()

        if not resp.ok:
            logger.warning("hunter error status=%d domain=%s", resp.status_code, domain)
            return EmailResult()

        try:
            data = resp.json()
        except ValueError:
            logger.warning("hunter invalid JSON domain=%s", domain)
            return EmailResult()

        # Quota-exceeded is also returned as a 200 with an error payload.
        errors = data.get("errors") or []
        for err in errors:
            if err.get("code") in (429, 413):
                logger.warning("hunter quota error domain=%s: %s", domain, err.get("details", ""))
                return EmailResult()

        emails_list: list[dict[str, object]] = (
            (data.get("data") or {}).get("emails") or []
        )
        if not emails_list:
            result = EmailResult()
        else:
            best = max(emails_list, key=lambda e: e.get("confidence", 0))  # type: ignore[arg-type]
            result = EmailResult(
                email=str(best.get("value", "")),
                source="hunter",
                confidence=float(best.get("confidence", 0)) / 100.0,
            )

        self._set_cache(domain, result)
        return result
