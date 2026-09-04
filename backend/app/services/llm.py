"""Gemini / OpenAI JSON completions used by analysis, ask, and speakers."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.services.meeting_lang import current_lang

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

TModel = TypeVar("TModel", bound=BaseModel)

class AnalysisError(Exception):
    pass

def _reload_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_PATH, override=True)
    except Exception:
        return


def _api_key() -> str:
    _reload_env()
    return (os.getenv("GEMINI_API_KEY") or settings.gemini_api_key or "").strip()


def _model_name() -> str:
    _reload_env()
    return (os.getenv("GEMINI_MODEL") or settings.gemini_model or "gemini-3.1-flash-lite").strip()


def _friendly_gemini_error(exc: BaseException) -> str:
    text = str(exc)
    lowered = text.lower()
    if "api_key_invalid" in lowered or "api key not valid" in lowered:
        return (
            "Gemini API anahtarı geçersiz. AI Studio’dan yeni anahtarı tam kopyalayıp "
            "backend/.env içindeki GEMINI_API_KEY satırına yapıştır, sonra tekrar dene."
        )
    if "permission" in lowered or "unauthenticated" in lowered:
        return "Gemini yetkisi reddedildi. Anahtarın Gemini API için açık olduğundan emin ol."
    if _is_quota_gemini(text):
        return (
            "Gemini ücretsiz kotası doldu. Kart gerekmez; kota yarın sıfırlanır. "
            "Aynı anahtarla GEMINI_MODEL=gemini-3.1-flash-lite veya gemini-2.5-flash-lite dene."
        )
    if _is_transient_gemini(text):
        return "Gemini şu an yoğun. Biraz sonra otomatik tekrar denenecek."
    return text or "Gemini isteği başarısız"


def _is_quota_gemini(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "resource_exhausted",
            "quota",
            "rate limit",
            "rate_limit",
            "429",
            "limit: 0",
            "exceeded",
        )
    )


def _is_transient_gemini(text: str) -> bool:
    if _is_quota_gemini(text):
        return False
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "503",
            "unavailable",
            "high demand",
            "overloaded",
            "temporarily",
            "try again",
            "yoğun",
        )
    )


TModel = TypeVar("TModel", bound=BaseModel)

_EN_FIELD_DESC = {
    "text": "One sentence: the adopted/rejected/chosen result. Keep named people, amounts, and places. Not a follow-up job.",
    "source_seq_start": "First transcript line # for this decision only",
    "source_seq_end": "Last transcript line # for this decision only; keep the span tight",
    "description": "Follow-up someone took on or assigned after the meeting. Not a question, complaint, or allegation.",
    "assignee": "Always null. Do not assign an owner.",
    "due_date": "YYYY-MM-DD; null if no explicit date",
    "notes": "1-2 sentences of context",
    "decisions": "Group outcomes. Keep names. Assigned follow-up work belongs in actions.",
    "actions": "Follow-up jobs someone took on or assigned. Not a question, complaint, allegation, or 'we'll discuss later'.",
    "section": "Narrative of this chunk. At least 3 paragraphs. No markdown.",
    "summary_frame": "Context, 4–6 sentences from the transcript. Do not write the heading.",
    "summary_agenda": "Agenda. Do not paste chunks. 4–7 sentences per topic. Do not write the heading.",
    "summary_close": "Outcome, 4–6 sentences. Actual close in the transcript. Do not write the heading.",
    "summary": "Fallback. Leave empty if the three fields are filled.",
}


def _output_lang_block() -> str:
    if current_lang.get() == "en":
        return (
            "Output language: English. Write every string field in English "
            "(section, summary_frame, summary_agenda, summary_close, decisions, actions, notes). "
            "Proper names stay as spoken.\n\n"
        )
    return (
        "Çıktı dili: Türkçe. Her metin alanını Türkçe yaz "
        "(section, summary_frame, summary_agenda, summary_close, decisions, actions, notes). "
        "Özel isimler konuşulduğu gibi kalsın.\n\n"
    )


def _json_schema(schema: type[BaseModel]) -> dict:
    payload = json.loads(json.dumps(schema.model_json_schema()))
    if current_lang.get() != "en":
        return payload

    def walk(obj: object, key: str | None) -> None:
        if isinstance(obj, dict):
            if key in _EN_FIELD_DESC and "description" in obj:
                obj["description"] = _EN_FIELD_DESC[key]
            for child_key, child in obj.items():
                walk(child, child_key)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, key)

    walk(payload, None)
    return payload


def _parse_model(model: type[TModel], raw: str) -> TModel:
    try:
        return model.model_validate_json(raw)
    except Exception:
        return model.model_validate(json.loads(raw))


def _openai_key() -> str:
    _reload_env()
    return (os.getenv("OPENAI_API_KEY") or settings.openai_api_key or "").strip()


def _openai_model() -> str:
    _reload_env()
    return (os.getenv("OPENAI_MODEL") or settings.openai_model or "gpt-4o-mini").strip()


def _model_candidates() -> list[str]:
    primary = _model_name()
    out = [primary]
    for name in ("gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"):
        if name not in out:
            out.append(name)
    return out


def _generate_json(
    client: object,
    prompt: str,
    schema: type[TModel],
    *,
    max_output_tokens: int = 8192,
    on_busy: Callable[[int], None] | None = None,
    waits: tuple[int, ...] = (0, 8),
) -> TModel:
    last: BaseException | None = None
    for model_name in _model_candidates():
        for attempt, wait in enumerate(waits, start=1):
            if wait:
                logger.warning("Gemini busy, retry %s on %s after %ss", attempt, model_name, wait)
                if on_busy:
                    on_busy(wait)
                time.sleep(wait)
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=_output_lang_block() + prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_json_schema": _json_schema(schema),
                        "system_instruction": _output_lang_block().strip(),
                        "max_output_tokens": max_output_tokens,
                    },
                )
            except Exception as exc:
                last = exc
                if _is_quota_gemini(str(exc)):
                    logger.warning("Gemini quota on %s, trying next free model", model_name)
                    break
                if _is_transient_gemini(str(exc)) and attempt < len(waits):
                    continue
                raise AnalysisError(_friendly_gemini_error(exc)) from exc
            raw = (response.text or "").strip()
            if not raw:
                last = AnalysisError("Gemini boş yanıt döndü")
                if attempt < len(waits):
                    continue
                break
            try:
                logger.warning("Gemini analysis used model %s", model_name)
                return _parse_model(schema, raw)
            except Exception as exc:
                last = exc
                if attempt < len(waits):
                    continue
                break
    raise AnalysisError(_friendly_gemini_error(last or Exception("Gemini isteği başarısız")))


def _generate_openai_json(
    prompt: str,
    schema: type[TModel],
    *,
    max_output_tokens: int = 16384,
) -> TModel:
    from openai import OpenAI

    key = _openai_key()
    if not key:
        raise AnalysisError("OPENAI_API_KEY tanımlı değil.")
    client = OpenAI(api_key=key, timeout=120.0)
    try:
        response = client.chat.completions.create(
            model=_openai_model(),
            messages=[
                {
                    "role": "system",
                    "content": _output_lang_block().strip() + " Return valid JSON only. No markdown.",
                },
                {"role": "user", "content": _output_lang_block() + prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_output_tokens,
        )
    except Exception as exc:
        text = str(exc)
        if _is_quota_gemini(text):
            raise AnalysisError(
                "OpenAI kotası veya bakiyesi doldu. platform.openai.com → Billing’den kredi yükle."
            ) from exc
        raise AnalysisError(text or "OpenAI isteği başarısız") from exc
    raw = ((response.choices[0].message.content if response.choices else None) or "").strip()
    if not raw:
        raise AnalysisError("OpenAI boş yanıt döndü")
    try:
        return _parse_model(schema, raw)
    except Exception as exc:
        raise AnalysisError("OpenAI yanıtı çözümlenemedi") from exc


def _complete_json(
    prompt: str,
    schema: type[TModel],
    *,
    gemini_key: str,
    openai_key: str,
    max_output_tokens: int,
    on_busy: Callable[[int], None] | None = None,
    waits: tuple[int, ...] = (0, 8),
) -> TModel:
    if gemini_key:
        from google import genai

        client = genai.Client(api_key=gemini_key)
        try:
            return _generate_json(
                client,
                prompt,
                schema,
                max_output_tokens=max_output_tokens,
                on_busy=on_busy,
                waits=waits,
            )
        except AnalysisError as exc:
            if openai_key and _is_quota_gemini(str(exc)):
                logger.warning("Gemini quota hit, falling back to OpenAI %s", _openai_model())
                return _generate_openai_json(prompt, schema, max_output_tokens=max_output_tokens)
            raise
    return _generate_openai_json(prompt, schema, max_output_tokens=max_output_tokens)
