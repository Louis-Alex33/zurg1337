from __future__ import annotations

import csv
import html
import io
import json
import threading
import traceback
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from audit import audit_domains
from config import (
    AUDIT_MODE_CONFIGS,
    DEFAULT_AUDIT_MODE,
    DEFAULT_DELAY,
    DEFAULT_DISCOVER_PROVIDER,
    DEFAULT_MAX_PAGES,
    DEFAULT_QUALIFY_MODE,
    QUALIFY_MODE_CONFIGS,
)
from discover import discover_domains, import_domains_from_file
from gsc import run_gsc_analysis
from qualify import qualify_domains
from utils import CLIError, parse_csv_list

ROOT_DIR = Path(__file__).resolve().parent
MAX_POST_BODY_BYTES = 1_048_576


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


def launch_ui(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), ProspectMachineUIHandler)
    print(f"Prospect Machine UI available at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUI stopped.")
    finally:
        server.server_close()


class ProspectMachineUIHandler(BaseHTTPRequestHandler):
    server_version = "ProspectMachineUI/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            query = parse_qs(parsed.query)
            flash = (query.get("flash") or [""])[0]
            self._send_html(render_dashboard(flash=flash))
            return
        if parsed.path.startswith("/jobs/"):
            job_id = parsed.path.split("/")[-1]
            self._send_html(render_job_page(job_id))
            return
        if parsed.path == "/files":
            query = parse_qs(parsed.query)
            file_path = (query.get("path") or [""])[0]
            variant = (query.get("variant") or ["full"])[0]
            self._serve_file(file_path, variant=variant)
            return
        if parsed.path == "/download":
            query = parse_qs(parsed.query)
            file_path = (query.get("path") or [""])[0]
            self._serve_download(file_path)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._is_same_origin():
            self.send_error(HTTPStatus.FORBIDDEN, "Cross-origin request refused")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            content_length = 0
        if content_length < 0:
            content_length = 0
        if content_length > MAX_POST_BODY_BYTES:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload too large")
            return
        payload = self.rfile.read(content_length).decode("utf-8")
        form = {key: values[0] for key, values in parse_qs(payload, keep_blank_values=True).items()}

        if parsed.path == "/run/discover":
            job = create_job("discover", form)
            threading.Thread(target=run_discover_job, args=(job.job_id,), daemon=True).start()
            self._redirect(f"/jobs/{job.job_id}")
            return
        if parsed.path == "/run/qualify":
            job = create_job("qualify", form)
            threading.Thread(target=run_qualify_job, args=(job.job_id,), daemon=True).start()
            self._redirect(f"/jobs/{job.job_id}")
            return
        if parsed.path == "/run/audit":
            job = create_job("audit", form)
            threading.Thread(target=run_audit_job, args=(job.job_id,), daemon=True).start()
            self._redirect(f"/jobs/{job.job_id}")
            return
        if parsed.path == "/run/gsc":
            job = create_job("gsc", form)
            threading.Thread(target=run_gsc_job, args=(job.job_id,), daemon=True).start()
            self._redirect(f"/jobs/{job.job_id}")
            return
        if parsed.path == "/delete-file":
            self._handle_delete_file(form)
            return
        if parsed.path == "/reset-pipeline":
            self._handle_reset_pipeline()
            return
        if parsed.path == "/delete-job":
            self._handle_delete_job(form)
            return
        if parsed.path == "/cancel-job":
            self._handle_cancel_job(form)
            return
        if parsed.path == "/clear-jobs":
            self._handle_clear_jobs()
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown action")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _is_same_origin(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return False
        parsed = urlparse(source)
        if not parsed.scheme or not parsed.netloc:
            return False
        host, port = self.server.server_address[:2]
        expected_origin = f"http://{host}:{port}"
        request_origin = f"{parsed.scheme}://{parsed.netloc}"
        return request_origin == expected_origin

    def _send_html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _serve_file(self, requested_path: str, variant: str = "full") -> None:
        try:
            file_path = resolve_local_file(requested_path)
        except CLIError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        self._send_html(render_file_page(file_path, variant=variant))

    def _serve_download(self, requested_path: str) -> None:
        try:
            file_path = resolve_local_file(requested_path)
        except CLIError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        body = file_path.read_bytes()
        content_type = "application/octet-stream"
        if file_path.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        elif file_path.suffix == ".csv":
            content_type = "text/csv; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.end_headers()
        self.wfile.write(body)

    def _handle_delete_file(self, form: dict[str, str]) -> None:
        requested_path = (form.get("path") or "").strip()
        redirect_to = (form.get("redirect_to") or "/").strip() or "/"
        cascade = form.get("cascade") == "on"
        try:
            deleted = delete_managed_file(requested_path, cascade=cascade)
        except CLIError as exc:
            self._redirect(f"/?flash={quote(str(exc))}")
            return

        if not deleted:
            message = f"Aucun fichier supprime pour {requested_path}."
        else:
            message = "Suppression terminee: " + ", ".join(deleted)
        separator = "&" if "?" in redirect_to else "?"
        self._redirect(f"{redirect_to}{separator}flash={quote(message)}")

    def _handle_reset_pipeline(self) -> None:
        deleted = reset_pipeline_outputs()
        if not deleted:
            message = "Aucun fichier de pipeline a supprimer."
        else:
            message = "Reset pipeline termine: " + ", ".join(deleted)
        self._redirect(f"/?flash={quote(message)}")

    def _handle_delete_job(self, form: dict[str, str]) -> None:
        job_id = (form.get("job_id") or "").strip()
        redirect_to = (form.get("redirect_to") or "/").strip() or "/"
        deleted = delete_job_record(job_id)
        if not deleted:
            message = f"Job introuvable ou deja supprime: {job_id}"
        else:
            message = f"Job supprime: {job_id}"
        separator = "&" if "?" in redirect_to else "?"
        self._redirect(f"{redirect_to}{separator}flash={quote(message)}")

    def _handle_cancel_job(self, form: dict[str, str]) -> None:
        job_id = (form.get("job_id") or "").strip()
        redirect_to = (form.get("redirect_to") or f"/jobs/{job_id}").strip() or f"/jobs/{job_id}"
        cancelled = request_job_cancel(job_id)
        if not cancelled:
            message = f"Impossible d'annuler ce job: {job_id}"
        else:
            message = f"Annulation demandee pour le job {job_id}"
        separator = "&" if "?" in redirect_to else "?"
        self._redirect(f"{redirect_to}{separator}flash={quote(message)}")

    def _handle_clear_jobs(self) -> None:
        deleted = clear_finished_jobs()
        if not deleted:
            message = "Aucun job termine a supprimer."
        else:
            message = f"{deleted} job(s) supprime(s) de l'historique."
        self._redirect(f"/?flash={quote(message)}")


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
    mode = (job.params.get("mode") or DEFAULT_AUDIT_MODE).strip() or DEFAULT_AUDIT_MODE
    top_raw = (job.params.get("top") or "").strip()
    min_score_raw = (job.params.get("min_score") or "").strip()
    max_pages = int(job.params.get("max_pages") or str(DEFAULT_MAX_PAGES))
    delay = float(job.params.get("delay") or str(DEFAULT_DELAY))
    announce_job_outputs(job, [str(Path(output_dir) / "audit_summary.csv")])

    def action() -> tuple[list[str], list[str]]:
        reports = audit_domains(
            input_csv=None if site else input_csv,
            output_dir=output_dir,
            top=int(top_raw) if top_raw else None,
            min_score=int(min_score_raw) if min_score_raw else None,
            mode=mode,
            max_pages=max_pages,
            delay=delay,
            site=site or None,
            cancel_callback=job_cancel_callback(job),
        )
        summary = [
            f"{len(reports)} audits termines",
            f"Mode: {mode}",
            f"Site direct: {site}" if site else f"Input CSV: {input_csv}",
            f"Summary CSV: {output_dir}/audit_summary.csv",
        ]
        outputs = [str(Path(output_dir) / "audit_summary.csv")]
        outputs.extend(str(Path(output_dir) / f"{report.domain}.json") for report in reports[:5])
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
        return (
            f"Pour {row_count} domaines: environ {format_duration(low)} a {format_duration(high)}."
        )

    if job.kind == "audit":
        mode = (job.params.get("mode") or DEFAULT_AUDIT_MODE).strip() or DEFAULT_AUDIT_MODE
        max_pages = int(job.params.get("max_pages") or str(AUDIT_MODE_CONFIGS[mode].max_pages))
        top_raw = (job.params.get("top") or "").strip()
        site = (job.params.get("site") or "").strip()
        target_count = 1 if site else int(top_raw) if top_raw else 3
        low = target_count * max_pages * 1
        high = target_count * max_pages * 6
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


def render_dashboard(flash: str = "") -> str:
    recent_jobs = recent_job_cards()
    raw_preview = render_data_preview("data/domains_raw.csv", title="Dernier domains_raw.csv")
    scored_preview = render_data_preview("data/domains_scored.csv", title="Dernier domains_scored.csv")
    audit_preview = render_data_preview("reports/audits/audit_summary.csv", title="Dernier audit_summary.csv")
    gsc_preview = render_data_preview("reports/gsc_report.csv", title="Dernier gsc_report.csv")
    flash_block = (
        f'<div class="flash-banner">{html.escape(unquote(flash))}</div>'
        if flash
        else ""
    )

    content = f"""
    {flash_block}
    <div class="hero">
      <div>
        <p class="eyebrow">Prospect Machine</p>
        <h1>ZURG 1337</h1>
        <p class="lede">
          Outil local pour trouver des sites, les trier, puis sortir un angle d'audit exploitable.
        </p>
        <div class="panel-actions hero-actions">
          <form method="post" action="/reset-pipeline" class="inline-form">
            <button class="ghost-button danger" type="submit">Reset pipeline</button>
          </form>
          <span class="muted">Nettoie raw, scored, audits et rapports GSC generes localement.</span>
        </div>
      </div>
      <div class="hero-panel">
        <div class="hero-stat"><strong>4 modules</strong><span>discover, qualify, audit, gsc</span></div>
        <div class="hero-stat"><strong>Guidage integre</strong><span>les cards indiquent quoi remplir et quoi lire ensuite</span></div>
        <div class="hero-stat"><strong>Jobs locaux</strong><span>aucun service externe requis</span></div>
        <div class="hero-stat"><strong>Fichiers simples</strong><span>CSV et JSON reutilisables partout</span></div>
      </div>
    </div>

    <div class="grid onboarding-grid">
      <section class="panel onboarding-panel">
        <div class="panel-head">
          <h2>Commencer Ici</h2>
          <span class="badge">workflow rapide</span>
        </div>
        <div class="quick-start-grid">
          <article class="quick-start-card">
            <p class="eyebrow">Cas 1</p>
            <h3>Je veux analyser un seul site</h3>
            <ol class="flow compact-flow">
              <li>Va dans la card <strong>Audit</strong>.</li>
              <li>Remplis seulement le champ <strong>Site</strong> avec `example.com`.</li>
              <li>Laisse `Max pages` sur `30` pour commencer.</li>
              <li>Ouvre ensuite `reports/audits/audit_summary.csv` puis le JSON du domaine.</li>
            </ol>
          </article>
          <article class="quick-start-card">
            <p class="eyebrow">Cas 2</p>
            <h3>Je veux faire de la prospection en lot</h3>
            <ol class="flow compact-flow">
              <li><strong>Discover</strong> pour produire une liste brute.</li>
              <li><strong>Qualify</strong> pour garder les bons candidats.</li>
              <li><strong>Audit</strong> sur les meilleurs scores.</li>
              <li><strong>GSC</strong> seulement si tu as des exports client.</li>
            </ol>
          </article>
          <article class="quick-start-card">
            <p class="eyebrow">A savoir</p>
            <h3>Ce que tu dois lire dans un rapport</h3>
            <ul class="clean-list compact-list">
              <li><strong>Points à corriger d'abord</strong>: les sujets à regarder en priorité.</li>
              <li><strong>Opportunités détectées</strong>: ce qui est le plus simple à valoriser commercialement.</li>
              <li><strong>Pages à revoir en premier</strong>: les exemples concrets à citer dans un message ou une courte vidéo.</li>
            </ul>
          </article>
        </div>
      </section>
    </div>

    <div class="grid two">
      {render_discover_card()}
      {render_qualify_card()}
    </div>

    <div class="grid two">
      {render_audit_card()}
      {render_gsc_card()}
    </div>

    <div class="grid two">
      <section class="panel">
        <div class="panel-head">
          <h2>Jobs recents</h2>
          <div class="panel-tools">
            <form method="post" action="/clear-jobs" class="inline-form">
              <button class="ghost-button" type="submit">Nettoyer</button>
            </form>
            <a class="subtle-link" href="/">Rafraichir</a>
          </div>
        </div>
        {recent_jobs}
      </section>
      <section class="panel">
        <div class="panel-head">
          <h2>Pipeline conseille</h2>
        </div>
        <ol class="flow">
          <li>Discover: genere une liste de domaines.</li>
          <li>Qualify: garde les sites qui ressemblent a de bons candidats editoriaux.</li>
          <li>Audit: creuse les meilleurs pour sortir des arguments concrets.</li>
          <li>GSC: ajoute cette brique seulement si tu as des exports client.</li>
        </ol>
      </section>
    </div>

    <div class="grid two">
      {raw_preview}
      {scored_preview}
    </div>

    <div class="grid two">
      {audit_preview}
      {gsc_preview}
    </div>
    """
    return page_shell("Prospect Machine UI", content)


