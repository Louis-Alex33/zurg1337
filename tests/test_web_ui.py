from __future__ import annotations

import importlib
import os
import tempfile
import threading
import time
import unittest

from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock, patch

from web_ui import (
    ProspectMachineUIHandler,
    JOBS,
    JOB_LOCK,
    announce_job_outputs,
    clear_finished_jobs,
    create_job,
    delete_managed_file,
    delete_job_record,
    execute_job,
    format_duration,
    get_job,
    job_elapsed_seconds,
    recent_job_cards,
    render_dashboard,
    render_job_page,
    render_file_page,
    request_job_cancel,
    reset_pipeline_outputs,
    resolve_local_file,
    run_audit_job,
)


class WebUITests(unittest.TestCase):
    def _make_post_handler(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> tuple[ProspectMachineUIHandler, list[tuple[HTTPStatus, str]]]:
        handler = ProspectMachineUIHandler.__new__(ProspectMachineUIHandler)
        handler.path = path
        handler.headers = MagicMock()
        header_values = headers or {}
        handler.headers.get.side_effect = lambda key, default=None: header_values.get(key, default)
        handler.rfile = MagicMock()
        handler.rfile.read.return_value = body
        handler.wfile = MagicMock()
        handler.server = MagicMock()
        handler.server.server_address = ("127.0.0.1", 8787)
        errors: list[tuple[HTTPStatus, str]] = []
        handler.send_error = lambda code, message=None: errors.append((code, message or ""))  # type: ignore[method-assign]
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        return handler, errors

    def test_root_dir_is_anchored_to_project_file_location(self) -> None:
        import web_ui

        original_cwd = Path.cwd()
        expected_root = Path(web_ui.__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                reloaded = importlib.reload(web_ui)
            finally:
                os.chdir(original_cwd)
                importlib.reload(web_ui)

        self.assertEqual(reloaded.ROOT_DIR, expected_root)

    def test_dashboard_contains_main_actions(self) -> None:
        page = render_dashboard()

        self.assertIn("/run/discover", page)
        self.assertIn("/run/qualify", page)
        self.assertIn("/run/audit", page)
        self.assertIn("/run/gsc", page)
        self.assertIn('name="site"', page)
        self.assertIn("ignore l'Input CSV", page)
        self.assertIn("Commencer Ici", page)
        self.assertIn("Je veux analyser un seul site", page)
        self.assertIn("3. Sortir Un Mini Audit Exploitable", page)
        self.assertIn("/clear-jobs", page)

    def test_run_audit_job_supports_direct_site_input(self) -> None:
        job = create_job(
            "audit",
            {
                "site": "eversportzone.com",
                "input_csv": "data/domains_scored.csv",
                "output_dir": "reports/audits",
                "max_pages": "20",
                "delay": "0.2",
            },
        )

        with patch("web_ui.audit_domains") as mock_audit_domains:
            mock_audit_domains.return_value = []
            run_audit_job(job.job_id)

        record = get_job(job.job_id)
        self.assertEqual(record.status, "done")
        self.assertIn("Site direct: eversportzone.com", record.summary_lines)
        mock_audit_domains.assert_called_once_with(
            input_csv=None,
            output_dir="reports/audits",
            top=None,
            min_score=None,
            mode="audit_light",
            max_pages=20,
            delay=0.2,
            site="eversportzone.com",
            cancel_callback=mock_audit_domains.call_args.kwargs["cancel_callback"],
        )

    def test_execute_job_exposes_logs_while_running(self) -> None:
        job = create_job("audit", {})
        started = threading.Event()
        release = threading.Event()

        def action() -> tuple[list[str], list[str]]:
            print("Crawl en cours sur example.com...")
            started.set()
            release.wait(timeout=2)
            return [], ["ok"]

        thread = threading.Thread(target=execute_job, args=(job, action), daemon=True)
        thread.start()

        self.assertTrue(started.wait(timeout=1))
        time.sleep(0.05)
        running_job = get_job(job.job_id)
        self.assertEqual(running_job.status, "running")
        self.assertIn("Crawl en cours sur example.com...", running_job.log)

        release.set()
        thread.join(timeout=2)
        finished_job = get_job(job.job_id)
        self.assertEqual(finished_job.status, "done")

    def test_render_job_page_explains_running_state(self) -> None:
        job = create_job("audit", {})
        job.status = "running"
        job.started_at = "2026-04-14T23:20:02"
        job.log = "Audit de 1 domaine..."

        page = render_job_page(job.job_id)

        self.assertIn("En cours d'execution", page)
        self.assertIn("Cette page se rafraichit automatiquement", page)
        self.assertIn("Annuler le job", page)
        self.assertIn("Rythme attendu", page)
        self.assertIn("Audit de 1 domaine...", page)
        self.assertIn("Que faire ensuite", page)

    def test_running_job_can_announce_outputs_before_completion(self) -> None:
        job = create_job("qualify", {})
        job.status = "running"

        announce_job_outputs(job, ["data/domains_scored.csv", "data/domains_scored.json"])

        self.assertEqual(job.outputs, ["data/domains_scored.csv", "data/domains_scored.json"])

    def test_render_job_page_for_done_audit_suggests_next_steps(self) -> None:
        job = create_job("audit", {})
        job.status = "done"
        job.outputs = ["reports/audits/audit_summary.csv", "reports/audits/example.com.json"]

        page = render_job_page(job.job_id)

        self.assertIn("Que faire ensuite", page)
        self.assertIn("ouvrir le recap des audits", page)
        self.assertIn("le rapport complet du domaine", page)

    def test_request_job_cancel_marks_running_job_and_recent_cards_show_it(self) -> None:
        with JOB_LOCK:
            JOBS.clear()
        job = create_job("audit", {"site": "example.com", "max_pages": "30"})
        job.status = "running"
        job.started_at = "2026-04-15T09:00:00"
        job.log = "Job demarre...\n"

        cancelled = request_job_cancel(job.job_id)
        cards = recent_job_cards()

        self.assertTrue(cancelled)
        self.assertTrue(job.cancel_requested)
        self.assertIn("Annulation demandee...", job.log)
        self.assertIn("Annuler", cards)
        self.assertIn("Duree:", cards)

    def test_execute_job_can_be_cancelled_cleanly(self) -> None:
        with JOB_LOCK:
            JOBS.clear()
        job = create_job("audit", {})
        started = threading.Event()

        def wrapped_action() -> tuple[list[str], list[str]]:
            print("Crawl en cours sur example.com...")
            started.set()
            while True:
                if job.cancel_event.is_set():
                    from web_ui import JobCancelledError

                    raise JobCancelledError
                time.sleep(0.02)

        thread = threading.Thread(target=execute_job, args=(job, wrapped_action), daemon=True)
        thread.start()

        self.assertTrue(started.wait(timeout=1))
        self.assertTrue(request_job_cancel(job.job_id))
        thread.join(timeout=2)

        finished_job = get_job(job.job_id)
        self.assertEqual(finished_job.status, "cancelled")
        self.assertIn("Job annule proprement.", finished_job.log)
        self.assertIn("Execution interrompue a la demande.", finished_job.summary_lines)

    def test_cancelled_jobs_are_cleared_with_finished_jobs(self) -> None:
        with JOB_LOCK:
            JOBS.clear()
        cancelled_job = create_job("audit", {})
        running_job = create_job("qualify", {})
        cancelled_job.status = "cancelled"
        running_job.status = "running"

        removed = clear_finished_jobs()

        self.assertEqual(removed, 1)
        self.assertEqual(get_job(running_job.job_id).status, "running")
        with self.assertRaises(Exception):
            get_job(cancelled_job.job_id)

    def test_duration_helpers_format_elapsed_time(self) -> None:
        with JOB_LOCK:
            JOBS.clear()
        job = create_job("audit", {})
        job.started_at = "2026-04-15T09:00:00"
        job.finished_at = "2026-04-15T09:03:05"

        elapsed = job_elapsed_seconds(job)

        self.assertEqual(elapsed, 185.0)
        self.assertEqual(format_duration(elapsed), "3m 05s")

    def test_recent_jobs_can_be_deleted_individually(self) -> None:
        job = create_job("audit", {})

        self.assertTrue(delete_job_record(job.job_id))
        self.assertFalse(delete_job_record(job.job_id))
        with self.assertRaises(Exception):
            get_job(job.job_id)

    def test_clear_finished_jobs_keeps_running_jobs(self) -> None:
        with JOB_LOCK:
            JOBS.clear()
        done_job = create_job("audit", {})
        failed_job = create_job("discover", {})
        running_job = create_job("qualify", {})
        done_job.status = "done"
        failed_job.status = "failed"
        running_job.status = "running"

        removed = clear_finished_jobs()

        self.assertEqual(removed, 2)
        self.assertEqual(get_job(running_job.job_id).status, "running")
        with self.assertRaises(Exception):
            get_job(done_job.job_id)

    def test_resolve_local_file_rejects_escape(self) -> None:
        with self.assertRaises(Exception):
            resolve_local_file("../../etc/passwd")

    def test_render_file_page_for_csv_contains_home_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            raw_csv = data_dir / "domains_raw.csv"
            raw_csv.write_text(
                "domain,source_query,source_provider,first_seen,title,snippet\n"
                "example.com,blog yoga,duckduckgo,2026-04-13T10:00:00+00:00,Example,Snippet\n",
                encoding="utf-8",
            )

            import web_ui

            original_root = web_ui.ROOT_DIR
            try:
                web_ui.ROOT_DIR = Path(tmp_dir).resolve()
                page = render_file_page(raw_csv.resolve())
            finally:
                web_ui.ROOT_DIR = original_root

        self.assertIn("Retour home", page)
        self.assertIn("CSV Viewer", page)
        self.assertIn("domain-pill", page)
        self.assertIn("Supprimer", page)

    def test_render_file_page_for_audit_summary_has_dedicated_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            audits_dir = root / "reports" / "audits"
            audits_dir.mkdir(parents=True, exist_ok=True)
            summary_csv = audits_dir / "audit_summary.csv"
            summary_csv.write_text(
                "domain,pages_crawled,observed_health_score,missing_titles,missing_meta_descriptions,"
                "missing_h1,thin_content_pages,duplicate_title_groups,duplicate_meta_description_groups,"
                "possible_content_overlap_pairs,probable_orphan_pages,weak_internal_linking_pages,"
                "deep_pages_detected,dated_content_signals\n"
                "example.com,30,58,0,0,0,2,1,0,3,0,1,0,5\n",
                encoding="utf-8",
            )
            (audits_dir / "example.com.json").write_text("{}", encoding="utf-8")

            import web_ui

            original_root = web_ui.ROOT_DIR
            try:
                web_ui.ROOT_DIR = root.resolve()
                page = render_file_page(summary_csv.resolve())
            finally:
                web_ui.ROOT_DIR = original_root

        self.assertIn("Vue d'ensemble des audits", page)
        self.assertIn("Vue rapide", page)
        self.assertIn("Opportunités prioritaires", page)
        self.assertIn("Voir rapport complet", page)
        self.assertIn("58/100", page)

    def test_render_file_page_for_audit_json_has_client_facing_report_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            audits_dir = root / "reports" / "audits"
            audits_dir.mkdir(parents=True, exist_ok=True)
            audit_json = audits_dir / "example.com.json"
            audit_json.write_text(
                """
                {
                  "domain": "example.com",
                  "audited_at": "2026-04-15T00:47:42",
                  "pages_crawled": 30,
                  "observed_health_score": 65,
                  "summary": {
                    "content_like_pages": 12,
                    "pages_ok": 30,
                    "pages_with_errors": 0,
                    "missing_meta_descriptions": 1,
                    "missing_h1": 2,
                    "weak_internal_linking_pages": 8,
                    "possible_content_overlap_pairs": 4,
                    "dated_content_signals": 3
                  },
                  "critical_findings": ["4 pages semblent répondre à la même intention"],
                  "business_priority_signals": [{"key": "possible_content_overlap_pairs", "signal": "Pages qui se concurrencent sur le même sujet", "severity": "HIGH", "count": 4}],
                  "top_pages_to_rework": [{"url": "https://example.com/blog/test", "priority_score": 6, "word_count": 180, "depth": 3, "reasons": ["contenu à enrichir pour mieux répondre à la recherche"], "confidence": "medium-high"}],
                  "possible_content_overlap": [{"title_1": "Page A", "title_2": "Page B", "similarity": 72.5}],
                  "dated_content_signals": [{"url": "https://example.com/blog/date", "references": ["Date visible dans le titre: 2024"]}],
                  "confidence_notes": ["Les priorites sont fondees sur le crawl observe."]
                }
                """,
                encoding="utf-8",
            )

            import web_ui

            original_root = web_ui.ROOT_DIR
            try:
                web_ui.ROOT_DIR = root.resolve()
                page = render_file_page(audit_json.resolve())
            finally:
                web_ui.ROOT_DIR = original_root

        self.assertIn("Audit SEO", page)
        self.assertIn("Exporter en PDF", page)
        self.assertIn("Version portfolio", page)
        self.assertIn("Analyse rapide d’un site de contenu pour repérer les pages à reprendre en priorité.", page)
        self.assertIn("En bref", page)
        self.assertIn("Signal principal", page)
        self.assertIn("Premières pages à regarder", page)
        self.assertIn("Ce que ce rapport aide à décider", page)
        self.assertIn("30 pages analysées", page)
        self.assertIn("12 contenus utiles", page)
        self.assertIn("Pages à revoir en priorité", page)
        self.assertIn("Ce que ce rapport permet de décider", page)
        self.assertIn("Repères complémentaires", page)
        self.assertIn("Voir des exemples concrets", page)
        self.assertIn("Dates visibles à vérifier", page)
        self.assertIn("Lecture rapide", page)
        self.assertIn("priorité de reprise : modérée", page)
        self.assertIn("3 clics", page)
        self.assertIn("lecture assez solide", page)
        self.assertNotIn("Télécharger le JSON", page)
        self.assertNotIn("Afficher le JSON brut", page)
        self.assertNotIn("JSON brut", page)
        self.assertNotIn("automatisation", page)

    def test_render_file_page_for_audit_json_supports_portfolio_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            audits_dir = root / "reports" / "audits"
            audits_dir.mkdir(parents=True, exist_ok=True)
            audit_json = audits_dir / "example.com.json"
            audit_json.write_text(
                """
                {
                  "domain": "example.com",
                  "pages_crawled": 18,
                  "observed_health_score": 72,
                  "summary": {
                    "content_like_pages": 7,
                    "thin_content_pages": 2,
                    "possible_content_overlap_pairs": 1,
                    "dated_content_signals": 1
                  },
                  "critical_findings": ["2 pages méritent d'être enrichies pour mieux répondre au sujet"],
                  "business_priority_signals": [{"key": "thin_content_pages", "signal": "Pages à enrichir en priorité", "severity": "HIGH", "count": 2}],
                  "top_pages_to_rework": [{"url": "https://example.com/guides/test", "priority_score": 8, "word_count": 220, "depth": 2, "reasons": ["contenu à enrichir pour mieux répondre à la recherche"], "confidence": "medium"}]
                }
                """,
                encoding="utf-8",
            )

            import web_ui

            original_root = web_ui.ROOT_DIR
            try:
                web_ui.ROOT_DIR = root.resolve()
                page = render_file_page(audit_json.resolve(), variant="portfolio")
            finally:
                web_ui.ROOT_DIR = original_root

        self.assertIn("Extrait portfolio", page)
        self.assertIn("Version complète", page)
        self.assertIn("Premières actions suggérées", page)
        self.assertIn("Méthode de lecture", page)
        self.assertIn("Ce que l’analyse fait apparaître", page)
        self.assertNotIn("Repères complémentaires", page)

    def test_audit_json_download_sets_attachment_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            audits_dir = root / "reports" / "audits"
            audits_dir.mkdir(parents=True, exist_ok=True)
            audit_json = audits_dir / "example.com.json"
            audit_json.write_text('{"domain":"example.com"}', encoding="utf-8")

            import web_ui

            original_root = web_ui.ROOT_DIR
            try:
                web_ui.ROOT_DIR = root.resolve()
                handler = ProspectMachineUIHandler.__new__(ProspectMachineUIHandler)
                status: dict[str, object] = {}
                headers: list[tuple[str, str]] = []
                body = bytearray()
                handler.send_response = lambda code: status.setdefault("code", code)  # type: ignore[method-assign]
                handler.send_header = lambda name, value: headers.append((name, value))  # type: ignore[method-assign]
                handler.end_headers = lambda: None  # type: ignore[method-assign]
                handler.wfile = type("WFile", (), {"write": body.extend})()

                handler._serve_download("reports/audits/example.com.json")
            finally:
                web_ui.ROOT_DIR = original_root

        self.assertEqual(status["code"], HTTPStatus.OK)
        self.assertIn(("Content-Disposition", 'attachment; filename="example.com.json"'), headers)
        self.assertTrue(body)

    def test_delete_managed_file_removes_scored_and_json_when_cascade_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            scored_csv = data_dir / "domains_scored.csv"
            scored_json = data_dir / "domains_scored.json"
            scored_csv.write_text("score,domain\n10,example.com\n", encoding="utf-8")
            scored_json.write_text("[]", encoding="utf-8")

            from web_ui import ROOT_DIR

            original_root = ROOT_DIR
            try:
                import web_ui

                web_ui.ROOT_DIR = Path(tmp_dir).resolve()
                deleted = delete_managed_file("data/domains_scored.csv", cascade=True)
            finally:
                web_ui.ROOT_DIR = original_root

            self.assertEqual(
                deleted,
                ["data/domains_scored.csv", "data/domains_scored.json"],
            )
            self.assertFalse(scored_csv.exists())
            self.assertFalse(scored_json.exists())

    def test_reset_pipeline_outputs_removes_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            (root / "reports/audits").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)

            targets = [
                root / "data/domains_raw.csv",
                root / "data/domains_scored.csv",
                root / "data/domains_scored.json",
                root / "reports/gsc_report.csv",
                root / "reports/audits/audit_summary.csv",
                root / "reports/audits/example.com.json",
            ]
            for target in targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")

            import web_ui

            original_root = web_ui.ROOT_DIR
            try:
                web_ui.ROOT_DIR = root.resolve()
                deleted = reset_pipeline_outputs()
            finally:
                web_ui.ROOT_DIR = original_root

            self.assertIn("data/domains_raw.csv", deleted)
            self.assertIn("reports/audits/example.com.json", deleted)
            self.assertFalse((root / "data/domains_raw.csv").exists())
            self.assertFalse((root / "reports/audits/example.com.json").exists())

    def test_post_rejects_oversized_payload(self) -> None:
        handler, errors = self._make_post_handler(
            "/unknown",
            headers={
                "Content-Length": "2000000",
                "Origin": "http://127.0.0.1:8787",
            },
        )

        handler.do_POST()

        self.assertEqual(errors, [(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload too large")])
        handler.rfile.read.assert_not_called()

    def test_post_rejects_cross_origin_request(self) -> None:
        handler, errors = self._make_post_handler(
            "/unknown",
            headers={
                "Content-Length": "0",
                "Origin": "http://evil.com",
            },
        )

        handler.do_POST()

        self.assertEqual(errors, [(HTTPStatus.FORBIDDEN, "Cross-origin request refused")])

    def test_post_accepts_same_origin_request(self) -> None:
        handler, errors = self._make_post_handler(
            "/unknown",
            headers={
                "Content-Length": "0",
                "Origin": "http://127.0.0.1:8787",
            },
        )

        handler.do_POST()

        self.assertTrue(errors)
        self.assertNotEqual(errors[0][0], HTTPStatus.FORBIDDEN)

    def test_post_rejects_missing_origin_and_referer(self) -> None:
        handler, errors = self._make_post_handler(
            "/unknown",
            headers={"Content-Length": "0"},
        )

        handler.do_POST()

        self.assertEqual(errors, [(HTTPStatus.FORBIDDEN, "Cross-origin request refused")])


if __name__ == "__main__":
    unittest.main()
