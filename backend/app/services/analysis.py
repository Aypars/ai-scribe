"""Meeting analysis via Gemini: summary, decisions, action items."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.models.transcript import Transcript
from app.services.turkish import fix_sentence_i

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

ANALYSIS_PROMPT = """Sen AI-SCRIBE için kıdemli bir toplantı raportörüsün. Transkripti baştan sona oku; atlama, sıkıştırarak yok etme.

Kayıt her türlü toplantı olabilir: şirket, ekip, müşteri, okul, dernek, belediye, meclis veya başka bir görüşme. Türe varsayım yapma.

Boş veya toplantı değilse (müzik, gürültü, şarkı sözü, sessizlik, anlamsız ses):
- summary: 1-2 cümle, kaydın toplantı olmadığını söyle.
- decisions: [].
- actions: [].
Uydurma karar, beyan, kapanış, gündem YASAK.

Toplantıysa JSON alanları:

- summary: Kurumsal toplantı raporu. Tek paragraf YASAK. Kısa kayıtta en az 3–4 paragraf; uzun toplantıda gündem maddesi başına ayrı paragraf, üst sınır yok.
  Yapı (her blok kendi paragrafı, başlık ayrı satır, markdown/madde işareti yok):
  1) Çerçeve: tür, tarih, kim yönetti, kimler katıldı, amaç.
  2) Gündem akışı: her madde sırayla; talep, kim ne dedi, gerekçe, varılan nokta.
  3) İdari hususlar: atama, yetki, protokol, alım, bağış, sevk. Yoksa bu bloğu atla.
  4) Sonuç.
  Uydurma isim, rakam, olay yok.

- decisions: Alınan HER karar. Sayı tavanı yok. Kabul, ret, sevk, atama, yetki, protokol, alım — ayrı madde.
  Aksiyon kararı silmez. Konuşulup bağlanan bir şey aksiyonda varsa kararda da olsun.
  “toplantı bitti / beyanla sona erdi” karar değildir. Tek cümle. source_seq_start / source_seq_end dar.

- actions: Yalnızca BU transkriptte yapılacak denmiş işler. Başka toplantıdaki aksiyonu kopyalama.
  Sayı tavanı yok. Birleştirip kısa liste yapma.
  description: net iş.
  assignee: yalnızca transkriptteki konuşmacı etiketi (Konuşmacı A/B/C…). Kişi defteri, başka toplantı, tahmin isim YASAK. Emin değilsen null.
  due_date: yalnız açık tarih. notes: 1 cümle veya "".

