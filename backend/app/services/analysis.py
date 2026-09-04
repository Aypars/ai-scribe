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
from app.services.meeting_lang import current_lang, maybe_fix_i, normalize_lang, speaker_prefix

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

ANALYSIS_PROMPT = """Sen AI-SCRIBE için kıdemli bir toplantı raportörüsün. Transkripti baştan sona oku; atlama, sıkıştırarak yok etme.

Kayıt her türlü görüşme olabilir. Türe varsayım yapma. Kaynak yalnızca transkript. Kullanıcı başlığı metadata; transkriptte geçmeyen hiçbir şeyi başlıktan olay, konu, süre veya karar yapma.

JSON sırası: önce decisions, sonra actions, en son summary.

Karar veya iş yoksa decisions ve actions boş kalır; özet yine üç bölümlü anlatılır. Yokken uydurma.

Boş / anlamsız seste: decisions [], actions [], summary 1-2 cümle.

Diyalog varsa:

- decisions: Grubun kabul / ret / seçtiği HER sonuç. Sayı tavanı yok. Ayrı sonuçlar ayrı madde.
  “toplantı bitti” karar değildir.
  Kişi, tutar, yer, kimlik geçtiyse cümlede tut; “ilgililer seçildi” diye isim silme. Birleştirirken isim düşecekse ayrı bırak.
  Karar = o anda varılan sonuç (kabul / ret / seçim). Oylanmayan “çalışın / böyle yapın” talimatı karar değil; actions.
  Aynı olguyu hem decisions hem actions’a yazma.
  Tek cümle. source_seq_start / source_seq_end dar.
  Karar yoksa [].

- actions: Toplantıdan SONRA kalacak iş. Kart, A’nın sormasından değil B’nin üstlenmesinden veya atamasından doğar.
  Şüphede kart yazma. Açık teslim veya açık atama yoksa boş bırak.
  Aynı oturumda okunan, aynı teslim türündeki (yazılı rapor / yazılı cevap) kalemler, müdürlükleri ayrı olsa da tek pakettir: tek kart; alt başlıklar notes’ta.
  Somut fiil söylendiyse (yazın, çevirin, hazırlayın) description’da o fiili koru; “incelensin / değerlendirilsin”e yumuşatma.
  Yalnız soru, şikayet, iddia, önerge metni, durum güncellemesi kart değildir.
  Odada bilgi istenip cevaplandıysa brifing kartı yazma. Cevaptan sonra kalan somut iş varsa yalnız onu yaz.
  Oylanmış gündem maddesinin uygulama adımı karar olarak kalsın; yeni aksiyon kartı yapma.
  Oylanmamış “gündeme alınsın / değerlendirilsin / uygun görüyoruz” önerisi kart değildir.
  Farklı yerleri tek karta yapıştırma. İki yer konuşulduysa yalnız somut emir verilen yer kalsın. Aynı konuşmacının peş peşe sorduğu yerler tek iş değildir.
  Oylanmamış önerge kart değildir. Önergenin “grupta/komisyonda görüşülmesi” de kart değildir; bu ertelemedir.
  Kartta iki yer adı varsa (ve/ile) birleştirme yapma: yalnız somut emir verilen yer kalsın; bilgi verilen yer adını notes’tan da sil.
  description net iş cümlesi olsun. notes yalnız o işe ait bağlam içersin.
  assignee her zaman null. due_date yalnız açık tarih.

- summary: Üç bölümlü anlatım. Karar listesini kopyalama; duyulanı anlat.
  Çerçeve: 4–6 cümle. Kim konuştu, kayıt ne üzerine, transkriptteki konular.
  Gündem akışı: sırayla ne dendi; tartışma. Dilim yapıştırma.
  Sonuç: 4–6 cümle. Transkriptteki kapanış / varılan nokta. Boş kapanış cümlesi yok.
  Uydurma yok. ISO tarih yok.

Üslup:
- Çıktı dili Türkçe. Özel isimler konuşulduğu gibi kalsın.
- Konuşmacı adlarını transkriptteki haliyle kullan.
- Bu kayıt tek başına. Başka kayıttaki kişi veya işi yazma.
"""

CHUNK_PROMPT = """Bu transkript DİLİMİ. Her satırı oku. Uydurma yok. Yalnızca bu satırlar.

JSON: decisions, actions, section.

KARAR (sonuç, usul değil):
- Yazılacak: bu dilimde gerçekten varılan sonuç (kabul / ret / seçim).
- Kişi, tutar, yer, kimlik geçtiyse cümlede tut; isimleri “ilgililer”e çevirme.
- Bir sürecin SONUCU tek maddedir (veya ayrı kazanan/ayrı konu başına bir).
- YAZILMAYACAK ayrı karar: hazırlık, ara, nasıl varıldığı, her ara cümle. Usul varsa en fazla bir cümle; asıl sonuç ayrı.
- Toplantı sonrası iş ve oylanmayan “çalışın / böyle yapın” karara yazılmaz; actions’a yazılır. Aynı olgu iki listede durmaz.
- Farklı kişi / farklı konu AYRI kalsın. “toplantı bitti” karar değil.
- Tek cümle. source_seq_start / source_seq_end yalnızca bu dilimdeki #.

AKSİYON (toplantıdan SONRA kalacak iş):
- Şüphede yazma. Açık teslim veya açık atama yoksa kart yok. Yöneticinin verdiği kısa somut emir (çevirin, yazın, çalışın) karttır.
- Kart, A’nın talebinden değil B’nin üstlenmesinden/atamasından doğar.
- Aynı oturumda okunan yazılı rapor/cevap kalemleri, müdürlükleri ayrı olsa da tek karttır; alt başlıklar notes’ta.
- Somut fiili koru; “incele / değerlendir”e yumuşatma.
- Soru, şikayet, iddia, önerge metni, durum bildirimi kart değildir.
- Odada bilgi istenip cevaplandıysa brifing kartı yazma; cevap sonrası kalan somut emir varsa onu yaz. Üye peş peşe iki yer sorup biri cevaplandıysa yalnız emir verilen yer kart olur.
- Oylanmış maddenin uygulama adımını ve oylanmamış “değerlendirilsin” önerisini kart yapma.
- Karar listesini görev listesine kopyalama.
- Farklı yerleri tek karta yapıştırma. Aynı konuşmacının peş peşe sorduğu yerler tek iş değildir. Aynı işi tekrarlama.
- description net ve tek iş olsun. notes yalnız o işin bağlamı olsun. assignee null.

section: Bu dilimin anlatımı. En az 3 paragraf, kısa tutma. Markdown yok, Çerçeve/Gündem/Sonuç başlığı yok.
Her konu için: ne konuşuldu, kim ne dedi. Karar yoksa karar icat etme. Transkriptte yoksa başlıktan konu alma.
"""

