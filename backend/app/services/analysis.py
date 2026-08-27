"""Meeting analysis via Gemini: summary, decisions, action items."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
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

JSON sırası: önce decisions, sonra actions, en son summary. Yalnızca özet yazıp listeleri boş bırakmak YASAK.

Boş veya toplantı değilse (müzik, gürültü, şarkı sözü, sessizlik, anlamsız ses):
- decisions: [].
- actions: [].
- summary: 1-2 cümle, kaydın toplantı olmadığını söyle.
Uydurma karar, beyan, kapanış, gündem YASAK.

Toplantıysa:

- decisions: Alınan HER karar. Sayı tavanı yok. Kabul, ret, oy birliği, sevk, atama, yetki, protokol, alım, gündem maddesi — ayrı madde.
  Aksiyon kararı silmez. Konuşulup bağlanan bir şey aksiyonda varsa kararda da olsun.
  “toplantı bitti / beyanla sona erdi” karar değildir. Tek cümle. source_seq_start / source_seq_end dar.
  Meclis/kurul toplantısında en az birkaç karar vardır; boş dizi ancak gerçekten hiç karar yoksa.

- actions: Yalnızca BU transkriptte yapılacak denmiş işler. Başka toplantıdaki aksiyonu kopyalama.
  Sayı tavanı yok. Birleştirip kısa liste yapma.
  description: net iş.
  assignee: her zaman null. Sorumlu kişi eşleme. due_date: yalnız açık tarih. notes: 1 cümle veya "".

- summary: Üç bölümlü resmi tutanak. Karar listesini kopyalama; müzakereyi anlat.
  Çerçeve: 4–6 cümle. Kurul, tarih, katılanlar, gündem başlıkları.
  Gündem akışı: maddeler sırayla, tekrar yok; tartışma + karar. Dilim yapıştırma.
  Sonuç: 4–6 cümle. Takip ve kapanış; boş kapanış cümlesi yok.
  Uydurma yok. ISO tarih yok.

Üslup:
- Transkriptle aynı dil.
- Konuşmacı adlarını transkriptteki güncel haliyle kullan (Ali Yılmaz veya Konuşmacı A).
- Bu kayıt tek başına. Başlık benzer diye başka toplantıdaki kişi veya işi yazma.
"""

CHUNK_PROMPT = """Bu transkript DİLİMİ. Her satırı oku. Uydurma yok. Yalnızca bu satırlar.

JSON: decisions, actions, section.

KARAR (sonuç, usul değil):
- Yazılacak: kabul, ret, sevk, atama, seçilen kişi, yetki, protokol, alım, bağış, resmi olur.
- Bir oylama/seçimin SONUCU tek (veya kazanan başına bir) karardır. “Murat Yıldız İklim Komisyonuna seçildi” yeter.
- YAZILMAYACAK ayrı karar: isimleri ekrana yansıt, oylamayı başlat, aday oku, yoklama, mikrofon, ara, “kura çekelim”, “yeniden oylayalım” tartışmasının her cümlesi. Usul tartışması varsa en fazla bir cümle, asıl sonuç ayrı.
- Farklı komisyon / farklı kişi / farklı gündem maddesi AYRI kalsın. “toplantı bitti” karar değil.
- Tek cümle. source_seq_start / source_seq_end yalnızca bu dilimdeki #.

AKSİYON (toplantıdan SONRA kalacak iş):
- Yazılacak: yazı/olur hazırlamak, tebliğ, ödeme, belge, başka kuruma iletmek, sonraki toplantıya rapor, takip.
- YAZILMAYACAK: salonda şimdi yapılanlar — oylama yapmak, isimleri yansıtmak, kura çekmek, aday belirlemek, seçim sürecini bu oturumda başlatmak. Bunlar görev kartı değil.
- Aynı işi tekrarlama. description net. notes biraz bağlam (1–2 cümle). assignee her zaman null. due_date yalnız açık tarih.

section: Bu dilimin anlatımı. En az 3 paragraf, kısa tutma. Markdown yok, Çerçeve/Gündem/Sonuç başlığı yok.
Her konu için: ne konuşuldu, kim ne önerdi veya itiraz etti, alternatifler, gerekçe, varılan nokta.
Karar cümlesini tek başına yazıp geçme. Usul (mikrofon, ekran, yoklama) bir cümleyi geçmesin.
"""

