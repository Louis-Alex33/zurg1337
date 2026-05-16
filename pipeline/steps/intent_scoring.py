from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from pipeline.base import PipelineStep
from prospect_machine.intent.runner import IntentSignals, load_config, run_intent_scoring

logger = logging.getLogger(__name__)

_OUTPUT_FILENAME = "domains_intent_scored.csv"
_DEFAULT_CONFIG = Path("config/intent_scoring.yaml")

_INTENT_EXTRA_FIELDNAMES = [
    "intent_score",
    "last_post_age_days",
    "wayback_trend",
    "wayback_quarters",
    "whois_domain_age_years",
    "whois_stagnation_ratio",
    "ga_has_ua_tag",
    "ga_has_ga4_tag",
]


class IntentScoringStep(PipelineStep):
    """Reads domains_enriched.csv, computes intent signals, writes domains_intent_scored.csv.

    Output: {run_dir}/IntentScoringStep/domains_intent_scored.csv
    """

    name = "IntentScoringStep"

    def __init__(
        self,
        config_path: Path = _DEFAULT_CONFIG,
        concurrency: int = 5,
    ) -> None:
        self._config_path = config_path
        self._concurrency = concurrency

    def _output_path(self, run_dir: Path) -> Path:
        return run_dir / self.name / _OUTPUT_FILENAME

    def _run(self, input_path: Path, run_dir: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            raise FileNotFoundError(f"IntentScoringStep: input not found: {input_path}")

        config = load_config(self._config_path)
        rows = _read_csv(input_path)

        logger.info(
            "IntentScoringStep: scoring %d domains (concurrency=%d)",
            len(rows),
            self._concurrency,
        )

        signals_list = run_intent_scoring(rows, config, concurrency=self._concurrency)
        signals_by_domain = {s.domain: s for s in signals_list}

        out_fieldnames = _fieldnames(rows) + _INTENT_EXTRA_FIELDNAMES
        out_rows: list[dict[str, Any]] = []
        for row in rows:
            domain = row.get("domain", "")
            sig = signals_by_domain.get(domain)
            out_rows.append({**row, **_signals_to_dict(sig)})

        _write_csv(output_path, out_fieldnames, out_rows)
        logger.info("IntentScoringStep: wrote %d rows to %s", len(out_rows), output_path)
        return output_path


def _signals_to_dict(sig: IntentSignals | None) -> dict[str, Any]:
    if sig is None:
        return {k: "" for k in _INTENT_EXTRA_FIELDNAMES}
    return {
        "intent_score": f"{sig.intent_score:.4f}",
        "last_post_age_days": sig.last_post_age_days if sig.last_post_age_days is not None else "",
        "wayback_trend": f"{sig.wayback_trend:.4f}" if sig.wayback_trend is not None else "",
        "wayback_quarters": "|".join(str(q) for q in sig.wayback_quarters),
        "whois_domain_age_years": f"{sig.whois_domain_age_years:.2f}" if sig.whois_domain_age_years is not None else "",
        "whois_stagnation_ratio": f"{sig.whois_stagnation_ratio:.2f}" if sig.whois_stagnation_ratio is not None else "",
        "ga_has_ua_tag": "yes" if sig.ga_has_ua_tag else "",
        "ga_has_ga4_tag": "yes" if sig.ga_has_ga4_tag else "",
    }


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    return list(rows[0].keys()) if rows else []


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
