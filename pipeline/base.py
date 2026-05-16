from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class PipelineStep(ABC):
    """Abstract base for a single pipeline step.

    Each step reads from an input path, writes its output to a run-scoped
    directory under data/runs/{run_id}/{step_name}/, and can report whether
    it has already been completed so the orchestrator can skip it on resume.
    """

    name: str

    def run(self, input_path: Path, run_dir: Path) -> Path:
        """Execute the step and return the path to its output artifact."""
        output_path = self._output_path(run_dir)
        logger.info("step=%s status=start input=%s output=%s", self.name, input_path, output_path)
        result = self._run(input_path=input_path, run_dir=run_dir, output_path=output_path)
        self._write_done_marker(run_dir)
        logger.info("step=%s status=done output=%s", self.name, result)
        return result

    @abstractmethod
    def _run(self, input_path: Path, run_dir: Path, output_path: Path) -> Path:
        raise NotImplementedError

    def is_done(self, run_dir: Path) -> bool:
        return self._done_marker(run_dir).exists()

    def _output_path(self, run_dir: Path) -> Path:
        return run_dir / self.name

    def _done_marker(self, run_dir: Path) -> Path:
        return run_dir / f".{self.name}.done"

    def _write_done_marker(self, run_dir: Path) -> None:
        marker = self._done_marker(run_dir)
        marker.write_text(json.dumps({"step": self.name}), encoding="utf-8")


class Pipeline:
    """Orchestrates a sequence of PipelineSteps, with optional resume support.

    Usage:
        pipeline = Pipeline(
            steps=[DiscoveryStep(...), QualificationStep(...), ExportStep(...)],
            run_id="2024-padel-01",
            skip_steps={"ExportStep"},
        )
        pipeline.run(input_path=Path("data/domains_raw.csv"))
    """

    def __init__(
        self,
        steps: list[PipelineStep],
        run_id: str,
        runs_root: Path = Path("data/runs"),
        skip_steps: set[str] | None = None,
        resume: bool = False,
    ) -> None:
        self.steps = steps
        self.run_id = run_id
        self.run_dir = runs_root / run_id
        self.skip_steps = skip_steps or set()
        self.resume = resume

    def run(self, input_path: Path) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        current_path = input_path

        for step in self.steps:
            if step.name in self.skip_steps:
                logger.info("step=%s status=skipped (--skip-step)", step.name)
                # Still update current_path to what the step *would* have produced,
                # so the next step receives the correct expected input.
                current_path = step._output_path(self.run_dir)
                continue

            if self.resume and step.is_done(self.run_dir):
                logger.info("step=%s status=skipped (already done)", step.name)
                current_path = step._output_path(self.run_dir)
                continue

            current_path = step.run(input_path=current_path, run_dir=self.run_dir)

        return current_path