def render_job_page(job_id: str) -> str:
    try:
        job = get_job(job_id)
    except CLIError:
        return page_shell("Job introuvable", '<section class="panel"><h2>Job introuvable</h2></section>')

    refresh = '<meta http-equiv="refresh" content="2">' if job.status == "running" else ""
    status_copy = {
        "queued": "En attente de demarrage",
        "running": "En cours d'execution",
        "done": "Termine",
        "cancelled": "Job annule",
        "failed": "Echec du job",
    }.get(job.status, job.status)
    elapsed = format_duration(job_elapsed_seconds(job))
    runtime_hint = estimate_job_duration(job)
    outputs = "".join(
        f'<li><a href="/files?path={quote(path)}">{html.escape(path)}</a></li>'
        for path in job.outputs
    ) or "<li>Aucune sortie declaree</li>"
    previews = "".join(render_data_preview(path, title=path) for path in job.outputs[:2])
    summary = "".join(f"<li>{html.escape(line)}</li>" for line in job.summary_lines) or "<li>Pas de resume.</li>"
    log_block = html.escape(job.log.strip() or "Aucun log capture.")
    error_block = f'<div class="error-box">{html.escape(job.error)}</div>' if job.error else ""
    next_steps = render_job_next_steps(job)
    cancel_action = (
        f"""
        <form method="post" action="/cancel-job" class="inline-form">
          <input type="hidden" name="job_id" value="{html.escape(job.job_id)}">
          <input type="hidden" name="redirect_to" value="/jobs/{html.escape(job.job_id)}">
          <button class="ghost-button danger" type="submit">Annuler le job</button>
        </form>
        """
        if job.status == "running"
        else ""
    )
    running_help = (
        "<p class='field-help running-help'>Le job tourne encore. Cette page se rafraichit automatiquement, les logs se remplissent en direct, et tu peux maintenant l'annuler proprement sans couper le serveur.</p>"
        if job.status == "running"
        else ""
    )
    runtime_block = (
        f"<div><strong>Rythme attendu</strong><span>{html.escape(runtime_hint)}</span></div>"
        if runtime_hint
        else ""
    )

    content = f"""
    {refresh}
    <section class="panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">Job {html.escape(job.job_id)}</p>
          <h1>{html.escape(job.kind.title())}</h1>
          <p class="lede">{status_copy}</p>
          {running_help}
        </div>
        <div class="status-pill status-{html.escape(job.status)}">{html.escape(job.status)}</div>
      </div>
      <div class="meta-grid">
        <div><strong>Cree le</strong><span>{html.escape(job.created_at)}</span></div>
        <div><strong>Demarre le</strong><span>{html.escape(job.started_at or '-')}</span></div>
        <div><strong>Fini le</strong><span>{html.escape(job.finished_at or '-')}</span></div>
        <div><strong>Duree</strong><span>{html.escape(elapsed)}</span></div>
        {runtime_block}
      </div>
      {error_block}
      <div class="grid two">
        <section class="subpanel">
          <h2>Resume</h2>
          <ul class="clean-list">{summary}</ul>
        </section>
        <section class="subpanel">
          <h2>Sorties</h2>
          <ul class="clean-list">{outputs}</ul>
        </section>
      </div>
      <section class="subpanel">
        <h2>Que faire ensuite</h2>
        {next_steps}
      </section>
      <section class="subpanel">
        <h2>Logs</h2>
        <pre class="log-box">{log_block}</pre>
      </section>
      <div class="panel-actions">
        <a class="button secondary" href="/">Retour dashboard</a>
        {cancel_action}
      </div>
    </section>
    <div class="grid two">{previews}</div>
    """
    return page_shell(f"Job {job.job_id}", content)


def render_job_next_steps(job: JobRecord) -> str:
    items = build_job_next_steps(job)
    if not items:
        return "<p class='muted'>Aucune suite suggérée pour ce job.</p>"
    body = "".join(f"<li>{item}</li>" for item in items)
    return f"<ul class='clean-list'>{body}</ul>"


def build_job_next_steps(job: JobRecord) -> list[str]:
    if job.status == "running":
        return [
            "Laisse cette page ouverte: elle se met a jour automatiquement avec les logs, la duree et les sorties.",
            "Dès que le job se termine, ouvre le premier fichier de sortie pour verifier rapidement le resultat.",
        ]
    if job.status == "cancelled":
        return [
            "Relis les derniers logs pour voir jusqu'ou le job a pu aller avant l'arret.",
            "Relance ensuite avec des parametres plus legers, par exemple moins de pages ou sans sitemap pour un premier passage.",
        ]
    if job.status == "failed":
        return [
            "Relis le bloc d'erreur et les logs pour voir si le probleme vient d'un chemin de fichier, d'un domaine ou d'un timeout.",
            "Corrige les paramètres du job puis relance-le depuis le dashboard.",
        ]

    if job.kind == "discover":
        output_csv = first_output_matching(job.outputs, ".csv")
        return [
            f"Ouvre {file_anchor(output_csv, 'le CSV de decouverte')} pour verifier si la liste est bien dans la bonne niche."
            if output_csv
            else "Ouvre le CSV de sortie pour verifier si la liste est bien dans la bonne niche.",
            "Enchaine ensuite avec Qualify pour filtrer les sites qui ressemblent vraiment a de bons candidats editoriaux.",
        ]
    if job.kind == "qualify":
        scored_csv = first_output_matching(job.outputs, ".csv")
        scored_json = first_output_matching(job.outputs, ".json")
        items = [
            f"Ouvre {file_anchor(scored_csv, 'le CSV score')} pour repérer les meilleurs candidats."
            if scored_csv
            else "Ouvre le CSV score pour repérer les meilleurs candidats.",
            "Regarde en priorité les champs de fit éditorial, puis lance Audit sur les domaines les plus prometteurs.",
        ]
        if scored_json:
            items.append(f"{file_anchor(scored_json, 'Le JSON détaillé')} est plus pratique si tu veux relire tous les signaux domaine par domaine.")
        return items
    if job.kind == "audit":
        summary_csv = first_output_containing(job.outputs, "audit_summary.csv")
        first_report = first_output_matching(job.outputs, ".json")
        items = [
            f"Commence par {file_anchor(summary_csv, 'ouvrir le recap des audits')} pour voir quels domaines ressortent le plus."
            if summary_csv
            else "Commence par ouvrir le recap des audits pour voir quels domaines ressortent le plus.",
            f"Ensuite, ouvre {file_anchor(first_report, 'le rapport complet du domaine')} pour lire les pages a retravailler et les signaux prioritaires."
            if first_report
            else "Ensuite, ouvre le rapport complet du domaine pour lire les pages a retravailler et les signaux prioritaires.",
            "Si le rapport est convaincant, reprends le resume et les pages citees pour preparer une courte video ou un message de prospection.",
        ]
        return items
    if job.kind == "gsc":
        html_report = first_output_matching(job.outputs, ".html")
        csv_report = first_output_matching(job.outputs, ".csv")
        items = [
            f"Ouvre {file_anchor(html_report, 'le rapport HTML')} pour une lecture plus simple."
            if html_report
            else "Ouvre le rapport HTML pour une lecture plus simple.",
            f"Utilise ensuite {file_anchor(csv_report, 'le CSV')} si tu veux retravailler les priorites ailleurs."
            if csv_report
            else "Utilise ensuite le CSV si tu veux retravailler les priorites ailleurs.",
        ]
        return items
    return ["Retourne au dashboard pour lancer l'etape suivante du pipeline."]


def first_output_matching(paths: list[str], suffix: str) -> str | None:
    for path in paths:
        if path.endswith(suffix):
            return path
    return None


def first_output_containing(paths: list[str], fragment: str) -> str | None:
    for path in paths:
        if fragment in path:
            return path
    return None


def file_anchor(path: str | None, label: str) -> str:
    if not path:
        return html.escape(label)
    return f"<a class='subtle-link' href='/files?path={quote(path)}'>{html.escape(label)}</a>"


def render_discover_card() -> str:
    return f"""
    <section class="panel accent-clay">
      <div class="panel-head"><h2>Discover</h2><span class="badge">live ou fichier</span></div>
      <p class="card-lede">Utilise cette card pour construire une premiere liste de domaines. Si tu veux juste analyser un seul site, saute directement a <strong>Audit</strong>.</p>
      <div class="card-tip">Remplis <strong>Niches</strong> si tu cherches de nouveaux sites, ou <strong>Domains file</strong> si tu as deja une liste.</div>
      <form method="post" action="/run/discover" class="stack">
        <label>Niches
          <input type="text" name="niches" value="blog yoga" placeholder="padel,yoga,velo">
        </label>
        <p class="field-help">Exemples: `padel`, `blog yoga`, `comparatif mutuelle`. Separe plusieurs sujets par des virgules.</p>
        <label>Domains file
          <input type="text" name="domains_file" value="" placeholder="data/mes_sites.txt">
        </label>
        <p class="field-help">Fichier texte avec un domaine ou une URL par ligne. Pratique si tu as deja une shortlist.</p>
        <div class="inline-fields">
          <label>Limit
            <input type="number" name="limit" value="30" min="1">
          </label>
          <label>Delay
            <input type="number" step="0.1" name="delay" value="{DEFAULT_DELAY}">
          </label>
        </div>
        <p class="field-help">`Limit` controle combien de domaines tu veux sortir. `Delay` ralentit legerement la collecte pour rester plus propre.</p>
        <div class="inline-fields">
          <label>Provider
            <input type="text" name="provider" value="{DEFAULT_DISCOVER_PROVIDER}">
          </label>
          <label>Query mode
            <input type="text" name="query_mode" value="auto" placeholder="auto | exact | expand">
          </label>
        </div>
        <div class="inline-fields">
          <label>Output
            <input type="text" name="output" value="data/domains_raw.csv">
          </label>
        </div>
        <p class="field-help">La sortie cree en general `data/domains_raw.csv`, qui devient l'entree naturelle de <strong>Qualify</strong>.</p>
        <button class="button" type="submit">1. Generer Une Liste De Domaines</button>
      </form>
    </section>
    """


def render_qualify_card() -> str:
    mode_options = "".join(
        f'<option value="{name}" {"selected" if name == DEFAULT_QUALIFY_MODE else ""}>{name}</option>'
        for name in sorted(QUALIFY_MODE_CONFIGS)
    )
    return f"""
    <section class="panel accent-sage">
      <div class="panel-head"><h2>Qualify</h2><span class="badge">scoring rapide</span></div>
      <p class="card-lede">Cette card trie les domaines et aide a separer les bons candidats editoriaux des profils app, docs ou marketplace.</p>
      <div class="card-tip">Dans la plupart des cas, tu peux garder les valeurs par defaut et lancer le job.</div>
      <form method="post" action="/run/qualify" class="stack">
        <label>Input CSV
          <input type="text" name="input_csv" value="data/domains_raw.csv">
        </label>
        <p class="field-help">Mets ici le fichier cree par <strong>Discover</strong>, en general `data/domains_raw.csv`.</p>
        <div class="inline-fields">
          <label>Output CSV
            <input type="text" name="output" value="data/domains_scored.csv">
          </label>
          <label>Output JSON
            <input type="text" name="json_output" value="data/domains_scored.json">
          </label>
        </div>
        <p class="field-help">Le CSV sert pour la suite du pipeline. Le JSON est plus agreable a relire si tu veux inspecter les details.</p>
        <div class="inline-fields">
          <label>Mode
            <select name="mode">{mode_options}</select>
          </label>
          <label>Delay
            <input type="number" step="0.1" name="delay" value="{DEFAULT_DELAY}">
          </label>
        </div>
        <p class="field-help">`qualify_fast` limite fortement le cout machine. `qualify_full` creuse un peu plus le domaine, notamment via le sitemap.</p>
        <button class="button" type="submit">2. Trier Les Domaines Prometteurs</button>
      </form>
    </section>
    """


def render_audit_card() -> str:
    mode_options = "".join(
        f'<option value="{name}" {"selected" if name == DEFAULT_AUDIT_MODE else ""}>{name}</option>'
        for name in sorted(AUDIT_MODE_CONFIGS)
    )
    return f"""
    <section class="panel accent-ink">
      <div class="panel-head"><h2>Audit</h2><span class="badge">triage ou deep dive</span></div>
      <p class="card-lede">La card la plus utile si tu veux comprendre un site vite. Tu peux l'utiliser directement sur un seul domaine, sans passer par le CSV.</p>
      <div class="card-tip">Pour un test simple, remplis seulement <strong>Site</strong>, garde `audit_light`, laisse `Max pages` a `30`, puis lance l'audit.</div>
      <form method="post" action="/run/audit" class="stack">
        <label>Input CSV
          <input type="text" name="input_csv" value="data/domains_scored.csv">
        </label>
        <p class="field-help">Utilise ce champ si tu veux auditer plusieurs domaines deja qualifies.</p>
        <label>Site
          <input type="text" name="site" value="" placeholder="example.com ou https://example.com">
        </label>
        <p class="field-help">Si ce champ est rempli, l'audit part directement sur ce domaine et ignore l'Input CSV.</p>
        <div class="inline-fields">
          <label>Mode
            <select name="mode">{mode_options}</select>
          </label>
          <label>Top
            <input type="number" name="top" value="3" min="1">
          </label>
          <label>Min score
            <input type="number" name="min_score" value="50" min="0" max="100">
          </label>
        </div>
        <p class="field-help">`audit_light` privilegie un audit rapide et peu gourmand. `audit_full` est reserve aux quelques domaines qui meritent plus de profondeur.</p>
        <div class="inline-fields">
          <label>Max pages
            <input type="number" name="max_pages" value="30" min="1">
          </label>
          <label>Delay
            <input type="number" step="0.1" name="delay" value="0.2">
          </label>
        </div>
        <p class="field-help">Commence avec `10` a `30` pages pour un triage rapide. Au-dela, certains sites lents peuvent facilement depasser 3 minutes, surtout avec plusieurs domaines.</p>
        <label>Output dir
          <input type="text" name="output_dir" value="reports/audits">
        </label>
        <p class="field-help">Regarde ensuite `reports/audits/audit_summary.csv`, puis le JSON du domaine pour le detail.</p>
        <button class="button" type="submit">3. Sortir Un Mini Audit Exploitable</button>
      </form>
    </section>
    """