REFINE_PROMPT = """Ham çıkarımı tutanak kalitesine çek. Yeni olay uydurma. Farklı gündem maddesini silme.

KARARLAR:
- Bir seçim/oylama sürecinin adımlarını birleştir. Sonuç yazılsın: kim seçildi, ne kabul/ret/sevk edildi.
- Örnek yanlış: ayrı ayrı “oylama yapıldı”, “eşitlik oldu”, “kura çekilsin”, “MHP başkanı çeksin”, “kayıt alındı”.
- Örnek doğru: “İklim Değişikliği ve Çevre Komisyonuna Murat Yıldız seçildi (eşitlikte kura).”
- Farklı komisyonlar ve farklı kazananlar AYRI karar kalsın.
- source_seq_start / source_seq_end, birleştirdiğin ham maddelerdeki aralıktan alınsın.

AKSİYONLAR:
- Yalnızca toplantı bittikten sonra yapılacak işler. Salondaki oylama, ekrana yansıtma, kura, aday okuma SİL.
- Aynı takip işini tek maddede birleştir; notes’u biraz geniş tut (hangi birim, ne istenecek).
- assignee her zaman null. Sorumlu kişi yazma.

ÖZET:
- Üç alan: summary_frame, summary_agenda, summary_close. Başlığı metnin içine yazma.
- Üç bölüm de dolu olsun. Çerçeve ve Sonuç’u birer cümleye indirme. Gündem’e ham dilimleri alt alta yapıştırma.
- Dilimler örtüşür; aynı konuyu (ör. yaya geçidi) iki kez yazma. Her madde tek paragraf.
- Yoklama, ekrana yansıtma, mikrofon gibi usulü yazma.
- ISO tarih yasak.
- summary_frame: 4–6 cümle. Kurul, tarih, kim yönetti, kimler, gündemde neler var (madde adlarıyla).
- summary_agenda: her gündem maddesi 4–7 cümle (talep, kim ne dedi, itiraz, gerekçe, karar, takip). Karar listesini kopyalama.
- summary_close: 4–6 cümle. Ana sonuçların kısa bağlanması, takip işleri, kapanış. “Gündem maddeleri karara bağlanmıştır” gibi boş cümle YASAK.
- Uydurma yok. Markdown yok.
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
        description="Her zaman null. Sorumlu kişi eşleme.",
    )
    due_date: str | None = Field(default=None, description="YYYY-MM-DD; açık tarih yoksa null")
    notes: str = Field(default="", description="1-2 cümle bağlam")


def _coerce_decision_items(value: object) -> object:
    if not isinstance(value, list):
        return value
    items: list[object] = []
    for item in value:
        if isinstance(item, str):
            items.append({"text": item})
        else:
            items.append(item)
    return items


def _coerce_action_items(value: object) -> object:
    if not isinstance(value, list):
        return value
    items: list[object] = []
    for item in value:
        if isinstance(item, str):
            items.append({"description": item})
        else:
            items.append(item)
    return items


class ChunkDraft(BaseModel):
    decisions: list[DecisionDraft] = Field(
        description="Bu dilimdeki sonuç kararları. Oylama usulünün her adımı değil.",
    )
    actions: list[ActionDraft] = Field(
        description="Toplantıdan sonra kalacak işler. Salondaki oylama/yansıtma değil.",
    )
    section: str = Field(description="Bu dilimin eksiksiz kısa anlatımı")

    @field_validator("decisions", mode="before")
    @classmethod
    def _coerce_decisions(cls, value: object) -> object:
        return _coerce_decision_items(value)

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: object) -> object:
        return _coerce_action_items(value)


class RefineDraft(BaseModel):
    decisions: list[DecisionDraft] = Field(
        description="Süzülmüş sonuç kararları. Usul adımı yok. Farklı gündemler ayrı.",
    )
    actions: list[ActionDraft] = Field(
        description="Yalnızca toplantı sonrası işler. Salondaki oylama/yansıtma yok.",
    )
    summary_frame: str = Field(
        default="",
        description="Çerçeve, 4–6 cümle. Kurul, tarih, katılanlar, gündem başlıkları. Tek cümle bırakma. Başlık yazma.",
    )
    summary_agenda: str = Field(
        default="",
        description="Gündem akışı. Dilimleri yapıştırma, tekrarları birleştir. Her madde 4–7 cümle. Başlık yazma.",
    )
    summary_close: str = Field(
        default="",
        description="Sonuç, 4–6 cümle. Takip ve kapanış. Boş kapanış cümlesi yazma. Başlık yazma.",
    )
    summary: str = Field(
        default="",
        description="Yedek. Üç alan dolduysa boş bırak.",
    )

    @field_validator("decisions", mode="before")
    @classmethod
    def _coerce_decisions(cls, value: object) -> object:
        return _coerce_decision_items(value)

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: object) -> object:
        return _coerce_action_items(value)


class AnalysisDraft(BaseModel):
    decisions: list[DecisionDraft] = Field(
        default_factory=list,
        description="Alınan, reddedilen veya sevk edilen her karar. Atlanmaz. Dar source_seq_start / source_seq_end.",
    )
    actions: list[ActionDraft] = Field(
        default_factory=list,
        description="Yalnızca bu transkriptteki işler. Başka toplantıdan kopyalama. Tavan yok.",
    )
    summary: str = Field(
        description="Kapsamlı kurumsal toplantı raporu. Tek paragraf yasak. Gündem maddelerini sırayla anlatan birden fazla paragraf."
    )

    @field_validator("decisions", mode="before")
    @classmethod
    def _coerce_decisions(cls, value: object) -> object:
        return _coerce_decision_items(value)

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: object) -> object:
        return _coerce_action_items(value)


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


_MIN_CHUNK_LINES = 80
_CHUNK_OVERLAP = 10
_MAX_CHUNKS = 8


def _chunk_line_count(n: int) -> int:
    if n <= _MIN_CHUNK_LINES + _CHUNK_OVERLAP:
        return n
    size = _MIN_CHUNK_LINES
    while size < n:
        step = max(1, size - _CHUNK_OVERLAP)
        chunks = 1 + (max(0, n - size) + step - 1) // step
        if chunks <= _MAX_CHUNKS:
            return size
        size = min(n, size + 25)
    return n


def _iter_chunks(lines: list[Transcript]) -> list[list[Transcript]]:
    if not lines:
        return []
    size = _chunk_line_count(len(lines))
    if len(lines) <= size:
        return [lines]
    out: list[list[Transcript]] = []
    start = 0
    while start < len(lines):
        end = min(len(lines), start + size)
        out.append(lines[start:end])
        if end >= len(lines):
            break
        start = max(start + 1, end - _CHUNK_OVERLAP)
    return out


def _norm_key(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _jaccard(a: str, b: str) -> float:
    left, right = set(_tokens(a)), set(_tokens(b))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _decision_dup(a: DecisionResult, b: DecisionResult) -> bool:
    if _norm_key(a.text) == _norm_key(b.text):
        return True
    sa, sb = a.source_seq, b.source_seq
    close = sa is not None and sb is not None and abs(sa - sb) <= 12
    return close and _jaccard(a.text, b.text) >= 0.88


def _action_dup(a: ActionResult, b: ActionResult) -> bool:
    if _norm_key(a.description) == _norm_key(b.description):
        return True
    return _jaccard(a.description, b.description) >= 0.93


def _merge_decisions(items: list[DecisionResult]) -> list[DecisionResult]:
    kept: list[DecisionResult] = []
    for item in items:
        hit = next((row for row in kept if _decision_dup(row, item)), None)
        if hit is None:
            kept.append(item)
            continue
        if len(item.text) > len(hit.text):
            kept[kept.index(hit)] = item
    kept.sort(key=lambda row: (row.source_seq is None, row.source_seq or 0))
    return kept


def _assemble_summary(
    *,
    title: str,
    meeting_date: str | None,
    attendees: str | None,
    sections: list[str],
) -> str:
    frame, agenda, close = _summary_parts(
        title=title, meeting_date=meeting_date, attendees=attendees, sections=sections
    )
    return _join_report(frame, agenda, close)


def _summary_parts(
    *,
    title: str,
    meeting_date: str | None,
    attendees: str | None,
    sections: list[str],
) -> tuple[str, str, str]:
    when = _format_meeting_when(meeting_date)
    title_text = (title or "").strip().rstrip(".")
    frame_bits: list[str] = []
    if title_text and when:
        frame_bits.append(f"{title_text}, {when} tarihinde olağan toplantısını yapmıştır.")
    elif title_text:
        frame_bits.append(f"{title_text} olağan toplantısını yapmıştır.")
    elif when:
        frame_bits.append(f"Toplantı {when} tarihinde yapılmıştır.")
    named = (attendees or "").strip()
    if named:
        frame_bits.append(f"Toplantıya {named} katılmıştır.")
    frame_bits.append(
        "Komisyon gündem maddelerini sırayla görüşmüş; talep, itiraz ve öneriler dinlendikten sonra karar almıştır."
    )
    body = [_strip_summary_labels(part) for part in sections]
    body = [part for part in body if part]
    agenda = "\n\n".join(body)
    close = (
        "Oturumda görüşülen her madde için komisyonun tutumu netleşmiş, itiraz edilen noktalar oylanarak bağlanmıştır. "
        "Karara bağlanan işler ilgili birimlerin takibine bırakılmış; süre, tebligat ve yazışma takvimi konuşulmuştur. "
        "Gündem dışı kalan kısa hususlar da kayda geçirilmiş ve toplantı bu çerçevede kapatılmıştır."
    )
    return " ".join(frame_bits), agenda, close


def _join_report(frame: str, agenda: str, close: str) -> str:
    blocks: list[str] = []
    frame_text = _strip_summary_labels(_humanize_dates_in_text(frame))
    agenda_text = _strip_summary_labels(_humanize_dates_in_text(agenda))
    close_text = _strip_summary_labels(_humanize_dates_in_text(close))
    if frame_text:
        blocks.extend(["Çerçeve", frame_text])
    if agenda_text:
        blocks.extend(["Gündem akışı", agenda_text])
    if close_text:
        blocks.extend(["Sonuç", close_text])
    return fix_sentence_i("\n\n".join(blocks).strip())


def _summary_parts_from_draft(text: str) -> tuple[str, str, str]:
    buckets = {"çerçeve": [], "gündem akışı": [], "sonuç": []}
    current: str | None = None
    for line in (text or "").splitlines():
        key = line.strip().casefold()
        if key in buckets:
            current = key
            continue
        if current:
            buckets[current].append(line)
    joined = {name: "\n".join(rows).strip() for name, rows in buckets.items()}
    return joined["çerçeve"], joined["gündem akışı"], joined["sonuç"]


_MONTHS_TR = (
    "",
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)
_SUMMARY_LABEL = re.compile(
    r"^(çerçeve|gündem akışı|gündem|sonuç|katılımcılar|idari hususlar)\s*:?\s*$",
    re.I,
)
_ISO_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?")


def _format_meeting_when(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None and re.match(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            day = date.fromisoformat(raw[:10])
            return f"{day.day} {_MONTHS_TR[day.month]} {day.year}"
        except ValueError:
            return raw
    if parsed is None:
        return raw
    local = parsed.astimezone() if parsed.tzinfo else parsed
    text = f"{local.day} {_MONTHS_TR[local.month]} {local.year}"
    if local.hour or local.minute:
        text += f" saat {local.hour:02d}.{local.minute:02d}"
    return text


def _strip_summary_labels(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _SUMMARY_LABEL.match(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _humanize_dates_in_text(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return _format_meeting_when(match.group(0)) or match.group(0)

    return _ISO_STAMP.sub(replace, text or "")


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
                {"role": "system", "content": "Sadece geçerli JSON yaz. Markdown yok."},
                {"role": "user", "content": prompt},
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


def _speaker_labels(lines: list[Transcript]) -> dict[str, str]:
    from app.services.speakers import strip_guess_mark

    allowed: dict[str, str] = {}
    for row in lines:
        raw = (row.speaker or "").strip()
        if not raw:
            continue
        clean = strip_guess_mark(raw)
        allowed[raw.casefold()] = clean
        allowed[clean.casefold()] = clean
    return allowed


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
                assignee=None,
                due_date=_parse_due(item.due_date),
                notes=fix_sentence_i((item.notes or "").strip()),
            )
        )


def _looks_like_non_meeting(summary: str) -> bool:
    text = (summary or "").casefold()
    return any(
        needle in text
        for needle in (
            "toplantı değil",
            "toplantı olmad",
            "anlamsız ses",
            "kayıt toplantı değil",
        )
    )


def _collect_decisions(items: list[DecisionDraft], lines: list[Transcript]) -> list[DecisionResult]:
    decisions: list[DecisionResult] = []
    for item in items:
        text = fix_sentence_i((item.text or "").strip())
        if not text:
            continue
        start_seq, end_seq = match_decision_span(
            text, lines, item.source_seq_start, item.source_seq_end
        )
        decisions.append(DecisionResult(text=text, source_seq=start_seq, source_end_seq=end_seq))
    return decisions


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


def _format_raw_decisions(items: list[DecisionResult]) -> str:
    rows: list[str] = []
    for index, item in enumerate(items, start=1):
        span = ""
        if item.source_seq is not None:
            end = item.source_end_seq or item.source_seq
            span = f" [#{item.source_seq}–#{end}]"
        rows.append(f"{index}.{span} {item.text}")
    return "\n".join(rows) if rows else "(yok)"


def _format_raw_actions(items: list[ActionResult]) -> str:
    rows: list[str] = []
    for index, item in enumerate(items, start=1):
        note = f" | {item.notes}" if item.notes else ""
        rows.append(f"{index}. {item.description}{note}")
    return "\n".join(rows) if rows else "(yok)"


def _refine_extracted(
    *,
    lines: list[Transcript],
    decisions: list[DecisionResult],
    actions: list[ActionResult],
    speakers: str,
    title: str,
    draft_summary: str,
    gemini_key: str,
    openai_key: str,
    allowed: dict[str, str],
    on_busy: Callable[[int], None] | None,
    on_progress: Callable[[str], None] | None,
) -> tuple[list[DecisionResult], list[ActionResult], str | None]:
    if not decisions and not actions and not (draft_summary or "").strip():
        return decisions, actions, None
    if on_progress:
        on_progress("Karar, görev ve özet süzülüyor…")
    prompt = (
        f"{REFINE_PROMPT}\n"
        f"Toplantı: {title}\n"
        f"Konuşmacı adları: {speakers}\n\n"
        f"Ham kararlar:\n{_format_raw_decisions(decisions)}\n\n"
        f"Ham aksiyonlar:\n{_format_raw_actions(actions)}\n\n"
        f"Ham özet:\n{draft_summary.strip() or '(yok)'}\n"
    )
    try:
        refined = _complete_json(
            prompt,
            RefineDraft,
            gemini_key=gemini_key,
            openai_key=openai_key,
            max_output_tokens=8192,
            on_busy=on_busy,
            waits=(0, 6),
        )
    except AnalysisError:
        logger.exception("Refine pass failed; keeping chunk results")
        return decisions, actions, None
    next_decisions = _collect_decisions(refined.decisions, lines)
    next_actions: list[ActionResult] = []
    seen: set[str] = set()
    _append_actions(refined.actions, next_actions, seen, allowed)
    if decisions and not next_decisions:
        logger.warning("Refine wiped decisions; keeping chunk results")
        next_decisions = decisions
    frame, agenda, close = _summary_parts_from_draft(draft_summary)
    rf = (refined.summary_frame or "").strip()
    ra = (refined.summary_agenda or "").strip()
    rc = (refined.summary_close or "").strip()
    if len(rf) < 160:
        rf = frame or rf
    if len(ra) < 240:
        ra = agenda or ra
    if len(rc) < 160:
        rc = close or rc
    polished = _join_report(rf, ra, rc)
    if "Çerçeve" not in polished:
        leftover = _humanize_dates_in_text((refined.summary or "").strip())
        polished = leftover if "Çerçeve" in leftover else None
    logger.warning(
        "Refine pass decisions %s→%s actions %s→%s summary=%s",
        len(decisions),
        len(next_decisions),
        len(actions),
        len(next_actions),
        "yes" if polished else "keep",
    )
    return next_decisions, next_actions, polished


def analyze_transcript(
    lines: list[Transcript],
    *,
    title: str,
    attendees: str | None,
    meeting_date: str | None,
    description: str | None = None,
    named_attendees: str | None = None,
    on_busy: Callable[[int], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> AnalysisResult:
    gemini_key = _api_key()
    openai_key = _openai_key()
    if not gemini_key and not openai_key:
        raise AnalysisError("GEMINI_API_KEY veya OPENAI_API_KEY tanımlı değil.")
    if not lines:
        raise AnalysisError("Analiz için transkript yok.")

    from app.services.speakers import parse_named_attendees

    labels = sorted(set(_speaker_labels(lines).values()))
    speakers = ", ".join(labels) or "yok"
    declared = parse_named_attendees(named_attendees)
    named = ", ".join(declared) if declared else (attendees or "")
    extra = f"Açıklama: {description}\n" if description else ""
    when = _format_meeting_when(meeting_date) or meeting_date or "belirtilmedi"
    allowed = _speaker_labels(lines)
    slices = _iter_chunks(lines)
    total = len(slices)
    logger.warning("Analysis scanning %s lines in %s chunks", len(lines), total)

    draft_decisions: list[DecisionResult] = []
    action_rows: list[ActionResult] = []
    sections: list[str] = []
    seen_actions: set[str] = set()
    failed = 0

    for index, slice_lines in enumerate(slices, start=1):
        if on_progress:
            on_progress(f"Satırlar taranıyor ({index}/{total})…")
        seqs = [row.seq for row in slice_lines]
        prompt = (
            f"{CHUNK_PROMPT}\n"
            f"Toplantı: {title}\n"
            f"Tarih: {when}\n"
            f"Konuşmacı adları: {speakers}\n"
            f"Bu dilim satır aralığı: #{seqs[0]}–#{seqs[-1]}\n"
            f"{extra}"
            f"Transkript dilimi:\n{_transcript_text(slice_lines)}\n"
        )
        try:
            chunk = _complete_json(
                prompt,
                ChunkDraft,
                gemini_key=gemini_key,
                openai_key=openai_key,
                max_output_tokens=8192,
                on_busy=on_busy,
                waits=(0, 6),
            )
        except AnalysisError:
            failed += 1
            logger.exception("Chunk %s/%s failed", index, total)
            continue
        draft_decisions.extend(_collect_decisions(chunk.decisions, lines))
        _append_actions(chunk.actions, action_rows, seen_actions, allowed)
        if (chunk.section or "").strip():
            sections.append(fix_sentence_i(chunk.section.strip()))

    if failed == total:
        raise AnalysisError("Analiz dilimlerinin hiçbiri tamamlanamadı.")

    decisions = _merge_decisions(draft_decisions)
    actions: list[ActionResult] = []
    action_kept: set[str] = set()
    for item in action_rows:
        if any(_action_dup(item, prev) for prev in actions):
            continue
        key = _norm_key(item.description)
        if key in action_kept:
            continue
        action_kept.add(key)
        actions.append(item)

    summary = _assemble_summary(
        title=title,
        meeting_date=meeting_date,
        attendees=named,
        sections=sections,
    )
    decisions, actions, polished = _refine_extracted(
        lines=lines,
        decisions=decisions,
        actions=actions,
        speakers=speakers,
        title=title,
        draft_summary=summary,
        gemini_key=gemini_key,
        openai_key=openai_key,
        allowed=allowed,
        on_busy=on_busy,
        on_progress=on_progress,
    )
    if polished:
        summary = fix_sentence_i(polished)
    if _looks_like_non_meeting(summary) and not decisions and not actions:
        summary = fix_sentence_i(sections[0] if sections else summary)

    logger.warning(
        "Chunked analysis lines=%s chunks=%s failed=%s summary_len=%s decisions=%s actions=%s",
        len(lines),
        total,
        failed,
        len(summary),
        len(decisions),
        len(actions),
    )
    return AnalysisResult(summary=summary, decisions=decisions, actions=actions, speakers={})
