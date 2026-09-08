"""Local Whisper transcription via the installed CLI (GPU-capable system Python)."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.services.meeting_lang import current_lang, maybe_fix_i, normalize_lang, speaker_prefix

logger = logging.getLogger(__name__)
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_SENTENCE_END = re.compile(r"[.!?…][\"')\]]*(?:\s+|$)")


def _reload_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_PATH, override=True)
    except Exception:
        return


def _whisperx_model() -> str:
    _reload_env()
    return (os.getenv("WHISPERX_MODEL") or settings.whisperx_model or "large-v3").strip()


def _split_timed_pieces(pieces: list[tuple[float, float, str]]) -> list[tuple[int, str]]:
    joined = ""
    ts_at: list[float] = []
    for start, end, text in pieces:
        span = max(end - start, 1.0)
        if joined:
            joined += " "
            ts_at.append(start)
        for index, char in enumerate(text):
            ts_at.append(start + (index / max(len(text), 1)) * span)
            joined += char

    sentences: list[tuple[int, str]] = []
    last = 0
    last_ts = 0
    for match in _SENTENCE_END.finditer(joined):
        end = match.end()
        text = joined[last:end].strip()
        if text:
            lead = len(joined[last:]) - len(joined[last:].lstrip())
            idx = min(last + lead, max(len(ts_at) - 1, 0))
            timestamp = max(last_ts, int(ts_at[idx]) if ts_at else 0)
            last_ts = timestamp
            sentences.append((timestamp, text))
        last = end
    tail = joined[last:].strip()
    if tail:
        lead = len(joined[last:]) - len(joined[last:].lstrip())
        idx = min(last + lead, max(len(ts_at) - 1, 0))
        timestamp = max(last_ts, int(ts_at[idx]) if ts_at else 0)
        sentences.append((timestamp, tail))
    return sentences


def _split_sentence_segments(raw_segments: list[dict]) -> list[TranscriptSegment]:
    pieces: list[tuple[float, float, str]] = []
    for item in raw_segments:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = float(item.get("start") or 0)
        end = float(item.get("end") or start)
        if end <= start:
            end = start + max(1.0, len(text) / 14)
        pieces.append((start, end, text))
    return [TranscriptSegment(timestamp=ts, text=maybe_fix_i(text)) for ts, text in _split_timed_pieces(pieces)]

_WINGET_FFMPEG = Path.home() / (
    "AppData/Local/Microsoft/WinGet/Packages/"
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
)
_PERCENT = re.compile(r"(?<!\d)(\d{1,3})\s*%")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class TranscriptSegment:
    timestamp: int
    text: str
    speaker: str | None = None


@dataclass
class TranscriptResult:
    segments: list[TranscriptSegment]
    duration_seconds: int
    language: str | None


@dataclass
class TranscriptionJob:
    meeting_id: int
    state: str = "running"
    progress: int = 0
    message: str = "Yazıya çevriliyor…"
    error: str | None = None
    started_at: float = field(default_factory=time.time)


class TranscriptionError(RuntimeError):
    pass


class TranscriptionCancelled(TranscriptionError):
    pass


_jobs: dict[int, TranscriptionJob] = {}
_jobs_lock = threading.Lock()
_transcribe_lock = threading.Lock()
_proc_lock = threading.Lock()
_procs: dict[int, subprocess.Popen[str]] = {}
_cancel_ids: set[int] = set()


def get_job(meeting_id: int) -> TranscriptionJob | None:
    with _jobs_lock:
        job = _jobs.get(meeting_id)
        if job is None:
            return None
        return TranscriptionJob(
            meeting_id=job.meeting_id,
            state=job.state,
            progress=job.progress,
            message=job.message,
            error=job.error,
            started_at=job.started_at,
        )


def start_job(meeting_id: int) -> TranscriptionJob:
    with _jobs_lock:
        existing = _jobs.get(meeting_id)
        if existing is not None and existing.state == "running":
            return existing
        job = TranscriptionJob(meeting_id=meeting_id, progress=3, message="WhisperX başlatılıyor…")
        _jobs[meeting_id] = job
        return job


def update_job(meeting_id: int, *, progress: int | None = None, message: str | None = None) -> None:
    with _jobs_lock:
        job = _jobs.get(meeting_id)
        if job is None or job.state != "running":
            return
        if progress is not None:
            job.progress = max(job.progress, min(99, progress))
        if message is not None:
            job.message = message


def finish_job(meeting_id: int) -> None:
    with _jobs_lock:
        job = _jobs.get(meeting_id)
        if job is None:
            return
        job.state = "done"
        job.progress = 100
        job.message = "Yazıya çevrildi"
        job.error = None


def fail_job(meeting_id: int, error: str) -> None:
    with _jobs_lock:
        job = _jobs.get(meeting_id)
        if job is None:
            job = TranscriptionJob(meeting_id=meeting_id)
            _jobs[meeting_id] = job
        job.state = "failed"
        job.message = "Yazıya çevirme başarısız"
        job.error = error[:400]


def _is_cancelled(meeting_id: int | None) -> bool:
    if meeting_id is None:
        return False
    with _proc_lock:
        return meeting_id in _cancel_ids


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    proc.kill()


def _kill_matching_windows(needle: str) -> None:
    safe = needle.replace("'", "").replace("`", "")
    if os.name != "nt" or not safe:
        return
    script = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -and $_.CommandLine.Contains('{safe}') }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def cancel_transcription(meeting_id: int, audio_path: str | None = None) -> None:
    with _proc_lock:
        _cancel_ids.add(meeting_id)
        proc = _procs.get(meeting_id)
    if proc is not None:
        logger.warning("Killing Whisper process for meeting %s (pid %s)", meeting_id, proc.pid)
        _kill_tree(proc)
    if audio_path:
        name = Path(audio_path).name
        if name:
            _kill_matching_windows(name)
    with _jobs_lock:
        job = _jobs.get(meeting_id)
        if job is not None and job.state == "running":
            job.state = "failed"
            job.message = "Yazıya çevirme iptal edildi"
            job.error = None


def clear_transcription(meeting_id: int) -> None:
    with _proc_lock:
        _cancel_ids.discard(meeting_id)
        _procs.pop(meeting_id, None)


def _kill_whisperx_binaries() -> None:
    if os.name != "nt":
        return
    subprocess.run(
        ["taskkill", "/IM", "whisperx.exe", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def cancel_all_transcriptions() -> None:
    with _proc_lock:
        ids = list(_procs)
        procs = list(_procs.values())
        _cancel_ids.update(ids)
    for proc in procs:
        _kill_tree(proc)
    _kill_whisperx_binaries()


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _find_ffmpeg() -> Path | None:
    if settings.ffmpeg_bin:
        configured = Path(settings.ffmpeg_bin)
        if configured.is_file():
            return configured
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)
    extra: list[Path] = []
    if _WINGET_FFMPEG.is_dir():
        extra.extend(_WINGET_FFMPEG.glob("ffmpeg-*/bin/ffmpeg.exe"))
    return _first_existing(extra)


def extract_audio_from_video(video_path: Path) -> Path:
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise TranscriptionError("Video için ffmpeg gerekli. ffmpeg kurulu değil.")
    dest = video_path.with_suffix(".m4a")
    cmd = [
        str(ffmpeg),
        "-hide_banner",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30 * 60,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        dest.unlink(missing_ok=True)
        raise TranscriptionError("Videodan ses çıkarımı zaman aşımına uğradı") from exc
    if completed.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        detail = (completed.stderr or completed.stdout or "").strip().lower()
        if "does not contain any stream" in detail or "no audio" in detail:
            raise TranscriptionError("Videoda ses kanalı yok")
        raise TranscriptionError("Videodan ses çıkarılamadı")
    return dest


_convert_locks_guard = threading.Lock()
_convert_locks: dict[str, threading.Lock] = {}


def _playback_copy(path: Path) -> Path:
    return path.with_name(f"{path.stem}.seek.mp3")


def ensure_seekable_audio(path: Path) -> Path:
    """VBR MP3 Xing table is coarse (~1% of duration). CBR seeks to the second."""
    if not path.is_file():
        return path
    if path.suffix.lower() != ".mp3" or path.name.endswith(".seek.mp3"):
        return path
    dest = _playback_copy(path)
    if dest.is_file() and dest.stat().st_size > 1024:
        return dest
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        return path
    key = str(path.resolve())
    with _convert_locks_guard:
        lock = _convert_locks.setdefault(key, threading.Lock())
    with lock:
        if dest.is_file() and dest.stat().st_size > 1024:
            return dest
        tmp = path.with_name(f"{path.stem}.seek.tmp.mp3")
        cmd = [
            str(ffmpeg),
            "-hide_banner",
            "-y",
            "-i",
            str(path),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(tmp),
        ]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30 * 60,
                creationflags=_CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            tmp.unlink(missing_ok=True)
            return path
        if completed.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            return path
        tmp.replace(dest)
    return dest if dest.is_file() else path


def schedule_seekable_audio(path: Path) -> None:
    if path.suffix.lower() != ".mp3" or path.name.endswith(".seek.mp3"):
        return
    threading.Thread(target=ensure_seekable_audio, args=(path,), daemon=True).start()


def playback_audio_path(path: Path) -> Path:
    if path.suffix.lower() != ".mp3":
        return path
    cbr = _playback_copy(path)
    if cbr.is_file() and cbr.stat().st_size > 1024:
        return cbr
    m4a = path.with_suffix(".m4a")
    if m4a.is_file() and m4a.stat().st_size > 1024:
        return m4a
    schedule_seekable_audio(path)
    return path


def _find_whisper() -> Path | None:
    if settings.whisper_bin:
        configured = Path(settings.whisper_bin)
        if configured.is_file():
            return configured
    found = shutil.which("whisper")
    if found:
        return Path(found)
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    extra: list[Path] = []
    if local.is_dir():
        extra.extend(local.glob("Python*/Scripts/whisper.exe"))
    return _first_existing(extra)


def _find_whisperx() -> Path | None:
    if settings.whisperx_bin:
        configured = Path(settings.whisperx_bin)
        if configured.is_file():
            return configured
    found = shutil.which("whisperx")
    if found:
        return Path(found)
    desktop = Path.home() / "OneDrive" / "Desktop" / "whisperx-env" / "Scripts" / "whisperx.exe"
    extra = [
        desktop,
        Path.home() / "Desktop" / "whisperx-env" / "Scripts" / "whisperx.exe",
    ]
    return _first_existing(extra)


def _find_python() -> Path | None:
    whisperx = _find_whisperx()
    if whisperx is not None:
        candidate = whisperx.parent.parent / "Scripts" / "python.exe"
        if candidate.is_file():
            return candidate
        candidate = whisperx.parent / "python.exe"
        if candidate.is_file():
            return candidate
    whisper = _find_whisper()
    if whisper is not None:
        candidate = whisper.parent.parent / "python.exe"
        if candidate.is_file():
            return candidate
    return None


def _speaker_label(raw: object) -> str | None:
    value = str(raw or "").strip()
    if not value:
        return None
    match = re.match(r"SPEAKER_(\d+)$", value, re.I)
    if match:
        index = int(match.group(1))
        if index < 26:
            return f"{speaker_prefix()} {chr(ord('A') + index)}"
        return f"{speaker_prefix()} {index + 1}"
    return value


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÂÇĞİÖŞÜIÜ])")
_ENDED = re.compile(r"[.!?…][\"')\]]*$")


def _join_words(parts: list[str]) -> str:
    out = ""
    for part in parts:
        token = str(part or "")
        if out and not out.endswith(" ") and not token.startswith(" "):
            out += " "
        out += token
    return re.sub(r"\s+", " ", out).strip()


def _split_sentences(text: str) -> list[str]:
    value = re.sub(r"\s+", " ", (text or "").strip())
    if not value:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(value) if part.strip()]
    return parts or [value]


def _fill_word_speakers(speakers: list[str | None], seg_speaker: str | None) -> list[str | None]:
    """Keep word-level labels. Never paint a word with the whole-chunk speaker
    when any word already has a label — that is what tags an interruption as
    the person who was already talking."""
    if not any(speakers):
        return [seg_speaker for _ in speakers]
    filled: list[str | None] = []
    n = len(speakers)
    for i, speaker in enumerate(speakers):
        if speaker:
            filled.append(speaker)
            continue
        left = next((speakers[j] for j in range(i - 1, -1, -1) if speakers[j]), None)
        right = next((speakers[j] for j in range(i + 1, n) if speakers[j]), None)
        filled.append(left if left and left == right else None)
    return filled


def _speaker_runs(labels: list[str | None]) -> list[tuple[int, int, str | None]]:
    if not labels:
        return []
    runs: list[tuple[int, int, str | None]] = []
    start = 0
    current = labels[0]
    for index, label in enumerate(labels[1:], 1):
        if label != current:
            runs.append((start, index, current))
            start = index
            current = label
    runs.append((start, len(labels), current))
    return runs


def _smooth_word_speakers(speakers: list[str | None], *, max_island: int = 2) -> list[str | None]:
    """Drop 1–2 word speaker flips sandwiched in the same voice (pyannote noise)."""
    labels = list(speakers)
    for _ in range(len(labels) + 1):
        runs = _speaker_runs(labels)
        absorbed = False
        for index, (start, end, speaker) in enumerate(runs):
            width = end - start
            if width > max_island or not speaker:
                continue
            left = runs[index - 1][2] if index else None
            right = runs[index + 1][2] if index + 1 < len(runs) else None
            take = None
            if left and left == right and left != speaker:
                take = left
            elif left is None and right and right != speaker:
                take = right
            elif right is None and left and left != speaker:
                take = left
            if not take:
                continue
            labels[start:end] = [take] * width
            absorbed = True
            break
        if not absorbed:
            break
    return labels


def _backfill_speakers(speakers: list[str | None], seg_speaker: str | None) -> list[str | None]:
    filled = list(speakers)
    last: str | None = None
    for index, speaker in enumerate(filled):
        if speaker:
            last = speaker
        elif last:
            filled[index] = last
    last = None
    for index in range(len(filled) - 1, -1, -1):
        if filled[index]:
            last = filled[index]
        elif last:
            filled[index] = last
    if seg_speaker:
        filled = [item or seg_speaker for item in filled]
    return filled


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def collapse_speaker_flicker(rows: list[TranscriptSegment], *, max_island: int = 2) -> list[TranscriptSegment]:
    items = [
        TranscriptSegment(timestamp=row.timestamp, text=(row.text or "").strip(), speaker=row.speaker)
        for row in rows
        if (row.text or "").strip()
    ]
    for _ in range(len(items) + 1):
        absorbed = False
        for index in range(1, len(items) - 1):
            mid = items[index]
            if _word_count(mid.text) > max_island:
                continue
            left = items[index - 1].speaker
            right = items[index + 1].speaker
            if not left or left != right or left == mid.speaker:
                continue
            items[index - 1].text = f"{items[index - 1].text} {mid.text}".strip()
            del items[index]
            absorbed = True
            break
        if not absorbed:
            break
    return spread_long_lines(_merge_broken_sentences(items))


def _fit_word_times(seg_start: float, seg_end: float, stamps: list[float]) -> list[float]:
    """Snap drifted alignment times back onto the ASR segment clock."""
    if not stamps:
        return []
    first = stamps[0]
    last = max(stamps[-1], first)
    dest_end = seg_end if seg_end > seg_start else last
    late = first - seg_start
    overrun = last - dest_end if dest_end else 0.0
    if late <= 0.75 and overrun <= 0.75:
        return stamps
    src_span = last - first
    dst_span = max(dest_end - seg_start, 0.05)
    if src_span <= 0.02:
        return [seg_start for _ in stamps]
    return [seg_start + (stamp - first) / src_span * dst_span for stamp in stamps]


def _speaker_word_groups(item: dict) -> list[tuple[str | None, list[tuple[float, str]]]]:
    text = str(item.get("text") or "").strip()
    start = float(item.get("start") or 0)
    end = float(item.get("end") or start)
    seg_speaker = _speaker_label(item.get("speaker"))
    words = item.get("words") or []
    if not isinstance(words, list) or not words:
        return [(seg_speaker, [(start, text)] if text else [])]

    tokens: list[tuple[float, str]] = []
    raw_speakers: list[str | None] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        token = str(word.get("word") or word.get("text") or "")
        if not token.strip():
            continue
        tokens.append((float(word.get("start") or start), token))
        raw_speakers.append(_speaker_label(word.get("speaker")))
    if not tokens:
        return [(seg_speaker, [(start, text)] if text else [])]

    fitted = _fit_word_times(start, end, [stamp for stamp, _ in tokens])
    tokens = [(fitted[index], token) for index, (_, token) in enumerate(tokens)]
    speakers = _backfill_speakers(
        _smooth_word_speakers(_fill_word_speakers(raw_speakers, seg_speaker)),
        seg_speaker,
    )
    groups: list[tuple[str | None, list[tuple[float, str]]]] = []
    current: list[tuple[float, str]] = []
    current_speaker = speakers[0]
    for (stamp, token), speaker in zip(tokens, speakers):
        if speaker != current_speaker and current:
            groups.append((current_speaker, current))
            current = [(stamp, token)]
            current_speaker = speaker
            continue
        current.append((stamp, token))
        current_speaker = speaker
    if current:
        groups.append((current_speaker, current))
    return groups or [(seg_speaker, [(start, text)] if text else [])]


def _group_words_by_speaker(item: dict) -> list[tuple[float, str, str | None]]:
    groups: list[tuple[float, str, str | None]] = []
    for speaker, words in _speaker_word_groups(item):
        if not words:
            continue
        groups.append((words[0][0], _join_words([token for _, token in words]), speaker))
    if groups:
        return groups
    text = str(item.get("text") or "").strip()
    start = float(item.get("start") or 0)
    return [(start, text, _speaker_label(item.get("speaker")))] if text else []


def _sentences_from_words(words: list[tuple[float, str]]) -> list[tuple[int, str]]:
    pieces: list[tuple[float, float, str]] = []
    for index, (stamp, token) in enumerate(words):
        token = str(token or "").strip()
        if not token:
            continue
        nxt = words[index + 1][0] if index + 1 < len(words) else stamp + max(0.35, len(token) / 12)
        pieces.append((stamp, max(nxt, stamp + 0.05), token))
    return _split_timed_pieces(pieces) if pieces else []


def _merge_broken_sentences(rows: list[TranscriptSegment]) -> list[TranscriptSegment]:
    merged: list[TranscriptSegment] = []
    for row in rows:
        text = (row.text or "").strip()
        if not text:
            continue
        if (
            merged
            and merged[-1].speaker == row.speaker
            and not _ENDED.search((merged[-1].text or "").strip())
            and _word_count(text) <= 4
        ):
            merged[-1].text = f"{merged[-1].text} {text}".strip()
            continue
        merged.append(
            TranscriptSegment(timestamp=row.timestamp, text=text, speaker=row.speaker)
        )
    return merged


_MAX_LINE_WORDS = 14


def spread_long_lines(rows: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Give long agenda dumps their own timestamps so a click is not 8s early."""
    out: list[TranscriptSegment] = []
    total_rows = len(rows)
    for index, row in enumerate(rows):
        words = re.findall(r"\S+", row.text or "")
        if len(words) <= _MAX_LINE_WORDS:
            out.append(
                TranscriptSegment(timestamp=row.timestamp, text=(row.text or "").strip(), speaker=row.speaker)
            )
            continue
        next_ts = rows[index + 1].timestamp if index + 1 < total_rows else row.timestamp + max(len(words), 1)
        span = max(next_ts - row.timestamp, 1)
        used = 0
        for start in range(0, len(words), _MAX_LINE_WORDS):
            chunk = words[start : start + _MAX_LINE_WORDS]
            stamp = row.timestamp + int(used / len(words) * span)
            out.append(TranscriptSegment(timestamp=stamp, text=" ".join(chunk), speaker=row.speaker))
            used += len(chunk)
    return out


