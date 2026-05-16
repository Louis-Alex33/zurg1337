from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from config import DEFAULT_DELAY, DEFAULT_QUALIFY_MODE
from io_helpers import qualified_rows, read_discovery_csv
from pipeline.base import PipelineStep
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
    """Calls qualify_domains() then appends extended signals to each domain.

    Two outputs are produced:
    - data/domains_scored.csv          → identical to what qualify_domains() always wrote,
                                          kept for the web UI (no change to that contract).
    - {run_dir}/QualificationStep/domains_qualified.csv
                                       → same rows + extra columns for the pipeline
                                          (has_contact_page, contact_emails, last_post_date, …).

    The extended signals in this step are placeholders (empty strings / False).
    They will be populated by QualificationStep in Étape 2 once the async
    qualification module exists. The schema is fixed here so downstream steps
    can rely on it from Étape 1 onward.
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

        # 1. Run the existing qualify pipeline — writes data/domains_scored.csv
        #    with the unchanged signature the web UI depends on.
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

        # 2. Build extended rows: start from the standard qualified_rows() dict
        #    and append the new columns with empty/default values.
        #    Étape 2 will replace _stub_extended_signals() with real async fetches.
        base_rows = qualified_rows(qualified)
        extended_rows = [_merge_extended(row, _stub_extended_signals()) for row in base_rows]

        _write_extended_csv(output_path, extended_rows)
        logger.info("QualificationStep: wrote %d rows to %s", len(extended_rows), output_path)

        return output_path


def _stub_extended_signals() -> dict[str, Any]:
    """Placeholder extended signals — replaced by real data in Étape 2."""
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
