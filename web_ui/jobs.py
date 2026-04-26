from __future__ import annotations

import csv
import io
import threading
import traceback
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from config import (
    DEFAULT_CRAWL_SOURCE,
    DEFAULT_AUDIT_MODE,
    DEFAULT_DELAY,
    DEFAULT_DISCOVER_PROVIDER,
    DEFAULT_QUALIFY_MODE,
    DEFAULT_UI_AUDIT_MAX_PAGES,
)
from discover import discover_domains, import_domains_from_file
from gsc import run_gsc_analysis
from qualify import qualify_domains
from utils import CLIError, parse_csv_list

from . import _audit_domains
from .fs_ops import resolve_local_file


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    started_at: str | None = None
    finished_at: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    log: str = ""
    error: str = ""
    outputs: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)


JOB_LOCK = threading.Lock()
JOBS: dict[str, JobRecord] = {}


class JobCancelledError(Exception):
    pass


class JobLogCapture(io.StringIO):
    def __init__(self, job_id: str) -> None:
        super().__init__()
        self.job_id = job_id

    def write(self, text: str) -> int:
        written = super().write(text)
        with JOB_LOCK:
            job = JOBS.get(self.job_id)
            if job is not None and job.status == "running":
                job.log = self.getvalue()
        return written


def create_job(kind: str, params: dict[str, Any]) -> JobRecord:
    job = JobRecord(job_id=uuid.uuid4().hex[:12], kind=kind, params=params)
    with JOB_LOCK:
        JOBS[job.job_id] = job
    return job


def run_discover_job(job_id: str) -> None:
    job = get_job(job_id)
    output = (job.params.get("output") or "data/domains_raw.csv").strip()
    provider = (job.params.get("provider") or DEFAULT_DISCOVER_PROVIDER).strip()
    query_mode = (job.params.get("query_mode") or "auto").strip()
    domains_file = (job.params.get("domains_file") or "").strip()
    limit = int(job.params.get("limit") or "50")
    delay = float(job.params.get("delay") or str(DEFAULT_DELAY))
    niches_raw = (job.params.get("niches") or "").strip()
    announce_job_outputs(job, [output])

    def action() -> tuple[list[str], list[str]]:
        if domains_file:
            ensure_job_can_continue(job)
            results = import_domains_from_file(input_path=domains_file, output=output)
        else:
            results = discover_domains(
                niches=parse_csv_list(niches_raw),
                limit=limit,
                output=output,
                provider_name=provider,
                delay=delay,
                query_mode=query_mode,
                cancel_callback=job_cancel_callback(job),
            )
        summary = [
            f"{len(results)} domaines exportes",
            f"Provider: {provider if not domains_file else 'manual'}",
            f"Query mode: {query_mode if not domains_file else 'manual'}",
            f"Output: {output}",
        ]
        return [output], summary

    execute_job(job, action)


def run_qualify_job(job_id: str) -> None:
    job = get_job(job_id)
    input_csv = (job.params.get("input_csv") or "data/domains_raw.csv").strip()
    output = (job.params.get("output") or "data/domains_scored.csv").strip()
    json_output = (job.params.get("json_output") or output.replace(".csv", ".json")).strip()
    mode = (job.params.get("mode") or DEFAULT_QUALIFY_MODE).strip() or DEFAULT_QUALIFY_MODE
    delay = float(job.params.get("delay") or str(DEFAULT_DELAY))
    announce_job_outputs(job, [output, json_output])

    def action() -> tuple[list[str], list[str]]:
        results = qualify_domains(
            input_csv=input_csv,
            output=output,
            json_output=json_output,
            mode=mode,
            delay=delay,
            cancel_callback=job_cancel_callback(job),
        )
        summary = [
            f"{len(results)} domaines qualifies",
            f"Mode: {mode}",
            f"Top score: {results[0].score if results else 0}",
            f"Output: {output}",
        ]
        return [output, json_output], summary

    execute_job(job, action)


