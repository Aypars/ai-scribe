"""Per-meeting language for Whisper, speaker labels, and analysis prompts."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Literal

from app.services.turkish import fix_sentence_i

Lang = Literal["tr", "en"]

current_lang: ContextVar[Lang] = ContextVar("meeting_lang", default="tr")


def normalize_lang(value: str | None) -> Lang:
    raw = (value or "").strip().lower()
    if raw in {"en", "eng", "english", "ingilizce"}:
        return "en"
    return "tr"


def is_en() -> bool:
    return current_lang.get() == "en"


def speaker_prefix() -> str:
    return "Speaker" if is_en() else "Konuşmacı"


def maybe_fix_i(text: str, lang: str | None = None) -> str:
    use = normalize_lang(lang) if lang is not None else current_lang.get()
    if use == "en":
        return text
    return fix_sentence_i(text)
