from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Paths to probe in order for a contact/about page.
_CONTACT_PATHS = [
    "/contact",
    "/about",
    "/a-propos",
    "/qui-sommes-nous",
    "/equipe",
    "/team",
    "/mentions-legales",
]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Lazy-loaded spacy models — loaded once per process, keyed by model name.
_SPACY_MODELS: dict[str, object] = {}


def _load_spacy(model_name: str) -> object | None:
    if model_name in _SPACY_MODELS:
        return _SPACY_MODELS[model_name]
    try:
        import spacy  # type: ignore[import-untyped]
        nlp = spacy.load(model_name)
        _SPACY_MODELS[model_name] = nlp
        return nlp
    except Exception as exc:
        logger.warning("spacy model %s unavailable: %s", model_name, exc)
        _SPACY_MODELS[model_name] = None
        return None


@dataclass
class ContactResult:
    has_contact_page: bool = False
    contact_page_url: str = ""
    emails: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)


async def fetch_contact_signals(
    domain: str,
    session: "aiohttp.ClientSession",
    timeout: int = 8,
    lang: str = "fr",
) -> ContactResult:
    """Probe contact/about paths sequentially, return first HTTP-200 result."""
    base = f"https://{domain}"
    spacy_model = "fr_core_news_sm" if lang == "fr" else "en_core_web_sm"

    for path in _CONTACT_PATHS:
        url = f"{base}{path}"
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text(errors="replace")
                return _parse_contact_page(
                    html=html,
                    url=str(resp.url),
                    spacy_model=spacy_model,
                )
        except Exception as exc:
            logger.debug("contact probe %s: %s", url, exc)
            continue

    return ContactResult()


def _parse_contact_page(html: str, url: str, spacy_model: str) -> ContactResult:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Emails: mailto: links first, then regex over visible text.
    emails: list[str] = []
    seen_emails: set[str] = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if href.startswith("mailto:"):
            addr = href[7:].split("?")[0].strip().lower()
            if addr and addr not in seen_emails:
                seen_emails.add(addr)
                emails.append(addr)
    for match in _EMAIL_RE.finditer(text):
        addr = match.group(0).lower()
        if addr not in seen_emails:
            seen_emails.add(addr)
            emails.append(addr)

    # Names via spacy NER (PERSON entities), fallback to empty list.
    names: list[str] = []
    nlp = _load_spacy(spacy_model)
    if nlp is not None:
        # Cap text length to keep latency reasonable.
        doc = nlp(text[:4000])
        seen_names: set[str] = set()
        for ent in doc.ents:
            if ent.label_ == "PER" and ent.text not in seen_names:
                seen_names.add(ent.text)
                names.append(ent.text)

    return ContactResult(
        has_contact_page=True,
        contact_page_url=url,
        emails=emails,
        names=names,
    )
