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
    requested_url: str = ""
    final_url: str = ""
    status_code: int = 0
    title: str = ""
    meta_description: str = ""
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)
    word_count: int = 0
    internal_links_out: list[str] = field(default_factory=list)
    internal_link_anchors_out: dict[str, list[str]] = field(default_factory=dict)
    generic_internal_anchor_count: int = 0
    empty_internal_anchor_count: int = 0
    images_total: int = 0
    images_without_alt: int = 0
    depth: int = 0
    load_time: float = 0.0
    issues: list[str] = field(default_factory=list)
    dated_references: list[str] = field(default_factory=list)
    canonical: str = ""
    canonical_status: str = ""
    meta_robots: str = ""
    is_noindex: bool = False
    robots_allowed: bool = True
    redirect_count: int = 0
    redirect_chain: list[str] = field(default_factory=list)
    redirect_source: str = ""
    redirect_cleanup_needed: bool = False
    redirect_cleanup_recommendation: str = ""
    has_structured_data: bool = False
    structured_data_text: str = ""
    page_type: str = ""
    page_type_confidence: str = ""
    page_type_reason: str = ""
    business_value: str = ""
    business_reason: str = ""
    monetization_potential: str = ""
    date_signals: list[dict[str, str | int]] = field(default_factory=list)
    outdated_date_signal: bool = False
    date_signal_locations: list[str] = field(default_factory=list)
    date_severity: str = ""
    recommended_date_action: str = ""
    inbound_internal_links_count: int = 0
    outbound_internal_links_count: int = 0
    internal_link_strength: str = ""
    orphan_like: bool = False
    linked_from_homepage: bool = False
    linked_from_high_value_pages: bool = False
    anchors_received: list[str] = field(default_factory=list)
    duplicate_anchors: list[str] = field(default_factory=list)
    recommended_source_pages: list[str] = field(default_factory=list)
    recommended_anchor_texts: list[str] = field(default_factory=list)
    internal_links_to_redirected_urls: list[str] = field(default_factory=list)
    duplicate_group_id: str = ""
    duplicate_group_size: int = 0
    duplicate_type: str = ""
    recommended_unique_angle: str = ""
    recovery_opportunity_score: int = 0
    crawl_based_recovery_score: int = 0
    recovery_priority: str = ""
    recovery_reason: str = ""
    needs_gsc_validation: bool = True
    evidence_sources: list[str] = field(default_factory=list)
    source: str = ""
    crawl_depth: int = 0
    load_time_seconds: float = 0.0
    crawl_error: str = ""
    page_health_score: int = 100
    content_like: bool = False
    meaningful_h1_count: int = 0
    overlap_fingerprint: str = ""
    requested_url_normalized: str = ""
    final_url_normalized: str = ""
    canonical_url_normalized: str = ""
    path_normalized: str = ""
    gsc_data_available: bool = False
    gsc_matched: bool = False
    gsc_match_type: str = ""
    gsc_clicks_before: int = 0
    gsc_clicks_after: int = 0
    gsc_click_loss: int = 0
    gsc_click_loss_pct: float | None = None
    gsc_impressions_before: int = 0
    gsc_impressions_after: int = 0
    gsc_impression_loss: int = 0
    gsc_impression_loss_pct: float | None = None
    gsc_ctr_before: float = 0.0
    gsc_ctr_after: float = 0.0
    gsc_ctr_delta: float = 0.0
    gsc_position_before: float = 0.0
    gsc_position_after: float = 0.0
    gsc_position_delta: float = 0.0
    gsc_top_losing_queries: list[dict[str, Any]] = field(default_factory=list)
    potential_cannibalization: bool = False
    cannibalization_group_id: str = ""
    competing_urls: list[str] = field(default_factory=list)
    cannibalization_confidence: str = ""
    content_quality: dict[str, Any] = field(default_factory=dict)
    commercial_signal_score: int = 0
    trust_signal_score: int = 0
    intent_clarity_score: int = 0
    content_recommendations: list[str] = field(default_factory=list)
    recommended_action: str = ""
    suggested_title: str = ""
    suggested_meta_description: str = ""
    all_requested_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AuditReport:
    domain: str
    audited_at: str
    pages_crawled: int
    observed_health_score: int
    technical_health_score: int = 0
    seo_opportunity_score: int = 0
    urgency_level: str = ""
    report_type: str = "standard"
    report_mode: str = "executive"
    site_context: str = ""
    lang: str = "fr"
    recovery_opportunity_score: int = 0
    confidence_level: str = ""
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
    technical_checks: dict[str, Any] = field(default_factory=dict)
    internal_linking_opportunities: list[dict[str, Any]] = field(default_factory=list)
    top_recovery_opportunities: list[dict[str, Any]] = field(default_factory=list)
    traffic_drop_investigation: dict[str, Any] = field(default_factory=dict)
    page_type_breakdown: dict[str, int] = field(default_factory=dict)
    business_value_breakdown: dict[str, int] = field(default_factory=dict)
    redirect_summary: dict[str, Any] = field(default_factory=dict)
    site: dict[str, Any] = field(default_factory=dict)
    structured_summary: dict[str, Any] = field(default_factory=dict)
    traffic_drop: dict[str, Any] = field(default_factory=dict)
    top_losing_pages: list[dict[str, Any]] = field(default_factory=list)
    top_losing_queries: list[dict[str, Any]] = field(default_factory=list)
    top_losing_countries: list[dict[str, Any]] = field(default_factory=list)
    top_losing_devices: list[dict[str, Any]] = field(default_factory=list)
    traffic_losing_pages_with_crawl_issues: list[dict[str, Any]] = field(default_factory=list)
    recovery_candidates: list[dict[str, Any]] = field(default_factory=list)
    cannibalization_groups: list[dict[str, Any]] = field(default_factory=list)
    content_intent_gaps: list[dict[str, Any]] = field(default_factory=list)
    methodology: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    crawl_metadata: dict[str, Any] = field(default_factory=dict)
    history_path: str = ""
    html_path: str = ""
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
    page_type: str = ""
    business_value: str = "low"
    business_reason: str = ""
    monetization_possible: str = "none"
    opportunity_score: int = 0
    priority_label: str = "Watch"
    action_type: str = "content refresh"
    main_query: str = ""
    recommendation: str = ""
    cannibalization_group_id: str = ""
    urls_in_group: list[str] = field(default_factory=list)
    shared_queries: list[str] = field(default_factory=list)
    cannibalization_confidence: str = ""
    cannibalization_recommendation: str = ""
