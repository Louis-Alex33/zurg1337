from __future__ import annotations

import ipaddress
import threading
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from utils import CLIError

from .fs_ops import delete_managed_file, reset_pipeline_outputs, resolve_local_file, save_uploaded_gsc_file
from .jobs import (
    clear_finished_jobs,
    create_job,
    delete_job_record,
    request_job_cancel,
    run_audit_job,
    run_discover_job,
    run_gsc_job,
    run_qualify_job,
)
from .rendering import render_dashboard, render_file_page, render_job_page

MAX_POST_BODY_BYTES = 52_428_800


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
            lang = (query.get("lang") or ["fr"])[0]
            self._serve_file(file_path, variant=variant, lang=lang)
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
        payload = self.rfile.read(content_length)
        try:
            form = self._parse_post_form(payload, content_length)
        except CLIError as exc:
            self._redirect(f"/?flash={quote(str(exc))}")
            return

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

    def _parse_post_form(self, payload: bytes, content_length: int) -> dict[str, str]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            raw_message = (
                f"Content-Type: {content_type}\r\n"
                "MIME-Version: 1.0\r\n\r\n"
            ).encode("utf-8") + payload
            message = BytesParser(policy=default).parsebytes(raw_message)
            form: dict[str, str] = {}
            upload_fields = {"current_upload", "previous_upload", "queries_upload"}
            upload_targets = {
                "current_upload": "current_csv",
                "previous_upload": "previous_csv",
                "queries_upload": "queries_csv",
            }
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                filename = part.get_filename()
                if name in upload_fields and filename:
                    saved_path = save_uploaded_gsc_file(filename, part.get_payload(decode=True) or b"")
                    form[upload_targets[name]] = saved_path
                elif not filename:
                    charset = part.get_content_charset() or "utf-8"
                    form[name] = (part.get_payload(decode=True) or b"").decode(charset, errors="replace")
            return form

        payload_text = payload.decode("utf-8")
        return {key: values[0] for key, values in parse_qs(payload_text, keep_blank_values=True).items()}

    def log_message(self, format: str, *args: object) -> None:
        return

    def _is_same_origin(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return False
        parsed = urlparse(source)
        if not parsed.scheme or not parsed.netloc or parsed.hostname is None:
            return False
        host, port = self.server.server_address[:2]
        if parsed.scheme != "http":
            return False
        request_port = parsed.port or (80 if parsed.scheme == "http" else None)
        if request_port != port:
            return False
        return parsed.hostname == host or (
            _is_loopback_host(parsed.hostname) and _is_loopback_host(str(host))
        )

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

    def _serve_file(self, requested_path: str, variant: str = "full", lang: str = "fr") -> None:
        try:
            file_path = resolve_local_file(requested_path)
        except CLIError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        if file_path.suffix.lower() == ".html":
            self._send_html(file_path.read_text("utf-8", errors="ignore"))
            return
        self._send_html(render_file_page(file_path, variant=variant, lang=lang))

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


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
