from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

from config import BIG_SITE_DOMAINS, HARD_BLOCKED_DOMAINS, HARD_BLOCKED_SUFFIXES, REQUEST_HEADERS


class CLIError(Exception):
    """Exception levee pour les erreurs utilisateur comprehensibles en CLI."""


@dataclass(slots=True)
class LimitedHTMLResponse:
    url: str
    request_url: str
    status_code: int
    content_type: str
    text: str = ""
    content_length: int = 0
    too_large: bool = False
    skip_reason: str = ""
    redirect_count: int = 0


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_domain(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    domain = parsed.netloc.lower().replace("www.", "").strip()
    return domain.rstrip(".")


def domain_from_url(url: str) -> str:
    return clean_domain(url)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def absolute_url(base_url: str, href: str) -> str:
    return normalize_url(urljoin(base_url, href))


def parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session


def is_big_site(domain: str) -> bool:
    domain = clean_domain(domain)
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in BIG_SITE_DOMAINS)


def is_hard_blocked_domain(domain: str) -> bool:
    domain = clean_domain(domain)
    if any(domain == blocked or domain.endswith(f".{blocked}") for blocked in HARD_BLOCKED_DOMAINS):
        return True
    return any(domain.endswith(suffix) for suffix in HARD_BLOCKED_SUFFIXES)


def coerce_int(value: str | int | None, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    cleaned = value.replace("\xa0", "").replace(" ", "").replace(",", "").strip()
    if not cleaned:
        return default
    return int(cleaned)


def coerce_float(value: str | float | None, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float):
        return value
    cleaned = value.replace("%", "").replace(",", ".").strip()
    if not cleaned:
        return default
    return float(cleaned)


def truncate(text: str, size: int) -> str:
    if len(text) <= size:
        return text
    return text[: max(0, size - 3)].rstrip() + "..."


def unique_everseen(items: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    ordered: list[Any] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def decode_duckduckgo_target(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        params = parse_qs(parsed.query)
        target = params.get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def contains_year_reference(text: str) -> bool:
    return bool(re.search(r"\b20(1[8-9]|2[0-9])\b", text))


def fetch_limited_html(
    session: requests.Session,
    url: str,
    timeout: int,
    max_html_bytes: int,
    allow_redirects: bool = True,
    max_redirects: int = 5,
) -> LimitedHTMLResponse:
    with session.get(url, timeout=timeout, allow_redirects=allow_redirects, stream=True) as response:
        content_type = response.headers.get("content-type", "")
        redirect_count = len(response.history)
        request_url = response.request.url if response.request is not None else url
        if redirect_count > max_redirects:
            return LimitedHTMLResponse(
                url=response.url,
                request_url=request_url,
                status_code=response.status_code,
                content_type=content_type,
                skip_reason="too_many_redirects",
                redirect_count=redirect_count,
            )
        if response.status_code >= 400:
            return LimitedHTMLResponse(
                url=response.url,
                request_url=request_url,
                status_code=response.status_code,
                content_type=content_type,
                redirect_count=redirect_count,
            )
        if "text/html" not in content_type.lower():
            return LimitedHTMLResponse(
                url=response.url,
                request_url=request_url,
                status_code=response.status_code,
                content_type=content_type,
                skip_reason="non_html",
                redirect_count=redirect_count,
            )

        header_length = response.headers.get("content-length", "").strip()
        if header_length.isdigit() and int(header_length) > max_html_bytes:
            return LimitedHTMLResponse(
                url=response.url,
                request_url=request_url,
                status_code=response.status_code,
                content_type=content_type,
                content_length=int(header_length),
                too_large=True,
                skip_reason="html_too_large",
                redirect_count=redirect_count,
            )

        chunks: list[bytes] = []
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=16_384):
            if not chunk:
                continue
            total_bytes += len(chunk)
            if total_bytes > max_html_bytes:
                return LimitedHTMLResponse(
                    url=response.url,
                    request_url=request_url,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=total_bytes,
                    too_large=True,
                    skip_reason="html_too_large",
                    redirect_count=redirect_count,
                )
            chunks.append(chunk)

        encoding = response.encoding or "utf-8"
        text = b"".join(chunks).decode(encoding, errors="replace")
        return LimitedHTMLResponse(
            url=response.url,
            request_url=request_url,
            status_code=response.status_code,
            content_type=content_type,
            text=text,
            content_length=total_bytes,
            redirect_count=redirect_count,
        )