REFINE_PROMPT = """Ham çıkarımı netleştir. Yeni olay uydurma. Farklı konuyu silme.

KARARLAR:
- Bir sonucun adımlarını birleştir. Sonuç yazılsın: ne kabul/ret edildi; kişi, tutar, yer, kimlik geçtiyse adı kalsın.
- İsim düşüren birleştirme yanlış; o zaman ayrı bırak. Ayrı seçimler ayrı madde, ya da tek cümlede bütün adlar. Aday gösterenleri seçilmiş yazma.
- Yanlış: süreci parça parça ayrı maddeler yapmak.
- Doğru: tek sonuç cümlesi. Ayrı konular ayrı kalsın.
- Toplantı sonrası iş ve oylanmayan “çalışın / böyle yapın” buradan actions’a taşı; kararda bırakma. İki listede aynı olgu durmasın.
- source_seq_start / source_seq_end, birleştirdiğin ham maddelerdeki aralıktan alınsın.

AKSİYONLAR:
- Aynı oturumda okunan yazılı rapor/cevap/önerge kalemleri, konu başlıkları farklı görünse de TEK pakettir: tek kart. Alt başlıkları notes’ta sırala. Müdürlük müdürlük ayrı kart bırakma.
- Açık teslimi veya açık ataması olmayan kartı sil.
- Kart B’nin üstlendiği/atadığı teslim olsun. Somut fiil ve isimleri koru; yumuşatma.
- Teslimi olmayan erteleme, salt durum, salt soru/şikayet/iddia, oylanmamış öneriyi sil.
- Odada bilgi istenip cevaplanan başlığı sil. İki yer konuşulduysa yalnız somut emir verilen yer kalsın; bilgi verilen yeri diğerine yapıştırma. Aynı konuşmacının peş peşe sorduğu yerler tek iş değildir.
- Cevaptan sonra kalan somut emir varsa o emri ayrı kart olarak bırak; soyutlaştırma.
- Üyenin oylanmayan “uygun görüyoruz / öneriyoruz” işlemini aksiyona çevirme.
- Aynı işin kopyasını sil. Farklı yer adı taşıyan kartları birleştirme. İki yer “güvenlik” temasında olsa bile tek kart yapma.
- Karar listesini actions’a kopyalama.
- assignee her zaman null.

ÖZET:
- Üç alan: summary_frame, summary_agenda, summary_close. Başlığı metnin içine yazma.
- Üç bölüm de dolu olsun. Çerçeve ve Sonuç’u birer cümleye indirme. Gündem’e ham dilimleri alt alta yapıştırma.
- Transkriptte geçmeyen başlık kelimelerini özete sokma.
- Dilimler örtüşür; aynı konuyu iki kez yazma. Her madde tek paragraf.
- ISO tarih yasak.
- summary_frame: 4–6 cümle. Kim konuştu, kayıt ne üzerine, transkriptteki konular.
- summary_agenda: her konu 4–7 cümle (kim ne dedi, itiraz, varılan nokta). Karar listesini kopyalama.
- summary_close: 4–6 cümle. Transkriptteki sonuç / kapanış. Boş kapanış cümlesi yazma.
- Uydurma yok. Markdown yok.
"""