def run_audit_job(job_id: str) -> None:
    job = get_job(job_id)
    site = (job.params.get("site") or "").strip()
    input_csv = (job.params.get("input_csv") or "data/domains_scored.csv").strip()
    output_dir = (job.params.get("output_dir") or "reports/audits").strip()
    html_output = (job.params.get("html_output") or "").strip()
    mode = (job.params.get("mode") or DEFAULT_AUDIT_MODE).strip() or DEFAULT_AUDIT_MODE
    crawl_source = (job.params.get("crawl_source") or DEFAULT_CRAWL_SOURCE).strip() or DEFAULT_CRAWL_SOURCE
    top_raw = (job.params.get("top") or "").strip()
    min_score_raw = (job.params.get("min_score") or "").strip()
    max_pages = int(job.params.get("max_pages") or str(DEFAULT_UI_AUDIT_MAX_PAGES))
    max_seconds_raw = (job.params.get("max_total_seconds_per_domain") or "").strip()
    delay = float(job.params.get("delay") or str(DEFAULT_DELAY))
    respect_robots = job.params.get("skip_robots") != "on"
    cache_enabled = job.params.get("cache_enabled") == "on"
    announced_outputs = [str(Path(output_dir) / "audit_summary.csv"), str(Path(output_dir) / "audit_index.sqlite")]
    if html_output:
        announced_outputs.append(html_output)
    announce_job_outputs(job, announced_outputs)

    def action() -> tuple[list[str], list[str]]:
        reports = _audit_domains()(
            input_csv=None if site else input_csv,
            output_dir=output_dir,
            top=int(top_raw) if top_raw else None,
            min_score=int(min_score_raw) if min_score_raw else None,
            mode=mode,
            max_pages=max_pages,
            max_total_seconds_per_domain=float(max_seconds_raw) if max_seconds_raw else None,
            delay=delay,
            crawl_source=crawl_source,
            respect_robots=respect_robots,
            html_output=html_output or None,
            cache_enabled=cache_enabled,
            site=site or None,
            cancel_callback=job_cancel_callback(job),
        )
        summary = [
            f"{len(reports)} audits termines",
            f"Mode: {mode}",
            f"Crawl source: {crawl_source}",
            (
                f"Budget temps/site: {format_duration(float(max_seconds_raw))}"
                if max_seconds_raw
                else "Budget temps/site: mode par defaut"
            ),
            f"Site direct: {site}" if site else f"Input CSV: {input_csv}",
            f"Summary CSV: {output_dir}/audit_summary.csv",
        ]
        outputs = [str(Path(output_dir) / "audit_summary.csv"), str(Path(output_dir) / "audit_index.sqlite")]
        if html_output:
            outputs.append(html_output)
        outputs.extend(str(Path(output_dir) / f"{report.domain}.json") for report in reports[:5])
        outputs.extend(report.html_path for report in reports[:5] if report.html_path and report.html_path not in outputs)
        return outputs, summary

    execute_job(job, action)


def run_gsc_job(job_id: str) -> None:
    job = get_job(job_id)
    current_csv = (job.params.get("current_csv") or "").strip()
    previous_csv = (job.params.get("previous_csv") or "").strip() or None
    queries_csv = (job.params.get("queries_csv") or "").strip() or None
    output_csv = (job.params.get("output_csv") or "reports/gsc_report.csv").strip()
    output_json = (job.params.get("output_json") or "reports/gsc_report.json").strip()
    output_html = (job.params.get("output_html") or "reports/gsc_report.html").strip()
    site_name = (job.params.get("site_name") or "").strip()
    niche_stopwords = parse_csv_list((job.params.get("niche_stopwords") or "").strip())
    auto_niche_stopwords = job.params.get("auto_niche_stopwords") == "on"
    announce_job_outputs(job, [output_csv, output_json, output_html])

    def action() -> tuple[list[str], list[str]]:
        results = run_gsc_analysis(
            current_csv=current_csv,
            previous_csv=previous_csv,
            queries_csv=queries_csv,
            output_csv=output_csv,
            output_html=output_html,
            output_json=output_json,
            site_name=site_name,
            niche_stopwords=niche_stopwords,
            auto_niche_stopwords=auto_niche_stopwords,
        )
        summary = [
            f"{len(results)} pages GSC analysees",
            f"CSV: {output_csv}",
        ]
        return [output_csv, output_json, output_html], summary

    execute_job(job, action)


def execute_job(job: JobRecord, action) -> None:  # type: ignore[no-untyped-def]
    capture = JobLogCapture(job.job_id)
    with JOB_LOCK:
        if job.cancel_requested:
            job.status = "cancelled"
            job.started_at = datetime.now().isoformat(timespec="seconds")
            job.finished_at = job.started_at
            job.log = "Job annule avant son demarrage.\n"
            return
        job.status = "running"
        job.started_at = datetime.now().isoformat(timespec="seconds")
        job.log = "Job demarre...\n"

    try:
        with redirect_stdout(capture), redirect_stderr(capture):
            outputs, summary_lines = action()
    except JobCancelledError:
        with JOB_LOCK:
            job.status = "cancelled"
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            job.log = capture.getvalue().rstrip()
            if job.log:
                job.log += "\n"
            job.log += "Job annule proprement.\n"
            job.error = ""
            job.summary_lines = ["Execution interrompue a la demande."]
        return
    except Exception as exc:  # noqa: BLE001
        with JOB_LOCK:
            job.status = "failed"
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            job.log = capture.getvalue()
            if not isinstance(exc, CLIError):
                job.log += "\n" + traceback.format_exc()
            job.error = str(exc)
        return

    with JOB_LOCK:
        job.status = "done"
        job.finished_at = datetime.now().isoformat(timespec="seconds")
        job.log = capture.getvalue()
        job.outputs = outputs
        job.summary_lines = summary_lines


