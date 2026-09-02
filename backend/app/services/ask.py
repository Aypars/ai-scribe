"""Answer questions about a single meeting transcript."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.transcript import Transcript
from app.services.analysis import AnalysisError, _api_key, _complete_json, _openai_key, _transcript_text
from app.services.meeting_lang import current_lang, maybe_fix_i, normalize_lang

_MAX_TRANSCRIPT_CHARS = 180_000


class AskError(Exception):
    pass


class AskCite(BaseModel):
    seq: int
    timestamp: int
    speaker: str | None
    text: str


class AskResult(BaseModel):
    answer: str
    cites: list[AskCite]


class _AskDraft(BaseModel):
    answer: str = Field(description="Answer from the transcript only.")
    cite_seqs: list[int] = Field(
        default_factory=list,
        description="Transcript # line numbers this answer rests on. At most 8.",
    )


def _prompt(question: str, transcript: str) -> str:
    if current_lang.get() == "en":
        return (
            "Answer the question using only the transcript below.\n"
            "If it is not in the transcript, say you do not know. Do not invent.\n"
            "The meeting title is not a source.\n"
            "Write the answer in English.\n"
            "cite_seqs: the # numbers of the lines you used, at most 8.\n\n"
            f"Question:\n{question}\n\n"
            f"Transcript:\n{transcript}\n"
        )
    return (
        "Soruyu yalnızca aşağıdaki transkripte göre yanıtla.\n"
        "Transkriptte yoksa bilmediğini söyle. Uydurma.\n"
        "Toplantı başlığı kaynak değildir.\n"
        "Yanıtı Türkçe yaz.\n"
        "cite_seqs: dayandığın satırların # numaraları, en fazla 8.\n\n"
        f"Soru:\n{question}\n\n"
        f"Transkript:\n{transcript}\n"
    )


def ask_transcript(
    lines: list[Transcript],
    question: str,
    *,
    language: str | None = None,
) -> AskResult:
    token = current_lang.set(normalize_lang(language))
    try:
        return _ask(lines, question)
    finally:
        current_lang.reset(token)


def _ask(lines: list[Transcript], question: str) -> AskResult:
    text = (question or "").strip()
    if not text:
        raise AskError("Soru boş.")
    if not lines:
        raise AskError("Bu toplantıda henüz transkript yok.")
    gemini_key = _api_key()
    openai_key = _openai_key()
    if not gemini_key and not openai_key:
        raise AskError("GEMINI_API_KEY veya OPENAI_API_KEY tanımlı değil.")
    body = _transcript_text(lines)
    if len(body) > _MAX_TRANSCRIPT_CHARS:
        body = body[:_MAX_TRANSCRIPT_CHARS]
    try:
        draft = _complete_json(
            _prompt(text, body),
            _AskDraft,
            gemini_key=gemini_key,
            openai_key=openai_key,
            max_output_tokens=2048,
            waits=(0, 6),
        )
    except AnalysisError as exc:
        raise AskError(str(exc)) from exc
    by_seq = {row.seq: row for row in lines}
    cites: list[AskCite] = []
    seen: set[int] = set()
    for seq in draft.cite_seqs[:8]:
        row = by_seq.get(seq)
        if row is None or seq in seen:
            continue
        seen.add(seq)
        cites.append(
            AskCite(
                seq=row.seq,
                timestamp=row.timestamp,
                speaker=row.speaker,
                text=(row.text or "").strip(),
            )
        )
    return AskResult(answer=maybe_fix_i((draft.answer or "").strip()), cites=cites)
