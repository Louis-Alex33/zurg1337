from __future__ import annotations

import csv
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prospect_machine.enrichment.base import EmailFinder, EmailResult
from prospect_machine.enrichment.scraping import ScrapingEmailFinder
from prospect_machine.enrichment.hunter import HunterEmailFinder, _CACHE_TTL_SECONDS
from prospect_machine.enrichment.chained import ChainedEmailFinder


# ---------------------------------------------------------------------------
# EmailResult
# ---------------------------------------------------------------------------

class TestEmailResult:
    def test_defaults(self) -> None:
        r = EmailResult()
        assert r.email == ""
        assert r.source == ""
        assert r.confidence == 0.0

    def test_filled(self) -> None:
        r = EmailResult(email="a@b.com", source="scrape", confidence=0.9)
        assert r.email == "a@b.com"


# ---------------------------------------------------------------------------
# EmailFinder ABC
# ---------------------------------------------------------------------------

class TestEmailFinderABC:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            EmailFinder()  # type: ignore[abstract]

    def test_concrete_subclass_works(self) -> None:
        class Concrete(EmailFinder):
            def find(self, domain: str) -> EmailResult:
                return EmailResult(email="x@y.com", source="test", confidence=1.0)

        assert Concrete().find("y.com").email == "x@y.com"


# ---------------------------------------------------------------------------
# ScrapingEmailFinder
# ---------------------------------------------------------------------------

class TestScrapingEmailFinder:
    def test_returns_first_email(self) -> None:
        finder = ScrapingEmailFinder(emails=["first@example.com", "second@example.com"])
        result = finder.find("example.com")
        assert result.email == "first@example.com"
        assert result.source == "scrape"
        assert result.confidence > 0

    def test_empty_list_returns_empty_result(self) -> None:
        finder = ScrapingEmailFinder(emails=[])
        result = finder.find("example.com")
        assert result.email == ""
        assert result.source == ""

    def test_none_emails_returns_empty_result(self) -> None:
        finder = ScrapingEmailFinder()
        result = finder.find("no-email.com")
        assert result.email == ""

    def test_domain_argument_ignored(self) -> None:
        # Domain is unused; the emails come from the injected list.
        finder = ScrapingEmailFinder(emails=["info@site.fr"])
        assert finder.find("other-domain.fr").email == "info@site.fr"


# ---------------------------------------------------------------------------
# HunterEmailFinder
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_cache(tmp_path: Path) -> Path:
    return tmp_path / "hunter_cache.db"


class TestHunterEmailFinderNoKey:
    def test_returns_empty_when_no_api_key(self, tmp_cache: Path) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HUNTER_API_KEY", None)
            finder = HunterEmailFinder(cache_db=tmp_cache)
            result = finder.find("example.com")
        assert result.email == ""
        assert result.source == ""

    def test_logs_warning_when_no_api_key(self, tmp_cache: Path, caplog: pytest.LogCaptureFixture) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HUNTER_API_KEY", None)
            import logging
            with caplog.at_level(logging.WARNING, logger="prospect_machine.enrichment.hunter"):
                finder = HunterEmailFinder(cache_db=tmp_cache)
                finder.find("example.com")
        assert any("HUNTER_API_KEY" in rec.message for rec in caplog.records)