ANALYSIS_PROMPT_EN = """You are a senior meeting rapporteur for AI-SCRIBE. Read the transcript start to finish; do not skip or compress events away.

The recording can be any kind of conversation. Do not assume a type. The transcript is the only source. The user title is metadata; do not turn anything from the title into an event, topic, deadline, or decision unless it was spoken.

JSON order: decisions first, then actions, then summary.

If there are no real decisions or tasks, leave those lists empty — still write a full three-part summary of what was heard. Do not invent.

Empty/nonsense audio: decisions [], actions [], summary 1-2 sentences.

If there is dialogue:

- decisions: EVERY outcome the group adopted, rejected, or chose. No cap. Distinct outcomes stay separate.
  “the meeting ended” is not a decision.
  If people, amounts, places, or identifiers were spoken, keep them in the sentence. Do not collapse named people into “the relevant parties were chosen”. If a merge would drop names, keep the items separate.
  A decision is the result reached in the room (adopted / rejected / chosen). An unvoted “do it this way / you two work on this” is an action, not a decision.
  Do not list the same fact as both a decision and an action.
  One sentence. Narrow source_seq_start / source_seq_end.
  If none were taken, return [].

- actions: Work remaining AFTER the meeting. The card must come from B assigning or taking ownership, not from A merely asking.
  If ownership or deliverable is unclear, do not write a card.
  Written-report / written-reply items read in one sitting are one packet even if directorates differ: one card; list sub-items in notes.
  Preserve concrete verbs (write, fence, prepare); do not soften them to “review / evaluate”.
  Do not write cards for pure questions, complaints, allegations, motion text, status updates, or unvoted “please consider this”.
  If someone asked for a briefing and it was answered in-room, do not keep a follow-up card. If a concrete remaining job is then assigned, keep only that job.
  Do not turn implementation of a voted agenda item into an action; leave it as a decision.
  Do not glue different places into one card. Remove duplicates of the same job.
  description: concrete task sentence. notes: context for that task only.
  assignee: always null. due_date: only when explicitly spoken.

- summary: A three-part narrative. Do not copy the decision list; narrate what was said.
  Context: 4–6 sentences. Who spoke, what the recording is about, topics from the transcript.
  Agenda: items in order; who said what. Do not paste chunks.
  Outcome: 4–6 sentences. Where the transcript actually lands. No empty closing sentence.
  No invention. No ISO timestamps.

Style:
- Output language: English. Every narrative field in English. Proper names stay as spoken.
- Use speaker names as they appear in the transcript.
- This recording stands alone. Do not pull people or tasks from another recording.
"""

CHUNK_PROMPT_EN = """This is a transcript CHUNK. Read every line. No invention. Only these lines.

Write section, decisions, and actions in English.

JSON: decisions, actions, section.

DECISION (outcome, not procedure):
- Write: an outcome actually reached in this chunk (adopted / rejected / chosen).
- If people, amounts, places, or identifiers were spoken, keep them; do not rewrite names as “the relevant parties”.
- The RESULT of one process is one item (or one per distinct winner/topic).
- Do NOT write as separate decisions: setup, a break, how the outcome was reached, every in-between sentence. If procedure is discussed, at most one sentence; the actual result is separate.
- Assigned follow-up work and an unvoted “do it this way” are actions, not decisions. Do not list the same fact in both lists.
- Different person / different topic stay SEPARATE. “the meeting ended” is not a decision.
- One sentence. source_seq_start / source_seq_end only # numbers in this chunk.

ACTION (work that remains AFTER the meeting):
- If ownership or deliverable is unclear, do not write a card.
- A card must represent B assigning or taking ownership of a deliverable.
- Written-report / written-reply items read as one packet in this chunk are one card; list sub-items in notes.
- Keep the original concrete action verb; do not soften it to review/evaluate.
- Do not write cards for questions, complaints, allegations, motion text, status updates, or unvoted “please consider this”.
- If a briefing was asked and answered in-room, drop it; keep only a concrete remaining job if one is then assigned.
- Do not turn voted-item implementation into an action.
- Do not duplicate decisions as actions.
- Do not glue different places into one card. Remove duplicates.
- description stays concrete; notes stay tied to that card; assignee is null.

section: Narrative of this chunk. At least 3 paragraphs, do not keep it short. No markdown, no Context/Agenda/Outcome headings.
For each topic: what was said, who said it. Do not invent a decision if there was none. Do not take topics from the title if they are not in the transcript.
"""

REFINE_PROMPT_EN = """Tighten the raw extraction. Invent no new events. Do not drop a distinct topic.

Write every summary field in English.

DECISIONS:
- Merge the steps of one outcome. Write the result: what was adopted/rejected; keep named people, amounts, places, identifiers.
- A merge that drops names is wrong; then keep the items separate. Separate elections stay separate, or one sentence with every name.
- Bad: listing the process as separate items.
- Good: one result sentence. Distinct topics stay separate.
- Move assigned follow-up work and an unvoted “do it this way” to actions; do not leave it as a decision. Do not keep the same fact in both lists.
- source_seq_start / source_seq_end come from the span of the merged raw items.

ACTIONS:
- Written-report / written-reply rows read in one sitting are ONE packet even if directorates differ: one card, sub-items in notes. Do not keep one card per directorate.
- Drop a card unless assignment or deliverable is explicit.
- The card must represent B assignment/ownership. Keep concrete verbs; do not soften them.
- Drop deferrals, status updates, questions, complaints, allegations, motion text, and unvoted “please consider this”.
- If a briefing was asked and answered in-room, drop the briefing. Keep a remaining concrete order if one was then assigned; do not drop that order as “just a briefing” and do not glue it into the report packet.
- Do not turn voted-item implementation into an action.
- Delete duplicates. Do not glue different places’ remaining orders into one card.
- Do not copy the decision list into actions.
- assignee always null.

SUMMARY:
- Three fields: summary_frame, summary_agenda, summary_close. Do not write the heading inside the text.
- All three must be filled. Do not shrink Context and Outcome to one sentence. Do not paste raw chunks into Agenda.
- Do not put title-only wording into the summary if it was not spoken.
- Chunks overlap; do not write the same topic twice. One paragraph per item.
- ISO dates forbidden.
- summary_frame: 4–6 sentences. Who spoke, what the recording is about from the transcript.
- summary_agenda: each topic 4–7 sentences (who said what, pushback, where it landed). Do not copy the decision list.
- summary_close: 4–6 sentences. The actual close in the transcript. Do not write an empty closing line.
- No invention. No markdown.
"""


