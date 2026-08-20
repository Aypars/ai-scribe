"""Map generic diarization labels to real person names via Gemini."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.services.turkish import title_word

logger = logging.getLogger(__name__)

GENERIC_LABEL = re.compile(r"^Konuşmacı\s+[A-Z0-9]+$", re.I)
_STRIP_PREFIX = re.compile(r"^sayın\s+", re.I)


class SpeakerGuess(BaseModel):
    label: str = Field(description="Konuşmacı A gibi diarization etiketi")
    name: str = Field(description="Transkriptteki kişi adı")


class SpeakerGuessList(BaseModel):
    mappings: list[SpeakerGuess] = Field(default_factory=list)


def is_generic_label(name: str | None) -> bool:
    value = (name or "").strip()
    return bool(value) and GENERIC_LABEL.match(value) is not None


def revert_invalid_speaker_names(_lines: list) -> dict[str, str]:
    """No-op. Kept so uvicorn reload cannot ImportError mid-save."""
    return {}


def _strip_guess_mark(name: str) -> str:
    return name.strip().removesuffix("?").strip()


def speaker_name(raw: str | None) -> str | None:
    """Take Gemini's name as-is. Empty or a leftover Konuşmacı etiketi is not a name."""
    text = re.sub(r"\s+", " ", (raw or "").strip(" .,;:!?-"))
    text = _STRIP_PREFIX.sub("", text).strip()
    if not text or is_generic_label(text):
        return None
    words = [title_word(part) for part in text.split() if part]
    return " ".join(words) or None


def display_name(name: str, *, guessed: bool = False) -> str:
    clean = _strip_guess_mark(name)
    return f"{clean} ?" if guessed else clean


def rewrite_labels(text: str, mapping: dict[str, str]) -> str:
    out = text or ""
    for label, name in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if label and name and label != name:
            out = out.replace(label, _strip_guess_mark(name))
    return out


def _transcript_for_names(lines: list) -> str:
    return "\n".join(
        f"[#{row.seq}] {row.speaker or 'Konuşmacı'}: {(row.text or '').strip()}"
        for row in lines
        if (row.text or "").strip()
    )


def _match_label(raw: str, allowed: dict[str, str]) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    hit = allowed.get(text.casefold())
    if hit:
        return hit
    short = text.rsplit(maxsplit=1)[-1]
    return allowed.get(f"konuşmacı {short}".casefold())


def _gemini_map(lines: list, *, title: str) -> dict[str, SpeakerGuess]:
    labels = sorted({(row.speaker or "").strip() for row in lines if is_generic_label(row.speaker)})
    if not labels:
        return {}

    from app.services.analysis import AnalysisError, _api_key, _generate_json

    api_key = _api_key()
    if not api_key:
        return {}

    from google import genai

    prompt = f"""Transkriptteki Konuşmacı A/B/C… etiketlerini gerçek kişi adlarıyla eşle.

Kural:
- Başkan "Buyurun Sayın Mehmet Yılmaz" deyip ardından o etiket konuşuyorsa o kişidir.
- Biri kendini "Ben İsmail Bey" diye tanıtıyorsa odur.
- name alanına transkriptte geçen kişi adını yaz.
- Eşleyemediğin etiketi listeden tamamen çıkar. Uydurma, tahmin, cümle, fiil yazma.

Toplantı: {title}
Etiketler: {", ".join(labels)}

Transkript:
{_transcript_for_names(lines)}
"""
    client = genai.Client(api_key=api_key)
    try:
        draft = _generate_json(client, prompt, SpeakerGuessList, max_output_tokens=4096, waits=(0, 6))
    except AnalysisError:
        logger.exception("Speaker name resolution via Gemini failed")
        return {}
    out: dict[str, SpeakerGuess] = {}
    allowed = {label.casefold(): label for label in labels}
    for item in draft.mappings:
        label = _match_label(item.label, allowed)
        name = speaker_name(item.name)
        if not label or not name:
            continue
        out[label] = SpeakerGuess(label=label, name=name)
    logger.warning("Gemini speaker mappings kept %s/%s: %s", len(out), len(labels), out)
    return out


def _put_map(mapping: dict[str, str], lines: list, label: str, shown: str) -> None:
    mapping[label] = shown
    for row in lines:
        current = (row.speaker or "").strip()
        origin = (row.speaker_origin or "").strip()
        if current == label or origin == label:
            mapping[current] = shown


def resolve_speaker_map(lines: list, *, title: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        for label, guess in _gemini_map(lines, title=title).items():
            _put_map(mapping, lines, label, display_name(guess.name, guessed=False))
    except Exception:
        logger.exception("Speaker name resolution via Gemini failed")
    return {source: target for source, target in mapping.items() if source and target and source != target}
