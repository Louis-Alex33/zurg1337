from __future__ import annotations

import logging
from pathlib import Path

from config import DEFAULT_DELAY, DEFAULT_DISCOVER_PROVIDER
from discover import discover_domains, import_domains_from_file
from pipeline.base import PipelineStep

logger = logging.getLogger(__name__)

# Output artifact: CSV file written by discover_domains()
_OUTPUT_FILENAME = "domains_raw.csv"


class DiscoveryStep(PipelineStep):
    """Wraps discover_domains() (or import_domains_from_file()) as a pipeline step.

    Output: {run_dir}/DiscoveryStep/domains_raw.csv
    The existing data/domains_raw.csv default path (used by the web UI) is
    untouched — this step writes into the run-scoped directory only.
    """

    name = "DiscoveryStep"

    def __init__(
        self,
        niches: list[str] | None = None,
        domains_file: str | None = None,
        limit: int = 100,
        provider_name: str = DEFAULT_DISCOVER_PROVIDER,
        delay: float = DEFAULT_DELAY,
        query_mode: str = "auto",
    ) -> None:
        if not niches and not domains_file:
            raise ValueError("DiscoveryStep requires either 'niches' or 'domains_file'.")
        self.niches = niches or []
        self.domains_file = domains_file
        self.limit = limit
        self.provider_name = provider_name
        self.delay = delay
        self.query_mode = query_mode

    def _output_path(self, run_dir: Path) -> Path:
        return run_dir / self.name / _OUTPUT_FILENAME

    def _run(self, input_path: Path, run_dir: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.domains_file:
            logger.info("DiscoveryStep: importing from file %s", self.domains_file)
            import_domains_from_file(
                input_path=self.domains_file,
                output=str(output_path),
            )
        else:
            logger.info(
                "DiscoveryStep: discovering niches=%s limit=%d provider=%s",
                self.niches,
                self.limit,
                self.provider_name,
            )
            discover_domains(
                niches=self.niches,
                limit=self.limit,
                output=str(output_path),
                provider_name=self.provider_name,
                delay=self.delay,
                query_mode=self.query_mode,
            )

        return output_path
