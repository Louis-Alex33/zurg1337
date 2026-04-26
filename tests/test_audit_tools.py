from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compare_audits import compare_audit_reports
from doctor import format_doctor_results, run_doctor


class AuditToolsTests(unittest.TestCase):
    def test_compare_audit_reports_returns_score_and_page_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_path = root / "old.json"
            new_path = root / "new.json"
            old_path.write_text(
                json.dumps(
                    {
                        "domain": "example.com",
                        "audited_at": "2026-04-01T10:00:00",
                        "observed_health_score": 60,
                        "pages_crawled": 1,
                        "summary": {"thin_content_pages": 2},
                        "pages": [
                            {
                                "url": "https://example.com/a",
                                "page_health_score": 50,
                                "issues": ["Contenu à enrichir"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            new_path.write_text(
                json.dumps(
                    {
                        "domain": "example.com",
                        "audited_at": "2026-04-02T10:00:00",
                        "observed_health_score": 72,
                        "pages_crawled": 1,
                        "summary": {"thin_content_pages": 0},
                        "pages": [
                            {
                                "url": "https://example.com/a",
                                "page_health_score": 82,
                                "issues": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            comparison = compare_audit_reports(str(old_path), str(new_path), output_csv=str(root / "delta.csv"))

            self.assertEqual(comparison["observed_health_delta"], 12)
            self.assertEqual(len(comparison["improved_pages"]), 1)
            self.assertTrue((root / "delta.csv").exists())

    def test_doctor_formats_setup_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            checks = run_doctor(tmp_dir)
            lines = format_doctor_results(checks)

        self.assertTrue(checks)
        self.assertTrue(all(" | " in line for line in lines))


if __name__ == "__main__":
    unittest.main()
