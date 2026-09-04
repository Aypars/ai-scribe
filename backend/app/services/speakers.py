"""Match diarization labels to names the user typed at upload."""

from __future__ import annotations

import concurrent.futures
import logging
import re

from pydantic import BaseModel, Field

from app.services.meeting_lang import current_lang
from app.services.turkish import lower_tr, title_word

logger = logging.getLogger(__name__)

GENERIC_LABEL = re.compile(r"^(?:Konuşmacı|Speaker)\s+[A-Z0-9]+$", re.I)
_STRIP_PREFIX = re.compile(r"^(?:sayın|mr\.?|ms\.?|mrs\.?|mx\.?)\s+", re.I)
_SPLIT_NAMES = re.compile(r"[,;\n]+")


def _title_person(word: str) -> str:
    if current_lang.get() == "en":
        return word[:1].upper() + word[1:] if word else word
    return title_word(word)


class SpeakerGuess(BaseModel):
    label: str = Field(description="Diarization label such as Speaker A")
    name: str = Field(description="Person name from the user-provided list")


class SpeakerGuessList(BaseModel):
    mappings: list[SpeakerGuess] = Field(default_factory=list)


def is_generic_label(name: str | None) -> bool:
    value = (name or "").strip()
    return bool(value) and GENERIC_LABEL.match(value) is not None


def revert_invalid_speaker_names(_lines: list) -> dict[str, str]:
    """No-op. Kept so uvicorn reload cannot ImportError mid-save."""
    return {}


def strip_guess_mark(name: str) -> str:
    return name.strip().removesuffix("?").strip()


def speaker_name(raw: str | None) -> str | None:
    text = re.sub(r"\s+", " ", (raw or "").strip(" .,;:!?-"))
    text = _STRIP_PREFIX.sub("", text).strip()
    if not text or is_generic_label(text):
        return None
    words = [_title_person(part) for part in text.split() if part]
    return " ".join(words) or None


def display_name(name: str, *, guessed: bool = False) -> str:
    clean = strip_guess_mark(name)
    return f"{clean} ?" if guessed else clean


