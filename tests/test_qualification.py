from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prospect_machine.qualification.contact import ContactResult, _parse_contact_page
from prospect_machine.qualification.editorial import (
    EditorialResult,
    _extract_date_from_rss,
    _extract_lastmod_from_sitemap_xml,
    _parse_iso_date,
    _parse_rfc_or_iso_date,
)
from prospect_machine.qualification.size import SizeResult, _count_sitemap_urls
from prospect_machine.qualification.runner import DomainSignals, run_qualification


# ---------------------------------------------------------------------------
# contact.py
# ---------------------------------------------------------------------------

class TestParseContactPage:
    def test_extracts_mailto_email(self) -> None:
        html = '<html><body><a href="mailto:hello@example.com">Contact</a></body></html>'
        result = _parse_contact_page(html, "https://example.com/contact", "fr_core_news_sm")
        assert "hello@example.com" in result.emails
        assert result.has_contact_page is True

    def test_extracts_inline_email(self) -> None:
        html = "<html><body><p>Écrivez-nous à contact@monsite.fr pour plus d'infos.</p></body></html>"
        result = _parse_contact_page(html, "https://monsite.fr/contact", "fr_core_news_sm")
        assert "contact@monsite.fr" in result.emails

    def test_deduplicates_emails(self) -> None:
        html = (
            '<html><body>'
            '<a href="mailto:hi@x.com">hi</a>'
            '<p>hi@x.com</p>'
            '</body></html>'
        )
        result = _parse_contact_page(html, "https://x.com/contact", "en_core_web_sm")
        assert result.emails.count("hi@x.com") == 1

    def test_no_email_returns_empty_list(self) -> None:
        html = "<html><body><p>Aucune adresse ici.</p></body></html>"
        result = _parse_contact_page(html, "https://empty.fr/contact", "fr_core_news_sm")
        assert result.emails == []
        assert result.has_contact_page is True


class TestFetchContactSignals:
    def test_returns_empty_on_all_404(self) -> None:
        """All contact paths return 404 → ContactResult with has_contact_page=False."""

        async def _run() -> ContactResult:
            mock_resp = MagicMock()
            mock_resp.status = 404

            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=mock_resp)
            cm.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=cm)

            from prospect_machine.qualification.contact import fetch_contact_signals
            return await fetch_contact_signals("no-contact.fr", mock_session)

        result = asyncio.run(_run())
        assert result.has_contact_page is False
        assert result.emails == []

    def test_returns_result_on_200(self) -> None:
        """First 200 response → has_contact_page=True."""

        async def _run() -> ContactResult:
            html = '<html><body><a href="mailto:info@site.fr">email</a></body></html>'

            # aiohttp uses an async context manager: session.get(...) returns
            # the context manager, whose __aenter__ returns the response object.
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.url = "https://site.fr/contact"
            mock_resp.text = AsyncMock(return_value=html)

            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=mock_resp)
            cm.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=cm)

            from prospect_machine.qualification.contact import fetch_contact_signals
            return await fetch_contact_signals("site.fr", mock_session)

        result = asyncio.run(_run())
        assert result.has_contact_page is True
        assert "info@site.fr" in result.emails


# ---------------------------------------------------------------------------
# editorial.py
# ---------------------------------------------------------------------------

class TestParseIsoDates:
    def test_standard_iso(self) -> None:
        assert _parse_iso_date("2024-03-15") == date(2024, 3, 15)

    def test_iso_embedded_in_string(self) -> None:
        assert _parse_iso_date("Updated on 2023-11-01T00:00:00Z") == date(2023, 11, 1)

    def test_invalid_returns_none(self) -> None:
        assert _parse_iso_date("not-a-date") is None

    def test_rfc_date(self) -> None:
        assert _parse_rfc_or_iso_date("Mon, 15 Mar 2024 10:00:00 +0000") == date(2024, 3, 15)


class TestSitemapLastmod:
    def test_extracts_most_recent_lastmod(self) -> None:
        xml = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://x.fr/a</loc><lastmod>2023-01-01</lastmod></url>
          <url><loc>https://x.fr/b</loc><lastmod>2024-06-15</lastmod></url>
          <url><loc>https://x.fr/c</loc><lastmod>2022-12-31</lastmod></url>
        </urlset>"""
        result = _extract_lastmod_from_sitemap_xml(xml)
        assert result == date(2024, 6, 15)

    def test_no_lastmod_returns_none(self) -> None:
        xml = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://x.fr/a</loc></url>
        </urlset>"""
        assert _extract_lastmod_from_sitemap_xml(xml) is None

    def test_invalid_xml_returns_none(self) -> None:
        assert _extract_lastmod_from_sitemap_xml("not xml at all<<<") is None