def _segments_from_whisperx(raw_segments: list[dict]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        for speaker, words in _speaker_word_groups(item):
            sentences = _sentences_from_words(words)
            if not sentences and words:
                joined = _join_words([token for _, token in words])
                if joined:
                    sentences = [(max(0, int(words[0][0])), joined)]
            for stamp, sentence in sentences:
                segments.append(
                    TranscriptSegment(
                        timestamp=max(0, stamp),
                        text=maybe_fix_i(sentence),
                        speaker=speaker,
                    )
                )
    return collapse_speaker_flicker(_merge_broken_sentences(segments))


def _tool_env() -> dict[str, str]:
    env = os.environ.copy()
    extras: list[str] = []
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        extras.append(str(ffmpeg.parent))
    whisperx = _find_whisperx()
    if whisperx:
        extras.append(str(whisperx.parent))
    else:
        whisper = _find_whisper()
        python = _find_python()
        if whisper:
            extras.append(str(whisper.parent))
        if python:
            extras.append(str(python.parent))
    if extras:
        env["PATH"] = os.pathsep.join(extras) + os.pathsep + env.get("PATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if settings.hf_token:
        env["HF_TOKEN"] = settings.hf_token
        env["HUGGING_FACE_HUB_TOKEN"] = settings.hf_token
    return env


def _whisper_language() -> str:
    return current_lang.get()


def _append_language_and_task(cmd: list[str]) -> None:
    # transcribe = spoken language as-is. --language tr on English audio
    # makes Whisper rewrite the transcript into Turkish.
    cmd.extend(["--task", "transcribe", "--language", _whisper_language()])


def _asr_hints(names: list[str] | None) -> tuple[str, str]:
    clean = [name.strip() for name in (names or []) if name and name.strip()][:24]
    if current_lang.get() == "en":
        prompt = "Formal English meeting. Motion carried, unanimously, action items, next steps."
        if clean:
            prompt += " Attendees: " + ", ".join(clean) + "."
    else:
        prompt = "Türkçe resmi toplantı. Kabul edildi, oy birliği, sevk, buyurun."
        if clean:
            prompt += " Katılımcılar: " + ", ".join(clean) + "."
    return prompt, ", ".join(clean)


def _whisperx_cmd(
    audio_path: Path,
    out_dir: Path,
    *,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    hint_names: list[str] | None = None,
) -> list[str]:
    whisperx = _find_whisperx()
    if whisperx is None:
        raise TranscriptionError("whisperx bulunamadı. Masaüstündeki whisperx-env ortamını kurun.")
    cmd = [
        str(whisperx),
        str(audio_path),
        "--model",
        _whisperx_model(),
        "--batch_size",
        str(settings.whisperx_batch_size),
        "--beam_size",
        "5",
        "--condition_on_previous_text",
        "False",
        "--chunk_size",
        "10",
        "--output_format",
        "json",
        "--output_dir",
        str(out_dir),
    ]
    prompt, hotwords = _asr_hints(hint_names)
    cmd.extend(["--initial_prompt", prompt])
    if hotwords:
        cmd.extend(["--hotwords", hotwords])
    if settings.hf_token.strip():
        cmd.extend(["--diarize", "--hf_token", settings.hf_token.strip()])
        low = max(2, min_speakers or 2)
        high = max(low, max_speakers or 12)
        high = min(18, high)
        cmd.extend(["--min_speakers", str(low), "--max_speakers", str(high)])
    _append_language_and_task(cmd)
    return cmd


def _whisper_cmd(audio_path: Path, out_dir: Path) -> list[str]:
    python = _find_python()
    args = [
        str(audio_path),
        "--model",
        settings.whisper_model,
        "--output_format",
        "json",
        "--output_dir",
        str(out_dir),
        "--verbose",
        "False",
    ]
    _append_language_and_task(args)
    if python is not None and _find_whisperx() is None:
        return [str(python), "-u", "-m", "whisper", *args]
    whisper = _find_whisper()
    if whisper is None:
        raise TranscriptionError("whisper komutu bulunamadı.")
    return [str(whisper), *args]


def _handle_output_line(line: str, on_progress: Callable[[int, str], None] | None) -> None:
    clean = _ANSI.sub("", line).strip()
    if not clean or on_progress is None:
        return
    lower = clean.lower()
    if "performing transcription" in lower:
        on_progress(25, "Yazıya çevriliyor…")
    elif "detected language" in lower:
        on_progress(45, "Yazıya çevriliyor…")
    elif "performing alignment" in lower:
        on_progress(70, "Zaman damgaları hizalanıyor…")
    elif "performing diarization" in lower:
        on_progress(85, "Konuşmacılar ayrılıyor…")
    match = _PERCENT.search(clean)
    if match:
        on_progress(min(99, int(match.group(1))), "Yazıya çevriliyor…")


def _pump_output(stream: object, on_progress: Callable[[int, str], None] | None) -> None:
    buffer = ""
    read = getattr(stream, "read", None)
    if read is None:
        return
    while True:
        chunk = read(64)
        if not chunk:
            break
        buffer += chunk
        while True:
            idx_r = buffer.find("\r")
            idx_n = buffer.find("\n")
            if idx_r < 0 and idx_n < 0:
                break
            if idx_r < 0:
                idx = idx_n
            elif idx_n < 0:
                idx = idx_r
            else:
                idx = min(idx_r, idx_n)
            _handle_output_line(buffer[:idx], on_progress)
            buffer = buffer[idx + 1 :]
    if buffer:
        _handle_output_line(buffer, on_progress)


def transcribe_audio(
    audio_path: Path,
    on_progress: Callable[[int, str], None] | None = None,
    meeting_id: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    hint_names: list[str] | None = None,
    language: str | None = None,
) -> TranscriptResult:
    token = current_lang.set(normalize_lang(language))
    try:
        return _transcribe_audio(
            audio_path,
            on_progress=on_progress,
            meeting_id=meeting_id,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            hint_names=hint_names,
        )
    finally:
        current_lang.reset(token)


def _transcribe_audio(
    audio_path: Path,
    on_progress: Callable[[int, str], None] | None = None,
    meeting_id: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    hint_names: list[str] | None = None,
) -> TranscriptResult:
    if _is_cancelled(meeting_id):
        raise TranscriptionCancelled("Yazıya çevirme iptal edildi")
    if not audio_path.is_file():
        raise TranscriptionError(f"Ses dosyası bulunamadı: {audio_path}")

    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise TranscriptionError("ffmpeg bulunamadı. Whisper sesi açmak için ffmpeg gerekir.")

    use_whisperx = _find_whisperx() is not None
    if not use_whisperx and _find_whisper() is None:
        raise TranscriptionError("whisperx bulunamadı. Masaüstündeki whisperx-env ortamını kurun.")

    if on_progress:
        on_progress(5, "WhisperX başlatılıyor…" if use_whisperx else "Model yükleniyor…")
    schedule_seekable_audio(audio_path)

    with tempfile.TemporaryDirectory(prefix="whisper-") as tmp:
        out_dir = Path(tmp)
        cmd = (
            _whisperx_cmd(
                audio_path,
                out_dir,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                hint_names=hint_names,
            )
            if use_whisperx
            else _whisper_cmd(audio_path, out_dir)
        )
        logger.warning("Transcription starting with %s", Path(cmd[0]).name)
        returncode = 1
        try:
            with _transcribe_lock:
                if _is_cancelled(meeting_id):
                    raise TranscriptionCancelled("Yazıya çevirme iptal edildi")
                _kill_matching_windows(audio_path.name)
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=_tool_env(),
                    creationflags=_CREATE_NO_WINDOW,
                )
                if meeting_id is not None:
                    with _proc_lock:
                        _procs[meeting_id] = proc
                pump = threading.Thread(
                    target=_pump_output,
                    args=(proc.stdout, on_progress),
                    daemon=True,
                )
                pump.start()
                try:
                    returncode = proc.wait(timeout=30 * 60)
                except subprocess.TimeoutExpired as exc:
                    _kill_tree(proc)
                    raise TranscriptionError("WhisperX zaman aşımına uğradı") from exc
                finally:
                    if meeting_id is not None:
                        with _proc_lock:
                            current = _procs.get(meeting_id)
                            if current is proc:
                                _procs.pop(meeting_id, None)
                pump.join(timeout=5)
        except TranscriptionCancelled:
            raise
        except OSError as exc:
            raise TranscriptionError(f"WhisperX başlatılamadı: {exc}") from exc

        if _is_cancelled(meeting_id):
            raise TranscriptionCancelled("Yazıya çevirme iptal edildi")
        if returncode != 0:
            raise TranscriptionError("WhisperX başarısız oldu")

        json_path = out_dir / f"{audio_path.stem}.json"
        if not json_path.is_file():
            matches = list(out_dir.glob("*.json"))
            if not matches:
                raise TranscriptionError("WhisperX JSON çıktısı üretmedi")
            json_path = matches[0]
        payload = json.loads(json_path.read_text(encoding="utf-8"))

    raw_segments = payload.get("segments") or []
    if use_whisperx:
        segments = _segments_from_whisperx(raw_segments)
    else:
        segments = _split_sentence_segments(raw_segments)

    full_text = str(payload.get("text") or "").strip()
    if not segments and full_text:
        segments = [TranscriptSegment(timestamp=0, text=maybe_fix_i(full_text))]

    last_end = 0.0
    for item in raw_segments:
        try:
            last_end = max(last_end, float(item.get("end") or 0))
        except (TypeError, ValueError):
            continue
    duration = int(round(last_end)) if last_end else (segments[-1].timestamp if segments else 0)
    language = payload.get("language")
    if on_progress:
        on_progress(100, "Yazıya çevrildi")
    return TranscriptResult(
        segments=segments,
        duration_seconds=duration,
        language=str(language) if language else None,
    )
