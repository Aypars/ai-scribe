"""Meeting analysis: summary, decisions, action items."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.transcript import Transcript
from app.services.analysis_prompts import (
    ACTION_DEDUP_PROMPT,
    ACTION_DEDUP_PROMPT_EN,
    ACTION_QA_PROMPT,
    ACTION_QA_PROMPT_EN,
    _prompts,
)
from app.services.llm import (
    AnalysisError,
    _api_key,
    _complete_json,
    _openai_key,
)
from app.services.meeting_lang import current_lang, maybe_fix_i, normalize_lang, speaker_prefix

logger = logging.getLogger(__name__)

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