ACTION_DEDUP_PROMPT = """Aksiyon listesini yalnız kendi içinde süz.

Kurallar:
- Ham listeyi geri verme; yalnız nihai listeyi ver.
- Aynı oturumda okunan yazılı rapor/cevap kalemleri konu başlıkları farklı görünse de TEK karta indir; alt başlıkları notes’ta sırala.
- Aynı işin kopyasını/dar-geniş tekrarını tek karta indir.
- Karar cümlesini ve oylanmış maddenin uygulama adımını görev kartına çevirme.
- Oylanmamış önerge metnini ve önergenin grupta görüşülmesini çıkar.
- Odada bilgi istenip cevaplanan başlığı çıkar. Cevaptan sonra kalan somut emir varsa o emri bırak; rapor paketine yapıştırma.
- Farklı yer adı taşıyan kartları birleştirme. Aynı tema (güvenlik, rapor) olsa bile mahalle/yer birleştirmek yasak. Aynı konuşmacının peş peşe sorduğu iki yer tek kart olmaz.
- Somut fiili koru, yumuşatma.
- Yeni kart ekleme; yalnız birleştir, böl veya çıkar.

JSON: actions. assignee null. due_date yalnız listede açık tarih varsa.
"""

ACTION_QA_PROMPT = """Aksiyonları son kalite kontrolünden geçir. Transkript kanıtını esas al.
Yeni iş uydurma. Listedeki konuyu başka bir gündem maddesine çevirme. Girdide yoksa yeni kart ekleme; yalnız birleştir veya çıkar.

Zorunlu:
1) Aynı oturumda okunan yazılı rapor/cevap kartlarını, konu başlıkları farklı görünse de TEK karta birleştir. Alt başlıkları notes’ta sırala. Bunu atlama.
2) Odada cevaplanan brifing kartını çıkar. Cevaplanmış bilgi talebini sonradan “yazılı rapor sunulsun” kartına çevirme. Ana fiili bilgi vermek / gözden geçirmek / incelemek olan ve somut emri olmayan kartı çıkar.
3) Kartta iki yer adı varsa (ve/ile bağlacı) birleştirmedir. Kart sayısını artırma. Yalnız somut emir verilen yer kalsın; bilgi verilen yer adını başlıktan ve notes’tan sil.
4) Salt iddia üzerine “inceleme başlatın” kartı yazma. Somut teslim yoksa kart değildir.
5) Oylanmamış önergeyi çıkar. Kartın bütün işi bir önergeyi grupta veya komisyonda görüşmekse çıkar; bu teslim değil ertelemedir.

Korunacak:
- Brifingden sonra verilen somut emri koru. Bu emri rapor paketiyle birleştirme ve silme. Somut fiili soyutlaştırma.
- Başkanın ayrı bir konu için “çalışın / başlayalım” dediği iş. Bunu güvenlik veya rapor kartına yapıştırma.
- Birleştirilmiş rapor paketi.

Yanlış: aynı paketin alt başlıklarını ayrı kart yapmak; cevaplanmış brifingi tutmak; iki yeri tek karta yapıştırmak.
Doğru: tek rapor paketi + somut emir verilen ayrı iş kartları.

JSON: actions. assignee null. due_date yalnız açık tarih varsa.
"""

ACTION_DEDUP_PROMPT_EN = """Filter the action list against itself.

Rules:
- Return the filtered final list, not the raw dump.
- Merge duplicates and narrow-vs-wide restatements of the same job.
- Written-report / written-reply items from one packet are ONE card even if directorates differ; keep sub-items in notes.
- Do not convert decision statements or voted-item implementation into action cards.
- Remove cards that are only questions, complaints, allegations, motion text, status updates, or unvoted “please consider this”.
- If a briefing was asked and answered in-room, drop the briefing. Keep a remaining concrete order if one was then assigned; do not drop that order as “just a briefing”.
- Do not merge cards that name different places. Same theme (security, reports) does not make them one job.
- Preserve concrete action verbs.
- If ownership or deliverable is unclear, drop the card.
- Invent no new jobs.

JSON: actions. assignee null. due_date only if an explicit date already in the list.
"""

ACTION_QA_PROMPT_EN = """Run a final quality gate on action cards. Trust the transcript evidence.
Invent no new jobs. Do not rewrite the list into a different agenda item.

Required:
1) Merge written-report / written-reply cards into ONE card even if directorates differ. List sub-items in notes. Do not skip this.
2) Drop a briefing that was answered in-room. Drop a card whose main verb is brief / review / look into with no remaining concrete order.
3) If a card names two places joined by and/with, that is a glue. Do not add cards. Keep only the place that received a remaining concrete order; delete the briefed place name from the title and from notes.
4) Do not write an “open an investigation” card from an allegation alone. “They will inform us / we will look together” is not a card without a concrete deliverable.
5) Drop an unvoted proposal. If the whole card is “discuss this motion in the group/committee”, drop it; that is a deferral, not a deliverable.

Keep:
- A remaining concrete order after a briefing.
- The merged report packet.

Bad: leaving report cards split; keeping an answered briefing; gluing two neighborhoods into one card.
Good: one report-packet card plus remaining concrete-order cards.

JSON: actions. assignee null. due_date only when explicitly spoken.
"""


def _prompts() -> tuple[str, str, str]:
    if current_lang.get() == "en":
        return ANALYSIS_PROMPT_EN, CHUNK_PROMPT_EN, REFINE_PROMPT_EN
    return ANALYSIS_PROMPT, CHUNK_PROMPT, REFINE_PROMPT



class AnalysisError(Exception):
    pass