def render_gsc_card() -> str:
    return """
    <section class="panel accent-gold">
      <div class="panel-head"><h2>GSC</h2><span class="badge">exports client</span></div>
      <p class="card-lede">Cette card sert surtout si tu travailles deja avec un client et que tu as ses exports Google Search Console.</p>
      <div class="card-tip">Si tu n'as pas de fichiers GSC, tu peux ignorer cette card pour l'instant.</div>
      <form method="post" action="/run/gsc" class="stack">
        <label>Current CSV
          <input type="text" name="current_csv" value="exports/pages_recent.csv">
        </label>
        <p class="field-help">Export recent des pages depuis GSC. C'est le fichier principal.</p>
        <label>Previous CSV
          <input type="text" name="previous_csv" value="exports/pages_old.csv">
        </label>
        <p class="field-help">Export plus ancien pour comparer les baisses. Tu peux le laisser vide si tu n'en as pas.</p>
        <label>Queries CSV
          <input type="text" name="queries_csv" value="exports/queries.csv">
        </label>
        <p class="field-help">Export des requetes. Il enrichit l'analyse, mais reste optionnel.</p>
        <label>Site label
          <input type="text" name="site_name" value="">
        </label>
        <p class="field-help">Nom lisible du site ou du client, juste pour rendre les sorties plus propres.</p>
        <div class="inline-fields">
          <label>Output CSV
            <input type="text" name="output_csv" value="reports/gsc_report.csv">
          </label>
          <label>Output JSON
            <input type="text" name="output_json" value="reports/gsc_report.json">
          </label>
        </div>
        <label>Output HTML
          <input type="text" name="output_html" value="reports/gsc_report.html">
        </label>
        <p class="field-help">Le HTML est souvent le plus simple a relire ensuite. Le CSV et le JSON servent surtout a retravailler la sortie.</p>
        <button class="button" type="submit">4. Analyser Des Exports GSC</button>
      </form>
    </section>
    """


def recent_job_cards() -> str:
    with JOB_LOCK:
        jobs = sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)[:8]
    if not jobs:
        return "<p class='muted'>Aucun job lance pour l'instant. Commence par la card Audit si tu veux juste tester un domaine.</p>"
    cards = []
    for job in jobs:
        elapsed = format_duration(job_elapsed_seconds(job))
        runtime_hint = estimate_job_duration(job)
        cancel_action = (
            f"""
            <form method="post" action="/cancel-job" class="inline-form">
              <input type="hidden" name="job_id" value="{html.escape(job.job_id)}">
              <input type="hidden" name="redirect_to" value="/">
              <button class="ghost-button danger" type="submit">Annuler</button>
            </form>
            """
            if job.status == "running"
            else ""
        )
        cards.append(
            f"""
            <div class="job-card">
              <div class="job-top">
                <a class="job-main-link" href="/jobs/{job.job_id}">
                  <strong>{html.escape(job.kind.title())}</strong>
                </a>
                <span class="status-pill status-{html.escape(job.status)}">{html.escape(job.status)}</span>
              </div>
              <a class="job-main-link" href="/jobs/{job.job_id}">
                <p>{html.escape(job.job_id)} · {html.escape(job.created_at)}</p>
                <p class="job-meta">Duree: {html.escape(elapsed)}</p>
                <p class="job-meta">{html.escape(runtime_hint or 'Temps variable selon le reseau et les fichiers fournis.')}</p>
              </a>
              <div class="job-actions">
                {cancel_action}
                <form method="post" action="/delete-job" class="inline-form">
                  <input type="hidden" name="job_id" value="{html.escape(job.job_id)}">
                  <input type="hidden" name="redirect_to" value="/">
                  <button class="ghost-button job-delete" type="submit">Supprimer</button>
                </form>
              </div>
            </div>
            """
        )
    return "".join(cards)


def render_data_preview(relative_path: str, title: str) -> str:
    path = ROOT_DIR / relative_path
    if not path.exists():
        return (
            f'<section class="panel"><div class="panel-head"><h2>{html.escape(title)}</h2></div>'
            f'<p class="muted">Aucun fichier trouve pour {html.escape(relative_path)}.</p></section>'
        )
    link = f"/files?path={quote(relative_path)}"
    actions = ""
    if relative_path in {"data/domains_raw.csv", "data/domains_scored.csv"}:
        cascade_input = '<input type="hidden" name="cascade" value="on">' if relative_path == "data/domains_scored.csv" else ""
        actions = (
            '<form method="post" action="/delete-file" class="inline-form">'
            f'<input type="hidden" name="path" value="{html.escape(relative_path)}">'
            '<input type="hidden" name="redirect_to" value="/">'
            f"{cascade_input}"
            '<button class="ghost-button danger" type="submit">Supprimer</button>'
            "</form>"
        )
    try:
        if path.suffix == ".csv":
            table = render_csv_preview(path)
        elif path.suffix == ".json":
            payload = html.escape(
                json.dumps(json.loads(path.read_text("utf-8")), ensure_ascii=False, indent=2)[:3000]
            )
            table = f"<pre class='log-box'>{payload}</pre>"
        else:
            payload = html.escape(path.read_text("utf-8", errors="ignore")[:3000])
            table = f"<pre class='log-box'>{payload}</pre>"
    except Exception as exc:  # noqa: BLE001
        table = f"<p class='muted'>Preview indisponible: {html.escape(str(exc))}</p>"
    return (
        f'<section class="panel"><div class="panel-head"><h2>{html.escape(title)}</h2>'
        f'<div class="panel-tools"><a class="subtle-link" href="{link}">Ouvrir</a>{actions}</div></div>{table}</section>'
    )


def render_csv_preview(path: Path, max_rows: int = 8) -> str:
    if path.name == "audit_summary.csv":
        return render_audit_summary_preview(path, max_rows=max_rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = []
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            rows.append(row)
    if not fieldnames:
        return "<p class='muted'>CSV vide.</p>"
    headers = "".join(f"<th>{html.escape(name)}</th>" for name in fieldnames)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape((row.get(name) or '')[:140])}</td>" for name in fieldnames)
        body_rows.append(f"<tr>{cells}</tr>")
    body = "".join(body_rows) or f"<tr><td colspan='{len(fieldnames)}'>Aucune ligne.</td></tr>"
    return f"<div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></div>"


def render_file_page(path: Path, variant: str = "full") -> str:
    relative_path = path.relative_to(ROOT_DIR)
    file_size = human_file_size(path.stat().st_size)
    delete_action = ""
    if str(relative_path) in {"data/domains_raw.csv", "data/domains_scored.csv"}:
        cascade_input = '<input type="hidden" name="cascade" value="on">' if str(relative_path) == "data/domains_scored.csv" else ""
        delete_action = (
            '<form method="post" action="/delete-file" class="inline-form">'
            f'<input type="hidden" name="path" value="{html.escape(str(relative_path))}">'
            '<input type="hidden" name="redirect_to" value="/">'
            f"{cascade_input}"
            '<button class="ghost-button danger" type="submit">Supprimer ce fichier</button>'
            "</form>"
        )
    if path.suffix == ".csv":
        if str(relative_path) == "reports/audits/audit_summary.csv":
            return render_audit_summary_page(path, file_size=file_size)
        stats, table = render_full_csv_table(path)
        content = f"""
        <section class="panel file-shell">
          <div class="panel-head">
            <div>
              <p class="eyebrow">CSV Viewer</p>
              <h1>{html.escape(str(relative_path))}</h1>
              <p class="lede">Vue tabulaire complete, plus agreable pour relire rapidement les exports de prospection.</p>
            </div>
            <div class="panel-actions">
              {delete_action}
              <a class="button secondary" href="/">Retour home</a>
            </div>
          </div>
          <div class="meta-grid file-meta">
            <div><strong>Type</strong><span>CSV</span></div>
            <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
            <div><strong>Lignes</strong><span>{stats['rows']}</span></div>
            <div><strong>Colonnes</strong><span>{stats['columns']}</span></div>
          </div>
          <section class="subpanel">
            <h2>Apercu complet</h2>
            {table}
          </section>
        </section>
        """
        return page_shell(f"CSV - {relative_path}", content)

    if path.suffix == ".json":
        if is_audit_report_json(relative_path):
            return render_audit_report_page(path, relative_path=relative_path, file_size=file_size, variant=variant)
        pretty_json = html.escape(json.dumps(json.loads(path.read_text("utf-8")), ensure_ascii=False, indent=2))
        content = f"""
        <section class="panel file-shell">
          <div class="panel-head">
            <div>
              <p class="eyebrow">JSON Viewer</p>
              <h1>{html.escape(str(relative_path))}</h1>
              <p class="lede">Lecture rapide du JSON genere par le pipeline.</p>
            </div>
            <div class="panel-actions">
              {delete_action}
              <a class="button secondary" href="/">Retour home</a>
            </div>
          </div>
          <div class="meta-grid file-meta">
            <div><strong>Type</strong><span>JSON</span></div>
            <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
          </div>
          <pre class="log-box">{pretty_json}</pre>
        </section>
        """
        return page_shell(f"JSON - {relative_path}", content)

    payload = html.escape(path.read_text("utf-8", errors="ignore"))
    content = f"""
    <section class="panel file-shell">
      <div class="panel-head">
        <div>
          <p class="eyebrow">File Viewer</p>
          <h1>{html.escape(str(relative_path))}</h1>
          <p class="lede">Apercu texte du fichier.</p>
        </div>
        <div class="panel-actions">
          {delete_action}
          <a class="button secondary" href="/">Retour home</a>
        </div>
      </div>
      <div class="meta-grid file-meta">
        <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
      </div>
      <pre class="log-box">{payload}</pre>
    </section>
    """
    return page_shell(f"File - {relative_path}", content)


def is_audit_report_json(relative_path: Path) -> bool:
    return (
        relative_path.suffix == ".json"
        and str(relative_path).startswith("reports/audits/")
        and relative_path.name != "audit_summary.json"
    )


def read_csv_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def format_report_datetime(value: object) -> str:
    if value in {None, ""}:
        return "-"
    raw_value = str(value)
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return raw_value
    months = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return (
        f"{parsed.day} {months[parsed.month - 1]} {parsed.year}"
        f" à {parsed.hour:02d}:{parsed.minute:02d}"
    )


def audit_score_title(score: int) -> str:
    if score >= 75:
        return "Base globalement solide"
    if score >= 60:
        return "Base crédible, avec des optimisations visibles"
    return "Potentiel clair, mais plusieurs points sautent aux yeux"


def build_audit_hero_summary(
    score: int,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
) -> str:
    top_signal = ""
    if business_signals:
        top_signal = client_signal_label(
            str(business_signals[0].get("key") or ""),
            str(business_signals[0].get("signal") or ""),
        ).lower()

    if score >= 75:
        intro = "Le site donne une impression plutôt rassurante à première lecture."
    elif score >= 60:
        intro = "Le site repose sur une base crédible, avec plusieurs améliorations faciles à illustrer."
    else:
        intro = "Le site laisse apparaître plusieurs points visibles qui peuvent nourrir une prise de contact."

    if top_signal:
        intro += f" Le sujet le plus lisible aujourd'hui concerne {top_signal}."

    content_pages = int(summary.get("content_like_pages", 0) or 0)
    if content_pages:
        intro += f" L'analyse s'appuie sur {content_pages} contenus repérés sur le site."
    return intro


def sanitize_report_variant(variant: str) -> str:
    return "portfolio" if variant == "portfolio" else "full"


def client_report_subtitle() -> str:
    return "Analyse rapide d’un site de contenu pour repérer les pages à reprendre en priorité."


def client_score_label(score: int) -> str:
    if score >= 75:
        return "Base observée : plutôt saine"
    if score >= 60:
        return "Base observée : saine, avec plusieurs reprises utiles"
    return "Base observée : premiers signaux à corriger"


def client_score_note(score: int, pages_crawled: int) -> str:
    return (
        f"Lecture fondée sur {pages_crawled} page(s) publiques visitées. "
        f"L’indicateur {score}/100 aide à situer l’ensemble, sans prétendre résumer à lui seul la qualité du site."
    )


