from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from models import AuditReport


def record_audit_report(db_path: str | Path, report: AuditReport) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                audited_at TEXT NOT NULL,
                observed_health_score INTEGER NOT NULL,
                pages_crawled INTEGER NOT NULL,
                history_path TEXT,
                html_path TEXT,
                crawl_source TEXT,
                summary_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                page_type TEXT,
                page_health_score INTEGER,
                status_code INTEGER,
                word_count INTEGER,
                depth INTEGER,
                issues_json TEXT NOT NULL,
                FOREIGN KEY(audit_id) REFERENCES audits(id)
            )
            """
        )
        cursor = connection.execute(
            """
            INSERT INTO audits (
                domain, audited_at, observed_health_score, pages_crawled,
                history_path, html_path, crawl_source, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.domain,
                report.audited_at,
                report.observed_health_score,
                report.pages_crawled,
                report.history_path,
                report.html_path,
                str(report.crawl_metadata.get("crawl_source") or ""),
                json.dumps(report.summary, ensure_ascii=False),
            ),
        )
        audit_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO audit_pages (
                audit_id, url, page_type, page_health_score,
                status_code, word_count, depth, issues_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    audit_id,
                    str(page.get("url") or ""),
                    str(page.get("page_type") or ""),
                    int(page.get("page_health_score") or 0),
                    int(page.get("status_code") or 0),
                    int(page.get("word_count") or 0),
                    int(page.get("depth") or 0),
                    json.dumps(page.get("issues") or [], ensure_ascii=False),
                )
                for page in report.pages
            ],
        )
    return path