class TestRSSDateExtraction:
    def test_rss_pubdate(self) -> None:
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item><title>Post 1</title><pubDate>Mon, 10 Jun 2024 08:00:00 +0000</pubDate></item>
          <item><title>Post 2</title><pubDate>Tue, 01 Jan 2023 00:00:00 +0000</pubDate></item>
        </channel></rss>"""
        result = _extract_date_from_rss(xml)
        assert result == date(2024, 6, 10)

    def test_atom_updated(self) -> None:
        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry><updated>2024-05-20T12:00:00Z</updated></entry>
          <entry><updated>2023-01-01T00:00:00Z</updated></entry>
        </feed>"""
        result = _extract_date_from_rss(xml)
        assert result == date(2024, 5, 20)


# ---------------------------------------------------------------------------
# size.py
# ---------------------------------------------------------------------------

class TestCountSitemapUrls:
    def test_counts_loc_tags(self) -> None:
        xml = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://x.fr/a</loc></url>
          <url><loc>https://x.fr/b</loc></url>
          <url><loc>https://x.fr/c</loc></url>
        </urlset>"""

        async def _run() -> int:
            mock_session = MagicMock()
            return await _count_sitemap_urls(xml, "x.fr", mock_session, 8)

        assert asyncio.run(_run()) == 3

    def test_invalid_xml_returns_zero(self) -> None:
        async def _run() -> int:
            mock_session = MagicMock()
            return await _count_sitemap_urls("<<bad xml>>", "x.fr", mock_session, 8)

        assert asyncio.run(_run()) == 0


# ---------------------------------------------------------------------------
# runner.py — integration with mocked network
# ---------------------------------------------------------------------------

class TestRunQualification:
    def test_returns_one_result_per_domain(self) -> None:
        """run_qualification returns exactly one DomainSignals per input domain."""
        with (
            patch(
                "prospect_machine.qualification.runner.fetch_contact_signals",
                new_callable=AsyncMock,
                return_value=ContactResult(),
            ),
            patch(
                "prospect_machine.qualification.runner.fetch_editorial_signals",
                new_callable=AsyncMock,
                return_value=EditorialResult(),
            ),
            patch(
                "prospect_machine.qualification.runner.fetch_size_signals",
                new_callable=AsyncMock,
                return_value=SizeResult(),
            ),
        ):
            results = run_qualification(["alpha.fr", "beta.fr"], concurrency=2, timeout=5)

        assert len(results) == 2
        assert {r.domain for r in results} == {"alpha.fr", "beta.fr"}

    def test_error_in_one_domain_does_not_crash_others(self) -> None:
        """An exception on one domain is caught; other domains still return results."""

        async def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("network error")

        with (
            patch(
                "prospect_machine.qualification.runner.fetch_contact_signals",
                new_callable=AsyncMock,
                side_effect=boom,
            ),
            patch(
                "prospect_machine.qualification.runner.fetch_editorial_signals",
                new_callable=AsyncMock,
                return_value=EditorialResult(),
            ),
            patch(
                "prospect_machine.qualification.runner.fetch_size_signals",
                new_callable=AsyncMock,
                return_value=SizeResult(),
            ),
        ):
            results = run_qualification(["ok.fr", "fail.fr"], concurrency=2, timeout=5)

        assert len(results) == 2

    def test_contact_signals_merged(self) -> None:
        """Contact signals from the async module end up in DomainSignals."""
        contact = ContactResult(
            has_contact_page=True,
            contact_page_url="https://site.fr/contact",
            emails=["admin@site.fr"],
            names=["Jean Dupont"],
        )
        with (
            patch(
                "prospect_machine.qualification.runner.fetch_contact_signals",
                new_callable=AsyncMock,
                return_value=contact,
            ),
            patch(
                "prospect_machine.qualification.runner.fetch_editorial_signals",
                new_callable=AsyncMock,
                return_value=EditorialResult(last_post_date=date(2024, 3, 1), source="sitemap"),
            ),
            patch(
                "prospect_machine.qualification.runner.fetch_size_signals",
                new_callable=AsyncMock,
                return_value=SizeResult(estimated_size=120, source="sitemap"),
            ),
        ):
            results = run_qualification(["site.fr"], concurrency=1, timeout=5)

        r = results[0]
        assert r.has_contact_page is True
        assert "admin@site.fr" in r.contact_emails
        assert "Jean Dupont" in r.contact_names
        assert r.last_post_date == date(2024, 3, 1)
        assert r.last_post_source == "sitemap"
        assert r.estimated_size == 120
