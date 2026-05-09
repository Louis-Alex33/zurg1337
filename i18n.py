from __future__ import annotations

import gettext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SUPPORTED_LANGUAGES = {"fr", "en"}
DEFAULT_DOMAIN = "messages"
LOCALE_DIR = Path(__file__).resolve().parent / "locales"


def normalize_language(lang: str | None) -> str:
    value = str(lang or "").strip().lower()
    return value if value in SUPPORTED_LANGUAGES else "fr"


@dataclass(frozen=True)
class I18n:
    lang: str
    translations: gettext.NullTranslations

    def gettext(self, message: str) -> str:
        if self.lang == "fr":
            return message
        if not message:
            return message
        return self.translations.gettext(message)


def get_i18n(lang: str | None, domain: str = DEFAULT_DOMAIN) -> I18n:
    active_lang = normalize_language(lang)
    translations = gettext.translation(
        domain,
        localedir=str(LOCALE_DIR),
        languages=[active_lang],
        fallback=True,
    )
    return I18n(lang=active_lang, translations=translations)


def get_text(lang: str | None, domain: str = DEFAULT_DOMAIN) -> Callable[[str], str]:
    return get_i18n(lang, domain=domain).gettext