class TestHunterEmailFinderCache:
    def _make_finder(self, tmp_cache: Path) -> HunterEmailFinder:
        finder = HunterEmailFinder(cache_db=tmp_cache)
        finder._api_key = "fake-key"
        return finder

    def test_cache_hit_skips_network(self, tmp_cache: Path) -> None:
        finder = self._make_finder(tmp_cache)
        # Pre-populate cache.
        finder._get_conn().execute(
            "INSERT INTO hunter_cache (domain, email, confidence, fetched_at) VALUES (?,?,?,?)",
            ("cached.com", "cached@cached.com", 0.85, int(time.time())),
        )
        finder._get_conn().commit()

        with patch("prospect_machine.enrichment.hunter.requests.get") as mock_get:
            result = finder.find("cached.com")
            mock_get.assert_not_called()

        assert result.email == "cached@cached.com"
        assert result.source == "hunter"
        assert result.confidence == pytest.approx(0.85)

    def test_expired_cache_triggers_network_call(self, tmp_cache: Path) -> None:
        finder = self._make_finder(tmp_cache)
        old_ts = int(time.time()) - _CACHE_TTL_SECONDS - 1
        finder._get_conn().execute(
            "INSERT INTO hunter_cache (domain, email, confidence, fetched_at) VALUES (?,?,?,?)",
            ("stale.com", "old@stale.com", 0.5, old_ts),
        )
        finder._get_conn().commit()

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"emails": [{"value": "new@stale.com", "confidence": 72}]}
        }

        with patch("prospect_machine.enrichment.hunter.requests.get", return_value=mock_resp):
            result = finder.find("stale.com")

        assert result.email == "new@stale.com"

    def test_result_is_cached_after_api_call(self, tmp_cache: Path) -> None:
        finder = self._make_finder(tmp_cache)
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"emails": [{"value": "hi@domain.com", "confidence": 80}]}
        }

        with patch("prospect_machine.enrichment.hunter.requests.get", return_value=mock_resp) as mock_get:
            finder.find("domain.com")
            finder.find("domain.com")  # second call should hit cache

        assert mock_get.call_count == 1

    def test_empty_emails_list_cached_as_empty(self, tmp_cache: Path) -> None:
        finder = self._make_finder(tmp_cache)
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"emails": []}}

        with patch("prospect_machine.enrichment.hunter.requests.get", return_value=mock_resp):
            result = finder.find("noemail.com")

        assert result.email == ""


class TestHunterEmailFinderQuota:
    def _make_finder(self, tmp_cache: Path) -> HunterEmailFinder:
        finder = HunterEmailFinder(cache_db=tmp_cache)
        finder._api_key = "fake-key"
        return finder

    def test_429_returns_empty_does_not_raise(self, tmp_cache: Path) -> None:
        finder = self._make_finder(tmp_cache)
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 429

        with patch("prospect_machine.enrichment.hunter.requests.get", return_value=mock_resp):
            result = finder.find("busy.com")

        assert result.email == ""

    def test_quota_error_in_200_payload_returns_empty(self, tmp_cache: Path) -> None:
        finder = self._make_finder(tmp_cache)
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "errors": [{"code": 429, "details": "You have reached your requests limit for the month"}]
        }

        with patch("prospect_machine.enrichment.hunter.requests.get", return_value=mock_resp):
            result = finder.find("quota.com")

        assert result.email == ""

    def test_network_error_returns_empty(self, tmp_cache: Path) -> None:
        import requests as req_lib
        finder = self._make_finder(tmp_cache)

        with patch(
            "prospect_machine.enrichment.hunter.requests.get",
            side_effect=req_lib.RequestException("timeout"),
        ):
            result = finder.find("unreachable.com")

        assert result.email == ""


# ---------------------------------------------------------------------------
# ChainedEmailFinder
# ---------------------------------------------------------------------------

class TestChainedEmailFinder:
    def test_uses_scraping_when_email_present(self) -> None:
        scraping = ScrapingEmailFinder(emails=["local@site.fr"])
        hunter = HunterEmailFinder.__new__(HunterEmailFinder)

        finder = ChainedEmailFinder(scraping=scraping, hunter=hunter)
        result = finder.find("site.fr")

        assert result.email == "local@site.fr"
        assert result.source == "scrape"

    def test_falls_back_to_hunter_when_scraping_empty(self, tmp_cache: Path) -> None:
        scraping = ScrapingEmailFinder(emails=[])

        hunter = HunterEmailFinder(cache_db=tmp_cache)
        hunter._api_key = "fake-key"
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"emails": [{"value": "found@hunter.com", "confidence": 90}]}
        }

        with patch("prospect_machine.enrichment.hunter.requests.get", return_value=mock_resp):
            finder = ChainedEmailFinder(scraping=scraping, hunter=hunter)
            result = finder.find("hunter.com")

        assert result.email == "found@hunter.com"
        assert result.source == "hunter"

    def test_returns_empty_when_both_miss(self, tmp_cache: Path) -> None:
        scraping = ScrapingEmailFinder(emails=[])
        hunter = HunterEmailFinder(cache_db=tmp_cache)
        hunter._api_key = ""

        finder = ChainedEmailFinder(scraping=scraping, hunter=hunter)
        result = finder.find("nothing.com")

        assert result.email == ""

    def test_default_construction_does_not_raise(self) -> None:
        # Should not raise even if HUNTER_API_KEY is unset.
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HUNTER_API_KEY", None)
            finder = ChainedEmailFinder()
            result = finder.find("any.com")
        assert isinstance(result, EmailResult)


