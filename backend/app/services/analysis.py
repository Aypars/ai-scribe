"""Meeting analysis via Gemini: summary, decisions, action items."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.models.transcript import Transcript

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

ANALYSIS_PROMPT = """Sen AI-SCRIBE için kıdemli bir toplantı ve görüşme analistisin. Görevin, verilen transkripti bir yönetici asistanı gibi okuyup kurumsal kalitede, net ve kullanılabilir bir analiz üretmektir.

Kayıt resmi bir toplantı, standup, müşteri görüşmesi, ders, dil pratiği, podcast veya gündelik sohbet olabilir. Türü ne olursa olsun boş bırakma. Her kayıttan mutlaka (1) düzgün bir özet, (2) en az birkaç karar / çıkarım ve (3) somut aksiyon maddeleri üret. Kullanıcı bunları görev panosunda görmek zorundadır.

Nasıl düşün:
Transkripti baştan sona oku. Kimlerin konuştuğunu, asıl konuyu, dönülen noktaları, uzlaşılan fikirleri ve “şunu yapalım / bakayım / göndereyim / karar verdik / tamam” gibi taahhütleri yakala. Açıkça “karar aldık” denmese bile üzerinde anlaşılan tercih, kural, tarih, yaklaşım veya sonuç bir karardır. “Yarın bakarım”, “mail atayım”, “şunu hazırlayalım”, “bunu kontrol edelim” gibi cümleler aksiyondur. Sohbet veya dil pratiği olsa bile: pratik hedefleri, tekrar edilecek konular, düzeltilecek hatalar, sonraki adımlar ve kimin ne yapacağı aksiyon olarak yazılsın.

Çıktı alanları (JSON şemasına birebir uy):
- summary: Yönetici özeti. Kısa kayıtta 2 paragraf yeter; uzun toplantıda ihtiyaç kadar yaz, üst sınır yok. Birinci paragraf kaydın türünü, amacını ve katılımcıları versin. Sonrakiler önemli tartışmaları, varılan noktayı ve iş etkisi olan sonuçları anlatsın. Madde işareti kullanma. Uydurma isim, rakam veya olay ekleme; transkriptte geçenleri profesyonel dille toparla.
- decisions: Kayıtta ne kadar karar / uzlaşı / çıkarım varsa hepsini yaz. Sayı tavanı yok; 1 saatlik toplantıda onlarca madde normaldir. Her madde tek, net, sonuç cümlesi olsun (“X konusunda Y yaklaşımı benimsenecek”). Belirsiz “belki konuşulur” cümlelerini karar yapma; örtük uzlaşıyı ve pratik çıkarımları karar olarak yaz. Boş dizi döndürme. Her karar için source_seq_start ve source_seq_end ver: yalnızca BU kararı söyleyen, netleştiren veya onaylayan satırların # numaraları. Aralık mümkün olduğunca dar olsun. İki replikte bittiyse tam o iki satır; tek cümleyse tek satır. Önceki/sonraki gündemi, selamlaşmayı, geçiş cümlesini veya alakasız sohbeti koyma. Dakikaya göre şişirme.
- actions: Kayıtta ne kadar yapılacak iş varsa hepsini yaz. Sayı tavanı yok; tekrar etme, atlama. Her aksiyon yapılabilir bir iş olsun.
  - description: emir kipi / net iş (“Sunumu güncelle”, “Kelime listesini tekrarla”, “Müşteriye tarih teyit et”).
  - assignee: transkriptteki konuşmacı adı; yoksa null.
  - due_date: yalnızca açık bir tarih geçiyorsa YYYY-MM-DD; yoksa null.
  - notes: 1–2 cümle bağlam: neden bu iş çıktı, transkriptte hangi noktaya bağlı.

Üslup:
- Çıktıyı transkriptle aynı dilde yaz (Türkçe kayıt → Türkçe, İngilizce → İngilizce).
- Kurumsal, sakin, kesin ol. Argo, emoji, “aslında / belki / galiba” dolgusu yok.
- Aynı işi iki kez yazma. Aksiyonlar kararı tekrar etmesin; kararı uygulamaya çevirsin.
- Konuşmacı adlarını transkriptteki haliyle kullan (Konuşmacı A gibi etiketler dahil).
- Tarih uydurma. Sayı, isim ve vaatleri transkriptten al.
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
    assignee: str | None = Field(default=None, description="Transkriptteki konuşmacı adı; yoksa null")
    due_date: str | None = Field(default=None, description="YYYY-MM-DD; açık tarih yoksa null")
    notes: str = Field(default="", description="1-2 cümle bağlam")


class AnalysisDraft(BaseModel):
    summary: str = Field(description="Profesyonel yönetici özeti; uzunluk kayda göre, tavan yok")
    decisions: list[DecisionDraft] = Field(
        description="Kayıttaki tüm karar ve çıkarımlar; her birinde dar source_seq_start / source_seq_end olsun"
    )
    actions: list[ActionDraft] = Field(description="Kayıttaki tüm aksiyonlar; sayı tavanı yok, boş olmasın")

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
    return text or "Gemini isteği başarısız"


def analyze_transcript(
    lines: list[Transcript],
    *,
    title: str,
    attendees: str | None,
    meeting_date: str | None,
    description: str | None = None,
) -> AnalysisResult:
    api_key = _api_key()
    if not api_key:
        raise AnalysisError("GEMINI_API_KEY tanımlı değil.")
    if not lines:
        raise AnalysisError("Analiz için transkript yok.")

    from google import genai

    body = _transcript_text(lines)
    extra = f"Açıklama: {description}\n" if description else ""
    prompt = (
        f"{ANALYSIS_PROMPT}\n"
        f"Toplantı: {title}\n"
        f"Tarih: {meeting_date or 'belirtilmedi'}\n"
        f"Katılımcılar: {attendees or 'belirtilmedi'}\n"
        f"{extra}\n"
        f"Transkript:\n{body}\n"
    )

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=_model_name(),
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": AnalysisDraft.model_json_schema(),
            },
        )
    except Exception as exc:
        raise AnalysisError(_friendly_gemini_error(exc)) from exc

    raw = (response.text or "").strip()
    if not raw:
        raise AnalysisError("Gemini boş yanıt döndü")

    try:
        draft = AnalysisDraft.model_validate_json(raw)
    except Exception:
        try:
            draft = AnalysisDraft.model_validate(json.loads(raw))
        except Exception as exc:
            raise AnalysisError("Gemini yanıtı çözümlenemedi") from exc

    summary = draft.summary.strip()
    if not summary:
        raise AnalysisError("Özet boş geldi")

    decisions: list[DecisionResult] = []
    for item in draft.decisions:
        text = item.text.strip()
        if not text:
            continue
        start_seq, end_seq = match_decision_span(
            text, lines, item.source_seq_start, item.source_seq_end
        )
        decisions.append(DecisionResult(text=text, source_seq=start_seq, source_end_seq=end_seq))

    return AnalysisResult(
        summary=summary,
        decisions=decisions,
        actions=[
            ActionResult(
                description=item.description.strip(),
                assignee=(item.assignee or "").strip() or None,
                due_date=_parse_due(item.due_date),
                notes=(item.notes or "").strip(),
            )
            for item in draft.actions
            if item.description.strip()
        ],
    )
