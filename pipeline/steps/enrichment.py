from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from pipeline.base import PipelineStep
from prospect_machine.enrichment import ChainedEmailFinder, EmailResult, ScrapingEmailFinder
from prospect_machine.enrichment.hunter import HunterEmailFinder

logger = logging.getLogger(__name__)

_OUTPUT_FILENAME = "domains_enriched.csv"

# Columns produced by this step (superset of qualification columns).
_ENRICHED_EXTRA_FIELDNAMES = ["email", "email_source", "email_confidence"]


class EnrichmentStep(PipelineStep):
    """Reads domains_qualified.csv and appends email enrichment columns.

    Uses ChainedEmailFinder: scraping first (from contact_emails already in the
    row), Hunter.io as fallback.  Hunter quota errors are silently swallowed —
    the step always completes.

    Output: {run_dir}/EnrichmentStep/domains_enriched.csv
    """

    name = "EnrichmentStep"

    def __init__(self, hunter_cache_db: str = "data/hunter_cache.db") -> None:
        self._hunter_cache_db = Path(hunter_cache_db)

    def _output_path(self, run_dir: Path) -> Path:
        return run_dir / self.name / _OUTPUT_FILENAME

    def _run(self, input_path: Path, run_dir: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            raise FileNotFoundError(f"EnrichmentStep: input not found: {input_path}")

        hunter = HunterEmailFinder(cache_db=self._hunter_cache_db)

        rows = _read_csv(input_path)
        out_fieldnames = _fieldnames(rows) + _ENRICHED_EXTRA_FIELDNAMES

        enriched: list[dict[str, Any]] = []
        for row in rows:
            domain: str = row.get("domain", "")
            emails_raw: str = row.get("contact_emails", "")
            scraped_emails = [e.strip() for e in emails_raw.split("|") if e.strip()]

            finder = ChainedEmailFinder(
                scraping=ScrapingEmailFinder(emails=scraped_emails),
                hunter=hunter,
            )
            result: EmailResult = finder.find(domain)

            enriched.append(
                {
                    **row,
                    "email": result.email,
                    "email_source": result.source,
                    "email_confidence": f"{result.confidence:.2f}" if result.email else "",
                }
            )

        _write_csv(output_path, out_fieldnames, enriched)
        logger.info("EnrichmentStep: wrote %d rows to %s", len(enriched), output_path)
        return output_path


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    return list(rows[0].keys())


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
