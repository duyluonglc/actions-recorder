"""Minimal UI translation: English source strings, Vietnamese dictionary."""

from __future__ import annotations

import locale
import os

_lang = "en"


def detect() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v.lower().startswith("vi"):
            return "vi"
    try:
        from PySide6.QtCore import QLocale
        if QLocale.system().name().lower().startswith("vi"):
            return "vi"
    except Exception:
        pass
    try:
        loc = locale.getlocale()[0] or ""
        if loc.lower().startswith("vi"):
            return "vi"
    except Exception:
        pass
    return "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = detect() if lang in ("", "auto", None) else lang


def language() -> str:
    return _lang


def tr(s: str) -> str:
    if _lang == "vi":
        return VI.get(s, s)
    return s


from .i18n_vi import VI  # noqa: E402
