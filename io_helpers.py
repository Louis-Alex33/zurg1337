from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from models import DomainDiscovery, QualifiedDomain
from utils import CLIError


def ensure_parent_dir(path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def write_csv_rows(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> Path:
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_path


def init_csv_file(path: str | Path, fieldnames: list[str]) -> Path:
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        handle.flush()
    return output_path


def append_csv_rows(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> Path:
    output_path = ensure_parent_dir(path)
    with output_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        for row in rows:
            writer.writerow(row)
        handle.flush()
    return output_path


def write_json_file(path: str | Path, payload: Any) -> Path:
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return output_path


def dataclasses_to_dicts(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if is_dataclass(item):
            rows.append(asdict(item))
        elif isinstance(item, dict):
            rows.append(item)
        else:
            raise TypeError(f"Unsupported row type: {type(item)!r}")
    return rows


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    input_path = Path(path)
    if not input_path.exists():
        raise CLIError(f"Fichier introuvable: {input_path}")
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def read_discovery_csv(path: str | Path) -> list[DomainDiscovery]:
    rows = read_csv_rows(path)
    results: list[DomainDiscovery] = []
    for index, row in enumerate(rows, start=2):
        domain = (row.get("domain") or "").strip()
        if not domain:
            raise CLIError(f"Ligne {index}: colonne 'domain' manquante ou vide dans {path}")
        results.append(
            DomainDiscovery(
                domain=domain,
                source_query=(row.get("source_query") or "").strip(),
                source_provider=(row.get("source_provider") or "").strip(),
                first_seen=(row.get("first_seen") or "").strip(),
                title=(row.get("title") or "").strip(),
                snippet=(row.get("snippet") or "").strip(),
            )
        )
    return results


def read_scored_csv(path: str | Path) -> list[QualifiedDomain]:
    rows = read_csv_rows(path)
    results: list[QualifiedDomain] = []
    for index, row in enumerate(rows, start=2):
        domain = (row.get("domain") or "").strip()
        if not domain:
            raise CLIError(f"Ligne {index}: colonne 'domain' manquante ou vide dans {path}")
        score_raw = (row.get("score") or "0").strip()
        try:
            score = int(float(score_raw))
        except ValueError as exc:
            raise CLIError(f"Ligne {index}: score invalide '{score_raw}' dans {path}") from exc

        results.append(
            QualifiedDomain(
                score=score,
                domain=domain,
                cms=(row.get("cms") or "").strip(),
                estimated_pages=_bool_or_int(row.get("estimated_pages") or "0"),
                hard_blocked=_as_bool(row.get("hard_blocked")),
                size_score=_bool_or_int(row.get("size_score") or "0"),
                rejected=_as_bool(row.get("rejected")),
                rejection_reason=(row.get("rejection_reason") or "").strip(),
                rejection_confidence=(row.get("rejection_confidence") or "").strip(),
                has_blog=_as_bool(row.get("has_blog")),
                has_dated_content=_as_bool(row.get("has_dated_content")),
                dated_urls_count=_bool_or_int(row.get("dated_urls_count") or "0"),
                contact_found=(row.get("contact_found") or "").strip(),
                social_links=_split_pipe(row.get("social_links") or ""),
                issues=_split_pipe(row.get("issues") or ""),
                title=(row.get("title") or "").strip(),
                notes=(row.get("notes") or "").strip(),
                sitemap_available=_as_bool(row.get("sitemap_available")),
                source_query=(row.get("source_query") or "").strip(),
                source_provider=(row.get("source_provider") or "").strip(),
                first_seen=(row.get("first_seen") or "").strip(),
                is_editorial_candidate=_as_bool(row.get("is_editorial_candidate")),
                is_app_like=_as_bool(row.get("is_app_like")),
                app_signal=_bool_or_int(row.get("app_signal") or "0"),
                is_docs_like=_as_bool(row.get("is_docs_like")),
                docs_signal=_bool_or_int(row.get("docs_signal") or "0"),
                is_marketplace_like=_as_bool(row.get("is_marketplace_like")),
                marketplace_signal=_bool_or_int(row.get("marketplace_signal") or "0"),
                refresh_repair_fit=(row.get("refresh_repair_fit") or "").strip(),
                site_type_note=(row.get("site_type_note") or "").strip(),
                nav_link_ratio=_as_float(row.get("nav_link_ratio")),
                content_link_ratio=_as_float(row.get("content_link_ratio")),
                editorial_word_count=_bool_or_int(row.get("editorial_word_count") or "0"),
            )
        )
    return results


def discovery_rows(items: list[DomainDiscovery]) -> list[dict[str, Any]]:
    return [
        {
            "domain": item.domain,
            "source_query": item.source_query,
            "source_provider": item.source_provider,
            "first_seen": item.first_seen,
            "title": item.title,
            "snippet": item.snippet,
        }
        for item in items
    ]


def qualified_rows(items: list[QualifiedDomain]) -> list[dict[str, Any]]:
    return [
        {
            "score": item.score,
            "domain": item.domain,
            "cms": item.cms,
            "estimated_pages": item.estimated_pages,
            "hard_blocked": "yes" if item.hard_blocked else "",
            "size_score": item.size_score,
            "rejected": "yes" if item.rejected else "",
            "rejection_reason": item.rejection_reason,
            "rejection_confidence": item.rejection_confidence,
            "has_blog": "yes" if item.has_blog else "",
            "has_dated_content": "yes" if item.has_dated_content else "",
            "dated_urls_count": item.dated_urls_count,
            "contact_found": item.contact_found,
            "social_links": " | ".join(item.social_links),
            "issues": " | ".join(item.issues),
            "title": item.title,
            "notes": item.notes,
            "sitemap_available": "yes" if item.sitemap_available else "",
            "source_query": item.source_query,
            "source_provider": item.source_provider,
            "first_seen": item.first_seen,
            "is_editorial_candidate": "yes" if item.is_editorial_candidate else "",
            "is_app_like": "yes" if item.is_app_like else "",
            "app_signal": item.app_signal,
            "is_docs_like": "yes" if item.is_docs_like else "",
            "docs_signal": item.docs_signal,
            "is_marketplace_like": "yes" if item.is_marketplace_like else "",
            "marketplace_signal": item.marketplace_signal,
            "refresh_repair_fit": item.refresh_repair_fit,
            "site_type_note": item.site_type_note,
            "nav_link_ratio": round(item.nav_link_ratio, 2),
            "content_link_ratio": round(item.content_link_ratio, 2),
            "editorial_word_count": item.editorial_word_count,
        }
        for item in items
    ]


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _as_bool(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in {"1", "true", "yes", "oui"}


def _bool_or_int(value: str) -> int:
    try:
        return int(float(value.strip() or "0"))
    except ValueError:
        return 0


def _as_float(value: str | None) -> float:
    try:
        return round(float((value or "").strip() or "0"), 2)
    except ValueError:
        return 0.0
