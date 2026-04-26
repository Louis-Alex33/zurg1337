from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from io_helpers import write_csv_rows, write_json_file
from utils import CLIError


def compare_audit_reports(
    old_report_path: str,
    new_report_path: str,
    output_csv: str | None = None,
    output_json: str | None = None,
) -> dict[str, Any]:
    old_report = read_report(old_report_path)
    new_report = read_report(new_report_path)
    old_pages = pages_by_url(old_report)
    new_pages = pages_by_url(new_report)
    old_urls = set(old_pages)
    new_urls = set(new_pages)
    common_urls = sorted(old_urls & new_urls)

    improved_pages = []
    regressed_pages = []
    unchanged_pages = []
    for url in common_urls:
        old_score = int(old_pages[url].get("page_health_score") or 0)
        new_score = int(new_pages[url].get("page_health_score") or 0)
        delta = new_score - old_score
        row = {
            "url": url,
            "old_page_health_score": old_score,
            "new_page_health_score": new_score,
            "delta": delta,
            "old_issues": " | ".join(str(item) for item in old_pages[url].get("issues") or []),
            "new_issues": " | ".join(str(item) for item in new_pages[url].get("issues") or []),
        }
        if delta >= 5:
            improved_pages.append(row)
        elif delta <= -5:
            regressed_pages.append(row)
        else:
            unchanged_pages.append(row)

    old_summary = old_report.get("summary") or {}
    new_summary = new_report.get("summary") or {}
    comparison = {
        "domain": new_report.get("domain") or old_report.get("domain") or "",
        "old_audited_at": old_report.get("audited_at") or "",
        "new_audited_at": new_report.get("audited_at") or "",
        "old_observed_health_score": int(old_report.get("observed_health_score") or 0),
        "new_observed_health_score": int(new_report.get("observed_health_score") or 0),
        "observed_health_delta": int(new_report.get("observed_health_score") or 0)
        - int(old_report.get("observed_health_score") or 0),
        "old_pages_crawled": int(old_report.get("pages_crawled") or 0),
        "new_pages_crawled": int(new_report.get("pages_crawled") or 0),
        "added_pages": sorted(new_urls - old_urls),
        "removed_pages": sorted(old_urls - new_urls),
        "improved_pages": improved_pages,
        "regressed_pages": regressed_pages,
        "unchanged_pages_count": len(unchanged_pages),
        "summary_deltas": compare_summary_values(old_summary, new_summary),
    }

    if output_json:
        write_json_file(output_json, comparison)
    if output_csv:
        rows = [
            {
                "url": item["url"],
                "old_page_health_score": item["old_page_health_score"],
                "new_page_health_score": item["new_page_health_score"],
                "delta": item["delta"],
                "status": "improved" if item["delta"] > 0 else "regressed",
                "old_issues": item["old_issues"],
                "new_issues": item["new_issues"],
            }
            for item in [*improved_pages, *regressed_pages]
        ]
        write_csv_rows(
            output_csv,
            rows,
            fieldnames=[
                "url",
                "old_page_health_score",
                "new_page_health_score",
                "delta",
                "status",
                "old_issues",
                "new_issues",
            ],
        )
    return comparison


def read_report(path: str) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.exists():
        raise CLIError(f"Rapport introuvable: {path}")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CLIError(f"Rapport JSON illisible: {path}") from exc
    if not isinstance(payload, dict):
        raise CLIError(f"Rapport JSON invalide: {path}")
    return payload


def pages_by_url(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(page.get("url")): dict(page)
        for page in report.get("pages") or []
        if isinstance(page, dict) and page.get("url")
    }


def compare_summary_values(old_summary: dict[str, Any], new_summary: dict[str, Any]) -> dict[str, int]:
    keys = sorted(set(old_summary) | set(new_summary))
    deltas: dict[str, int] = {}
    for key in keys:
        old_value = as_int(old_summary.get(key))
        new_value = as_int(new_summary.get(key))
        if old_value != new_value:
            deltas[key] = new_value - old_value
    return deltas


def as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
