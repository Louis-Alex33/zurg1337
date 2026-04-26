from __future__ import annotations

import re
import base64
import hashlib
import json
import time
from dataclasses import dataclass
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
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


class CachedResponse:
    def __init__(
        self,
        url: str,
        request_url: str,
        status_code: int,
        headers: dict[str, str],
        content: bytes,
        history_urls: list[str],
        encoding: str | None = None,
    ) -> None:
        self.url = url
        self.request = SimpleNamespace(url=request_url)
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.text = content.decode(encoding or "utf-8", errors="replace")
        self.history = [SimpleNamespace(url=item) for item in history_urls]
        self.encoding = encoding or "utf-8"

    def __enter__(self) -> "CachedResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        return None

    def iter_content(self, chunk_size: int = 16_384):  # type: ignore[no-untyped-def]
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error for url: {self.url}")


class CachedSession:
    def __init__(self, cache_dir: str | Path, ttl_seconds: int = 604_800) -> None:
        self.session = make_session()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.headers = self.session.headers

    def get(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        return self.session.post(url, **kwargs)

    def _request(self, method: str, url: str, **kwargs):  # type: ignore[no-untyped-def]
        cache_key = hashlib.sha256(f"{method}:{url}:{kwargs.get('params') or ''}".encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        now = time.time()
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if now - float(payload.get("stored_at", 0)) <= self.ttl_seconds:
                    return CachedResponse(
                        url=str(payload.get("url") or url),
                        request_url=str(payload.get("request_url") or url),
                        status_code=int(payload.get("status_code") or 0),
                        headers={str(k): str(v) for k, v in dict(payload.get("headers") or {}).items()},
                        content=base64.b64decode(str(payload.get("content") or "")),
                        history_urls=[str(item) for item in payload.get("history_urls") or []],
                        encoding=str(payload.get("encoding") or "utf-8"),
                    )
            except Exception:
                pass

        response = self.session.request(method, url, **kwargs)
        content = response.content
        payload = {
            "stored_at": now,
            "url": response.url,
            "request_url": response.request.url if response.request is not None else url,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": base64.b64encode(content).decode("ascii"),
            "history_urls": [item.url for item in response.history],
            "encoding": response.encoding or "utf-8",
        }
        try:
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
        return CachedResponse(
            url=response.url,
            request_url=payload["request_url"],
            status_code=response.status_code,
            headers=dict(response.headers),
            content=content,
            history_urls=payload["history_urls"],
            encoding=response.encoding or "utf-8",
        )


def make_cached_session(cache_dir: str, ttl_seconds: int = 604_800) -> CachedSession:
    return CachedSession(cache_dir=cache_dir, ttl_seconds=ttl_seconds)


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