# ---------------------------------------------------------------------------
# EnrichmentStep
# ---------------------------------------------------------------------------

class TestEnrichmentStep:
    def _write_qualified_csv(self, path: Path, rows: list[dict[str, str]]) -> None:
        if not rows:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_adds_email_columns(self, tmp_path: Path) -> None:
        from pipeline.steps.enrichment import EnrichmentStep

        input_csv = tmp_path / "QualificationStep" / "domains_qualified.csv"
        rows = [
            {"domain": "alpha.fr", "contact_emails": "info@alpha.fr | other@alpha.fr", "score": "42"},
            {"domain": "beta.fr", "contact_emails": "", "score": "10"},
        ]
        self._write_qualified_csv(input_csv, rows)

        run_dir = tmp_path / "run01"
        step = EnrichmentStep(hunter_cache_db=str(tmp_path / "cache.db"))

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HUNTER_API_KEY", None)
            output = step.run(input_path=input_csv, run_dir=run_dir)

        assert output.exists()
        with output.open(encoding="utf-8", newline="") as fh:
            result_rows = list(csv.DictReader(fh))

        assert len(result_rows) == 2

        alpha = next(r for r in result_rows if r["domain"] == "alpha.fr")
        assert alpha["email"] == "info@alpha.fr"
        assert alpha["email_source"] == "scrape"
        assert alpha["email_confidence"] != ""

        beta = next(r for r in result_rows if r["domain"] == "beta.fr")
        assert beta["email"] == ""
        assert beta["email_confidence"] == ""

    def test_raises_on_missing_input(self, tmp_path: Path) -> None:
        from pipeline.steps.enrichment import EnrichmentStep

        step = EnrichmentStep(hunter_cache_db=str(tmp_path / "cache.db"))
        with pytest.raises(FileNotFoundError):
            step.run(input_path=tmp_path / "nonexistent.csv", run_dir=tmp_path / "run")

    def test_writes_done_marker(self, tmp_path: Path) -> None:
        from pipeline.steps.enrichment import EnrichmentStep

        input_csv = tmp_path / "qualified.csv"
        rows = [{"domain": "test.fr", "contact_emails": "x@test.fr", "score": "5"}]
        self._write_qualified_csv(input_csv, rows)

        run_dir = tmp_path / "runX"
        step = EnrichmentStep(hunter_cache_db=str(tmp_path / "cache.db"))

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HUNTER_API_KEY", None)
            step.run(input_path=input_csv, run_dir=run_dir)

        assert (run_dir / ".EnrichmentStep.done").exists()

    def test_hunter_called_when_scraping_misses(self, tmp_path: Path) -> None:
        from pipeline.steps.enrichment import EnrichmentStep

        input_csv = tmp_path / "qualified.csv"
        rows = [{"domain": "needs-hunter.fr", "contact_emails": "", "score": "7"}]
        self._write_qualified_csv(input_csv, rows)

        run_dir = tmp_path / "run_hunter"
        cache_db = tmp_path / "cache.db"
        step = EnrichmentStep(hunter_cache_db=str(cache_db))

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"emails": [{"value": "boss@needs-hunter.fr", "confidence": 75}]}
        }

        with patch.dict(os.environ, {"HUNTER_API_KEY": "test-key"}):
            with patch("prospect_machine.enrichment.hunter.requests.get", return_value=mock_resp):
                output = step.run(input_path=input_csv, run_dir=run_dir)

        with output.open(encoding="utf-8", newline="") as fh:
            result_rows = list(csv.DictReader(fh))

        assert result_rows[0]["email"] == "boss@needs-hunter.fr"
        assert result_rows[0]["email_source"] == "hunter"