class DecisionDraft(BaseModel):
    text: str = Field(
        description="One sentence: the adopted/rejected/chosen result. Keep named people, amounts, and places. Not a follow-up job.",
    )
    source_seq_start: int | None = Field(
        default=None,
        description="First transcript line # for this decision only",
    )
    source_seq_end: int | None = Field(
        default=None,
        description="Last transcript line # for this decision only; keep the span tight",
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
    description: str = Field(
        description="Follow-up someone took on or assigned after the meeting. Not a question, complaint, allegation, or 'we'll discuss later'.",
    )
    assignee: str | None = Field(
        default=None,
        description="Always null. Do not assign an owner.",
    )
    due_date: str | None = Field(default=None, description="YYYY-MM-DD; null if no explicit date")
    notes: str = Field(default="", description="Context for this job only. Do not mix in a second topic.")


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
        description="Group outcomes in this chunk. Keep names. Assigned follow-up work belongs in actions.",
    )
    actions: list[ActionDraft] = Field(
        description="Follow-up jobs someone took on or assigned. Not a question, complaint, allegation, or 'we'll discuss later'.",
    )
    section: str = Field(description="Narrative of this chunk. At least 3 paragraphs. No markdown.")

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
        description="Adopted outcomes with names kept. Move assigned follow-up work to actions. Distinct items stay separate.",
    )
    actions: list[ActionDraft] = Field(
        description="Keep assigned follow-ups. Drop questions, complaints, allegations, copies, and 'we'll discuss later'.",
    )
    summary_frame: str = Field(
        default="",
        description="Context, 4–6 sentences from the transcript. Do not write the heading.",
    )
    summary_agenda: str = Field(
        default="",
        description="Agenda. Do not paste chunks. 4–7 sentences per topic. Do not write the heading.",
    )
    summary_close: str = Field(
        default="",
        description="Outcome, 4–6 sentences. Actual close in the transcript. Do not write the heading.",
    )
    summary: str = Field(
        default="",
        description="Fallback. Leave empty if the three fields are filled.",
    )

    @field_validator("decisions", mode="before")
    @classmethod
    def _coerce_decisions(cls, value: object) -> object:
        return _coerce_decision_items(value)

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: object) -> object:
        return _coerce_action_items(value)


class ActionDedupeDraft(BaseModel):
    actions: list[ActionDraft] = Field(
        description="The same jobs with copies removed. Do not invent a new job. Do not merge two distinct jobs.",
    )

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: object) -> object:
        return _coerce_action_items(value)


class ActionQADraft(BaseModel):
    actions: list[ActionDraft] = Field(
        description=(
            "Final action cards only. Keep explicit follow-up deliverables, remove non-action placeholders, "
            "and merge duplicate/redundant cards without inventing new work."
        ),
    )

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, value: object) -> object:
        return _coerce_action_items(value)


