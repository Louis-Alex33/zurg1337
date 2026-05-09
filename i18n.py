from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from deep_translator import GoogleTranslator

SUPPORTED_LANGUAGES = {"fr", "en"}
CACHE_FILE = Path(__file__).resolve().parent / "translation_cache.json"


def normalize_language(lang: str | None) -> str:
    value = str(lang or "").strip().lower()
    return value if value in SUPPORTED_LANGUAGES else "fr"


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _translate(text: str, target_lang: str, cache: dict, save: bool = True) -> str:
    if not text or not text.strip():
        return text
    if text in cache:
        return cache[text]
    try:
        translated = GoogleTranslator(source="fr", target=target_lang).translate(text)
        time.sleep(0.1)
    except Exception:
        return text
    cache[text] = translated
    if save:
        _save_cache(cache)
    return translated


class I18n:
    def __init__(self, lang: str):
        self.lang = lang
        self._cache: dict = _load_cache() if lang != "fr" else {}

    def gettext(self, message: str) -> str:
        if self.lang == "fr":
            return message
        return _translate(message, self.lang, self._cache)

    def flush(self) -> None:
        if self.lang != "fr":
            _save_cache(self._cache)


def get_i18n(lang: str | None) -> I18n:
    return I18n(lang=normalize_language(lang))


def get_text(lang: str | None) -> Callable[[str], str]:
    return get_i18n(lang).gettext