def client_scope_summary(summary: dict[str, object], pages_crawled: int) -> str:
    content_pages = int(summary.get("content_like_pages", 0) or 0)
    if content_pages:
        return f"{pages_crawled} pages visitées, dont {content_pages} pages de contenu réellement utiles pour la lecture."
    return f"{pages_crawled} pages publiques visitées pour établir une première lecture structurée."


def top_priority_summary(top_pages: list[dict[str, object]]) -> str:
    if not top_pages:
        return "Aucune page prioritaire nette n’a été isolée."
    first_targets = ", ".join(format_url_display(str(item.get("url") or "")) for item in top_pages[:2] if item.get("url"))
    if not first_targets:
        return "Quelques pages ressortent, mais demandent encore une vérification manuelle."
    return f"Les premières pages à regarder sont {first_targets}."


def build_client_takeaways(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if business_signals:
        lines.append(
            f"Le signal qui ressort en premier concerne {client_signal_label(str(business_signals[0].get('key') or ''), str(business_signals[0].get('signal') or '')).lower()}."
        )
    if int(summary.get("content_like_pages", 0) or 0):
        lines.append(
            f"Le site présente une base de contenus suffisante pour prioriser des reprises ciblées avant de produire du neuf."
        )
    if top_pages:
        lines.append(
            f"Quelques pages permettent de matérialiser rapidement l’analyse avec des exemples concrets à montrer."
        )
    return lines[:3]


def build_client_actions(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[str]:
    actions: list[str] = []
    if int(summary.get("dated_content_signals", 0) or 0):
        actions.append("Vérifier que les dates visibles correspondent bien à l’état réel des contenus importants.")
    if int(summary.get("thin_content_pages", 0) or 0):
        actions.append("Retravailler d’abord les pages les plus légères avant d’ouvrir de nouveaux sujets.")
    if int(summary.get("possible_content_overlap_pairs", 0) or 0):
        actions.append("Clarifier l’angle des contenus qui semblent répondre au même besoin.")
    if int(summary.get("probable_orphan_pages", 0) or 0) or int(summary.get("weak_internal_linking_pages", 0) or 0):
        actions.append("Renforcer le maillage interne depuis les pages déjà visibles ou déjà bien positionnées.")
    if top_pages:
        actions.append("Prioriser 2 à 3 pages à reprendre en premier pour montrer rapidement un avant / après.")
    if not actions:
        actions.append("Vérifier manuellement les pages les plus visibles avant de décider d’un plan de reprise.")
    return actions[:5]


def build_primary_rationale(
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if business_signals:
        lines.append(
            f"Le rapport fait ressortir en priorité : {client_signal_label(str(business_signals[0].get('key') or ''), str(business_signals[0].get('signal') or '')).lower()}."
        )
    if int(summary.get("weak_internal_linking_pages", 0) or 0):
        lines.append("Certaines pages semblent peu soutenues par les liens internes, ce qui limite leur visibilité dans le site.")
    if int(summary.get("possible_content_overlap_pairs", 0) or 0):
        lines.append("Plusieurs contenus paraissent proches dans leur intention, ce qui brouille parfois la lecture éditoriale.")
    if int(summary.get("dated_content_signals", 0) or 0):
        lines.append("Certaines dates visibles méritent une vérification, car elles influencent directement l’impression de fraîcheur.")
    return lines[:4]


def build_method_lines(summary: dict[str, object], pages_crawled: int) -> list[str]:
    content_pages = int(summary.get("content_like_pages", 0) or 0)
    return [
        f"Lecture fondée sur {pages_crawled} pages publiques visitées.",
        f"{content_pages} page(s) de contenu ont été retenues pour établir les priorités." if content_pages else "Le rapport repose sur les pages réellement accessibles pendant l’analyse.",
        "L’objectif est de prioriser les reprises utiles, pas de produire un audit exhaustif du site.",
    ]


def should_render_secondary_signal_section(
    overlaps: list[dict[str, object]],
    dated_content: list[dict[str, object]],
    business_signals: list[dict[str, object]],
) -> bool:
    return bool(overlaps or dated_content or business_signals)


def format_url_display(url: str, max_length: int = 58) -> str:
    if not url:
        return "-"
    cleaned = url.replace("https://", "").replace("http://", "").rstrip("/")
    return cleaned if len(cleaned) <= max_length else cleaned[: max_length - 1].rstrip("/") + "…"


def client_signal_label(signal_key: str, fallback: str) -> str:
    labels = {
        "thin_content_pages": "Pages à reprendre en priorité",
        "duplicate_title_groups": "Titres Google trop proches d’une page à l’autre",
        "duplicate_meta_description_groups": "Descriptions Google à clarifier",
        "dated_content_signals": "Dates visibles à vérifier",
        "probable_orphan_pages": "Pages peu mises en avant dans le site",
        "weak_internal_linking_pages": "Pages peu soutenues par les liens internes",
        "deep_pages_detected": "Pages éloignées de l’accueil",
        "possible_content_overlap_pairs": "Contenus trop proches sur le même sujet",
    }
    return labels.get(signal_key, fallback or "Aucune priorité nette")


def client_reason_label(reason: str) -> str:
    labels = {
        "contenu à enrichir pour mieux répondre à la recherche": "contenu à renforcer pour mieux couvrir le sujet",
        "date visible à actualiser": "date visible à vérifier",
        "page difficile à retrouver dans le site": "page peu visible dans la navigation",
        "peu de liens internes vers cette page": "page peu soutenue par les liens internes",
        "page trop éloignée de l'accueil": "page assez loin de l’accueil",
        "description Google absente": "description Google absente",
        "titre Google absent": "titre Google absent",
    }
    return labels.get(reason, reason)


def client_finding_text(finding: str) -> str:
    cleaned = finding.strip()
    replacements = {
        " pages affichent une date qui peut donner une impression de contenu ancien": " pages affichent des dates visibles à vérifier",
        " paires de pages semblent répondre à la même intention": " paires de pages semblent traiter le même sujet",
        " pages reçoivent trop peu de liens internes pour bien remonter": " pages reçoivent peu de liens internes",
        " pages importantes semblent trop éloignées de l'accueil": " pages importantes semblent assez éloignées de l’accueil",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    return cleaned


def file_view_link(path: str, variant: str) -> str:
    return f"/files?path={quote(path)}&variant={quote(variant)}"


def render_report_intro_cards(
    summary: dict[str, object],
    pages_crawled: int,
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> str:
    signal_label = (
        client_signal_label(
            str(business_signals[0].get("key") or ""),
            str(business_signals[0].get("signal") or ""),
        )
        if business_signals
        else "Aucune priorité nette"
    )
    return (
        "<div class='report-intro-grid'>"
        f"<article class='report-summary-card'><span class='report-summary-label'>Ce qui a été analysé</span><strong>{html.escape(client_scope_summary(summary, pages_crawled))}</strong></article>"
        f"<article class='report-summary-card'><span class='report-summary-label'>Ce qui ressort d'abord</span><strong>{html.escape(signal_label)}</strong></article>"
        f"<article class='report-summary-card'><span class='report-summary-label'>Pages à revoir d'abord</span><strong>{html.escape(top_priority_summary(top_pages))}</strong></article>"
        "</div>"
    )


def render_client_decision_block(actions: list[str]) -> str:
    return (
        "<section class='subpanel report-action-panel'>"
        "<h2>Ce que ce rapport permet de décider</h2>"
        f"{render_string_list(actions, empty_label='Aucune action simple n’a été isolée.')}"
        "</section>"
    )


def render_cover_brief_grid(
    observed_score: int,
    pages_crawled: int,
    summary: dict[str, object],
    top_pages: list[dict[str, object]],
) -> str:
    pages_to_review = min(len(top_pages), 3)
    cards = [
        ("Base observée", client_score_label(observed_score).replace("Base observée : ", "")),
        ("Pages analysées", f"{pages_crawled} pages analysées"),
        ("Contenus utiles", f"{_as_int(summary.get('content_like_pages'))} contenus utiles"),
        ("Pages à revoir d’abord", f"{pages_to_review} pages à revoir d’abord"),
    ]
    body = "".join(
        "<article class='report-summary-card cover-brief-card'>"
        f"<span class='report-summary-label'>{html.escape(label)}</span>"
        f"<strong>{html.escape(value)}</strong>"
        "</article>"
        for label, value in cards
    )
    return f"<div class='cover-brief-grid'>{body}</div>"


def render_cover_signal_block(business_signals: list[dict[str, object]]) -> str:
    if business_signals:
        signal_label = client_signal_label(
            str(business_signals[0].get("key") or ""),
            str(business_signals[0].get("signal") or ""),
        )
    else:
        signal_label = "Aucun signal prioritaire net n’a été isolé à ce stade."
    return (
        "<section class='subpanel cover-side-card'>"
        "<h2>Signal principal</h2>"
        f"<p class='cover-strong-line'>{html.escape(signal_label)}</p>"
        "</section>"
    )


def render_cover_top_pages_block(top_pages: list[dict[str, object]]) -> str:
    if not top_pages:
        body = "<p class='muted'>Aucune page prioritaire n’a été isolée.</p>"
    else:
        items = "".join(
            "<li>"
            f"<a class='cover-url-link' href='{html.escape(str(item.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(format_url_display(str(item.get('url') or ''), max_length=78))}</a>"
            "</li>"
            for item in top_pages[:3]
        )
        body = f"<ul class='clean-list cover-url-list'>{items}</ul>"
    return (
        "<section class='subpanel cover-side-card'>"
        "<h2>Premières pages à regarder</h2>"
        f"{body}"
        "</section>"
    )


def render_cover_decision_block(actions: list[str]) -> str:
    lines = actions[:3]
    return (
        "<section class='subpanel cover-side-card'>"
        "<h2>Ce que ce rapport aide à décider</h2>"
        f"{render_string_list(lines, empty_label='Aucune décision simple n’a été isolée.')}"
        "</section>"
    )


def render_portfolio_method_strip(lines: list[str]) -> str:
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    return (
        "<section class='subpanel portfolio-method-strip'>"
        "<h2>Méthode de lecture</h2>"
        f"<ul class='clean-list'>{items}</ul>"
        "</section>"
    )


def render_portfolio_priority_grid(top_pages: list[dict[str, object]], pages_by_url: dict[str, dict[str, object]]) -> str:
    if not top_pages:
        return "<p class='muted'>Aucune page prioritaire n’a été isolée pour cette version courte.</p>"
    return render_top_pages_to_rework(top_pages[:3], pages_by_url)


def render_full_report_layout(
    domain: str,
    observed_score: int,
    pages_crawled: int,
    subtitle: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    critical_findings: list[str],
    confidence_notes: list[str],
    overlaps: list[dict[str, object]],
    dated_content: list[dict[str, object]],
    pages_by_url: dict[str, dict[str, object]],
) -> str:
    takeaways = build_client_takeaways(summary, business_signals, top_pages)
    actions = build_client_actions(summary, business_signals, top_pages)
    rationale = build_primary_rationale(summary, business_signals)
    client_findings = [client_finding_text(str(item)) for item in critical_findings]
    cover_brief_grid = render_cover_brief_grid(observed_score, pages_crawled, summary, top_pages)
    cover_signal_block = render_cover_signal_block(business_signals)
    cover_top_pages_block = render_cover_top_pages_block(top_pages)
    cover_decision_block = render_cover_decision_block(actions)
    decision_block = render_client_decision_block(actions)
    secondary_sections = ""
    if should_render_secondary_signal_section(overlaps, dated_content, business_signals):
        secondary_sections = f"""
        <section class="report-page report-page-secondary">
          <section class="subpanel">
            <h2>Repères complémentaires</h2>
            <p class="section-intro">Cette page complète la synthèse avec les chiffres utiles et les signaux qui demandent une vérification plus fine.</p>
            {render_summary_key_figures(summary)}
          </section>
          <div class="grid two audit-report-grid">
            <section class="subpanel">
              <h2>Signaux secondaires</h2>
              {render_business_signals(business_signals, {"possible_content_overlap": overlaps, "dated_content_signals": dated_content, "top_pages_to_rework": top_pages, "duplicate_titles": {}, "duplicate_meta_descriptions": {}, "probable_orphan_pages": []})}
            </section>
            <section class="subpanel">
              <h2>Éléments à vérifier</h2>
              {render_dated_signals(dated_content) if dated_content else render_overlap_pairs(overlaps)}
            </section>
          </div>
        </section>
        """
    return f"""
    <section class="report-page report-page-cover">
      <div class="audit-report-topbar">
        <div class="audit-report-heading">
          <p class="eyebrow">Audit SEO</p>
          <h1>{html.escape(domain)}</h1>
          <p class="lede">{html.escape(subtitle)}</p>
        </div>
      </div>
      <div class="cover-layout-grid">
        <section class="audit-hero-card audit-hero-primary cover-main-card">
          <p class="audit-hero-surtitle">En bref</p>
          <h2>{html.escape(client_score_label(observed_score))}</h2>
          <p class="audit-hero-copy">{html.escape(build_audit_hero_summary(observed_score, summary, business_signals))}</p>
          <p class="audit-score-explainer">Cette première page aide à repérer rapidement l’état général du site, le point qui ressort en premier et les pages à regarder d’abord.</p>
          {cover_brief_grid}
        </section>
        <aside class="cover-side-stack">
          {cover_signal_block}
          {cover_top_pages_block}
          {cover_decision_block}
        </aside>
      </div>
    </section>

    <section class="report-page report-page-reading">
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>Lecture rapide</h2>
          {render_string_list(takeaways, empty_label="Pas assez d’éléments pour sortir une lecture claire.")}
        </section>
        <section class="subpanel">
          <h2>Pourquoi ce point compte</h2>
          {render_string_list(rationale, empty_label="Aucun point secondaire notable à signaler.")}
        </section>
      </div>
      {decision_block}
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>Points à corriger d’abord</h2>
          {render_string_list(client_findings, empty_label="Aucun point prioritaire n’a été remonté.")}
        </section>
        <section class="subpanel">
          <h2>À garder en tête</h2>
          {render_string_list(confidence_notes, empty_label="Aucune précision complémentaire.")}
        </section>
      </div>
    </section>

    <section class="report-page report-page-priority">
      <section class="subpanel">
        <h2>Pages à revoir en priorité</h2>
        <p class="section-intro">Ces pages donnent les exemples les plus concrets pour décider d’une reprise ciblée.</p>
        {render_top_pages_to_rework(top_pages, pages_by_url)}
      </section>
    </section>

    {secondary_sections}
    """


def render_portfolio_report_layout(
    domain: str,
    observed_score: int,
    pages_crawled: int,
    subtitle: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    critical_findings: list[str],
    pages_by_url: dict[str, dict[str, object]],
) -> str:
    actions = build_client_actions(summary, business_signals, top_pages)
    method_lines = build_method_lines(summary, pages_crawled)
    client_findings = [client_finding_text(str(item)) for item in critical_findings]
    signal_label = (
        client_signal_label(
            str(business_signals[0].get("key") or ""),
            str(business_signals[0].get("signal") or ""),
        )
        if business_signals
        else "Aucune priorité nette"
    )
    return f"""
    <section class="report-page portfolio-page portfolio-cover">
      <div class="audit-report-topbar">
        <div class="audit-report-heading">
          <p class="eyebrow">Extrait portfolio</p>
          <h1>{html.escape(domain)}</h1>
          <p class="lede">{html.escape(subtitle)}</p>
        </div>
      </div>
      <div class="audit-hero-grid portfolio-hero-grid">
        <section class="audit-hero-card audit-hero-primary">
          <p class="audit-hero-surtitle">Ce qui ressort en premier</p>
          <h2>{html.escape(client_score_label(observed_score))}</h2>
          <p class="audit-hero-copy">{html.escape(build_audit_hero_summary(observed_score, summary, business_signals))}</p>
          <div class="portfolio-kpi-grid">
            <article class="report-summary-card"><span class="report-summary-label">Signal principal</span><strong>{html.escape(signal_label)}</strong></article>
            <article class="report-summary-card"><span class="report-summary-label">Pages visitées</span><strong>{pages_crawled}</strong></article>
            <article class="report-summary-card"><span class="report-summary-label">Contenus utiles</span><strong>{summary.get("content_like_pages", 0)}</strong></article>
          </div>
        </section>
        <aside class="audit-hero-card audit-hero-secondary">
          <p class="audit-side-label">Repère</p>
          <div class="audit-hero-stat-block">
            <span class="audit-status-chip">{html.escape(client_score_label(observed_score))}</span>
            <strong>{observed_score}/100</strong>
            <p>{html.escape(client_score_note(observed_score, pages_crawled))}</p>
          </div>
          {render_portfolio_method_strip(method_lines)}
        </aside>
      </div>
    </section>

    <section class="report-page portfolio-page portfolio-details">
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>Ce que l’analyse fait apparaître</h2>
          {render_string_list(client_findings[:4], empty_label="Aucun point prioritaire net n’a été isolé.")}
        </section>
        <section class="subpanel">
          <h2>Premières actions suggérées</h2>
          {render_string_list(actions, empty_label="Aucune action simple n’a été isolée.")}
        </section>
      </div>
      <section class="subpanel">
        <h2>Pages à revoir en premier</h2>
        {render_portfolio_priority_grid(top_pages, pages_by_url)}
      </section>
    </section>
    """


def render_audit_report_page(path: Path, relative_path: Path, file_size: str, variant: str = "full") -> str:
    active_variant = sanitize_report_variant(variant)
    payload = json.loads(path.read_text("utf-8"))
    domain = str(payload.get("domain") or relative_path.stem)
    summary = payload.get("summary") or {}
    business_signals = payload.get("business_priority_signals") or []
    top_pages = payload.get("top_pages_to_rework") or []
    overlaps = payload.get("possible_content_overlap") or []
    confidence_notes = payload.get("confidence_notes") or []
    critical_findings = payload.get("critical_findings") or []
    dated_content = payload.get("dated_content_signals") or []
    observed_score = _as_int(payload.get("observed_health_score"))
    subtitle = client_report_subtitle()
    pages_by_url = {
        str(page.get("url")): page
        for page in (payload.get("pages") or [])
        if isinstance(page, dict) and page.get("url")
    }
    switch_variant = "portfolio" if active_variant == "full" else "full"
    switch_label = "Version portfolio" if active_variant == "full" else "Version complète"
    variant_content = (
        render_full_report_layout(
            domain=domain,
            observed_score=observed_score,
            pages_crawled=_as_int(payload.get("pages_crawled")),
            subtitle=subtitle,
            summary=summary,
            business_signals=business_signals,
            top_pages=top_pages,
            critical_findings=critical_findings,
            confidence_notes=confidence_notes or payload.get("notes") or [],
            overlaps=overlaps,
            dated_content=dated_content,
            pages_by_url=pages_by_url,
        )
        if active_variant == "full"
        else render_portfolio_report_layout(
            domain=domain,
            observed_score=observed_score,
            pages_crawled=_as_int(payload.get("pages_crawled")),
            subtitle=subtitle,
            summary=summary,
            business_signals=business_signals,
            top_pages=top_pages,
            critical_findings=critical_findings,
            pages_by_url=pages_by_url,
        )
    )
    content = f"""
    <section class="panel file-shell audit-report-shell audit-report-variant-{html.escape(active_variant)}">
      <div class="panel-actions audit-report-actions no-print report-toolbar">
        <button class="button print-button" type="button" onclick="window.print()">Exporter en PDF</button>
        <a class="button secondary" href="{file_view_link(str(relative_path), switch_variant)}">{switch_label}</a>
        <a class="button secondary" href="/">Retour home</a>
      </div>
      {variant_content}
    </section>
    """
    return page_shell(f"Audit - {domain}", content)


def render_string_list(items: list[str], empty_label: str) -> str:
    if not items:
        return f"<p class='muted'>{html.escape(empty_label)}</p>"
    body = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul class='clean-list'>{body}</ul>"


def render_business_signals(items: list[dict[str, object]], payload: dict[str, object]) -> str:
    if not items:
        return "<p class='muted'>Aucune opportunité prioritaire n'a été repérée.</p>"
    cards: list[str] = []
    for item in items[:8]:
        severity = str(item.get("severity") or "")
        signal_key = str(item.get("key") or "")
        signal_label = client_signal_label(signal_key, str(item.get("signal") or "Signal"))
        tone = "signal-medium"
        severity_label = "À surveiller"
        if severity == "HIGH":
            tone = "signal-high"
            severity_label = "Priorité forte"
        examples_html = render_signal_examples(signal_key, payload)
        cards.append(
            "<div class='signal-row-card'>"
            "<div class='signal-row'>"
            f"<span class='pill signal-pill {tone}'>{html.escape(severity_label)}</span>"
            f"<strong>{html.escape(signal_label)}</strong>"
            f"<span>{html.escape(str(item.get('count') or 0))}</span>"
            "</div>"
            f"<p class='signal-help'>{html.escape(signal_helper_text(signal_key))}</p>"
            f"{examples_html}"
            "</div>"
        )
    return "<div class='signal-list'>" + "".join(cards) + "</div>"


def signal_helper_text(signal_key: str) -> str:
    helpers = {
        "thin_content_pages": "Ces pages méritent un enrichissement pour mieux répondre à la recherche.",
        "duplicate_title_groups": "Plusieurs pages envoient presque la même promesse dans Google.",
        "duplicate_meta_description_groups": "Le texte affiché sous le résultat Google semble répété sur plusieurs pages.",
        "dated_content_signals": "Une date visible mérite d’être vérifiée car elle influence la perception du contenu.",
        "probable_orphan_pages": "Certaines pages semblent difficiles à retrouver depuis le reste du site.",
        "weak_internal_linking_pages": "Certaines pages reçoivent trop peu de liens internes pour être bien soutenues.",
        "deep_pages_detected": "Certaines pages paraissent trop éloignées de la page d'accueil.",
        "possible_content_overlap_pairs": "Certaines pages semblent répondre au même besoin et peuvent se concurrencer.",
    }
    return helpers.get(signal_key, "Ce signal mérite une vérification manuelle dans le contexte du site.")


def render_signal_examples(signal_key: str, payload: dict[str, object]) -> str:
    examples = build_signal_examples(signal_key, payload)
    if not examples:
        return ""
    body = "".join(f"<li>{html.escape(example)}</li>" for example in examples[:5])
    return (
        "<details class='signal-details'>"
        "<summary>Voir des exemples concrets</summary>"
        f"<ul class='clean-list signal-example-list'>{body}</ul>"
        "</details>"
    )


def build_signal_examples(signal_key: str, payload: dict[str, object]) -> list[str]:
    top_pages = payload.get("top_pages_to_rework") or []
    overlaps = payload.get("possible_content_overlap") or []
    dated_content = payload.get("dated_content_signals") or []
    duplicate_titles = payload.get("duplicate_titles") or {}
    duplicate_metas = payload.get("duplicate_meta_descriptions") or {}
    probable_orphans = payload.get("probable_orphan_pages") or []

    if signal_key == "dated_content_signals":
        return [
            f"{format_url_display(str(item.get('url', '-')))} : {', '.join(str(ref) for ref in item.get('references', [])[:2])}"
            for item in dated_content[:5]
        ]
    if signal_key == "possible_content_overlap_pairs":
        return [
            f"{item.get('title_1', '-')} / {item.get('title_2', '-')} ({item.get('similarity', 0)}%)"
            for item in overlaps[:5]
        ]
    if signal_key == "probable_orphan_pages":
        return [format_url_display(str(url)) for url in probable_orphans[:5]]
    if signal_key in {"thin_content_pages", "weak_internal_linking_pages", "deep_pages_detected"}:
        reason_map = {
            "thin_content_pages": "contenu à enrichir pour mieux répondre à la recherche",
            "weak_internal_linking_pages": "peu de liens internes vers cette page",
            "deep_pages_detected": "page trop éloignée de l'accueil",
        }
        reason = reason_map[signal_key]
        return [
            f"{format_url_display(str(item.get('url', '-')))}"
            for item in top_pages
            if reason in [str(value) for value in item.get("reasons", [])]
        ][:5]
    if signal_key == "duplicate_title_groups":
        return [
            f"\"{title}\" repris sur {len(urls)} pages"
            for title, urls in list(duplicate_titles.items())[:5]
        ]
    if signal_key == "duplicate_meta_description_groups":
        return [
            f"Même texte de présentation repris sur {len(urls)} pages"
            for _meta, urls in list(duplicate_metas.items())[:5]
        ]
    return []


def priority_score_label(value: object) -> str:
    score = _as_int(value)
    if score >= 10:
        return "priorité de reprise : très élevée"
    if score >= 7:
        return "priorité de reprise : élevée"
    if score >= 4:
        return "priorité de reprise : modérée"
    return "priorité de reprise : légère"


def depth_label(value: object) -> str:
    depth = _as_int(value)
    if depth <= 0:
        return "accès depuis l'accueil : page d'entrée"
    if depth == 1:
        return "accès depuis l'accueil : 1 clic"
    return f"accès depuis l'accueil : {depth} clics"


def render_top_pages_to_rework(items: list[dict[str, object]], pages_by_url: dict[str, dict[str, object]]) -> str:
    if not items:
        return "<p class='muted'>Aucune page prioritaire n'a été remontée.</p>"
    cards: list[str] = []
    for item in items[:6]:
        reasons = item.get("reasons") or []
        page_details = pages_by_url.get(str(item.get("url") or ""), {})
        confidence = confidence_label(str(item.get("confidence") or ""))
        priority_label = priority_score_label(item.get("priority_score"))
        page_depth_label = depth_label(item.get("depth"))
        display_url = format_url_display(str(item.get("url") or ""), max_length=72)
        chips = "".join(
            f"<span class='priority-chip'>{html.escape(client_reason_label(str(reason)))}</span>"
            for reason in reasons
        )
        issue_block = render_page_issue_details(page_details)
        cards.append(
            "<article class='page-priority-card'>"
            f"<a class='page-url' href='{html.escape(str(item.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(display_url)}</a>"
            f"<div class='page-priority-meta'><span class='audit-pages-pill'>{html.escape(priority_label)}</span>"
            f"<span class='audit-pages-pill'>{html.escape(str(item.get('word_count') or 0))} mots</span>"
            f"<span class='audit-pages-pill'>{html.escape(page_depth_label)}</span>"
            f"<span class='audit-pages-pill'>{html.escape(confidence)}</span></div>"
            f"<div class='audit-compact-body'>{chips or '<span class=\"muted\">Aucune raison spécifiée.</span>'}</div>"
            f"{issue_block}"
            "</article>"
        )
    return "<div class='page-priority-list'>" + "".join(cards) + "</div>"


def render_commercial_read(
    domain: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> str:
    lines = build_commercial_read_lines(domain, summary, business_signals, top_pages)
    return render_string_list(lines, empty_label="Pas assez d'elements pour sortir une lecture commerciale.")


def build_commercial_read_lines(
    domain: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if business_signals:
        lead_signal = business_signals[0]
        lines.append(
            f"Pour {domain}, le point le plus simple à valoriser commercialement est : {str(lead_signal.get('signal') or 'une remise à niveau ciblée des contenus').lower()}."
        )
    content_pages = int(summary.get("content_like_pages", 0) or 0)
    if content_pages:
        lines.append(
            f"L'analyse a repéré {content_pages} pages qui ressemblent à de vrais contenus, ce qui suffit pour illustrer des gains rapides."
        )
    if top_pages:
        first_urls = ", ".join(str(item.get("url") or "-") for item in top_pages[:2])
        lines.append(f"Les premières pages à montrer dans un message ou une courte vidéo sont : {first_urls}.")
    if not lines:
        lines.append("Le rapport reste trop léger pour formuler un angle commercial fiable sans vérification manuelle.")
    return lines


def render_reusable_summary(
    domain: str,
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    summary: dict[str, object],
) -> str:
    pitch = build_reusable_summary_text(domain, business_signals, top_pages, summary)
    return (
        f"<div class='copy-block'><p>{html.escape(pitch)}</p></div>"
        "<p class='field-help'>Ce texte reste volontairement prudent. Tu peux le reprendre dans un message, une courte vidéo ou un autre outil. Le JSON téléchargé reste la version structurée la plus exploitable.</p>"
    )


def build_reusable_summary_text(
    domain: str,
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    summary: dict[str, object],
) -> str:
    signal_labels = [str(item.get("signal") or "").strip().lower() for item in business_signals[:2] if item.get("signal")]
    if signal_labels:
        signals_part = " et ".join(signal_labels)
    else:
        signals_part = "plusieurs signaux éditoriaux à vérifier"

    page_targets = ", ".join(str(item.get("url") or "-") for item in top_pages[:2])
    if not page_targets:
        page_targets = "quelques pages prioritaires du site"

    content_pages = int(summary.get("content_like_pages", 0) or 0)
    return (
        f"En regardant {domain}, le crawl observé remonte surtout {signals_part}. "
        f"Le site présente environ {content_pages} pages qui ressemblent à de vrais contenus, ce qui rend une mise à niveau éditoriale crédible. "
        f"Les premières URLs à revoir seraient {page_targets}. "
        "L'opportunité semble davantage liée à la clarté des contenus et à leur mise en avant qu'à un problème purement technique."
    )


def render_audit_report_next_steps(relative_path: Path, top_pages: list[dict[str, object]]) -> str:
    download_link = f"/download?path={quote(str(relative_path))}"
    steps = [
        "Ouvre 2 ou 3 URLs prioritaires dans le navigateur pour verifier rapidement si les constats se confirment visuellement.",
        f"<a class='subtle-link' href='{download_link}'>Télécharge le JSON</a> si tu veux le réutiliser dans un autre outil, un script ou une automatisation.",
    ]
    if top_pages:
        first_target = str(top_pages[0].get("url") or "")
        if first_target:
            steps.append(
                f"Commence par {external_anchor(first_target, 'ouvrir la page la plus prioritaire')} pour préparer un exemple concret."
            )
    body = "".join(f"<li>{step}</li>" for step in steps)
    return f"<ul class='clean-list'>{body}</ul>"


def external_anchor(url: str, label: str) -> str:
    return f"<a class='subtle-link' href='{html.escape(url)}' target='_blank' rel='noreferrer'>{html.escape(label)}</a>"


def confidence_label(value: str) -> str:
    mapping = {
        "medium-high": "lecture assez solide",
        "medium": "lecture à confirmer",
        "low": "lecture à vérifier",
    }
    return mapping.get(value, value or "confiance non précisée")


def render_page_issue_details(page: dict[str, object]) -> str:
    issues = [str(issue) for issue in (page.get("issues") or [])[:6]]
    dated_refs = [str(ref) for ref in (page.get("dated_references") or [])[:4]]
    if not issues and not dated_refs:
        return ""
    items = "".join(f"<li>{html.escape(issue)}</li>" for issue in issues)
    items += "".join(f"<li>{html.escape(ref)}</li>" for ref in dated_refs)
    return (
        "<details class='signal-details'>"
        "<summary>Voir les éléments relevés sur cette page</summary>"
        f"<ul class='clean-list signal-example-list'>{items}</ul>"
        "</details>"
    )


def render_overlap_pairs(items: list[dict[str, object]]) -> str:
    if not items:
        return "<p class='muted'>Aucun sujet trop proche n'a été repéré parmi les pages analysées.</p>"
    rows: list[str] = []
    for item in items[:6]:
        rows.append(
            "<article class='pair-card'>"
            f"<strong>{html.escape(str(item.get('similarity') or 0))}% de similarité</strong>"
            f"<p>{html.escape(str(item.get('title_1') or '-'))}</p>"
            f"<p>{html.escape(str(item.get('title_2') or '-'))}</p>"
            "</article>"
        )
    return "<div class='pair-list'>" + "".join(rows) + "</div>"


def render_dated_signals(items: list[dict[str, object]]) -> str:
    if not items:
        return "<p class='muted'>Aucune date à actualiser n'a été repérée sur les pages analysées.</p>"
    rows: list[str] = []
    for item in items[:6]:
        references = item.get("references") or []
        refs = "".join(f"<span class='priority-chip'>{html.escape(str(ref))}</span>" for ref in references[:3])
        display_url = format_url_display(str(item.get("url") or ""), max_length=72)
        rows.append(
            "<article class='pair-card'>"
            f"<a class='page-url' href='{html.escape(str(item.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(display_url)}</a>"
            f"<div class='audit-compact-body'>{refs}</div>"
            "</article>"
        )
    return "<div class='pair-list'>" + "".join(rows) + "</div>"


def render_summary_key_figures(summary: dict[str, object]) -> str:
    if not summary:
        return "<p class='muted'>Aucun résumé chiffré disponible.</p>"
    preferred_keys = [
        ("pages_ok", "Pages saines"),
        ("pages_with_errors", "Pages en erreur"),
        ("missing_meta_descriptions", "Descriptions Google manquantes"),
        ("missing_h1", "Titres principaux manquants"),
        ("weak_internal_linking_pages", "Pages peu reliées"),
        ("possible_content_overlap_pairs", "Sujets trop proches"),
        ("dated_content_signals", "Dates visibles à vérifier"),
    ]
    cards: list[str] = []
    for key, label in preferred_keys:
        cards.append(render_metric_card(label, str(summary.get(key, 0)), ""))
    return "<div class='audit-metric-grid'>" + "".join(cards) + "</div>"


def render_audit_summary_preview(path: Path, max_rows: int = 8) -> str:
    _, rows = read_csv_table(path)
    if not rows:
        return "<p class='muted'>CSV vide.</p>"

    top_rows = rows[:max_rows]
    cards = "".join(render_audit_summary_compact_card(row) for row in top_rows)
    return f"<div class='audit-summary-preview'>{cards}</div>"


def render_audit_summary_page(path: Path, file_size: str) -> str:
    _, rows = read_csv_table(path)
    if not rows:
        empty = """
        <section class="panel file-shell">
          <div class="panel-head">
            <div>
              <p class="eyebrow">Vue d'ensemble des audits</p>
              <h1>reports/audits/audit_summary.csv</h1>
              <p class="lede">Aucun audit disponible pour l'instant.</p>
            </div>
            <div class="panel-actions">
              <a class="button secondary" href="/">Retour home</a>
            </div>
          </div>
        </section>
        """
        return page_shell("Audit Summary", empty)

    metrics = compute_audit_summary_metrics(rows)
    table = render_audit_summary_table(rows)
    metric_cards = "".join(
        [
            render_metric_card("Sites analysés", str(metrics["domains"]), "audits présents dans ce récapitulatif"),
            render_metric_card("Note moyenne", str(metrics["avg_score"]), "état moyen observé"),
            render_metric_card("Sites à surveiller", str(metrics["watch_domains"]), "sites avec une note observée < 70"),
            render_metric_card("Dates à actualiser", str(metrics["dated_signals"]), "occurrences repérées"),
        ]
    )

    content = f"""
    <section class="panel file-shell audit-shell">
      <div class="panel-head">
        <div>
          <p class="eyebrow">Vue d'ensemble des audits</p>
          <h1>reports/audits/audit_summary.csv</h1>
          <p class="lede">Vue simple pour repérer rapidement les sites qui montrent le plus d'opportunités d'amélioration.</p>
        </div>
        <div class="panel-actions">
          <a class="button secondary" href="/">Retour home</a>
        </div>
      </div>
      <div class="meta-grid file-meta">
        <div><strong>Type</strong><span>Tableau récapitulatif</span></div>
        <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
        <div><strong>Lignes</strong><span>{metrics["domains"]}</span></div>
        <div><strong>Colonnes</strong><span>{metrics["columns"]}</span></div>
      </div>
      <section class="subpanel">
        <h2>Vue rapide</h2>
        <div class="audit-metric-grid">{metric_cards}</div>
      </section>
      <section class="subpanel">
        <h2>Sites analysés</h2>
        {table}
      </section>
    </section>
    """
    return page_shell("Audit Summary", content)


def compute_audit_summary_metrics(rows: list[dict[str, str]]) -> dict[str, int]:
    scores = [_as_int(row.get("observed_health_score")) for row in rows]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    watch_domains = sum(1 for score in scores if score < 70)
    dated_signals = sum(_as_int(row.get("dated_content_signals")) for row in rows)
    return {
        "domains": len(rows),
        "columns": len(rows[0]) if rows else 0,
        "avg_score": avg_score,
        "watch_domains": watch_domains,
        "dated_signals": dated_signals,
    }


def render_metric_card(title: str, value: str, note: str) -> str:
    return (
        "<div class='audit-metric-card'>"
        f"<strong>{html.escape(value)}</strong>"
        f"<span>{html.escape(title)}</span>"
        f"<p>{html.escape(note)}</p>"
        "</div>"
    )


def render_audit_summary_compact_card(row: dict[str, str]) -> str:
    domain = row.get("domain", "").strip() or "n/a"
    score = _as_int(row.get("observed_health_score"))
    score_badge = render_health_score_badge(score)
    priorities = render_priority_chips_html(build_priority_labels(row, limit=2))
    json_path = audit_json_relative_path(domain)
    link = f"<a class='subtle-link' href='/files?path={quote(json_path)}'>Voir rapport complet</a>" if (ROOT_DIR / json_path).exists() else ""
    return (
        "<article class='audit-compact-card'>"
        f"<div class='audit-compact-head'><span class='pill domain-pill'>{html.escape(domain)}</span>{score_badge}</div>"
        f"<div class='audit-compact-body'>{priorities or '<span class=\"muted\">Peu de signaux prioritaires dans ce summary.</span>'}</div>"
        f"<div class='audit-compact-foot'>{link}</div>"
        "</article>"
    )


def render_audit_summary_table(rows: list[dict[str, str]]) -> str:
    body_rows: list[str] = []
    for row in rows:
        domain = row.get("domain", "").strip()
        pages = _as_int(row.get("pages_crawled"))
        score = _as_int(row.get("observed_health_score"))
        priorities = build_priority_labels(row, limit=4)
        json_path = audit_json_relative_path(domain)
        json_link = (
            f"<a class='subtle-link' href='/files?path={quote(json_path)}'>Voir rapport complet</a>"
            if (ROOT_DIR / json_path).exists()
            else "<span class='muted'>JSON non trouve</span>"
        )
        body_rows.append(
            "<tr>"
            f"<td><div class='audit-domain-cell'><span class='pill domain-pill'>{html.escape(domain)}</span>{json_link}</div></td>"
            f"<td>{render_health_score_badge(score)}</td>"
            f"<td><span class='audit-pages-pill'>{pages} pages</span></td>"
            f"<td>{render_priority_chips_html(priorities)}</td>"
            f"<td>{html.escape(build_audit_summary_signal_note(row))}</td>"
            "</tr>"
        )
    body = "".join(body_rows)
    return (
        "<div class='table-wrap file-table audit-summary-table'>"
        "<table>"
        "<thead><tr>"
        "<th>Domaine</th>"
        "<th>État observé</th>"
        "<th>Pages analysées</th>"
        "<th>Opportunités prioritaires</th>"
        "<th>Lecture rapide</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )


def render_health_score_badge(score: int) -> str:
    tone = "health-bad"
    label = "à renforcer"
    if score >= 75:
        tone = "health-good"
        label = "plutôt solide"
    elif score >= 60:
        tone = "health-watch"
        label = "a surveiller"
    return f"<span class='pill health-pill {tone}'>{score}/100 · {label}</span>"


def build_priority_labels(row: dict[str, str], limit: int = 4) -> list[str]:
    mapping = [
        ("thin_content_pages", "contenus à enrichir"),
        ("duplicate_title_groups", "titres Google répétés"),
        ("duplicate_meta_description_groups", "descriptions Google répétées"),
        ("possible_content_overlap_pairs", "sujets trop proches"),
        ("probable_orphan_pages", "pages difficiles à retrouver"),
        ("weak_internal_linking_pages", "liens internes insuffisants"),
        ("deep_pages_detected", "pages loin de l'accueil"),
        ("dated_content_signals", "dates à actualiser"),
    ]
    labels: list[str] = []
    for key, label in mapping:
        count = _as_int(row.get(key))
        if count > 0:
            labels.append(f"{label} ({count})")
        if len(labels) >= limit:
            break
    return labels


def render_priority_chips_html(labels: list[str]) -> str:
    if not labels:
        return "<span class='muted'>Rien de saillant ici.</span>"
    return "".join(f"<span class='priority-chip'>{html.escape(label)}</span>" for label in labels)


def build_audit_summary_signal_note(row: dict[str, str]) -> str:
    score = _as_int(row.get("observed_health_score"))
    priorities = build_priority_labels(row, limit=2)
    if not priorities and score >= 75:
        return "Peu d'opportunités prioritaires ressortent dans ce récapitulatif."
    if priorities:
        return "À regarder d'abord : " + ", ".join(priorities)
    return "Audit présent, mais peu de points marquants dans ce résumé."


def audit_json_relative_path(domain: str) -> str:
    return f"reports/audits/{domain}.json"


def render_full_csv_table(path: Path) -> tuple[dict[str, int], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = [row for row in reader]

    if not fieldnames:
        return {"rows": 0, "columns": 0}, "<p class='muted'>CSV vide.</p>"

    headers = "".join(
        f"<th><span class='col-name'>{html.escape(name)}</span></th>"
        for name in fieldnames
    )
    body_rows = []
    for row in rows:
        cells = []
        for name in fieldnames:
            value = (row.get(name) or "").strip()
            cell_class = "cell-empty" if not value else ""
            cells.append(f"<td class='{cell_class}'>{format_csv_cell(name, value)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    body = "".join(body_rows) or f"<tr><td colspan='{len(fieldnames)}'>Aucune ligne.</td></tr>"
    table = (
        "<div class='table-wrap file-table'>"
        "<table>"
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )
    return {"rows": len(rows), "columns": len(fieldnames)}, table


def format_csv_cell(column_name: str, value: str) -> str:
    if not value:
        return "<span class='muted'>-</span>"
    escaped = html.escape(value)
    lower_name = column_name.lower()
    if lower_name == "domain":
        return f"<span class='pill domain-pill'>{escaped}</span>"
    if lower_name in {"source_query", "cms"}:
        return f"<span class='pill soft-pill'>{escaped}</span>"
    if lower_name == "score":
        try:
            score = int(float(value))
        except ValueError:
            return escaped
        tone = "score-low"
        if score >= 70:
            tone = "score-high"
        elif score >= 50:
            tone = "score-mid"
        return f"<span class='pill {tone}'>{score}</span>"
    if lower_name.endswith("provider"):
        return f"<span class='pill provider-pill'>{escaped}</span>"
    if lower_name in {"title", "snippet", "issues", "notes"}:
        return f"<div class='cell-text'>{escaped}</div>"
    return escaped


def human_file_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def _as_int(value: object) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, str):
            return int(float(value.strip() or "0"))
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def resolve_local_file(requested_path: str) -> Path:
    if not requested_path:
        raise CLIError("Chemin de fichier manquant.")
    resolved = (ROOT_DIR / unquote(requested_path)).resolve()
    if ROOT_DIR not in resolved.parents and resolved != ROOT_DIR:
        raise CLIError("Chemin non autorise.")
    return resolved


def delete_managed_file(requested_path: str, cascade: bool = False) -> list[str]:
    path = resolve_local_file(requested_path)
    relative = str(path.relative_to(ROOT_DIR))
    allowed = {
        "data/domains_raw.csv",
        "data/domains_scored.csv",
        "data/domains_scored.json",
    }
    if relative not in allowed:
        raise CLIError("Suppression non autorisee pour ce fichier.")

    deleted: list[str] = []
    targets = [path]
    if cascade and relative == "data/domains_scored.csv":
        targets.append((ROOT_DIR / "data/domains_scored.json").resolve())

    for target in targets:
        if not target.exists():
            continue
        target.unlink()
        deleted.append(str(target.relative_to(ROOT_DIR)))
    return deleted


def reset_pipeline_outputs() -> list[str]:
    deleted: list[str] = []
    candidate_files = [
        "data/domains_raw.csv",
        "data/domains_scored.csv",
        "data/domains_scored.json",
        "reports/gsc_report.csv",
        "reports/gsc_report.json",
        "reports/gsc_report.html",
        "reports/audits/audit_summary.csv",
    ]
    for relative in candidate_files:
        target = (ROOT_DIR / relative).resolve()
        if target.exists():
            target.unlink()
            deleted.append(relative)

    audits_dir = (ROOT_DIR / "reports/audits").resolve()
    if audits_dir.exists():
        for json_file in sorted(audits_dir.glob("*.json")):
            json_file.unlink()
            deleted.append(str(json_file.relative_to(ROOT_DIR)))

    return deleted


def page_shell(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --paper: #fcfaf4;
      --ink: #1f2b24;
      --muted: #66756c;
      --line: #d9d3c3;
      --clay: #d77842;
      --sage: #6f8f72;
      --gold: #b5862c;
      --inkdeep: #22384d;
      --danger: #b34a3c;
      --shadow: 0 14px 40px rgba(59, 48, 27, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(215,120,66,0.16), transparent 24rem),
        radial-gradient(circle at top right, rgba(111,143,114,0.18), transparent 22rem),
        linear-gradient(180deg, #f9f5ec 0%, var(--bg) 100%);
    }}
    a {{ color: inherit; text-decoration: none; }}
    .page {{ max-width: 1260px; margin: 0 auto; padding: 32px 24px 64px; }}
    .hero {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 24px;
      margin-bottom: 28px;
      align-items: stretch;
    }}
    .hero h1 {{
      margin: 0 0 12px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2rem, 4vw, 4rem);
      line-height: 0.98;
      letter-spacing: -0.03em;
    }}
    .lede {{ color: var(--muted); max-width: 52rem; font-size: 1.05rem; }}
    .eyebrow {{
      margin: 0 0 10px;
      color: var(--clay);
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-weight: 700;
      font-size: 0.76rem;
    }}
    .hero-panel, .panel {{
      background: rgba(252,250,244,0.92);
      border: 1px solid rgba(217,211,195,0.9);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }}
    .hero-panel {{
      padding: 18px;
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    .hero-stat {{
      border-radius: 14px;
      padding: 14px;
      background: linear-gradient(135deg, rgba(255,255,255,0.85), rgba(238,234,223,0.85));
      border: 1px solid rgba(217,211,195,0.8);
    }}
    .hero-stat strong {{ display: block; margin-bottom: 4px; }}
    .hero-stat span {{ color: var(--muted); font-size: 0.92rem; }}
    .grid {{ display: grid; gap: 20px; margin-bottom: 20px; }}
    .grid.two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .onboarding-grid {{ grid-template-columns: 1fr; }}
    .panel {{ padding: 22px; }}
    .subpanel {{
      padding: 18px;
      border-radius: 14px;
      background: rgba(255,255,255,0.55);
      border: 1px solid rgba(217,211,195,0.9);
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .panel h2, .subpanel h2 {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 1.45rem;
    }}
    .onboarding-panel {{
      background:
        linear-gradient(135deg, rgba(255,255,255,0.78), rgba(247,241,229,0.92)),
        rgba(252,250,244,0.92);
    }}
    .quick-start-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }}
    .quick-start-card {{
      border-radius: 16px;
      padding: 16px;
      border: 1px solid rgba(217,211,195,0.92);
      background: rgba(255,255,255,0.6);
    }}
    .quick-start-card h3 {{
      margin: 0 0 10px;
      font-size: 1.08rem;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .compact-flow {{
      margin: 0;
      padding-left: 1.1rem;
      line-height: 1.55;
    }}
    .compact-list {{
      margin: 0;
      line-height: 1.55;
    }}
    .badge {{
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 0.78rem;
      background: rgba(31,43,36,0.07);
      color: var(--muted);
    }}
    .card-lede {{
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.55;
    }}
    .card-tip {{
      margin: 0 0 16px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(34,56,77,0.06);
      border: 1px solid rgba(34,56,77,0.08);
      color: var(--inkdeep);
      line-height: 1.5;
    }}
    .stack {{ display: grid; gap: 14px; }}
    label {{
      display: grid;
      gap: 7px;
      font-weight: 600;
      color: var(--inkdeep);
    }}
    input,
    select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 0.98rem;
      background: rgba(255,255,255,0.9);
      color: var(--ink);
      appearance: none;
    }}
    input:focus,
    select:focus {{
      outline: 2px solid rgba(215,120,66,0.26);
      border-color: var(--clay);
    }}
    .inline-fields {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .field-help {{
      margin: -6px 2px 0;
      font-size: 0.9rem;
      color: var(--muted);
      line-height: 1.45;
    }}
    .running-help {{
      margin-top: 6px;
    }}
    .checkbox-line {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding-top: 24px;
    }}
    .checkbox-line input {{
      width: auto;
      transform: scale(1.2);
    }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: none;
      border-radius: 999px;
      padding: 12px 18px;
      font-weight: 700;
      background: linear-gradient(135deg, #1f2b24, #365448);
      color: #fffdf6;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease;
      box-shadow: 0 10px 26px rgba(31,43,36,0.16);
    }}
    .button:hover {{ transform: translateY(-1px); }}
    .button.secondary {{
      background: linear-gradient(135deg, #d9d3c3, #ebe4d5);
      color: var(--ink);
      box-shadow: none;
    }}
    .print-button {{
      background: linear-gradient(135deg, #b5862c, #d7a74a);
      color: #fffdf6;
      box-shadow: 0 12px 28px rgba(181,134,44,0.22);
    }}
    .hero-actions {{
      margin-top: 16px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .audit-summary-preview {{
      display: grid;
      gap: 12px;
    }}
    .audit-compact-card,
    .audit-metric-card {{
      border-radius: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.62);
      padding: 14px;
    }}
    .audit-compact-head,
    .audit-domain-cell {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .audit-compact-body {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .audit-compact-foot {{
      margin-top: 10px;
      font-size: 0.9rem;
    }}
    .audit-metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .audit-metric-card strong {{
      display: block;
      font-size: 1.7rem;
      font-family: Georgia, "Times New Roman", serif;
      margin-bottom: 4px;
    }}
    .audit-metric-card span {{
      display: block;
      font-weight: 700;
      color: var(--inkdeep);
    }}
    .audit-metric-card p {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .priority-chip,
    .audit-pages-pill {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.8rem;
      font-weight: 700;
      margin: 2px 6px 2px 0;
    }}
    .priority-chip {{
      background: rgba(215,120,66,0.12);
      color: #9b5125;
      border: 1px solid rgba(215,120,66,0.18);
    }}
    .audit-pages-pill {{
      background: rgba(34,56,77,0.08);
      color: var(--inkdeep);
    }}
    .health-pill {{
      white-space: nowrap;
    }}
    .health-good {{
      background: rgba(111,143,114,0.18);
      color: #35553d;
    }}
    .health-watch {{
      background: rgba(181,134,44,0.18);
      color: #8b641d;
    }}
    .health-bad {{
      background: rgba(179,74,60,0.15);
      color: var(--danger);
    }}
    .audit-summary-table td:nth-child(4) {{
      min-width: 18rem;
    }}
    .audit-report-grid {{
      margin-bottom: 0;
    }}
    .report-page {{
      display: grid;
      gap: 18px;
      margin-bottom: 18px;
    }}
    .report-page:last-child {{
      margin-bottom: 0;
    }}
    .cover-layout-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.95fr);
      gap: 18px;
      align-items: start;
    }}
    .cover-side-stack {{
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    .audit-report-topbar {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: start;
      margin-bottom: 22px;
    }}
    .audit-report-heading {{
      max-width: 48rem;
    }}
    .audit-report-actions {{
      margin-top: 0;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .audit-hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
      gap: 18px;
      margin-bottom: 18px;
    }}
    .audit-hero-card {{
      border-radius: 20px;
      border: 1px solid rgba(217,211,195,0.95);
      padding: 22px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.82), rgba(248,243,234,0.92));
      box-shadow: var(--shadow);
    }}
    .audit-hero-primary {{
      background:
        radial-gradient(circle at top right, rgba(215,120,66,0.12), transparent 16rem),
        linear-gradient(180deg, rgba(255,255,255,0.9), rgba(248,243,234,0.95));
    }}
    .audit-hero-secondary {{
      background:
        radial-gradient(circle at top left, rgba(34,56,77,0.08), transparent 14rem),
        linear-gradient(180deg, rgba(255,255,255,0.88), rgba(246,241,232,0.95));
    }}
    .audit-score-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }}
    .audit-hero-kicker {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.8rem;
      font-weight: 700;
      background: rgba(34,56,77,0.08);
      color: var(--inkdeep);
    }}
    .audit-hero-card h2 {{
      margin: 0 0 10px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(1.45rem, 2vw, 2rem);
      line-height: 1.08;
    }}
    .audit-hero-copy {{
      margin: 0;
      max-width: 44rem;
      color: var(--inkdeep);
      font-size: 1.02rem;
      line-height: 1.7;
    }}
    .audit-score-explainer {{
      margin: 14px 0 0;
      color: var(--muted);
      line-height: 1.55;
      font-size: 0.94rem;
    }}
    .audit-hero-stat-block {{
      display: grid;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .audit-hero-stat-block strong {{
      display: block;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 2rem;
      line-height: 1;
    }}
    .audit-hero-stat-block p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .audit-status-chip {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      border-radius: 999px;
      padding: 7px 12px;
      background: rgba(34,56,77,0.08);
      color: var(--inkdeep);
      font-size: 0.82rem;
      font-weight: 700;
    }}
    .cover-main-card {{
      min-height: 100%;
    }}
    .cover-brief-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .cover-brief-card strong {{
      font-size: 1.08rem;
      line-height: 1.35;
    }}
    .cover-side-card {{
      background:
        linear-gradient(180deg, rgba(255,255,255,0.78), rgba(248,243,234,0.88));
    }}
    .cover-side-card h2 {{
      margin-bottom: 10px;
    }}
    .cover-strong-line {{
      margin: 0;
      color: var(--inkdeep);
      font-size: 1.08rem;
      font-weight: 700;
      line-height: 1.5;
    }}
    .cover-url-list {{
      margin-top: 0;
    }}
    .cover-url-list li + li {{
      margin-top: 8px;
    }}
    .cover-url-link {{
      color: var(--inkdeep);
      font-weight: 700;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .report-intro-grid,
    .portfolio-kpi-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .report-summary-card {{
      border-radius: 16px;
      border: 1px solid rgba(217,211,195,0.92);
      background: rgba(255,255,255,0.68);
      padding: 14px;
      display: grid;
      gap: 8px;
    }}
    .report-summary-card strong {{
      color: var(--inkdeep);
      line-height: 1.5;
      font-size: 1rem;
    }}
    .report-summary-label {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.76rem;
      font-weight: 700;
    }}
    .compact-metric-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .section-intro {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .audit-highlight-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .audit-highlight-card {{
      border-radius: 16px;
      border: 1px solid rgba(217,211,195,0.92);
      background: rgba(255,255,255,0.68);
      padding: 14px;
    }}
    .audit-highlight-card strong {{
      display: block;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 1.7rem;
      line-height: 1;
      margin-bottom: 6px;
    }}
    .audit-highlight-card span {{
      display: block;
      color: var(--inkdeep);
      font-weight: 700;
    }}
    .audit-side-label {{
      margin: 0 0 14px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .audit-fact-list {{
      margin: 0;
      display: grid;
      gap: 12px;
    }}
    .audit-fact-list div {{
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(217,211,195,0.92);
    }}
    .audit-fact-list div:last-child {{
      padding-bottom: 0;
      border-bottom: none;
    }}
    .audit-fact-list dt {{
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    .audit-fact-list dd {{
      margin: 0;
      color: var(--inkdeep);
      line-height: 1.5;
      font-weight: 700;
    }}
    .audit-path {{
      word-break: break-word;
      font-weight: 600;
    }}
    .audit-print-note {{
      margin: 18px 0 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 0.92rem;
    }}
    .audit-technical-panel {{
      margin-bottom: 18px;
    }}
    .audit-tech-details summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--inkdeep);
      list-style: none;
    }}
    .audit-tech-details summary::-webkit-details-marker {{
      display: none;
    }}
    .audit-tech-grid {{
      margin-top: 14px;
      margin-bottom: 0;
    }}
    .audit-report-shell > .subpanel {{
      margin-bottom: 18px;
      padding: 22px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.74), rgba(248,243,234,0.86));
    }}
    .audit-report-shell > .subpanel h2 {{
      margin-bottom: 14px;
    }}
    .audit-report-shell .audit-metric-card {{
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.82);
    }}
    .audit-report-shell .signal-row-card,
    .audit-report-shell .page-priority-card,
    .audit-report-shell .pair-card {{
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.84);
    }}
    .audit-report-shell .signal-row-card {{
      border: 1px solid rgba(217,211,195,0.92);
    }}
    .audit-report-shell .signal-row,
    .audit-report-shell .page-priority-card,
    .audit-report-shell .pair-card {{
      border: none;
      background: transparent;
      padding: 0;
    }}
    .audit-report-shell .copy-block {{
      border-radius: 18px;
      padding: 18px 20px;
      background: linear-gradient(135deg, rgba(34,56,77,0.08), rgba(255,255,255,0.82));
    }}
    .audit-report-shell .copy-block p {{
      font-size: 1rem;
    }}
    .audit-report-shell .clean-list li + li {{
      margin-top: 10px;
    }}
    .signal-list,
    .page-priority-list,
    .pair-list {{
      display: grid;
      gap: 12px;
    }}
    .signal-row-card {{
      border-radius: 14px;
      padding: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.62);
    }}
    .signal-row,
    .page-priority-card,
    .pair-card {{
      border-radius: 14px;
      padding: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.62);
    }}
    .signal-row {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 10px;
      align-items: center;
    }}
    .signal-help {{
      margin: 10px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .signal-pill.signal-high {{
      background: rgba(179,74,60,0.14);
      color: var(--danger);
    }}
    .signal-pill.signal-medium {{
      background: rgba(181,134,44,0.18);
      color: #8b641d;
    }}
    .page-priority-meta {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .page-url {{
      display: block;
      font-weight: 700;
      color: var(--inkdeep);
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .pair-card p {{
      margin: 8px 0 0;
      line-height: 1.45;
      color: var(--inkdeep);
    }}
    .signal-details {{
      margin-top: 12px;
      border-top: 1px solid rgba(217,211,195,0.85);
      padding-top: 12px;
    }}
    .signal-details summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--inkdeep);
    }}
    .signal-example-list {{
      margin-top: 10px;
    }}
    .raw-json-box summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--inkdeep);
      margin-bottom: 12px;
    }}
    .copy-block {{
      padding: 16px 18px;
      border-radius: 14px;
      border: 1px solid rgba(34,56,77,0.12);
      background: linear-gradient(135deg, rgba(34,56,77,0.06), rgba(255,255,255,0.7));
    }}
    .copy-block p {{
      margin: 0;
      line-height: 1.7;
      color: var(--inkdeep);
      white-space: pre-wrap;
    }}
    .portfolio-page {{
      background:
        linear-gradient(180deg, rgba(255,255,255,0.38), rgba(255,255,255,0.05));
      border-radius: 22px;
      padding: 4px;
    }}
    .portfolio-hero-grid {{
      align-items: stretch;
    }}
    .portfolio-method-strip {{
      margin-top: 12px;
      padding: 16px;
    }}
    .portfolio-method-strip .clean-list {{
      margin-top: 6px;
    }}
    .ghost-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      padding: 10px 14px;
      border: 1px solid rgba(217,211,195,0.95);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      font-weight: 700;
      cursor: pointer;
    }}
    .ghost-button.danger {{
      color: var(--danger);
      border-color: rgba(179,74,60,0.25);
      background: rgba(179,74,60,0.08);
    }}
    .panel-actions {{ margin-top: 18px; display: flex; gap: 10px; }}
    .panel-tools {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .inline-form {{ margin: 0; }}
    .status-pill {{
      border-radius: 999px;
      padding: 7px 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.72rem;
    }}
    .status-queued {{ background: rgba(181,134,44,0.12); color: var(--gold); }}
    .status-running {{ background: rgba(34,56,77,0.12); color: var(--inkdeep); }}
    .status-done {{ background: rgba(111,143,114,0.18); color: var(--sage); }}
    .status-cancelled {{ background: rgba(179,74,60,0.12); color: #8c4538; }}
    .status-failed {{ background: rgba(179,74,60,0.14); color: var(--danger); }}
    .job-card {{
      display: grid;
      gap: 8px;
      padding: 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.58);
      border: 1px solid rgba(217,211,195,0.92);
      margin-bottom: 10px;
    }}
    .job-main-link {{
      display: block;
    }}
    .job-meta {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .job-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }}
    .job-actions {{
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .job-delete {{
      padding: 8px 12px;
      font-size: 0.84rem;
    }}
    .muted, .subtle-link {{ color: var(--muted); }}
    .flow {{
      margin: 0;
      padding-left: 1.2rem;
      color: var(--inkdeep);
      line-height: 1.7;
    }}
    .table-wrap {{
      overflow: auto;
      border-radius: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.68);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 540px;
      font-size: 0.92rem;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(217,211,195,0.85);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f5efe4;
      z-index: 1;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    .file-shell h1 {{
      margin: 0 0 10px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(1.8rem, 3vw, 3rem);
    }}
    .file-meta {{
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }}
    .file-table table {{
      min-width: 900px;
    }}
    .col-name {{
      display: inline-block;
      padding: 2px 0;
      white-space: nowrap;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.8rem;
      font-weight: 700;
      white-space: nowrap;
    }}
    .domain-pill {{
      background: rgba(34,56,77,0.10);
      color: var(--inkdeep);
    }}
    .provider-pill {{
      background: rgba(181,134,44,0.14);
      color: #8b641d;
    }}
    .soft-pill {{
      background: rgba(111,143,114,0.16);
      color: #43624b;
    }}
    .score-high {{
      background: rgba(111,143,114,0.2);
      color: #35553d;
    }}
    .score-mid {{
      background: rgba(181,134,44,0.18);
      color: #8b641d;
    }}
    .score-low {{
      background: rgba(215,120,66,0.18);
      color: #9b5125;
    }}
    .cell-empty {{
      background: rgba(255,255,255,0.3);
    }}
    .cell-text {{
      max-width: 28rem;
      line-height: 1.45;
      color: var(--inkdeep);
    }}
    .log-box {{
      margin: 0;
      max-height: 360px;
      overflow: auto;
      background: #1d2622;
      color: #eef4ed;
      padding: 16px;
      border-radius: 14px;
      font-size: 0.87rem;
      line-height: 1.5;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .meta-grid div {{
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.6);
      border: 1px solid rgba(217,211,195,0.9);
      display: grid;
      gap: 4px;
    }}
    .meta-grid strong {{ font-size: 0.82rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }}
    .clean-list {{
      margin: 0;
      padding-left: 1rem;
      line-height: 1.7;
    }}
    .error-box {{
      margin-bottom: 18px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(179,74,60,0.26);
      background: rgba(179,74,60,0.08);
      color: var(--danger);
      font-weight: 700;
    }}
    .flash-banner {{
      margin-bottom: 20px;
      padding: 14px 18px;
      border-radius: 14px;
      border: 1px solid rgba(111,143,114,0.24);
      background: rgba(111,143,114,0.12);
      color: #35553d;
      font-weight: 700;
    }}
    .accent-clay {{ border-top: 4px solid var(--clay); }}
    .accent-sage {{ border-top: 4px solid var(--sage); }}
    .accent-ink {{ border-top: 4px solid var(--inkdeep); }}
    .accent-gold {{ border-top: 4px solid var(--gold); }}
    @page {{
      size: A4;
      margin: 14mm;
    }}
    @media print {{
      body {{
        background: #ffffff;
      }}
      .page {{
        max-width: none;
        padding: 0;
      }}
      .no-print,
      .panel-actions,
      .raw-json-box,
      .hero,
      .flash-banner {{
        display: none !important;
      }}
      .panel,
      .subpanel,
      .audit-hero-card,
      .audit-metric-card,
      .signal-row-card,
      .page-priority-card,
      .pair-card,
      .copy-block,
      .audit-highlight-card {{
        background: #ffffff !important;
        box-shadow: none !important;
        border: 1px solid #d8d3c6 !important;
        backdrop-filter: none !important;
      }}
      .audit-report-shell {{
        padding: 0;
        border: none;
        box-shadow: none;
        background: transparent;
      }}
      .audit-report-topbar {{
        margin-bottom: 14px;
      }}
      .audit-hero-grid,
      .cover-layout-grid,
      .grid.two,
      .audit-metric-grid,
      .audit-highlight-grid,
      .report-intro-grid,
      .portfolio-kpi-grid,
      .file-meta {{
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      }}
      .report-page {{
        page-break-after: always;
        break-after: page;
      }}
      .report-page:last-child {{
        page-break-after: auto;
        break-after: auto;
      }}
      .audit-report-shell > .subpanel,
      .audit-hero-card,
      .audit-metric-card,
      .signal-row-card,
      .page-priority-card,
      .pair-card,
      .copy-block {{
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .file-shell h1 {{
        font-size: 28pt;
      }}
      .audit-hero-copy,
      .copy-block p,
      .clean-list,
      .signal-help {{
        font-size: 11pt;
        line-height: 1.55;
      }}
      a {{
        color: #111111;
        text-decoration: none;
      }}
    }}
    @media (max-width: 900px) {{
      .hero, .grid.two, .inline-fields, .meta-grid, .audit-metric-grid, .quick-start-grid, .audit-hero-grid, .audit-highlight-grid, .report-intro-grid, .portfolio-kpi-grid, .compact-metric-grid, .cover-layout-grid, .cover-brief-grid {{
        grid-template-columns: 1fr;
      }}
      .page {{ padding: 20px 14px 40px; }}
      .panel {{ padding: 18px; }}
      .audit-report-topbar {{
        flex-direction: column;
      }}
      .audit-report-actions {{
        width: 100%;
        justify-content: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    {content}
  </main>
</body>
</html>"""
