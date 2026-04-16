from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DomainDiscovery:
    domain: str
    source_query: str
    source_provider: str
    first_seen: str
    title: str = ""
    snippet: str = ""


@dataclass(slots=True)
class QualificationSignals:
    domain: str
    title: str = ""
    cms: str = ""
    estimated_pages: int = 0
    hard_blocked: bool = False
    size_score: int = 0
    rejected: bool = False
    rejection_reason: str = ""
    rejection_confidence: str = ""
    has_blog: bool = False
    has_dated_content: bool = False
    dated_urls_count: int = 0
    contact_found: str = ""
    social_links: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    notes: str = ""
    sitemap_available: bool = False
    source_query: str = ""
    source_provider: str = ""
    first_seen: str = ""
    is_editorial_candidate: bool = False
    is_app_like: bool = False
    app_signal: int = 0
    is_docs_like: bool = False
    docs_signal: int = 0
    is_marketplace_like: bool = False
    marketplace_signal: int = 0
    refresh_repair_fit: str = ""
    site_type_note: str = ""
    nav_link_ratio: float = 0.0
    content_link_ratio: float = 0.0
    editorial_word_count: int = 0


@dataclass(slots=True)
class QualifiedDomain:
    score: int
    domain: str
    cms: str = ""
    estimated_pages: int = 0
    hard_blocked: bool = False
    size_score: int = 0
    rejected: bool = False
    rejection_reason: str = ""
    rejection_confidence: str = ""
    has_blog: bool = False
    has_dated_content: bool = False
    dated_urls_count: int = 0
    contact_found: str = ""
    social_links: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    title: str = ""
    notes: str = ""
    sitemap_available: bool = False
    source_query: str = ""
    source_provider: str = ""
    first_seen: str = ""
    is_editorial_candidate: bool = False
    is_app_like: bool = False
    app_signal: int = 0
    is_docs_like: bool = False
    docs_signal: int = 0
    is_marketplace_like: bool = False
    marketplace_signal: int = 0
    refresh_repair_fit: str = ""
    site_type_note: str = ""
    nav_link_ratio: float = 0.0
    content_link_ratio: float = 0.0
    editorial_word_count: int = 0


@dataclass(slots=True)
class AuditPage:
    url: str
    status_code: int = 0
    title: str = ""
    meta_description: str = ""
    h1: list[str] = field(default_factory=list)
    word_count: int = 0
    internal_links_out: list[str] = field(default_factory=list)
    images_total: int = 0
    images_without_alt: int = 0
    depth: int = 0
    load_time: float = 0.0
    issues: list[str] = field(default_factory=list)
    dated_references: list[str] = field(default_factory=list)
    canonical: str = ""
    has_structured_data: bool = False
    content_like: bool = False
    meaningful_h1_count: int = 0
    overlap_fingerprint: str = ""


@dataclass(slots=True)
class AuditReport:
    domain: str
    audited_at: str
    pages_crawled: int
    observed_health_score: int
    notes: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    critical_findings: list[str] = field(default_factory=list)
    probable_orphan_pages: list[str] = field(default_factory=list)
    possible_content_overlap: list[dict[str, Any]] = field(default_factory=list)
    duplicate_titles: dict[str, list[str]] = field(default_factory=dict)
    duplicate_meta_descriptions: dict[str, list[str]] = field(default_factory=dict)
    dated_content_signals: list[dict[str, Any]] = field(default_factory=list)
    business_priority_signals: list[dict[str, Any]] = field(default_factory=list)
    top_pages_to_rework: list[dict[str, Any]] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class GSCPageData:
    url: str
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


@dataclass(slots=True)
class GSCQueryData:
    query: str
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


@dataclass(slots=True)
class GSCPageAnalysis:
    url: str
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0
    prev_clicks: int | None = None
    prev_impressions: int | None = None
    prev_position: float | None = None
    click_delta: int | None = None
    impression_delta: int | None = None
    position_delta: float | None = None
    score: float = 0.0
    category: str = ""
    actions: list[str] = field(default_factory=list)
    priority: str = ""
    possible_overlap_queries: list[str] = field(default_factory=list)
    estimated_recoverable_clicks: int | None = None
    impact_label: str = ""
