from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from config import DEFAULT_DELAY, DEFAULT_QUALIFY_MODE
from io_helpers import qualified_rows
from pipeline.base import PipelineStep
from prospect_machine.qualification.runner import DomainSignals, run_qualification, signals_to_row
from qualify import qualify_domains

logger = logging.getLogger(__name__)

# Columns added by QualificationStep on top of the standard qualify output.
_EXTENDED_FIELDNAMES = [
    "score",
    "domain",
    "cms",
    "estimated_pages",
    "hard_blocked",
    "size_score",
    "rejected",
    "rejection_reason",
    "rejection_confidence",
    "has_blog",
    "has_dated_content",
    "dated_urls_count",
    "contact_found",
    "social_links",
    "issues",
    "title",
    "notes",
    "sitemap_available",
    "source_query",
    "source_provider",
    "first_seen",
    "is_editorial_candidate",
    "is_app_like",
    "app_signal",
    "is_docs_like",
    "docs_signal",
    "is_marketplace_like",
    "marketplace_signal",
    "refresh_repair_fit",
    "site_type_note",
    "nav_link_ratio",
    "content_link_ratio",
    "editorial_word_count",
    # --- Extended signals (pipeline-only, not written to data/domains_scored.csv) ---
    "has_contact_page",
    "contact_page_url",
    "contact_emails",
    "contact_names",
    "last_post_date",
    "last_post_source",
]

_WEBUI_OUTPUT = "data/domains_scored.csv"
_OUTPUT_FILENAME = "domains_qualified.csv"


class QualificationStep(PipelineStep):
    """Calls qualify_domains() then enriches each domain with async qualification signals.

    Two outputs are produced:
    - data/domains_scored.csv                         → unchanged web UI output
    - {run_dir}/QualificationStep/domains_qualified.csv → enriched pipeline output
      (adds has_contact_page, contact_emails, last_post_date, last_post_source)
    """

    name = "QualificationStep"

    def __init__(
        self,
        delay: float = DEFAULT_DELAY,
        mode: str = DEFAULT_QUALIFY_MODE,
        check_sitemap: bool | None = None,
        max_html_bytes: int | None = None,
        max_total_seconds_per_domain: float | None = None,
        max_total_requests_per_domain: int | None = None,
        max_sitemap_urls: int | None = None,
        max_nested_sitemaps: int | None = None,
        webui_output: str = _WEBUI_OUTPUT,
        qualification_concurrency: int = 10,
        qualification_timeout: int = 10,
        lang: str = "fr",
    ) -> None:
        self.delay = delay
        self.mode = mode
        self.check_sitemap = check_sitemap
        self.max_html_bytes = max_html_bytes
        self.max_total_seconds_per_domain = max_total_seconds_per_domain
        self.max_total_requests_per_domain = max_total_requests_per_domain
        self.max_sitemap_urls = max_sitemap_urls
        self.max_nested_sitemaps = max_nested_sitemaps
        self.webui_output = webui_output
        self.qualification_concurrency = qualification_concurrency
        self.qualification_timeout = qualification_timeout
        self.lang = lang

    def _output_path(self, run_dir: Path) -> Path:
        return run_dir / self.name / _OUTPUT_FILENAME

    def _run(self, input_path: Path, run_dir: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "QualificationStep: qualifying from %s → web_ui=%s pipeline=%s",
            input_path,
            self.webui_output,
            output_path,
        )

        # 1. Run existing qualify pipeline → writes data/domains_scored.csv (web UI contract).
        qualified = qualify_domains(
            input_csv=str(input_path),
            output=self.webui_output,
            delay=self.delay,
            mode=self.mode,
            check_sitemap=self.check_sitemap,
            max_html_bytes=self.max_html_bytes,
            max_total_seconds_per_domain=self.max_total_seconds_per_domain,
            max_total_requests_per_domain=self.max_total_requests_per_domain,
            max_sitemap_urls=self.max_sitemap_urls,
            max_nested_sitemaps=self.max_nested_sitemaps,
        )

        # 2. Async qualification: contact page, editorial activity, site size.
        domains = [q.domain for q in qualified]
        logger.info(
            "QualificationStep: running async qualification on %d domains "
            "(concurrency=%d timeout=%d)",
            len(domains),
            self.qualification_concurrency,
            self.qualification_timeout,
        )
        signals_list = run_qualification(
            domains=domains,
            concurrency=self.qualification_concurrency,
            timeout=self.qualification_timeout,
            lang=self.lang,
        )
        signals_by_domain: dict[str, DomainSignals] = {s.domain: s for s in signals_list}

        # 3. Merge base qualify rows with extended signals → pipeline CSV.
        base_rows = qualified_rows(qualified)
        extended_rows: list[dict[str, Any]] = []
        for row in base_rows:
            domain = row["domain"]
            sig = signals_by_domain.get(domain)
            ext = _signals_to_extended(sig) if sig else _empty_extended()
            extended_rows.append({**row, **ext})

        _write_extended_csv(output_path, extended_rows)
        logger.info("QualificationStep: wrote %d rows to %s", len(extended_rows), output_path)

        return output_path


def _signals_to_extended(sig: DomainSignals) -> dict[str, Any]:
    return {
        "has_contact_page": "yes" if sig.has_contact_page else "",
        "contact_page_url": sig.contact_page_url,
        "contact_emails": " | ".join(sig.contact_emails),
        "contact_names": " | ".join(sig.contact_names),
        "last_post_date": sig.last_post_date.isoformat() if sig.last_post_date else "",
        "last_post_source": sig.last_post_source,
    }


def _empty_extended() -> dict[str, Any]:
    return {
        "has_contact_page": "",
        "contact_page_url": "",
        "contact_emails": "",
        "contact_names": "",
        "last_post_date": "",
        "last_post_source": "",
    }


def _merge_extended(base_row: dict[str, Any], extended: dict[str, Any]) -> dict[str, Any]:
    return {**base_row, **extended}


def _write_extended_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_EXTENDED_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