def get_job(job_id: str) -> JobRecord:
    with JOB_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise CLIError(f"Job introuvable: {job_id}")
    return job


def delete_job_record(job_id: str) -> bool:
    if not job_id:
        return False
    with JOB_LOCK:
        return JOBS.pop(job_id, None) is not None


def announce_job_outputs(job: JobRecord, outputs: list[str]) -> None:
    with JOB_LOCK:
        if job.status in {"done", "failed", "cancelled"}:
            return
        job.outputs = outputs


def request_job_cancel(job_id: str) -> bool:
    if not job_id:
        return False
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return False
        if job.status in {"done", "failed", "cancelled"}:
            return False
        job.cancel_requested = True
        job.cancel_event.set()
        if job.status == "queued":
            now = datetime.now().isoformat(timespec="seconds")
            job.status = "cancelled"
            job.started_at = now
            job.finished_at = now
            job.log = "Job annule avant son demarrage.\n"
            job.summary_lines = ["Execution annulee avant lancement."]
        elif "Annulation demandee..." not in job.log:
            job.log += "Annulation demandee...\n"
    return True


def job_cancel_callback(job: JobRecord) -> Callable[[], None]:
    def _callback() -> None:
        ensure_job_can_continue(job)

    return _callback


def ensure_job_can_continue(job: JobRecord) -> None:
    if job.cancel_event.is_set():
        raise JobCancelledError


def parse_job_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def job_elapsed_seconds(job: JobRecord) -> float | None:
    start = parse_job_timestamp(job.started_at or job.created_at)
    if start is None:
        return None
    end = parse_job_timestamp(job.finished_at) or datetime.now()
    delta = (end - start).total_seconds()
    return max(0.0, delta)


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    rounded = int(round(seconds))
    minutes, secs = divmod(rounded, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def estimate_job_duration(job: JobRecord) -> str | None:
    if job.kind == "discover":
        domains_file = (job.params.get("domains_file") or "").strip()
        if domains_file:
            return "Import local, en general tres rapide."
        niches = parse_csv_list((job.params.get("niches") or "").strip())
        query_mode = (job.params.get("query_mode") or "auto").strip() or "auto"
        try:
            query_count = len(build_discovery_queries_for_estimate(niches, query_mode))
        except CLIError:
            return None
        if not query_count:
            return None
        low = max(5, query_count * 4)
        high = max(12, query_count * 12)
        return f"Souvent autour de {format_duration(low)} a {format_duration(high)} selon le provider."

    if job.kind == "qualify":
        input_csv = (job.params.get("input_csv") or "data/domains_raw.csv").strip()
        row_count = safe_count_csv_rows(input_csv)
        if row_count is None:
            return "Le temps depend surtout du nombre de domaines et du sitemap."
        mode = (job.params.get("mode") or DEFAULT_QUALIFY_MODE).strip() or DEFAULT_QUALIFY_MODE
        per_domain = 2 if mode == "qualify_fast" else 5
        low = row_count * max(1, per_domain - 1)
        high = row_count * (per_domain + 6)
        return f"Pour {row_count} domaines: environ {format_duration(low)} a {format_duration(high)}."

    if job.kind == "audit":
        mode = (job.params.get("mode") or DEFAULT_AUDIT_MODE).strip() or DEFAULT_AUDIT_MODE
        max_pages = int(job.params.get("max_pages") or str(DEFAULT_UI_AUDIT_MAX_PAGES))
        max_seconds_raw = (job.params.get("max_total_seconds_per_domain") or "").strip()
        top_raw = (job.params.get("top") or "").strip()
        site = (job.params.get("site") or "").strip()
        target_count = 1 if site else int(top_raw) if top_raw else 3
        low = target_count * max_pages * 1
        high = target_count * max_pages * 6
        if max_seconds_raw:
            high = min(high, target_count * int(float(max_seconds_raw)))
            low = min(low, high)
        return (
            f"A {target_count} site(s) x {max_pages} pages, compte souvent {format_duration(low)} "
            f"a {format_duration(high)}. Les timeouts reseau peuvent rallonger."
        )

    return None


def safe_count_csv_rows(relative_path: str) -> int | None:
    if not relative_path:
        return None
    try:
        csv_path = resolve_local_file(relative_path)
    except CLIError:
        return None
    if not csv_path.exists():
        return None
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def build_discovery_queries_for_estimate(niches: list[str], query_mode: str) -> list[str]:
    from discover import build_queries

    return build_queries(niches, query_mode=query_mode)


def clear_finished_jobs() -> int:
    with JOB_LOCK:
        finished_ids = [job_id for job_id, job in JOBS.items() if job.status in {"done", "failed", "cancelled"}]
        for job_id in finished_ids:
            JOBS.pop(job_id, None)
    return len(finished_ids)