def parse_named_attendees(raw: str | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for part in _SPLIT_NAMES.split(raw or ""):
        name = speaker_name(part)
        if not name:
            continue
        key = lower_tr(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def rewrite_name_list(raw: str | None, mapping: dict[str, str]) -> str | None:
    if raw is None:
        return None
    folded = {lower_tr(old.strip()): new.strip() for old, new in mapping.items() if old and new}
    if not folded:
        return raw
    parts: list[str] = []
    seen: set[str] = set()
    for part in _SPLIT_NAMES.split(raw):
        name = part.strip()
        if not name:
            continue
        replaced = folded.get(lower_tr(name), name)
        key = lower_tr(replaced)
        if key in seen:
            continue
        seen.add(key)
        parts.append(replaced)
    return ", ".join(parts) if parts else None


def rewrite_labels(text: str, mapping: dict[str, str]) -> str:
    out = text or ""
    for label, name in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if label and name and label != name:
            out = out.replace(label, name)
    return out


def _match_label(raw: str, allowed: dict[str, str]) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    hit = allowed.get(text.casefold())
    if hit:
        return hit
    short = text.rsplit(maxsplit=1)[-1]
    return allowed.get(f"konuşmacı {short}".casefold()) or allowed.get(f"speaker {short}".casefold())


_INVITE = re.compile(
    r"\b(buyur(?:un|unuz|urum)?|söz\s+(?:sizde|sizin|onun)|mikrofon(?:u|unu)?\s+(?:ver|al)|söz\s+ver|"
    r"go\s+ahead|the\s+floor\s+is\s+yours|over\s+to\s+you)\b",
    re.I,
)


def _name_in_text(name: str, text: str) -> bool:
    needle = lower_tr(name).strip()
    if len(needle) < 2:
        return False
    pattern = re.compile(rf"(?<![0-9a-zçğıöşü]){re.escape(needle)}(?![0-9a-zçğıöşü])")
    return bool(pattern.search(lower_tr(text or "")))


def name_in_transcript(name: str, lines: list) -> bool:
    return any(_name_in_text(name, row.text or "") for row in lines)


def _is_invite_for(text: str, name: str) -> bool:
    if not _name_in_text(name, text):
        return False
    folded = lower_tr(text)
    if _INVITE.search(folded):
        return True
    stripped = folded.strip()
    return stripped.startswith("sayın") and len(stripped) < 90


def speaker_invites_name(label: str, name: str, lines: list) -> bool:
    mentions: list[bool] = []
    for row in lines:
        if (row.speaker or "").strip() != label:
            continue
        if not _name_in_text(name, row.text or ""):
            continue
        mentions.append(_is_invite_for(row.text or "", name))
    return bool(mentions) and all(mentions)


def _resolve_declared(raw: str | None, declared: list[str]) -> str | None:
    text = speaker_name(raw)
    if not text:
        return None
    folded = lower_tr(text)
    exact = [name for name in declared if lower_tr(name) == folded]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    partial = [
        name
        for name in declared
        if lower_tr(name).startswith(folded) or folded.startswith(lower_tr(name))
    ]
    if len(partial) == 1:
        return partial[0]
    return None


def filter_speaker_mappings(
    items: list,
    lines: list,
    names: list[str],
) -> dict[str, str]:
    """Keep AI guesses only when the name was declared and spoken."""
    labels = {(row.speaker or "").strip() for row in lines if is_generic_label(row.speaker)}
    if not labels or not names:
        return {}
    allowed = {label.casefold(): label for label in labels}
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for item in items:
        label = _match_label(getattr(item, "label", None), allowed)
        name = _resolve_declared(getattr(item, "name", None), names)
        if not label or not name or name in used:
            continue
        if not name_in_transcript(name, lines):
            logger.warning("Skip speaker map %s → %s; name not in transcript", label, name)
            continue
        if speaker_invites_name(label, name, lines):
            logger.warning("Skip speaker map %s → %s; this label only invites that name", label, name)
            continue
        used.add(name)
        mapping[label] = display_name(name, guessed=True)
    logger.warning("Speaker mappings kept %s/%s: %s", len(mapping), len(labels), mapping)
    return mapping


def _transcript_for_names(lines: list) -> str:
    return "\n".join(
        f"[#{row.seq}] {row.speaker or ('Speaker' if current_lang.get() == 'en' else 'Konuşmacı')}: {(row.text or '').strip()}"
        for row in lines
        if (row.text or "").strip()
    )


def resolve_speaker_map(lines: list, *, title: str = "", names: list[str] | None = None) -> dict[str, str]:
    declared = [name for name in (names or []) if name]
    labels = sorted({(row.speaker or "").strip() for row in lines if is_generic_label(row.speaker)})
    mentioned = [name for name in declared if name_in_transcript(name, lines)]
    if not labels or not mentioned:
        return {}

    from app.services.analysis import AnalysisError, _api_key, _generate_json

    api_key = _api_key()
    if not api_key:
        return {}

    from google import genai

    if current_lang.get() == "en":
        prompt = f"""Map Speaker A/B/C labels only to names the user provided.

Attendee list (do not invent names outside this list): {", ".join(mentioned)}

Rules:
- name must be one of the names on this list. Do not invent a person.
- If that name is not clearly in the transcript, do not map them.
- The person who SAYS "please, Jane / the floor is yours, Jane" is not that name; they are the chair inviting them.
- The DIFFERENT label that starts speaking right after the invite is that person.
- If someone introduces themselves with a list name, that is them.
- If there is no evidence, drop that label. No guessing.

Meeting: {title}
Labels: {", ".join(labels)}

Transcript:
{_transcript_for_names(lines)}
"""
    else:
        prompt = f"""Konuşmacı A/B/C etiketlerini yalnızca kullanıcının verdiği isimlerle eşle.

Katılımcı listesi (bunların DIŞINDA isim yazma): {", ".join(mentioned)}

Kural:
- name yalnızca bu listedeki bir isim olsun. Yeni kişi uydurma.
- Transkriptte o isim açıkça geçmiyorsa o kişiyi eşleme.
- "Buyurun Simge Hanım / Söz Simge Hanım'da" DİYEN kişi o isim değildir; davet eden başkan/moderatördür.
- Davetten hemen SONRA konuşmaya başlayan FARKLI etiket o kişidir.
- Biri kendini listedeki isimle tanıtıyorsa odur.
- Kanıt yoksa o etiketi listeden çıkar. Tahmin yasak.

Toplantı: {title}
Etiketler: {", ".join(labels)}

Transkript:
{_transcript_for_names(lines)}
"""
    client = genai.Client(api_key=api_key)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                lambda: _generate_json(
                    client, prompt, SpeakerGuessList, max_output_tokens=2048, waits=(0,)
                )
            )
            draft = future.result(timeout=30)
    except concurrent.futures.TimeoutError:
        logger.warning("Speaker name resolution timed out")
        return {}
    except AnalysisError:
        logger.exception("Speaker name resolution via Gemini failed")
        return {}
    except Exception:
        logger.exception("Speaker name resolution failed")
        return {}
    return filter_speaker_mappings(draft.mappings, lines, declared)