Üslup:
- Transkriptle aynı dil.
- Konuşmacı etiketlerini transkriptteki haliyle bırak (Konuşmacı A/B/C…).
- Bu kayıt tek başına. Başlık benzer diye başka toplantıdaki kişi veya işi yazma.
"""



class AnalysisError(Exception):
    pass


class DecisionDraft(BaseModel):
    text: str = Field(description="Tek net karar cümlesi")
    source_seq_start: int | None = Field(
        default=None,
        description="Yalnızca bu karara ait ilk transkript satırının # numarası; alakasız satır alma",
    )
    source_seq_end: int | None = Field(
        default=None,
        description="Yalnızca bu karara ait son transkript satırının # numarası; aralığı dar tut",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_span(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if data.get("source_seq_start") is None and data.get("source_seq") is not None:
            data["source_seq_start"] = data["source_seq"]
        if data.get("source_seq_end") is None:
            data["source_seq_end"] = data.get("source_seq_start")
        return data


class ActionDraft(BaseModel):
    description: str = Field(description="Yapılacak somut iş; tek net cümle")
    assignee: str | None = Field(
        default=None,
        description="Yalnızca bu transkriptteki Konuşmacı A/B/C etiketi; yoksa null. Başka toplantıdaki kişi yazma.",
    )
    due_date: str | None = Field(default=None, description="YYYY-MM-DD; açık tarih yoksa null")
    notes: str = Field(default="", description="1-2 cümle bağlam")


class AnalysisDraft(BaseModel):
    actions: list[ActionDraft] = Field(
        default_factory=list,
        description="Yalnızca bu transkriptteki işler. Başka toplantıdan kopyalama. Tavan yok.",
    )
    decisions: list[DecisionDraft] = Field(
        default_factory=list,
        description="Alınan, reddedilen veya sevk edilen her karar. Atlanmaz. Dar source_seq_start / source_seq_end.",
    )
    summary: str = Field(
        description="Kapsamlı kurumsal toplantı raporu. Tek paragraf yasak. Gündem maddelerini sırayla anlatan birden fazla paragraf."
    )

    @field_validator("decisions", mode="before")
    @classmethod
    def _coerce_decisions(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        items: list[object] = []
        for item in value:
            if isinstance(item, str):
                items.append({"text": item})
            else:
                items.append(item)
        return items


@dataclass
class DecisionResult:
    text: str
    source_seq: int | None
    source_end_seq: int | None


@dataclass
class ActionResult:
    description: str
    assignee: str | None
    due_date: date | None
    notes: str


@dataclass
class AnalysisResult:
    summary: str
    decisions: list[DecisionResult]
    actions: list[ActionResult]
    speakers: dict[str, str]


_STOP = {
    "icin",
    "için",
    "olan",
    "olarak",
    "daha",
    "gibi",
    "bir",
    "bu",
    "su",
    "şu",
    "ile",
    "ve",
    "veya",
    "ama",
    "fakat",
    "karar",
    "alindi",
    "alınan",
    "olacak",
    "edilecek",
    "yapilacak",
    "yapılacak",
    "benimsenecek",
    "konusunda",
    "hakkinda",
    "hakkında",
    "sonra",
    "once",
    "önce",
    "kadar",
    "uzere",
    "üzere",
}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[0-9a-zA-ZğüşöçıİĞÜŞÖÇ]+", (text or "").casefold())
    return [word for word in words if len(word) >= 4 and word not in _STOP]


def match_decision_seq(text: str, lines: list[Transcript], hinted: int | None = None) -> int | None:
    valid = {row.seq for row in lines if getattr(row, "seq", None) is not None}
    if hinted in valid:
        return hinted
    keys = _tokens(text)
    if not keys or not lines:
        return None
    best_seq: int | None = None
    best_score = 0
    for row in lines:
        seq = getattr(row, "seq", None)
        hay = (getattr(row, "text", None) or "")
        if not isinstance(hay, str):
            continue
        hay = hay.casefold()
        score = sum(1 for key in keys if key in hay)
        if seq is not None and score > best_score:
            best_score = score
            best_seq = seq
    if best_seq is None:
        return None
    needed = 2 if len(keys) >= 4 else 1
    return best_seq if best_score >= needed else None


def match_decision_span(
    text: str,
    lines: list[Transcript],
    start_hint: int | None = None,
    end_hint: int | None = None,
) -> tuple[int | None, int | None]:
    valid = {row.seq for row in lines if getattr(row, "seq", None) is not None}
    if not valid:
        return None, None

    start_ok = start_hint if start_hint in valid else None
    end_ok = end_hint if end_hint in valid else None
    if start_ok is not None:
        lo = start_ok
        hi = end_ok if end_ok is not None else start_ok
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    center_seq = match_decision_seq(text, lines)
    if center_seq is None:
        return None, None
    return center_seq, center_seq


def _fmt_ts(seconds: int) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _transcript_text(lines: list[Transcript]) -> str:
    chunks: list[str] = []
    for row in lines:
        stamp = _fmt_ts(row.timestamp)
        speaker = row.speaker or "Konuşmacı"
        chunks.append(f"[#{row.seq} {stamp}] {speaker}: {row.text.strip()}")
    return "\n".join(chunks)


def _parse_due(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


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
    return (os.getenv("GEMINI_MODEL") or settings.gemini_model or "gemini-3-flash-preview").strip()


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
            "Gemini ücretsiz kotası doldu (bu modelde günde 20 istek). "
            "Yarın sıfırlanır. Şimdi devam için Google AI Studio’da faturalama aç "
            "veya backend/.env içinde GEMINI_MODEL’i kotası kalan bir modele çevir."
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


def _parse_model(model: type[TModel], raw: str) -> TModel:
    try:
        return model.model_validate_json(raw)
    except Exception:
        return model.model_validate(json.loads(raw))


def _generate_json(
    client: object,
    prompt: str,
    schema: type[TModel],
    *,
    max_output_tokens: int = 8192,
    on_busy: Callable[[int], None] | None = None,
    waits: tuple[int, ...] = (0, 8, 20),
) -> TModel:
    last: BaseException | None = None
    for attempt, wait in enumerate(waits, start=1):
        if wait:
            logger.warning("Gemini busy, retry %s after %ss", attempt, wait)
            if on_busy:
                on_busy(wait)
            time.sleep(wait)
        try:
            response = client.models.generate_content(
                model=_model_name(),
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": schema.model_json_schema(),
                    "max_output_tokens": max_output_tokens,
                },
            )
        except Exception as exc:
            last = exc
            if _is_quota_gemini(str(exc)):
                raise AnalysisError(_friendly_gemini_error(exc)) from exc
            if _is_transient_gemini(str(exc)) and attempt < len(waits):
                continue
            raise AnalysisError(_friendly_gemini_error(exc)) from exc
        raw = (response.text or "").strip()
        if not raw:
            last = AnalysisError("Gemini boş yanıt döndü")
            if attempt < len(waits):
                continue
            raise last
        try:
            return _parse_model(schema, raw)
        except Exception as exc:
            last = exc
            if attempt < len(waits):
                continue
            raise AnalysisError("Gemini yanıtı çözümlenemedi") from exc
    raise AnalysisError(_friendly_gemini_error(last or Exception("Gemini isteği başarısız")))


def _speaker_labels(lines: list[Transcript]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for row in lines:
        name = (row.speaker or "").strip()
        if name:
            allowed[name.casefold()] = name
    return allowed


def _assignee_in_meeting(raw: str | None, allowed: dict[str, str]) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    hit = allowed.get(text.casefold())
    if hit:
        return hit
    short = text.rsplit(maxsplit=1)[-1]
    return allowed.get(f"konuşmacı {short}".casefold())


def _append_actions(
    items: list[ActionDraft],
    actions: list[ActionResult],
    seen: set[str],
    allowed: dict[str, str],
) -> None:
    for item in items:
        description_text = fix_sentence_i((item.description or "").strip())
        key = " ".join(description_text.lower().split())
        if not description_text or key in seen:
            continue
        seen.add(key)
        actions.append(
            ActionResult(
                description=description_text,
                assignee=_assignee_in_meeting(item.assignee, allowed),
                due_date=_parse_due(item.due_date),
                notes=fix_sentence_i((item.notes or "").strip()),
            )
        )


def analyze_transcript(
    lines: list[Transcript],
    *,
    title: str,
    attendees: str | None,
    meeting_date: str | None,
    description: str | None = None,
    on_busy: Callable[[int], None] | None = None,
) -> AnalysisResult:
    api_key = _api_key()
    if not api_key:
        raise AnalysisError("GEMINI_API_KEY tanımlı değil.")
    if not lines:
        raise AnalysisError("Analiz için transkript yok.")

    from google import genai

    body = _transcript_text(lines)
    speakers = ", ".join(_speaker_labels(lines).values()) or "yok"
    extra = f"Açıklama: {description}\n" if description else ""
    header = (
        f"Bu kayıt tek başına analiz edilecek. Başka toplantı, kişi listesi veya önceki analiz yok.\n"
        f"Toplantı başlığı (yalnızca bu kayıt): {title}\n"
        f"Tarih: {meeting_date or 'belirtilmedi'}\n"
        f"Bu transkriptteki konuşmacı etiketleri: {speakers}\n"
        f"{extra}\n"
        f"Transkript:\n{body}\n"
    )

    client = genai.Client(api_key=api_key)
    try:
        draft = _generate_json(
            client,
            f"{ANALYSIS_PROMPT}\n{header}",
            AnalysisDraft,
            max_output_tokens=16384,
            on_busy=on_busy,
        )
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError(_friendly_gemini_error(exc)) from exc

    summary = fix_sentence_i(draft.summary.strip())
    if not summary:
        raise AnalysisError("Özet boş geldi")

    decisions: list[DecisionResult] = []
    for item in draft.decisions:
        text = fix_sentence_i(item.text.strip())
        if not text:
            continue
        start_seq, end_seq = match_decision_span(
            text, lines, item.source_seq_start, item.source_seq_end
        )
        decisions.append(DecisionResult(text=text, source_seq=start_seq, source_end_seq=end_seq))

    seen: set[str] = set()
    actions: list[ActionResult] = []
    _append_actions(draft.actions, actions, seen, _speaker_labels(lines))
    logger.warning("Gemini analysis summary_len=%s decisions=%s actions=%s", len(summary), len(decisions), len(actions))

    return AnalysisResult(summary=summary, decisions=decisions, actions=actions, speakers={})