class AnalysisDraft(BaseModel):
    decisions: list[DecisionDraft] = Field(
        default_factory=list,
        description="Every adopted/rejected/chosen result. Keep names. Tight source_seq_start / source_seq_end.",
    )
    actions: list[ActionDraft] = Field(
        default_factory=list,
        description="Follow-up jobs from this transcript. Not a question, complaint, allegation, or 'we'll discuss later'.",
    )
    summary: str = Field(
        description="Three-part narrative. Do not collapse into one paragraph."
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


def _match_action_seqs(text: str, lines: list[Transcript], *, limit: int = 3) -> list[tuple[int, int]]:
    keys = _tokens(text)
    if not keys or not lines:
        return []
    scored: list[tuple[int, int]] = []
    for row in lines:
        seq = getattr(row, "seq", None)
        hay = (getattr(row, "text", None) or "")
        if seq is None or not isinstance(hay, str):
            continue
        hay = hay.casefold()
        score = 0
        for key in keys:
            if key not in hay:
                continue
            score += 2 if len(key) >= 8 else 1
        if score > 0:
            scored.append((seq, score))
    if not scored:
        return []
    scored.sort(key=lambda item: item[1], reverse=True)
    needed = 2 if len(keys) >= 5 else 1
    if scored[0][1] < needed:
        return []
    picked: list[tuple[int, int]] = []
    for seq, score in scored:
        if any(abs(seq - prev) < 20 for prev, _ in picked):
            continue
        picked.append((seq, score))
        if len(picked) >= limit:
            break
    return picked


def _transcript_window(lines: list[Transcript], center_seq: int, *, before: int = 3, after: int = 4) -> list[Transcript]:
    seq_to_idx = {getattr(row, "seq", None): idx for idx, row in enumerate(lines)}
    center_idx = seq_to_idx.get(center_seq)
    if center_idx is None:
        return []
    start = max(0, center_idx - before)
    end = min(len(lines), center_idx + after + 1)
    return lines[start:end]


def _format_action_evidence(actions: list[ActionResult], lines: list[Transcript]) -> str:
    if not actions:
        return _none_mark()
    blocks: list[str] = []
    for index, item in enumerate(actions, start=1):
        query = f"{item.description} {item.notes or ''}".strip()
        matches = _match_action_seqs(query, lines, limit=3)
        if not matches:
            evidence_block = _none_mark()
        else:
            parts: list[str] = []
            for seq, score in matches:
                excerpt = _transcript_text(_transcript_window(lines, seq, before=4, after=6))
                parts.append(f"candidate_seq: #{seq} (score={score})\n{excerpt}")
            evidence_block = "\n\n".join(parts)
        blocks.append(
            "\n".join(
                (
                    f"{index}) description: {item.description}",
                    f"notes: {item.notes or _none_mark()}",
                    "candidate_evidence:",
                    evidence_block,
                )
            )
        )
    return "\n\n---\n\n".join(blocks)


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
        speaker = row.speaker or speaker_prefix()
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


def _title_meta(title: str) -> str:
    text = re.sub(r"\s+", " ", (title or "").strip())
    if not text:
        return ""
    return text[:180]


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
    frame_bits: list[str] = []
    named = (attendees or "").strip()
    if current_lang.get() == "en":
        if when:
            frame_bits.append(f"The recording is from {when}.")
        if named:
            frame_bits.append(f"{named} spoke.")
        close = (
            "The recording closes on the last points that were actually spoken. "
            "Open questions in the dialogue stay open. "
            "Nothing beyond this recording is added."
        )
    else:
        if when:
            frame_bits.append(f"Kayıt {when} tarihine aittir.")
        if named:
            frame_bits.append(f"Konuşanlar: {named}.")
        close = (
            "Kayıt, transkriptte geçen son noktalarla bağlanır. "
            "Diyalogda açık kalan husus açık kalır. "
            "Kayıtta olmayan gündem yazılmaz."
        )
    body = [_strip_summary_labels(part) for part in sections]
    body = [part for part in body if part]
    agenda = "\n\n".join(body)
    return " ".join(frame_bits), agenda, close


def _join_report(frame: str, agenda: str, close: str) -> str:
    blocks: list[str] = []
    frame_text = _strip_summary_labels(_humanize_dates_in_text(frame))
    agenda_text = _strip_summary_labels(_humanize_dates_in_text(agenda))
    close_text = _strip_summary_labels(_humanize_dates_in_text(close))
    if current_lang.get() == "en":
        labels = ("Context", "Agenda", "Outcome")
    else:
        labels = ("Çerçeve", "Gündem akışı", "Sonuç")
    if frame_text:
        blocks.extend([labels[0], frame_text])
    if agenda_text:
        blocks.extend([labels[1], agenda_text])
    if close_text:
        blocks.extend([labels[2], close_text])
    return maybe_fix_i("\n\n".join(blocks).strip())


def _summary_parts_from_draft(text: str) -> tuple[str, str, str]:
    buckets = {"frame": [], "agenda": [], "close": []}
    heading = {
        "çerçeve": "frame",
        "context": "frame",
        "gündem akışı": "agenda",
        "gündem": "agenda",
        "agenda": "agenda",
        "sonuç": "close",
        "outcome": "close",
        "close": "close",
    }
    current: str | None = None
    for line in (text or "").splitlines():
        key = heading.get(line.strip().casefold())
        if key:
            current = key
            continue
        if current:
            buckets[current].append(line)
    joined = {name: "\n".join(rows).strip() for name, rows in buckets.items()}
    return joined["frame"], joined["agenda"], joined["close"]


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
_MONTHS_EN = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_SUMMARY_LABEL = re.compile(
    r"^(çerçeve|gündem akışı|gündem|sonuç|katılımcılar|idari hususlar|context|agenda|outcome|attendees)\s*:?\s*$",
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
    months = _MONTHS_EN if current_lang.get() == "en" else _MONTHS_TR
    if parsed is None and re.match(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            day = date.fromisoformat(raw[:10])
            return f"{day.day} {months[day.month]} {day.year}"
        except ValueError:
            return raw
    if parsed is None:
        return raw
    local = parsed.astimezone() if parsed.tzinfo else parsed
    text = f"{local.day} {months[local.month]} {local.year}"
    if local.hour or local.minute:
        if current_lang.get() == "en":
            text += f" at {local.hour:02d}:{local.minute:02d}"
        else:
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
        description_text = maybe_fix_i((item.description or "").strip())
        key = " ".join(description_text.lower().split())
        if not description_text or key in seen:
            continue
        seen.add(key)
        actions.append(
            ActionResult(
                description=description_text,
                assignee=None,
                due_date=_parse_due(item.due_date),
                notes=maybe_fix_i((item.notes or "").strip()),
            )
        )


def _collect_decisions(items: list[DecisionDraft], lines: list[Transcript]) -> list[DecisionResult]:
    decisions: list[DecisionResult] = []
    for item in items:
        text = maybe_fix_i((item.text or "").strip())
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


def _none_mark() -> str:
    return "(none)" if current_lang.get() == "en" else "(yok)"


def _format_raw_decisions(items: list[DecisionResult]) -> str:
    rows: list[str] = []
    for index, item in enumerate(items, start=1):
        span = ""
        if item.source_seq is not None:
            end = item.source_end_seq or item.source_seq
            span = f" [#{item.source_seq}–#{end}]"
        rows.append(f"{index}.{span} {item.text}")
    return "\n".join(rows) if rows else _none_mark()


def _format_raw_actions(items: list[ActionResult]) -> str:
    rows: list[str] = []
    for index, item in enumerate(items, start=1):
        note = f" | {item.notes}" if item.notes else ""
        rows.append(f"{index}. {item.description}{note}")
    return "\n".join(rows) if rows else _none_mark()


_TR_LETTERS = re.compile(r"[ğüşıöçĞÜŞİÖÇ]")


def _looks_turkish(text: str) -> bool:
    return len(_TR_LETTERS.findall(text or "")) >= 4


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
        on_progress("Karar, görev ve özet süzülüyor…" if current_lang.get() != "en" else "Filtering decisions, tasks and summary…")
    _analysis_prompt, _chunk_prompt, refine_prompt = _prompts()
    label = _title_meta(title)
    if current_lang.get() == "en":
        prompt = (
            f"{refine_prompt}\n"
            f"Title (metadata): {label or _none_mark()}\n"
            f"Speaker names: {speakers}\n\n"
            f"Raw decisions:\n{_format_raw_decisions(decisions)}\n\n"
            f"Raw actions:\n{_format_raw_actions(actions)}\n\n"
            f"Raw summary:\n{draft_summary.strip() or _none_mark()}\n"
        )
    else:
        prompt = (
            f"{refine_prompt}\n"
            f"Başlık (metadata): {label or _none_mark()}\n"
            f"Konuşmacı adları: {speakers}\n\n"
            f"Ham kararlar:\n{_format_raw_decisions(decisions)}\n\n"
            f"Ham aksiyonlar:\n{_format_raw_actions(actions)}\n\n"
            f"Ham özet:\n{draft_summary.strip() or _none_mark()}\n"
        )
    try:
        refined = _complete_json(
            prompt,
            RefineDraft,
            gemini_key=gemini_key,
            openai_key=openai_key,
            max_output_tokens=8192,
            on_busy=on_busy,
            waits=(0, 8, 16),
        )
        if current_lang.get() == "en" and _looks_turkish(
            " ".join(
                (
                    refined.summary_frame or "",
                    refined.summary_agenda or "",
                    refined.summary_close or "",
                    refined.summary or "",
                )
            )
        ):
            logger.warning("Refine returned the wrong language; retrying in English")
            refined = _complete_json(
                "Write every string field in English. Do not write another language.\n" + prompt,
                RefineDraft,
                gemini_key=gemini_key,
                openai_key=openai_key,
                max_output_tokens=8192,
                on_busy=on_busy,
                waits=(0, 8, 16),
            )
    except AnalysisError:
        logger.exception("Refine pass failed; keeping chunk results")
        return decisions, actions, None
    next_decisions = _collect_decisions(refined.decisions, lines)
    next_actions: list[ActionResult] = []
    seen: set[str] = set()
    _append_actions(refined.actions, next_actions, seen, allowed)
    if actions and not next_actions:
        logger.warning("Refine wiped actions; keeping chunk results")
        next_actions = actions
    if decisions and not next_decisions:
        logger.warning("Refine wiped decisions; keeping chunk results")
        next_decisions = decisions
    frame, agenda, close = _summary_parts_from_draft(draft_summary)
    rf = (refined.summary_frame or "").strip()
    ra = (refined.summary_agenda or "").strip()
    rc = (refined.summary_close or "").strip()
    if current_lang.get() == "en":
        if _looks_turkish(rf):
            rf = frame if not _looks_turkish(frame) else rf
        if _looks_turkish(ra):
            ra = agenda if not _looks_turkish(agenda) else ra
        if _looks_turkish(rc):
            rc = close if not _looks_turkish(close) else rc
    if len(rf) < 160 and not (current_lang.get() == "en" and _looks_turkish(frame)):
        rf = frame or rf
    if len(ra) < 240 and not (current_lang.get() == "en" and _looks_turkish(agenda)):
        ra = agenda or ra
    if len(rc) < 160 and not (current_lang.get() == "en" and _looks_turkish(close)):
        rc = close or rc
    polished = _join_report(rf, ra, rc)
    frame_heading = "Context" if current_lang.get() == "en" else "Çerçeve"
    if frame_heading not in polished:
        leftover = _humanize_dates_in_text((refined.summary or "").strip())
        polished = leftover if frame_heading in leftover else None
    logger.warning(
        "Refine pass decisions %s→%s actions %s→%s summary=%s",
        len(decisions),
        len(next_decisions),
        len(actions),
        len(next_actions),
        "yes" if polished else "keep",
    )
    return next_decisions, next_actions, polished


def _dedupe_actions_llm(
    actions: list[ActionResult],
    *,
    gemini_key: str,
    openai_key: str,
    allowed: dict[str, str],
    on_busy: Callable[[int], None] | None,
    on_progress: Callable[[str], None] | None,
) -> list[ActionResult]:
    if len(actions) <= 1:
        return actions
    if on_progress:
        on_progress(
            "Aksiyon kopyaları ayıklanıyor…"
            if current_lang.get() != "en"
            else "Removing duplicate tasks…"
        )
    prompt_core = ACTION_DEDUP_PROMPT_EN if current_lang.get() == "en" else ACTION_DEDUP_PROMPT
    listing = _format_raw_actions(actions)
    if current_lang.get() == "en":
        prompt = f"{prompt_core}\n\nAction list:\n{listing}\n"
    else:
        prompt = f"{prompt_core}\n\nAksiyon listesi:\n{listing}\n"
    try:
        draft = _complete_json(
            prompt,
            ActionDedupeDraft,
            gemini_key=gemini_key,
            openai_key=openai_key,
            max_output_tokens=4096,
            on_busy=on_busy,
            waits=(0, 8, 16),
        )
    except AnalysisError:
        logger.exception("Action dedupe pass failed; keeping list")
        return actions
    next_actions: list[ActionResult] = []
    seen: set[str] = set()
    _append_actions(draft.actions, next_actions, seen, allowed)
    if actions and not next_actions:
        logger.warning("Action dedupe wiped the list; keeping prior actions")
        return actions
    logger.warning("Action dedupe %s→%s", len(actions), len(next_actions))
    return next_actions


def _qa_actions_llm(
    actions: list[ActionResult],
    *,
    lines: list[Transcript],
    gemini_key: str,
    openai_key: str,
    allowed: dict[str, str],
    on_busy: Callable[[int], None] | None,
    on_progress: Callable[[str], None] | None,
) -> list[ActionResult]:
    if not actions:
        return actions
    if on_progress:
        on_progress(
            "Aksiyonlar son kontrolden geçiyor…"
            if current_lang.get() != "en"
            else "Final action quality pass…"
        )
    prompt_core = ACTION_QA_PROMPT_EN if current_lang.get() == "en" else ACTION_QA_PROMPT
    listing = _format_raw_actions(actions)
    evidence = _format_action_evidence(actions, lines)
    if current_lang.get() == "en":
        prompt = f"{prompt_core}\n\nAction list:\n{listing}\n\nTranscript evidence:\n{evidence}\n"
    else:
        prompt = f"{prompt_core}\n\nAksiyon listesi:\n{listing}\n\nTranskript kanıtı:\n{evidence}\n"
    try:
        draft = _complete_json(
            prompt,
            ActionQADraft,
            gemini_key=gemini_key,
            openai_key=openai_key,
            max_output_tokens=4096,
            on_busy=on_busy,
            waits=(0, 8, 16),
        )
    except AnalysisError:
        logger.exception("Action QA pass failed; keeping list")
        return actions
    next_actions: list[ActionResult] = []
    seen: set[str] = set()
    _append_actions(draft.actions, next_actions, seen, allowed)
    if actions and not next_actions:
        logger.warning("Action QA wiped the list; keeping prior actions")
        return actions
    prior_keys = {tok for item in actions for tok in _tokens(f"{item.description} {item.notes or ''}")}
    next_keys = {tok for item in next_actions for tok in _tokens(f"{item.description} {item.notes or ''}")}
    if prior_keys and next_keys and len(prior_keys & next_keys) < 2:
        logger.warning("Action QA replaced the list with unrelated cards; keeping prior actions")
        return actions
    logger.warning("Action QA %s→%s", len(actions), len(next_actions))
    return next_actions


def analyze_transcript(
    lines: list[Transcript],
    *,
    title: str,
    attendees: str | None,
    meeting_date: str | None,
    description: str | None = None,
    named_attendees: str | None = None,
    language: str | None = None,
    on_busy: Callable[[int], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> AnalysisResult:
    token = current_lang.set(normalize_lang(language))
    try:
        return _analyze_transcript(
            lines,
            title=title,
            attendees=attendees,
            meeting_date=meeting_date,
            description=description,
            named_attendees=named_attendees,
            on_busy=on_busy,
            on_progress=on_progress,
        )
    finally:
        current_lang.reset(token)


def _analyze_transcript(
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
    speakers = ", ".join(labels) or _none_mark()
    declared = parse_named_attendees(named_attendees)
    named = ", ".join(declared) if declared else (attendees or "")
    if current_lang.get() == "en":
        extra = f"Description: {description}\n" if description else ""
        when = _format_meeting_when(meeting_date) or meeting_date or "not specified"
    else:
        extra = f"Açıklama: {description}\n" if description else ""
        when = _format_meeting_when(meeting_date) or meeting_date or "belirtilmedi"
    allowed = _speaker_labels(lines)
    slices = _iter_chunks(lines)
    total = len(slices)
    logger.warning("Analysis scanning %s lines in %s chunks", len(lines), total)
    _analysis_prompt, chunk_prompt, _refine_prompt = _prompts()

    draft_decisions: list[DecisionResult] = []
    action_rows: list[ActionResult] = []
    sections: list[str] = []
    seen_actions: set[str] = set()
    failed = 0

    for index, slice_lines in enumerate(slices, start=1):
        if on_progress:
            on_progress(f"Satırlar taranıyor ({index}/{total})…")
        seqs = [row.seq for row in slice_lines]
        label = _title_meta(title)
        if current_lang.get() == "en":
            prompt = (
                f"{chunk_prompt}\n"
                f"Title (metadata): {label or _none_mark()}\n"
                f"Date: {when}\n"
                f"Speaker names: {speakers}\n"
                f"This chunk line range: #{seqs[0]}–#{seqs[-1]}\n"
                f"{extra}"
                f"Transcript chunk:\n{_transcript_text(slice_lines)}\n"
            )
        else:
            prompt = (
                f"{chunk_prompt}\n"
                f"Başlık (metadata): {label or _none_mark()}\n"
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
                waits=(0, 8, 16),
            )
            if current_lang.get() == "en" and _looks_turkish(chunk.section or ""):
                logger.warning("Chunk %s/%s returned the wrong language; retrying in English", index, total)
                chunk = _complete_json(
                    "Write every string field in English. Do not write another language.\n" + prompt,
                    ChunkDraft,
                    gemini_key=gemini_key,
                    openai_key=openai_key,
                    max_output_tokens=8192,
                    on_busy=on_busy,
                    waits=(0, 8, 16),
                )
        except AnalysisError:
            failed += 1
            logger.exception("Chunk %s/%s failed", index, total)
            continue
        draft_decisions.extend(_collect_decisions(chunk.decisions, lines))
        _append_actions(chunk.actions, action_rows, seen_actions, allowed)
        if (chunk.section or "").strip():
            sections.append(maybe_fix_i(chunk.section.strip()))

    if failed == total:
        raise AnalysisError("Analiz dilimlerinin hiçbiri tamamlanamadı.")

    decisions = draft_decisions
    actions = action_rows

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
        summary = maybe_fix_i(polished)
    actions = _dedupe_actions_llm(
        actions,
        gemini_key=gemini_key,
        openai_key=openai_key,
        allowed=allowed,
        on_busy=on_busy,
        on_progress=on_progress,
    )
    actions = _qa_actions_llm(
        actions,
        lines=lines,
        gemini_key=gemini_key,
        openai_key=openai_key,
        allowed=allowed,
        on_busy=on_busy,
        on_progress=on_progress,
    )

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
