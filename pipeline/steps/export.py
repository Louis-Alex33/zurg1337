from __future__ import annotations

import csv
import logging
import shutil
from pathlib import Path

from pipeline.base import PipelineStep

logger = logging.getLogger(__name__)

_OUTPUT_FILENAME = "domains_final.csv"


class ExportStep(PipelineStep):
    """Copies the previous step's CSV output into the run directory as the final artifact.

    Optionally also copies to a user-specified destination path
    (e.g. data/domains_pipeline_output.csv) for easy access outside the run dir.
    """

    name = "ExportStep"

    def __init__(self, final_output: str | None = None) -> None:
        # Optional path outside the run directory to copy the final file to.
        self.final_output = final_output

    def _output_path(self, run_dir: Path) -> Path:
        return run_dir / self.name / _OUTPUT_FILENAME

    def _run(self, input_path: Path, run_dir: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            raise FileNotFoundError(f"ExportStep: input not found: {input_path}")

        shutil.copy2(input_path, output_path)
        logger.info("ExportStep: copied %s → %s", input_path, output_path)

        row_count = _count_data_rows(output_path)
        logger.info("ExportStep: final export contains %d data rows", row_count)

        if self.final_output:
            dest = Path(self.final_output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, dest)
            logger.info("ExportStep: also copied to user destination %s", dest)

        return output_path


def _count_data_rows(path: Path) -> int:
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return sum(1 for _ in csv.reader(f)) - 1  # subtract header
    except Exception:
        return -1
