"""Gemini review of transcript: proper-name casing fixes and obvious-error warnings."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.services.meeting_lang import current_lang

logger = logging.getLogger(__name__)


class ReviewItem(BaseModel):
    seq: int = Field(description="Transkript satır numarası")
    original: str = Field(description="Satırda geçen tam parça")
    suggestion: str = Field(description="Önerilen düzeltme")
    kind: Literal["proper_name", "warning"] = "warning"
    reason: str = Field(default="", description="Kısa gerekçe")


class ReviewDraft(BaseModel):
    items: list[ReviewItem] = Field(default_factory=list)


def _fold_tr(value: str) -> str:
    return value.replace("İ", "i").replace("I", "ı").casefold()


def is_case_only(original: str, suggestion: str) -> bool:
    left = original.strip()
    right = suggestion.strip()
    return bool(left and right and left != right and _fold_tr(left) == _fold_tr(right))


def replace_ci(text: str, original: str, replacement: str) -> str | None:
    span = find_span(text, original)
    if span is None:
        return None
    start, end = span
    return text[:start] + replacement.strip() + text[end:]


def find_span(text: str, original: str) -> tuple[int, int] | None:
    needle = original.strip()
    if not needle:
        return None
    exact = text.find(needle)
    if exact >= 0:
        return exact, exact + len(needle)
    folded = _fold_tr(text)
    start = folded.find(_fold_tr(needle))
    if start < 0:
        return None
    return start, start + len(needle)


def review_transcript(lines: list, *, title: str) -> list[ReviewItem]:
    from app.services.analysis import _transcript_text
    from app.services.llm import _api_key, _model_name

    api_key = _api_key()
    if not api_key or not lines:
        return []

    from google import genai

    prompt = f"""Toplantı transkriptini baştan yazma. Sadece çok bariz sorunları işaretle.

1) proper_name: Özel isim küçük harfle yazılmışsa düzelt (ahmet yılmaz → Ahmet Yılmaz). Yalnızca büyük/küçük harf. Harf ekleme/çıkarma yok.
   Türkçe: i→İ, ı→I. Işık/Irmak/Ilık I ile kalır; İçişleri/İstanbul/İsmail İ ile yazılır. I harfini rastgele İ yapma.
2) warning: Satır anlamsız ASR saçmalığıysa (kelime salatası, yanlış dil, kopuk hece) işaretle ve kısa öneri ver. Emin değilsen dokunma.

Az sayıda, bariz olanlar. Şüphede boş bırak. original, satırdaki metnin birebir parçası olsun.

Toplantı: {title}

Transkript:
{_transcript_text(lines)}
"""
    if current_lang.get() == "en":
        prompt = f"""Do not rewrite the meeting transcript. Flag only very obvious issues.

1) proper_name: If a proper name is in lowercase, fix casing only (jane doe → Jane Doe). No added or removed letters.
2) warning: If a line is ASR nonsense (word salad, wrong language, broken syllables), flag it with a short suggestion. If unsure, leave it.

Few items, only the obvious ones. When in doubt, leave empty. original must be an exact span of that line.

Meeting: {title}

Transcript:
{_transcript_text(lines)}
"""
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=_model_name(),
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": ReviewDraft.model_json_schema(),
        },
    )
    raw = (response.text or "").strip()
    if not raw:
        return []
    draft = ReviewDraft.model_validate_json(raw)
    by_seq = {row.seq: (row.text or "") for row in lines}
    cleaned: list[ReviewItem] = []
    seen: set[tuple[int, str]] = set()
    for item in draft.items:
        text = by_seq.get(item.seq)
        original = item.original.strip()
        suggestion = item.suggestion.strip()
        if not text or not original or not suggestion or original == suggestion:
            continue
        if find_span(text, original) is None:
            continue
        key = (item.seq, _fold_tr(original))
        if key in seen:
            continue
        seen.add(key)
        kind = item.kind
        if kind == "proper_name" and not is_case_only(original, suggestion):
            kind = "warning"
        cleaned.append(
            ReviewItem(
                seq=item.seq,
                original=original,
                suggestion=suggestion,
                kind=kind,
                reason=(item.reason or "").strip()[:180],
            )
        )
        if len(cleaned) >= 40:
            break
    return cleaned
