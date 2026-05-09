from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from deep_translator import GoogleTranslator

CACHE_FILE = Path(__file__).resolve().parent / "translation_cache.json"

# Tags dont on ne traduit pas le contenu
_SKIP_TAGS = {"script", "style", "code", "pre", "svg"}

_URL_RE = re.compile(r"https?://[^\s\`\"<>]+|`[^`]+`")


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _protect_urls(text: str) -> tuple[str, dict[str, str]]:
    """Remplace les URLs et backtick-strings par des placeholders avant traduction."""
    placeholders = {}
    def replacer(m: re.Match) -> str:
        key = f"__PH{len(placeholders)}__"
        placeholders[key] = m.group(0)
        return key
    protected = _URL_RE.sub(replacer, text)
    return protected, placeholders


def _restore_urls(text: str, placeholders: dict[str, str]) -> str:
    for key, original in placeholders.items():
        text = text.replace(key, original)
    return text


def _batch_translate(texts: list[str], target_lang: str, cache: dict) -> list[str]:
    # Protège les URLs dans chaque texte
    protected_texts = []
    all_placeholders = []
    for t in texts:
        protected, ph = _protect_urls(t)
        protected_texts.append(protected)
        all_placeholders.append(ph)

    to_translate = [(i, t) for i, t in enumerate(protected_texts) if t not in cache]
    results = list(protected_texts)

    if to_translate:
        batch_size = 50
        for batch_start in range(0, len(to_translate), batch_size):
            batch = to_translate[batch_start : batch_start + batch_size]
            batch_texts = [t for _, t in batch]
            try:
                translated = GoogleTranslator(source="fr", target=target_lang).translate_batch(batch_texts)
                time.sleep(0.2)
            except Exception:
                translated = batch_texts

            for (i, original), tr in zip(batch, translated):
                cache[original] = tr or original
                results[i] = cache[original]

        _save_cache(cache)

    # Restaure les URLs dans les résultats
    return [_restore_urls(cache.get(pt, pt), ph) for pt, ph in zip(protected_texts, all_placeholders)]


def translate_html(html: str, target_lang: str) -> str:
    if target_lang == "fr":
        return html

    cache = _load_cache()
    soup = BeautifulSoup(html, "html.parser")

    # Collecte tous les noeuds texte à traduire
    text_nodes: list[NavigableString] = []
    text_values: list[str] = []

    for node in soup.find_all(string=True):
        # Ignore si le tag parent est à skipper
        parent = node.parent
        if parent and parent.name in _SKIP_TAGS:
            continue
        text = str(node)
        stripped = text.strip()
        if not stripped:
            continue
        # Ignore si c'est un nombre pur ou trop court
        if stripped.replace(",", "").replace(".", "").replace(" ", "").replace("%", "").replace("+", "").replace("-", "").isnumeric():
            continue
        if len(stripped) < 2:
            continue
        # Ignore si c'est une URL pure (sans autre texte)
        if _URL_RE.fullmatch(stripped):
            continue
        text_nodes.append(node)
        text_values.append(stripped)

    # Traduit en batch
    translated_values = _batch_translate(text_values, target_lang, cache)

    # Réinjecte les traductions en préservant les espaces originaux
    for node, original_stripped, translated in zip(text_nodes, text_values, translated_values):
        original = str(node)
        leading = original[: len(original) - len(original.lstrip())]
        trailing = original[len(original.rstrip()):]
        node.replace_with(NavigableString(leading + translated + trailing))

    return str(soup)
