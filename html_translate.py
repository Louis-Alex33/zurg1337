from __future__ import annotations

import json
import time
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from deep_translator import GoogleTranslator

CACHE_FILE = Path(__file__).resolve().parent / "translation_cache.json"

# Tags dont on ne traduit pas le contenu
_SKIP_TAGS = {"script", "style", "code", "pre", "svg"}

# Attributs HTML à traduire (ex: title, alt, placeholder)
_TRANSLATE_ATTRS = {"title", "alt", "placeholder", "aria-label"}


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _batch_translate(texts: list[str], target_lang: str, cache: dict) -> list[str]:
    to_translate = [(i, t) for i, t in enumerate(texts) if t not in cache]
    results = list(texts)

    if not to_translate:
        return [cache.get(t, t) for t in texts]

    # Envoie par batch de 50 pour éviter les timeouts
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
    return [cache.get(t, t) for t in texts]


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
        # Ignore si c'est un nombre pur, une URL, ou trop court
        if stripped.replace(",", "").replace(".", "").replace(" ", "").replace("%", "").replace("+", "").replace("-", "").isnumeric():
            continue
        if stripped.startswith("http") or stripped.startswith("/"):
            continue
        if len(stripped) < 2:
            continue
        text_nodes.append(node)
        text_values.append(stripped)

    # Traduit en batch
    translated_values = _batch_translate(text_values, target_lang, cache)

    # Réinjecte les traductions en préservant les espaces originaux
    for node, original_stripped, translated in zip(text_nodes, text_values, translated_values):
        original = str(node)
        # Préserve les espaces/sauts de ligne autour du texte
        new_text = original.replace(original_stripped, translated, 1)
        node.replace_with(NavigableString(new_text))

    return str(soup)
