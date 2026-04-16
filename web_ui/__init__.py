from __future__ import annotations

from pathlib import Path

from audit import audit_domains as audit_domains

ROOT_DIR = Path(__file__).resolve().parent.parent


def _root_dir() -> Path:
    return ROOT_DIR


def _audit_domains():
    return audit_domains


from .fs_ops import delete_managed_file, reset_pipeline_outputs, resolve_local_file
from .jobs import (
    JOBS,
    JOB_LOCK,
    JobCancelledError,
    JobLogCapture,
    JobRecord,
    announce_job_outputs,
    clear_finished_jobs,
    create_job,
    delete_job_record,
    execute_job,
    format_duration,
    get_job,
    job_elapsed_seconds,
    request_job_cancel,
    run_audit_job,
)
from .rendering import recent_job_cards, render_dashboard, render_file_page, render_job_page
from .server import MAX_POST_BODY_BYTES, ProspectMachineUIHandler, launch_ui

# Preserve the old module-based file location semantics for compatibility tests.
__file__ = str(ROOT_DIR / "web_ui.py")

__all__ = [
    "JOBS",
    "JOB_LOCK",
    "MAX_POST_BODY_BYTES",
    "ROOT_DIR",
    "JobCancelledError",
    "JobLogCapture",
    "JobRecord",
    "ProspectMachineUIHandler",
    "announce_job_outputs",
    "audit_domains",
    "clear_finished_jobs",
    "create_job",
    "delete_job_record",
    "delete_managed_file",
    "execute_job",
    "format_duration",
    "get_job",
    "job_elapsed_seconds",
    "launch_ui",
    "recent_job_cards",
    "render_dashboard",
    "render_file_page",
    "render_job_page",
    "request_job_cancel",
    "reset_pipeline_outputs",
    "resolve_local_file",
    "run_audit_job",
]
