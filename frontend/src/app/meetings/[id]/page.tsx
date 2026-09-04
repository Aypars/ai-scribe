"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import { AppShell } from "@/components/AppShell";
import { AttendeeListEditor, joinAttendeeList, parseAttendeeList } from "@/components/AttendeeListEditor";
import { useConfirm } from "@/components/ConfirmDialog";
import { MeetingBadge, TaskBadge, DueHint } from "@/components/StatusBadge";
import { PersonPicker } from "@/components/PersonPicker";
import { useToast } from "@/components/Toast";
import {
  createTask,
  deleteMeeting,
  dismissMeetingAction,
  ensurePerson,
  fetchMeeting,
  fetchMeetingAudioUrl,
  analyzeMeeting,
  renameMeetingSpeaker,
  updateMeeting,
  updateMeetingAction,
  updateMeetingDecision,
  updateMeetingSummary,
  updateTranscriptLine,
  type ActionItem,
  type Decision,
  type MeetingDetail,
  type TranscriptFlag,
  type TranscriptLine,
} from "@/lib/api";
import { dateOnly, dueTone, formatDay, formatDuration, formatTimestamp, nowDatetimeLocal, todayISO } from "@/lib/dates";
import { followUpFor, formatClock, suggestionFor } from "@/lib/meeting-detail";
import { ExportMeetingDialog } from "@/components/ExportMeetingDialog";
import { MeetingAsk } from "@/components/MeetingAsk";
import { downloadMeetingReport, previewMeetingReport } from "@/lib/export-meeting";
import { speakerStats, type SpeakerStat } from "@/lib/speaker-stats";
import { talkColorClass } from "@/lib/talk-colors";

const tabs = [
  { id: "transcript", label: "Transkript" },
  { id: "summary", label: "Özet" },
  { id: "decisions", label: "Kararlar" },
  { id: "actions", label: "Aksiyonlar" },
  { id: "ask", label: "Yapay Zeka'ya Sor" },
] as const;

type TabId = (typeof tabs)[number]["id"];

const field =
  "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

function MetaStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold tracking-[0.14em] text-slate-500 uppercase dark:text-teal-400/70">
        {label}
      </p>
      <div className="mt-1.5 text-sm font-medium text-slate-800 dark:text-teal-50">{value}</div>
      {hint ? <p className="mt-0.5 text-xs text-slate-400">{hint}</p> : null}
    </div>
  );
}

function TalkShareCard({
  speakers,
  onPick,
}: {
  speakers: SpeakerStat[];
  onPick: (name: string) => void;
}) {
  if (!speakers.length) return null;
  return (
    <section className="mt-6 rounded-2xl border border-slate-200/80 bg-white p-4 dark:border-teal-800/40 dark:bg-[#0f2220]">
      <p className="text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">
        Kim ne kadar konuştu
      </p>
      <div className="mt-3 flex h-3 gap-0.5 overflow-hidden rounded-full bg-slate-100 dark:bg-teal-950">
        {speakers.map((row, index) =>
          row.share < 1 ? null : (
            <div
              key={row.name}
              title={`${row.name} %${row.share}`}
              className={`h-full ${talkColorClass(index)}`}
              style={{ width: `${row.share}%` }}
            />
          ),
        )}
      </div>
      <ul className="mt-3 grid gap-1 sm:grid-cols-2">
        {speakers.map((row, index) => (
          <li key={row.name}>
            <button
              type="button"
              onClick={() => onPick(row.name)}
              className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-1.5 py-1.5 text-left text-sm hover:bg-slate-50 dark:hover:bg-teal-900/40"
            >
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${talkColorClass(index)}`} />
              <span className="min-w-0 truncate font-medium text-slate-800 dark:text-teal-50">{row.name}</span>
              <span className="ml-auto shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">
                {formatDuration(row.seconds)} · %{row.share}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AttendeeChips({ value }: { value: string | null }) {
  const names = (value ?? "")
    .split(/[,;]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!names.length) {
    return <span className="font-normal text-slate-400">Belirtilmedi</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {names.map((name) => (
        <span
          key={name}
          className="inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700 dark:bg-teal-900/55 dark:text-teal-100"
        >
          {name}
        </span>
      ))}
    </div>
  );
}

function formatDecisionSpan(item: Decision): string | null {
  if (item.timestamp == null) return null;
  const start = formatTimestamp(item.timestamp);
  if (item.end_timestamp != null && item.end_timestamp !== item.timestamp) {
    return `${start}–${formatTimestamp(item.end_timestamp)}`;
  }
  return start;
}

function linesForDecision(item: Decision, lines: TranscriptLine[]): TranscriptLine[] {
  if (!lines.length) return [];
  const start = item.source_seq;
  const end = item.source_end_seq ?? item.source_seq;
  if (start == null || end == null) return [];
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  return lines.filter((line) => line.seq >= lo && line.seq <= hi);
}

function toDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function splitTranscriptSentences(lines: TranscriptLine[]): TranscriptLine[] {
  const pieces = lines
    .map((line, index) => {
      const text = line.text.trim();
      const start = line.timestamp;
      const next = lines[index + 1];
      const end = next
        ? Math.max(start + 1, next.timestamp)
        : start + Math.max(1, Math.ceil(text.length / 14));
      return { start, end, text };
    })
    .filter((piece) => piece.text);

  let joined = "";
  const tsAt: number[] = [];
  for (const piece of pieces) {
    const span = Math.max(piece.end - piece.start, 1);
    if (joined) {
      joined += " ";
      tsAt.push(piece.start);
    }
    for (let i = 0; i < piece.text.length; i += 1) {
      tsAt.push(piece.start + Math.floor((i / Math.max(piece.text.length, 1)) * span));
      joined += piece.text[i];
    }
  }

  const sentences: TranscriptLine[] = [];
  const re = /[.!?…]["')\]]*(?:\s+|$)/g;
  let last = 0;
  let lastTs = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(joined)) !== null) {
    const end = match.index + match[0].length;
    const text = joined.slice(last, end).trim();
    if (text) {
      const start = last + (joined.slice(last).length - joined.slice(last).trimStart().length);
      const timestamp = Math.max(lastTs, tsAt[Math.min(start, tsAt.length - 1)] ?? 0);
      lastTs = timestamp;
      sentences.push({ seq: sentences.length + 1, timestamp, text, speaker: null });
    }
    last = end;
  }
  const tail = joined.slice(last).trim();
  if (tail) {
    const start = last + (joined.slice(last).length - joined.slice(last).trimStart().length);
    const timestamp = Math.max(lastTs, tsAt[Math.min(start, tsAt.length - 1)] ?? 0);
    sentences.push({ seq: sentences.length + 1, timestamp, text: tail, speaker: null });
  }
  return sentences;
}

function foldTr(value: string): string {
  return value.toLocaleLowerCase("tr");
}

function lineMatchesQuery(line: TranscriptLine, query: string): boolean {
  const needle = foldTr(query).trim();
  if (!needle) return true;
  return foldTr(line.text).includes(needle);
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  const needle = foldTr(query).trim();
  if (!needle) return <>{text}</>;
  const folded = foldTr(text);
  const parts: ReactNode[] = [];
  let last = 0;
  let from = 0;
  let matchIndex = 0;
  while (from <= folded.length - needle.length) {
    const start = folded.indexOf(needle, from);
    if (start === -1) break;
    if (start > last) parts.push(text.slice(last, start));
    parts.push(
      <mark
        key={`${start}-${matchIndex}`}
        className="rounded-sm bg-amber-200 px-0.5 text-slate-900 dark:bg-teal-400/35 dark:text-teal-50"
      >
        {text.slice(start, start + needle.length)}
      </mark>,
    );
    matchIndex += 1;
    last = start + needle.length;
    from = last;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

function findFlagSpan(text: string, original: string): { start: number; end: number } | null {
  if (!original) return null;
  const exact = text.indexOf(original);
  if (exact >= 0) return { start: exact, end: exact + original.length };
  const start = foldTr(text).indexOf(foldTr(original));
  if (start < 0) return null;
  return { start, end: start + original.length };
}

function FlaggedLineText({
  line,
  query,
  busy,
  openIndex,
  onToggle,
  onApply,
  onDismiss,
}: {
  line: TranscriptLine;
  query: string;
  busy: boolean;
  openIndex: number | null;
  onToggle: (index: number | null) => void;
  onApply: (index: number) => void;
  onDismiss: (index: number) => void;
}) {
  const flags = line.flags ?? [];
  if (query.trim()) return <HighlightedText text={line.text} query={query} />;
  if (!flags.length) return <>{line.text}</>;

  const spans = flags
    .map((flag, index) => {
      const span = findFlagSpan(line.text, flag.original);
      return span ? { ...span, index, flag } : null;
    })
    .filter((item): item is { start: number; end: number; index: number; flag: TranscriptFlag } => item != null)
    .sort((a, b) => a.start - b.start);

  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const item of spans) {
    if (item.start < cursor) continue;
    if (item.start > cursor) parts.push(line.text.slice(cursor, item.start));
    parts.push(
      <span key={`flag-${item.index}`} className="relative inline">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggle(openIndex === item.index ? null : item.index);
          }}
          className="cursor-pointer underline decoration-wavy decoration-rose-500 underline-offset-2 dark:decoration-rose-400"
        >
          {line.text.slice(item.start, item.end)}
        </button>
        {openIndex === item.index ? (
          <span
            className="absolute top-full left-0 z-30 mt-1 w-64 rounded-xl border border-slate-200 bg-white p-3 text-left text-slate-800 shadow-lg dark:border-teal-800 dark:bg-[#0f2220] dark:text-teal-50"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="text-[11px] font-medium text-rose-600 dark:text-rose-300">
              {item.flag.reason || "Olası transkript hatası"}
            </p>
            <p className="mt-1 text-sm leading-5">{item.flag.suggestion}</p>
            <span className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => onApply(item.index)}
                className="h-7 cursor-pointer rounded-md bg-teal-700 px-2.5 text-[11px] font-medium text-white hover:bg-teal-800 disabled:opacity-50"
              >
                Uygula
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onDismiss(item.index)}
                className="h-7 cursor-pointer rounded-md px-2.5 text-[11px] font-medium text-slate-500 hover:bg-slate-100 dark:hover:bg-teal-900/40"
              >
                Yoksay
              </button>
            </span>
          </span>
        ) : null}
      </span>,
    );
    cursor = item.end;
  }
  if (cursor < line.text.length) parts.push(line.text.slice(cursor));
  return <>{parts}</>;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return target.isContentEditable;
}

function EditPencil({ onClick, title = "Düzenle" }: { onClick: () => void; title?: string }) {
  return (
    <button
      type="button"
      title={title}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-teal-900/50 dark:hover:text-teal-100"
    >
      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L4.8 18.75l.55-3.885a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Z" />
      </svg>
      Düzenle
    </button>
  );
}

function stripGuessMark(name: string): string {
  return name.replace(/\s*\?+\s*$/, "").trim();
}

function nameKey(name: string): string {
  return name.trim().toLocaleLowerCase("tr-TR");
}

function uniqueNames(groups: string[][]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const group of groups) {
    for (const raw of group) {
      const name = raw.trim();
      const key = nameKey(name);
      if (!name || seen.has(key)) continue;
      seen.add(key);
      out.push(name);
    }
  }
  return out;
}

function displayAttendeeNames(named: string[], speakers: { name: string }[]): string | null {
  const names = uniqueNames([
    named,
    speakers.map((row) => stripGuessMark(row.name) || row.name),
  ]);
  return names.length ? names.join(", ") : null;
}

function isGuessName(name: string | null | undefined): boolean {
  return Boolean(name && /\S\s*\?+\s*$/.test(name));
}

function isPendingSpeaker(name: string, _lines: TranscriptLine[]): boolean {
  return isGuessName(name);
}

function SpeakerGuessActions({
  busy,
  onConfirm,
  onReject,
}: {
  busy: boolean;
  onConfirm: () => void;
  onReject: () => void;
}) {
  return (
    <span className="ml-1 inline-flex items-center gap-0.5 align-middle">
      <button
        type="button"
        disabled={busy}
        title="Onayla"
        onClick={(event) => {
          event.stopPropagation();
          onConfirm();
        }}
        className="inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded text-xs font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50 dark:text-emerald-300 dark:hover:bg-emerald-950/50"
      >
        ✓
      </button>
      <button
        type="button"
        disabled={busy}
        title="Konuşmacı etiketine dön"
        onClick={(event) => {
          event.stopPropagation();
          onReject();
        }}
        className="inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50 dark:text-rose-300 dark:hover:bg-rose-950/50"
      >
        ✕
      </button>
    </span>
  );
}

function SpeakerRenameBox({
  value,
  onChange,
  onClose,
  onSubmit,
  busy,
  assignNames = [],
  onAssign,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  onClose: () => void;
  onSubmit?: () => void;
  busy: boolean;
  assignNames?: string[];
  onAssign?: (name: string) => void;
  children: ReactNode;
}) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handlePointer(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) onClose();
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [onClose]);

  return (
    <div
      ref={boxRef}
        className="absolute top-full left-0 z-20 mt-1 w-80 rounded-xl border border-slate-200 bg-white p-3 text-slate-900 shadow-lg dark:border-teal-800 dark:bg-[#0f2220] dark:text-teal-50"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <input
        autoFocus
        value={value}
        disabled={busy}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter" && onSubmit) {
            e.preventDefault();
            onSubmit();
          }
        }}
        placeholder="Yeni isim"
        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-sm font-medium text-slate-900 outline-none placeholder:text-slate-400 focus:border-teal-600 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
      />
      {assignNames.length && onAssign ? (
        <div className="mt-2">
          <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">Katılımcıya ata</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {assignNames.map((name) => (
              <button
                key={name}
                type="button"
                disabled={busy}
                onClick={() => onAssign(name)}
                className="h-7 max-w-full cursor-pointer truncate rounded-full border border-teal-200 bg-teal-50 px-2.5 text-xs font-medium text-teal-800 hover:bg-teal-100 disabled:opacity-50 dark:border-teal-800 dark:bg-teal-950/50 dark:text-teal-100 dark:hover:bg-teal-900/50"
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function LineSpeaker({
  name,
  seq,
  editing,
  value,
  busy,
  pending,
  onOpen,
  onChange,
  onClose,
  onRenameLine,
  onRenameAll,
  onConfirm,
  onReject,
  assignNames,
  onAssign,
}: {
  name: string;
  seq: number;
  editing: boolean;
  value: string;
  busy: boolean;
  pending?: boolean;
  onOpen: (seq: number, name: string) => void;
  onChange: (value: string) => void;
  onClose: () => void;
  onRenameLine: () => void;
  onRenameAll: () => void;
  onConfirm?: () => void;
  onReject?: () => void;
  assignNames?: string[];
  onAssign?: (name: string) => void;
}) {
  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onOpen(seq, name);
        }}
        className="cursor-pointer font-semibold text-slate-800 hover:text-teal-700 hover:underline dark:text-teal-100 dark:hover:text-teal-300"
      >
        {name}
      </button>
      {pending && !editing && onConfirm && onReject ? (
        <SpeakerGuessActions busy={busy} onConfirm={onConfirm} onReject={onReject} />
      ) : null}
      {editing ? (
        <SpeakerRenameBox
          value={value}
          onChange={onChange}
          onClose={onClose}
          onSubmit={onRenameAll}
          busy={busy}
          assignNames={assignNames}
          onAssign={onAssign}
        >
          <button
            type="button"
            disabled={busy || !value.trim()}
            onClick={onRenameLine}
            className="h-8 cursor-pointer rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-teal-800 dark:text-slate-200 dark:hover:bg-teal-900/40"
          >
            Sadece bu satır
          </button>
          <button
            type="button"
            disabled={busy || !value.trim()}
            onClick={onRenameAll}
            className="h-8 cursor-pointer rounded-lg bg-teal-700 px-2.5 text-xs font-medium text-white hover:bg-teal-800 disabled:opacity-50"
          >
            Hepsini değiştir
          </button>
        </SpeakerRenameBox>
      ) : null}
    </div>
  );
}

function TranscriptAudioPlayer({
  src,
  loading,
  error,
  audioRef,
  onTimeUpdate,
}: {
  src: string | null;
  loading: boolean;
  error: string | null;
  audioRef: RefObject<HTMLAudioElement | null>;
  onTimeUpdate: (time: number) => void;
}) {
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [time, setTime] = useState(0);
  const [rate, setRate] = useState(1);
  const dragging = useRef(false);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;

    const syncTime = () => {
      if (!dragging.current) setTime(el.currentTime);
      onTimeUpdate(el.currentTime);
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onMeta = () => setDuration(Number.isFinite(el.duration) ? el.duration : 0);
    const onEnded = () => setPlaying(false);

    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("timeupdate", syncTime);
    el.addEventListener("seeked", syncTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("durationchange", onMeta);
    el.addEventListener("ended", onEnded);
    onMeta();
    setPlaying(!el.paused);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("timeupdate", syncTime);
      el.removeEventListener("seeked", syncTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("durationchange", onMeta);
      el.removeEventListener("ended", onEnded);
    };
  }, [audioRef, onTimeUpdate, src]);

  useEffect(() => {
    setPlaying(false);
    setTime(0);
    setDuration(0);
  }, [src]);

  const percent = duration > 0 ? Math.min(100, (time / duration) * 100) : 0;

  function togglePlay() {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) void el.play();
    else el.pause();
  }

  function seekTo(next: number) {
    const el = audioRef.current;
    if (!el || !Number.isFinite(next)) return;
    const apply = () => {
      const max = Number.isFinite(el.duration) && el.duration > 0 ? el.duration : next;
      const clamped = Math.min(max, Math.max(0, next));
      el.currentTime = clamped;
      setTime(clamped);
      onTimeUpdate(clamped);
    };
    if (el.readyState >= 1) apply();
    else el.addEventListener("loadedmetadata", apply, { once: true });
  }

  function skip(delta: number) {
    seekTo(time + delta);
  }

  function cycleRate() {
    const next = rate >= 2 ? 1 : rate >= 1.5 ? 2 : rate >= 1.25 ? 1.5 : 1.25;
    setRate(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  }

  return (
    <div className="mb-6 rounded-2xl border border-slate-200 bg-gradient-to-r from-teal-50 to-white px-4 py-4 dark:border-teal-800/70 dark:from-teal-950/70 dark:to-[#0c1c1b]">
      <audio
        ref={audioRef}
        src={src ?? undefined}
        preload="auto"
        className="hidden"
      />
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900 dark:text-teal-50">Kayıt</p>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Transkript satırına tıklayınca kayıt o ana gider
          </p>
        </div>
        {src ? (
          <button
            type="button"
            onClick={cycleRate}
            className="h-8 shrink-0 cursor-pointer rounded-full border border-teal-200 bg-white px-3 text-xs font-semibold text-teal-800 hover:bg-teal-50 dark:border-teal-700 dark:bg-teal-950 dark:text-teal-100 dark:hover:bg-teal-900"
          >
            {rate}x
          </button>
        ) : null}
      </div>
      {src ? (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => skip(-10)}
            aria-label="10 saniye geri"
            className="hidden h-9 min-w-9 shrink-0 cursor-pointer items-center justify-center rounded-full px-2 text-xs font-semibold text-teal-800 hover:bg-teal-100 sm:flex dark:text-teal-100 dark:hover:bg-teal-900/60"
          >
            −10
          </button>
          <button
            type="button"
            onClick={togglePlay}
            aria-label={playing ? "Duraklat" : "Oynat"}
            className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-teal-700 text-white shadow-sm hover:bg-teal-800"
          >
            {playing ? (
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden>
                <rect x="6.5" y="5" width="4" height="14" rx="1" />
                <rect x="13.5" y="5" width="4" height="14" rx="1" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" className="ml-0.5 h-5 w-5" fill="currentColor" aria-hidden>
                <path d="M8 5.5v13l11-6.5L8 5.5Z" />
              </svg>
            )}
          </button>
          <button
            type="button"
            onClick={() => skip(10)}
            aria-label="10 saniye ileri"
            className="hidden h-9 min-w-9 shrink-0 cursor-pointer items-center justify-center rounded-full px-2 text-xs font-semibold text-teal-800 hover:bg-teal-100 sm:flex dark:text-teal-100 dark:hover:bg-teal-900/60"
          >
            +10
          </button>
          <span className="w-11 shrink-0 text-right text-xs font-medium tabular-nums text-slate-600 dark:text-teal-200">
            {formatTimestamp(Math.floor(time))}
          </span>
          <div className="relative h-7 min-w-0 flex-1">
            <div className="pointer-events-none absolute top-1/2 right-0 left-0 h-1.5 -translate-y-1/2 rounded-full bg-slate-200 dark:bg-teal-950" />
            <div
              className="pointer-events-none absolute top-1/2 left-0 h-1.5 -translate-y-1/2 rounded-full bg-teal-600"
              style={{ width: `${percent}%` }}
            />
            <input
              type="range"
              min={0}
              max={duration || 0}
              step={0.1}
              value={Number.isFinite(time) ? time : 0}
              aria-label="Kayıt konumu"
              onPointerDown={() => {
                dragging.current = true;
              }}
              onPointerUp={() => {
                dragging.current = false;
              }}
              onChange={(event) => {
                seekTo(Number(event.target.value));
              }}
              className="absolute inset-0 w-full cursor-pointer appearance-none bg-transparent [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-teal-700 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-teal-700"
            />
          </div>
          <span className="w-11 shrink-0 text-xs font-medium tabular-nums text-slate-500 dark:text-slate-400">
            {formatTimestamp(Math.floor(duration))}
          </span>
        </div>
      ) : loading ? (
        <p className="text-sm text-slate-400">Ses yükleniyor…</p>
      ) : (
        <p className="text-sm text-rose-500">{error ?? "Ses kaydı açılamadı."}</p>
      )}
    </div>
  );
}

function WorkingIndicator({ elapsed }: { elapsed: number }) {
  return (
    <div className="flex items-start gap-3">
      <span
        className="mt-0.5 h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-amber-200 border-t-amber-500"
        aria-hidden
      />
      <div>
        <p className="text-sm font-medium text-slate-700">Yazıya çevriliyor…</p>
        <p className="mt-1 text-xs text-slate-400">
          {elapsed > 0 ? `${elapsed} sn` : "Başladı"} · bu işlem biraz sürebilir
        </p>
      </div>
    </div>
  );
}

function isMatchingSpeakers(meeting: MeetingDetail | null | undefined): boolean {
  return Boolean(meeting?.transcription?.message?.includes("eşleniyor"));
}

function isServerAnalyzing(meeting: MeetingDetail | null | undefined): boolean {
  if (!meeting || meeting.status === "uploaded" || meeting.status === "failed") return false;
  if (meeting.transcription?.error) return false;
  const message = meeting.transcription?.message || "";
  return Boolean(message) && !message.includes("eşleniyor");
}

function analysisProgressLabel(meeting: MeetingDetail, analysisBusy: boolean): string {
  const message = (meeting.transcription?.message || "").trim();
  if ((analysisBusy || isServerAnalyzing(meeting)) && message && !message.includes("eşleniyor")) {
    return message;
  }
  if (analysisBusy || isServerAnalyzing(meeting)) return "Analiz ediliyor…";
  return "";
}

function pendingAnalysisCopy(meeting: MeetingDetail, analysisBusy: boolean): string {
  if (meeting.status === "uploaded") return "Yazıya çevriliyor…";
  if (isMatchingSpeakers(meeting)) return "Konuşmacılar eşleniyor…";
  const analyzing = analysisProgressLabel(meeting, analysisBusy);
  if (analyzing) return analyzing;
  if (meeting.status === "transcribed") {
    return "Konuşmacı eşleşmelerini onaylayın, ardından Analiz yap’a basın.";
  }
  return "Henüz yok.";
}

export default function MeetingDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();
  const [tab, setTab] = useState<TabId>("transcript");
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [selected, setSelected] = useState<ActionItem | null>(null);
  const [actionNote, setActionNote] = useState("");
  const [actionSpeaker, setActionSpeaker] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [attendeeNames, setAttendeeNames] = useState<string[]>([]);
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [speakerBusy, setSpeakerBusy] = useState(false);
  const [lineEdit, setLineEdit] = useState<{ seq: number; current: string } | null>(null);
  const [lineName, setLineName] = useState("");
  const [textEdit, setTextEdit] = useState<{ seq: number; value: string } | null>(null);
  const [textBusy, setTextBusy] = useState(false);
  const [flagOpen, setFlagOpen] = useState<{ seq: number; index: number } | null>(null);
  const [bulkEdit, setBulkEdit] = useState<string | null>(null);
  const [bulkName, setBulkName] = useState("");
  const [filterSpeaker, setFilterSpeaker] = useState<string | null>(null);
  const [transcriptQuery, setTranscriptQuery] = useState("");
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [focusSeq, setFocusSeq] = useState<number | null>(null);
  const [decisionView, setDecisionView] = useState<Decision | null>(null);
  const [decisionDraft, setDecisionDraft] = useState<{
    source: Decision;
    title: string;
    assignee: string;
    assignee_id: number | null;
    assigneeNote: string;
    assigneeSpeaker: string | null;
    due_date: string;
    notes: string;
  } | null>(null);
  const [decisionTaskSaving, setDecisionTaskSaving] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState<string | null>(null);
  const [decisionEdit, setDecisionEdit] = useState<{ seq: number; text: string } | null>(null);
  const [analysisEditBusy, setAnalysisEditBusy] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const focusRef = useRef<HTMLLIElement | null>(null);
  const activeLineRef = useRef<HTMLLIElement | null>(null);
  const transcriptBoxRef = useRef<HTMLDivElement | null>(null);
  const lastFollowedSeq = useRef<number | null>(null);
  const [followAudio, setFollowAudio] = useState(true);

  const [elapsed, setElapsed] = useState(0);
  const [fromUpload, setFromUpload] = useState(false);
    const statusRef = useRef<string | null>(null);
    const pollRef = useRef(true);
    const startedAtRef = useRef<number | null>(null);
    const analysisBusyRef = useRef(false);

  useEffect(() => {
    setFromUpload(new URLSearchParams(window.location.search).get("transcribing") === "1");
  }, []);

  useEffect(() => {
    const id = Number(params.id);
    setTranscriptQuery("");
    setDecisionView(null);
    if (!Number.isFinite(id)) {
      setError("Toplantı bulunamadı");
      setLoading(false);
      return;
    }

    const startKey = `ai-scribe-transcribe:${id}`;
    const storedStart = Number(window.localStorage.getItem(startKey));
    if (Number.isFinite(storedStart) && storedStart > 0) {
      startedAtRef.current = storedStart;
      setElapsed(Math.max(0, Math.floor((Date.now() - storedStart) / 1000)));
    }

    let cancelled = false;

    const load = async (initial: boolean) => {
      try {
        const data = await fetchMeeting(id);
        if (cancelled) return;
        setError(null);
        statusRef.current = data.status;
        const matching = isMatchingSpeakers(data);
        const serverAnalyzing = isServerAnalyzing(data);
        if (
          analysisBusyRef.current &&
          !serverAnalyzing &&
          (data.status === "analyzed" || Boolean(data.summary) || Boolean(data.transcription?.error))
        ) {
          analysisBusyRef.current = false;
        }
        const busy = serverAnalyzing || analysisBusyRef.current;
        pollRef.current = data.status === "uploaded" || matching || busy;
        setAnalysisBusy(busy);
        setMeeting(data);
        if (!busy) {
          setActionItems(data.actions.map((item) => ({ ...item })));
        }
        if (data.status === "uploaded") {
          const serverElapsed = data.transcription?.elapsed_seconds ?? 0;
          const fromServer = Date.now() - serverElapsed * 1000;
          const current = startedAtRef.current;
          const startedAt = current && current > 0 ? Math.min(current, fromServer) : fromServer;
          startedAtRef.current = startedAt;
          window.localStorage.setItem(startKey, String(startedAt));
          setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
        } else {
          startedAtRef.current = null;
          window.localStorage.removeItem(startKey);
          setFromUpload(false);
        }
        if (initial) {
          setTitle(data.title);
          setDate(toDatetimeLocal(data.date));
          setAttendeeNames(parseAttendeeList(data.named_attendees ?? ""));
          setDescription(data.description ?? "");
          setEditing(new URLSearchParams(window.location.search).get("edit") === "1");
        }
      } catch (err: unknown) {
        if (cancelled) return;
        if (initial) setError(err instanceof Error ? err.message : "Toplantı alınamadı");
      } finally {
        if (!cancelled && initial) setLoading(false);
      }
    };

    void load(true);
    const interval = window.setInterval(() => {
      if (pollRef.current) {
        void load(false);
      }
    }, 1000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [params.id]);

  const transcribing = meeting?.status === "uploaded" || (loading && fromUpload);

  useEffect(() => {
    if (!transcribing) return;
    const tick = window.setInterval(() => {
      const startedAt = startedAtRef.current;
      if (startedAt == null) return;
      setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    }, 1000);
    return () => window.clearInterval(tick);
  }, [transcribing]);

  useEffect(() => {
    if (!meeting?.audio_path) {
      setAudioUrl(null);
      setAudioLoading(false);
      setAudioError(null);
      return;
    }
    const meetingId = meeting.meeting_id;
    let cancelled = false;
    let objectUrl: string | null = null;
    setAudioLoading(true);
    setAudioError(null);
    void fetchMeetingAudioUrl(meetingId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setAudioUrl(url);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setAudioError(err instanceof Error ? err.message : "Ses kaydı açılamadı");
      })
      .finally(() => {
        if (!cancelled) setAudioLoading(false);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [meeting?.meeting_id, meeting?.audio_path]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !audioUrl || pendingSeekRef.current == null) return;
    const time = pendingSeekRef.current;
    pendingSeekRef.current = null;
    const apply = () => {
      el.currentTime = time;
      void el.play();
      setCurrentTime(time);
    };
    if (el.readyState >= 1) apply();
    else el.addEventListener("loadedmetadata", apply, { once: true });
  }, [audioUrl]);

  useEffect(() => {
    if (tab !== "transcript") return;
    const line = focusSeq != null ? focusRef.current : followAudio ? activeLineRef.current : null;
    const box = transcriptBoxRef.current;
    if (!line || !box) return;
    const seq = Number(line.dataset.seq);
    if (!Number.isFinite(seq)) return;
    if (focusSeq == null && lastFollowedSeq.current === seq) return;
    lastFollowedSeq.current = seq;
    const frame = window.requestAnimationFrame(() => {
      const boxRect = box.getBoundingClientRect();
      const lineRect = line.getBoundingClientRect();
      const offset = lineRect.top - boxRect.top - box.clientHeight * 0.32;
      if (Math.abs(offset) < 12) return;
      box.scrollBy({ top: offset, behavior: "smooth" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [tab, focusSeq, followAudio, currentTime]);

  async function handleSave() {
    if (!meeting) return;
    if (date && date > nowDatetimeLocal()) {
      setError("Toplantı tarihi şu andan ileri olamaz");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await updateMeeting(meeting.meeting_id, {
        title,
        date,
        named_attendees: joinAttendeeList(attendeeNames),
        description,
      });
      const detail = await fetchMeeting(meeting.meeting_id);
      setMeeting({ ...meeting, ...updated, ...detail });
      pollRef.current = isMatchingSpeakers(detail);
      setEditing(false);
      router.replace(`/meetings/${meeting.meeting_id}`);
      toast("Toplantı başarıyla kaydedildi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  }

  function revertEdit() {
    if (meeting) {
      setTitle(meeting.title);
      setDate(toDatetimeLocal(meeting.date));
      setAttendeeNames(parseAttendeeList(meeting.named_attendees ?? ""));
      setDescription(meeting.description ?? "");
    }
    setEditing(false);
  }

  function openAction(item: ActionItem) {
    setActionNote("");
    setActionSpeaker(null);
    setSelected({ ...item, due_date: dateOnly(item.due_date) || todayISO() });
  }

  async function handleDelete() {
    if (!meeting) return;
    const ok = await confirm({
      message: `“${meeting.title}” silinsin mi? Bu işlem geri alınamaz.`,
    });
    if (!ok) return;
    setDeleting(true);
    try {
      await deleteMeeting(meeting.meeting_id);
      toast("Toplantı başarıyla silindi");
      router.push("/meetings");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Silinemedi");
      setDeleting(false);
    }
  }

  async function handleSpeakerGuess(name: string, action: "confirm" | "reject") {
    if (!meeting) return;
    const origin = meeting.transcript.find((line) => line.speaker === name)?.speaker_origin ?? null;
    const confirmed = stripGuessMark(name);
    setSpeakerBusy(true);
    setError(null);
    try {
      const updated = await renameMeetingSpeaker(meeting.meeting_id, {
        from_speaker: name,
        action,
      });
      setMeeting({
        ...meeting,
        transcript: updated.transcript,
        attendees: updated.attendees,
        named_attendees: updated.named_attendees,
        summary: updated.summary,
        decisions: updated.decisions,
        actions: updated.actions,
      });
      setActionItems(updated.actions.map((item) => ({ ...item })));
      if (filterSpeaker === name) {
        setFilterSpeaker(action === "confirm" ? confirmed : origin);
      }
      toast(action === "confirm" ? "Konuşmacı onaylandı" : "Konuşmacı etiketi kullanıldı");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Konuşmacı güncellenemedi");
    } finally {
      setSpeakerBusy(false);
    }
  }

  async function handleRenameSpeaker(body: { speaker: string; seq?: number; from_speaker?: string }) {
    if (!meeting) return;
    const speaker = body.speaker.trim();
    if (!speaker) return;
    setSpeakerBusy(true);
    setError(null);
    try {
      const updated = await renameMeetingSpeaker(meeting.meeting_id, {
        speaker,
        ...(body.seq != null ? { seq: body.seq } : { from_speaker: body.from_speaker }),
      });
      setMeeting({
        ...meeting,
        transcript: updated.transcript,
        attendees: updated.attendees,
        named_attendees: updated.named_attendees,
        summary: updated.summary,
        decisions: updated.decisions,
        actions: updated.actions,
      });
      setActionItems(updated.actions.map((item) => ({ ...item })));
      setAttendeeNames(parseAttendeeList(updated.named_attendees ?? ""));
      setLineEdit(null);
      setBulkEdit(null);
      toast("Konuşmacı başarıyla güncellendi");
      if (body.from_speaker && filterSpeaker === body.from_speaker) {
        setFilterSpeaker(speaker);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Konuşmacı adı güncellenemedi");
    } finally {
      setSpeakerBusy(false);
    }
  }

  async function handleSaveLineText() {
    if (!meeting || !textEdit) return;
    const text = textEdit.value.trim();
    if (!text) return;
    setTextBusy(true);
    setError(null);
    try {
      const updated = await updateTranscriptLine(meeting.meeting_id, { seq: textEdit.seq, text });
      setMeeting({ ...meeting, transcript: updated.transcript });
      setTextEdit(null);
      toast("Satır başarıyla kaydedildi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Satır güncellenemedi");
    } finally {
      setTextBusy(false);
    }
  }

  async function handleFlagApply(line: TranscriptLine, index: number) {
    if (!meeting) return;
    const flag = line.flags?.[index];
    if (!flag) return;
    const span = findFlagSpan(line.text, flag.original);
    const nextText = span
      ? `${line.text.slice(0, span.start)}${flag.suggestion}${line.text.slice(span.end)}`
      : line.text;
    const nextFlags = (line.flags ?? []).filter((_, i) => i !== index);
    setTextBusy(true);
    setError(null);
    try {
      const updated = await updateTranscriptLine(meeting.meeting_id, {
        seq: line.seq,
        text: nextText,
        flags: nextFlags,
      });
      setMeeting({ ...meeting, transcript: updated.transcript });
      setFlagOpen(null);
      toast("Düzeltme uygulandı");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Düzeltme uygulanamadı");
    } finally {
      setTextBusy(false);
    }
  }

  async function handleFlagDismiss(line: TranscriptLine, index: number) {
    if (!meeting) return;
    const nextFlags = (line.flags ?? []).filter((_, i) => i !== index);
    setTextBusy(true);
    setError(null);
    try {
      const updated = await updateTranscriptLine(meeting.meeting_id, {
        seq: line.seq,
        text: line.text,
        flags: nextFlags,
      });
      setMeeting({ ...meeting, transcript: updated.transcript });
      setFlagOpen(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Uyarı kapatılamadı");
    } finally {
      setTextBusy(false);
    }
  }

  async function handleRetryAnalysis() {
    if (!meeting) return;
    setError(null);
    setDecisionView(null);
    setSelected(null);
    setSummaryDraft(null);
    analysisBusyRef.current = true;
    setAnalysisBusy(true);
    pollRef.current = true;
    try {
      const updated = await analyzeMeeting(meeting.meeting_id);
      const still =
        Boolean(updated.transcription?.message) &&
        updated.status !== "uploaded" &&
        !updated.transcription?.error;
      setMeeting(updated);
      if (!still) {
        setActionItems(updated.actions.map((item) => ({ ...item })));
        analysisBusyRef.current = false;
        setAnalysisBusy(false);
      }
    } catch (err: unknown) {
      analysisBusyRef.current = false;
      setAnalysisBusy(false);
      setError(err instanceof Error ? err.message : "Analiz başlatılamadı");
    }
  }

  async function handleCreateTask(item: ActionItem, dueDate: string) {
    if (!meeting || item.task_status) return;
    const due = dateOnly(dueDate);
    if (!due) {
      setError("Görev oluşturmak için teslim tarihi gerekli");
      return;
    }
    if (due < todayISO()) {
      setError("Teslim tarihi geçmiş olamaz");
      return;
    }
    try {
      const assigned = await ensurePerson(item.assignee_id, item.assignee ?? "", actionNote);
      await createTask({
        meeting_id: meeting.meeting_id,
        title: item.description,
        assignee: assigned.assignee,
        assignee_id: assigned.assignee_id,
        speaker_label: actionSpeaker,
        due_date: due,
        description: item.notes || item.description,
        action_seq: item.seq,
      });
      const updated = await fetchMeeting(meeting.meeting_id);
      setMeeting(updated);
      setActionItems(updated.actions.map((row) => ({ ...row })));
      setAttendeeNames(parseAttendeeList(updated.named_attendees ?? ""));
      setSelected(null);
      setActionNote("");
      setActionSpeaker(null);
      toast("Görev başarıyla oluşturuldu");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Görev oluşturulamadı");
    }
  }

  function startDecisionFollowUp(item: Decision) {
    if (!meeting) return;
    const existing = followUpFor(item, actionItems);
    if (existing) {
      router.push(`/tasks?task=${meeting.meeting_id}-${existing.seq}`);
      return;
    }
    setSelected(null);
    setDecisionDraft({
      source: item,
      title: item.text,
      assignee: "",
      assignee_id: null,
      assigneeNote: "",
      assigneeSpeaker: null,
      due_date: todayISO(),
      notes: "",
    });
  }

  async function handleCreateDecisionTask() {
    if (!meeting || !decisionDraft) return;
    const due = dateOnly(decisionDraft.due_date);
    if (!due) {
      setError("Görev oluşturmak için teslim tarihi gerekli");
      return;
    }
    if (due < todayISO()) {
      setError("Teslim tarihi geçmiş olamaz");
      return;
    }
    setError(null);
    setDecisionTaskSaving(true);
    try {
      const assigned = await ensurePerson(
        decisionDraft.assignee_id,
        decisionDraft.assignee,
        decisionDraft.assigneeNote,
      );
      const suggestion = suggestionFor(decisionDraft.source, actionItems);
      const title = decisionDraft.title.trim() || decisionDraft.source.text;
      const description = decisionDraft.notes.trim();
      if (suggestion) {
        await createTask({
          meeting_id: meeting.meeting_id,
          title,
          assignee: assigned.assignee,
          assignee_id: assigned.assignee_id,
          speaker_label: decisionDraft.assigneeSpeaker,
          due_date: due,
          description,
          action_seq: suggestion.seq,
        });
      } else {
        await createTask({
          meeting_id: meeting.meeting_id,
          title,
          assignee: assigned.assignee,
          assignee_id: assigned.assignee_id,
          speaker_label: decisionDraft.assigneeSpeaker,
          due_date: due,
          description,
        });
      }
      const updated = await fetchMeeting(meeting.meeting_id);
      setMeeting(updated);
      setActionItems(updated.actions.map((item) => ({ ...item })));
      setAttendeeNames(parseAttendeeList(updated.named_attendees ?? ""));
      setDecisionDraft(null);
      toast("Görev oluşturuldu");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Görev oluşturulamadı");
    } finally {
      setDecisionTaskSaving(false);
    }
  }

  async function handleSaveSummary() {
    if (!meeting || summaryDraft == null) return;
    setError(null);
    setAnalysisEditBusy(true);
    try {
      const updated = await updateMeetingSummary(meeting.meeting_id, summaryDraft);
      setMeeting(updated);
      setSummaryDraft(null);
      toast("Özet kaydedildi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Özet kaydedilemedi");
    } finally {
      setAnalysisEditBusy(false);
    }
  }

  async function handleSaveDecision() {
    if (!meeting || !decisionEdit) return;
    const text = decisionEdit.text.trim();
    if (!text) {
      setError("Karar boş olamaz");
      return;
    }
    setError(null);
    setAnalysisEditBusy(true);
    try {
      const updated = await updateMeetingDecision(meeting.meeting_id, decisionEdit.seq, text);
      setMeeting(updated);
      const next = updated.decisions.find((item) => item.seq === decisionEdit.seq) ?? null;
      if (decisionView?.seq === decisionEdit.seq) setDecisionView(next);
      setDecisionEdit(null);
      toast("Karar kaydedildi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Karar kaydedilemedi");
    } finally {
      setAnalysisEditBusy(false);
    }
  }

  async function handleDismissAction(item: ActionItem) {
    if (!meeting) return;
    const ok = await confirm({
      title: item.task_status ? "Görevi sil" : "Öneriyi sil",
      message: `“${item.description}” silinsin mi?`,
    });
    if (!ok) return;
    try {
      const updated = await dismissMeetingAction(meeting.meeting_id, item.seq);
      setMeeting(updated);
      setActionItems(updated.actions);
      if (selected?.seq === item.seq) setSelected(null);
      toast("Aksiyon başarıyla silindi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Aksiyon silinemedi");
    }
  }

  async function saveSelected() {
    if (!selected || !meeting) return;
    try {
      const assigned = await ensurePerson(selected.assignee_id, selected.assignee ?? "", actionNote);
      await updateMeetingAction(meeting.meeting_id, {
        seq: selected.seq,
        description: selected.description,
        assignee: assigned.assignee || null,
        assignee_id: assigned.assignee_id,
        speaker_label: actionSpeaker,
        notes: selected.notes,
        due_date: selected.due_date,
      });
      const updated = await fetchMeeting(meeting.meeting_id);
      setMeeting(updated);
      setActionItems(updated.actions.map((row) => ({ ...row })));
      setAttendeeNames(parseAttendeeList(updated.named_attendees ?? ""));
      setSelected(null);
      setActionNote("");
      setActionSpeaker(null);
      toast("Aksiyon başarıyla kaydedildi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Kaydedilemedi");
    }
  }

  if (loading && !meeting) {
    return (
      <AppShell title={fromUpload ? "Yazıya çevriliyor…" : "Toplantı"} crumb="Toplantı analizi">
        {fromUpload ? (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
            <WorkingIndicator elapsed={elapsed} />
          </div>
        ) : (
          <p className="text-slate-500">Yükleniyor…</p>
        )}
      </AppShell>
    );
  }

  if (!meeting) {
    return (
      <AppShell title="Toplantı" crumb="Toplantı analizi">
        <p className="text-slate-600">{error ?? "Toplantı bulunamadı."}</p>
        <Link href="/meetings" className="mt-3 inline-block text-sm font-medium text-teal-700">
          Listeye dön
        </Link>
      </AppShell>
    );
  }

  const lines = meeting.transcript.some((line) => line.speaker)
    ? meeting.transcript
    : splitTranscriptSentences(meeting.transcript);
  const usingOriginalLines = meeting.transcript.some((line) => line.speaker);
  const speakers = speakerStats(lines, meeting.duration, (name) => isPendingSpeaker(name, lines));
  const declaredAttendees = parseAttendeeList(meeting.named_attendees ?? "");
  const attendeeValue =
    displayAttendeeNames(declaredAttendees, speakers) ||
    (speakers.length ? speakers.map((item) => item.name).join(", ") : meeting.attendees);
  const pickerAttendees = uniqueNames([
    declaredAttendees,
    speakers.map((item) => stripGuessMark(item.name) || item.name),
  ]);
  function assignChoices(current: string): string[] {
    const currentKey = nameKey(stripGuessMark(current) || current);
    return declaredAttendees.filter((name) => nameKey(name) !== currentKey);
  }
  const matching = isMatchingSpeakers(meeting);
  const analysisPending = pendingAnalysisCopy(meeting, analysisBusy);
  const visibleLines = lines.filter((line) => {
    if (filterSpeaker && line.speaker !== filterSpeaker) return false;
    return lineMatchesQuery(line, transcriptQuery);
  });
  const searchActive = foldTr(transcriptQuery).trim().length > 0;
  const summary = meeting.summary;
  const decisionList = meeting.decisions;
  const decisionLines = decisionView ? linesForDecision(decisionView, lines) : [];
  let activeSeq: number | null = null;
  for (const line of lines) {
    if (line.timestamp <= currentTime + 0.12) activeSeq = line.seq;
    else break;
  }

  function seekTo(time: number) {
    setFollowAudio(true);
    const el = audioRef.current;
    if (!el || !audioUrl) {
      pendingSeekRef.current = time;
      return;
    }
    const apply = () => {
      el.currentTime = time;
      void el.play();
      setCurrentTime(time);
    };
    if (el.readyState >= 1) apply();
    else el.addEventListener("loadedmetadata", apply, { once: true });
  }

  function openDecision(item: Decision) {
    setDecisionView(item);
  }

  function jumpToTranscript(line: TranscriptLine) {
    setDecisionView(null);
    setFilterSpeaker(null);
    setTranscriptQuery("");
    setTab("transcript");
    setFocusSeq(line.seq);
    seekTo(line.timestamp);
  }

  function jumpToAskCite(seq: number, timestamp: number) {
    const line = lines.find((row) => row.seq === seq);
    if (line) {
      jumpToTranscript(line);
      return;
    }
    setDecisionView(null);
    setFilterSpeaker(null);
    setTranscriptQuery("");
    setTab("transcript");
    setFocusSeq(seq);
    seekTo(timestamp);
  }

  function openLineEdit(seq: number, current: string) {
    setBulkEdit(null);
    setLineEdit({ seq, current });
    setLineName(stripGuessMark(current) || current);
  }

  function openBulkEdit(name: string) {
    setLineEdit(null);
    setBulkEdit(name);
    setBulkName(stripGuessMark(name) || name);
  }

  return (
    <AppShell crumb="Toplantı analizi">
      <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
        <div className="px-6 py-5">
          {editing ? (
            <div className="space-y-4">
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="font-medium text-slate-700 dark:text-teal-200">Başlık</span>
                <input value={title} onChange={(e) => setTitle(e.target.value)} className={field} />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="font-medium text-slate-700 dark:text-teal-200">Tarih</span>
                <input
                  type="datetime-local"
                  max={nowDatetimeLocal()}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="font-medium text-slate-700 dark:text-teal-200">Katılımcılar</span>
                <AttendeeListEditor
                  names={attendeeNames}
                  onChange={setAttendeeNames}
                  hint="İsmi yazıp Onayla’ya basın. Transkript hazır olunca bu isimler konuşmacılara eşlenir."
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="font-medium text-slate-700 dark:text-teal-200">Açıklama</span>
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={saving}
                  onClick={handleSave}
                  className="h-10 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                >
                  {saving ? "Kaydediliyor…" : "Kaydet"}
                </button>
                <button
                  type="button"
                  onClick={revertEdit}
                  className="h-10 cursor-pointer rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-teal-900/40"
                >
                  Vazgeç
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <Link
                    href="/meetings"
                    className="text-xs font-medium text-teal-700 hover:underline dark:text-teal-300"
                  >
                    ← Toplantılar
                  </Link>
                  <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">
                    {meeting.title}
                  </h1>
                  <p className="mt-1 text-xs font-medium text-teal-700 dark:text-teal-300">
                    {(meeting.language || "").trim().toLowerCase() === "en" ? "English" : "Türkçe"}
                  </p>
                  {meeting.description ? (
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                      {meeting.description}
                    </p>
                  ) : null}
                </div>
                <div className="flex items-center gap-2 pt-1">
                  {meeting.status === "uploaded" || matching || analysisBusy ? (
                    <span
                      className="h-4 w-4 animate-spin rounded-full border-2 border-amber-200 border-t-amber-500"
                      aria-hidden
                    />
                  ) : null}
                  <MeetingBadge status={meeting.status} />
                </div>
              </div>
              <div className="mt-5 grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-3 dark:border-teal-900/40">
                <MetaStat label="Tarih" value={formatDay(meeting.date)} hint={formatClock(meeting.date) || undefined} />
                <MetaStat label="Süre" value={formatDuration(meeting.duration)} />
                <MetaStat label="Katılımcılar" value={<AttendeeChips value={attendeeValue} />} />
              </div>
              <div className="mt-5 flex flex-wrap items-center gap-2">
                {meeting.transcript.length > 0 || meeting.status === "analyzed" || meeting.status === "transcribed" ? (
                  <button
                    type="button"
                    disabled={analysisBusy || matching || meeting.status === "uploaded"}
                    onClick={() => void handleRetryAnalysis()}
                    className="h-9 cursor-pointer rounded-lg bg-teal-700 px-3.5 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
                  >
                    {matching
                      ? "Konuşmacılar eşleniyor…"
                      : analysisBusy
                        ? analysisProgressLabel(meeting, true) || "Analiz ediliyor…"
                        : meeting.summary
                          ? "Analizi yenile"
                          : "Analiz yap"}
                  </button>
                ) : null}
                {meeting.status === "analyzed" && !analysisBusy ? (
                  <button
                    type="button"
                    disabled={exporting}
                    onClick={() => setExportOpen(true)}
                    className="h-9 cursor-pointer rounded-lg border border-slate-200 bg-white px-3.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-slate-200 dark:hover:bg-teal-900/40"
                  >
                    Dışa aktar
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="h-9 cursor-pointer rounded-lg border border-slate-200 bg-white px-3.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-slate-200 dark:hover:bg-teal-900/40"
                >
                  Düzenle
                </button>
                <button
                  type="button"
                  disabled={deleting}
                  onClick={handleDelete}
                  className="ml-auto h-9 cursor-pointer rounded-lg px-3.5 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50 dark:hover:bg-rose-950/40"
                >
                  Sil
                </button>
              </div>
            </>
          )}
          {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}
        </div>

        <div className="border-t border-slate-100 px-4 py-3 dark:border-teal-900/40 sm:px-6">
          <div className="flex gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1 dark:bg-teal-950/70">
            {tabs.map((item) => {
              const active = tab === item.id;
              const count =
                item.id === "transcript"
                  ? lines.length
                  : analysisBusy
                    ? null
                    : item.id === "decisions"
                      ? decisionList.length
                      : item.id === "actions"
                        ? actionItems.length
                        : null;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    if (item.id !== "decisions") setDecisionView(null);
                    setTab(item.id);
                  }}
                  className={`flex shrink-0 cursor-pointer items-center rounded-lg px-3.5 py-2 text-sm font-medium transition ${
                    active
                      ? "bg-white text-slate-900 shadow-sm dark:bg-teal-700 dark:text-white"
                      : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-teal-100"
                  }`}
                >
                  {item.label}
                  {count != null ? (
                    <span
                      className={`ml-1.5 rounded-md px-1.5 py-0.5 text-[10px] font-semibold tabular-nums ${
                        active
                          ? "bg-teal-600 text-white dark:bg-teal-900/60"
                          : "bg-slate-200 text-slate-500 dark:bg-teal-900 dark:text-slate-400"
                      }`}
                    >
                      {count}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>

        <div className="p-6">
          {tab === "transcript" && (
            <div>
              {meeting.audio_path ? (
                <TranscriptAudioPlayer
                  src={audioUrl}
                  loading={audioLoading}
                  error={audioError}
                  audioRef={audioRef}
                  onTimeUpdate={setCurrentTime}
                />
              ) : null}
              {lines.length === 0 ? (
              meeting.status === "uploaded" ? (
                <WorkingIndicator elapsed={elapsed} />
              ) : meeting.status === "failed" ? (
                <div>
                  <p className="text-sm font-medium text-rose-600">Yazıya çevirme başarısız.</p>
                  {meeting.transcription?.error ? (
                    <p className="mt-1 text-sm text-rose-500">{meeting.transcription.error}</p>
                  ) : null}
                </div>
              ) : (
                <p className="text-sm text-slate-400">Transkript henüz yok.</p>
              )
            ) : (
              <div>
              <div className="relative mb-5">
                <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />
                  </svg>
                </span>
                <input
                  value={transcriptQuery}
                  onChange={(e) => setTranscriptQuery(e.target.value)}
                  placeholder="Mesaj metninde ara…"
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white pr-20 pl-9 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
                />
                {searchActive ? (
                  <button
                    type="button"
                    onClick={() => setTranscriptQuery("")}
                    className="absolute top-1/2 right-2 -translate-y-1/2 cursor-pointer rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-teal-900/50 dark:hover:text-teal-100"
                  >
                    Temizle
                  </button>
                ) : null}
              </div>
              <div className="flex flex-col gap-6 lg:flex-row">
                <div className="min-w-0 flex-1">
                  <p className="mb-4 text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">
                    {searchActive
                      ? `${visibleLines.length} eşleşme`
                      : filterSpeaker
                        ? `${filterSpeaker} · ${visibleLines.length} satır`
                        : "Zaman damgalı transkript"}
                  </p>
                  {filterSpeaker ? (
                    <button
                      type="button"
                      onClick={() => setFilterSpeaker(null)}
                      className="mb-4 cursor-pointer text-xs font-medium text-teal-700 hover:underline"
                    >
                      Tüm konuşmacıları göster
                    </button>
                  ) : null}
                  {visibleLines.length === 0 ? (
                    <p className="text-sm text-slate-400">Bu aramaya uyan satır yok.</p>
                  ) : (
                  <div
                    ref={transcriptBoxRef}
                    onWheel={() => {
                      if (followAudio) setFollowAudio(false);
                    }}
                    onTouchMove={() => {
                      if (followAudio) setFollowAudio(false);
                    }}
                    className="relative max-h-[calc(100dvh-18rem)] overflow-y-auto overscroll-contain rounded-xl border border-slate-200 dark:border-teal-800/50"
                  >
                  <ul className="divide-y divide-slate-100 px-2 dark:divide-teal-900/40">
                    {visibleLines.map((line) => {
                      const speaker = line.speaker;
                      const speakerNode = speaker ? (
                        <span onClick={(event) => event.stopPropagation()}>
                          <LineSpeaker
                            name={speaker}
                            seq={line.seq}
                            editing={lineEdit?.seq === line.seq}
                            value={lineName}
                            busy={speakerBusy}
                            pending={isGuessName(speaker)}
                            onOpen={openLineEdit}
                            onChange={setLineName}
                            onClose={() => setLineEdit(null)}
                            onRenameLine={() => handleRenameSpeaker({ speaker: lineName, seq: line.seq })}
                            onRenameAll={() =>
                              handleRenameSpeaker({ speaker: lineName, from_speaker: speaker })
                            }
                            assignNames={assignChoices(speaker)}
                            onAssign={(name) =>
                              handleRenameSpeaker({ speaker: name, from_speaker: speaker })
                            }
                            onConfirm={() => void handleSpeakerGuess(speaker, "confirm")}
                            onReject={() => void handleSpeakerGuess(speaker, "reject")}
                          />
                        </span>
                      ) : null;
                      const focused = focusSeq === line.seq;
                      const active = !focused && activeSeq === line.seq;
                      const editingText = textEdit?.seq === line.seq;
                      return (
                        <li
                          key={line.seq}
                          data-seq={line.seq}
                          ref={(el) => {
                            if (focused) focusRef.current = el;
                            if (activeSeq === line.seq) activeLineRef.current = el;
                          }}
                          className="first:pt-0 last:pb-0"
                        >
                          {editingText ? (
                            <div
                              className="rounded-xl bg-slate-50 px-2 py-4 dark:bg-teal-900/20"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <div className="text-xs text-slate-400">
                                <span className="font-medium text-teal-600">{formatTimestamp(line.timestamp)}</span>
                                {speakerNode ? <>{" · "}{speakerNode}</> : null}
                              </div>
                              <textarea
                                autoFocus
                                value={textEdit.value}
                                disabled={textBusy}
                                rows={3}
                                onChange={(e) => setTextEdit({ seq: line.seq, value: e.target.value })}
                                onKeyDown={(e) => {
                                  if (e.key === "Escape") setTextEdit(null);
                                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                                    e.preventDefault();
                                    void handleSaveLineText();
                                  }
                                }}
                                className="mt-2 w-full resize-y rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm leading-6 text-slate-800 outline-none focus:border-teal-600 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                              />
                              <div className="mt-2 flex gap-2">
                                <button
                                  type="button"
                                  disabled={textBusy || !textEdit.value.trim()}
                                  onClick={() => void handleSaveLineText()}
                                  className="h-7 cursor-pointer rounded-md bg-teal-700 px-2.5 text-[11px] font-medium text-white hover:bg-teal-800 disabled:opacity-50"
                                >
                                  Kaydet
                                </button>
                                <button
                                  type="button"
                                  disabled={textBusy}
                                  onClick={() => setTextEdit(null)}
                                  className="h-7 cursor-pointer rounded-md px-2.5 text-[11px] font-medium text-slate-500 hover:bg-slate-100 dark:hover:bg-teal-900/40"
                                >
                                  Vazgeç
                                </button>
                              </div>
                            </div>
                          ) : (
                          <div
                            role="button"
                            tabIndex={0}
                            onClick={() => {
                              setFocusSeq(null);
                              seekTo(line.timestamp);
                            }}
                            onKeyDown={(event) => {
                              if (isTypingTarget(event.target)) return;
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                seekTo(line.timestamp);
                              }
                            }}
                            className={`group w-full cursor-pointer rounded-xl px-2 py-4 text-left transition-colors ${
                              focused
                                ? "bg-teal-100 ring-2 ring-teal-600 dark:bg-teal-900/50 dark:ring-teal-400"
                                : active
                                  ? "bg-teal-50 dark:bg-teal-900/40"
                                  : "hover:bg-slate-50 dark:hover:bg-teal-900/20"
                            }`}
                          >
                            <div className="flex items-start gap-2 text-xs text-slate-400">
                              <div className="min-w-0 flex-1">
                                <span className={`font-medium ${active ? "text-teal-700 dark:text-teal-300" : "text-teal-600"}`}>
                                  {formatTimestamp(line.timestamp)}
                                </span>
                                {speakerNode ? <>{" · "}{speakerNode}</> : null}
                              </div>
                              {usingOriginalLines ? (
                                <button
                                  type="button"
                                  title="Metni düzelt"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setLineEdit(null);
                                    setTextEdit({ seq: line.seq, value: line.text });
                                  }}
                                  className="mt-0.5 inline-flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded text-slate-300 opacity-40 transition group-hover:opacity-100 hover:bg-slate-200/80 hover:text-slate-600 sm:opacity-0 sm:group-hover:opacity-100 dark:text-teal-800 dark:hover:bg-teal-900/60 dark:hover:text-teal-200 dark:group-hover:text-teal-600"
                                >
                                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L4.8 18.75l.55-3.885a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Z" />
                                  </svg>
                                </button>
                              ) : null}
                            </div>
                            <p className="mt-1 text-sm leading-6 text-slate-800 dark:text-slate-200">
                              <FlaggedLineText
                                line={line}
                                query={transcriptQuery}
                                busy={textBusy}
                                openIndex={flagOpen?.seq === line.seq ? flagOpen.index : null}
                                onToggle={(index) =>
                                  setFlagOpen(index == null ? null : { seq: line.seq, index })
                                }
                                onApply={(index) => void handleFlagApply(line, index)}
                                onDismiss={(index) => void handleFlagDismiss(line, index)}
                              />
                            </p>
                          </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                  {!followAudio && activeSeq != null ? (
                    <div className="sticky bottom-3 flex justify-center px-2 pb-2">
                      <button
                        type="button"
                        onClick={() => {
                          lastFollowedSeq.current = null;
                          setFollowAudio(true);
                        }}
                        className="cursor-pointer rounded-full bg-teal-700 px-3 py-1.5 text-xs font-semibold text-white shadow-lg hover:bg-teal-800"
                      >
                        Konuşulan satıra dön
                      </button>
                    </div>
                  ) : null}
                  </div>
                  )}
                </div>
                {speakers.length > 0 ? (
                  <aside className="relative z-10 lg:sticky lg:top-4 lg:max-h-[calc(100dvh-18rem)] lg:w-56 lg:shrink-0 lg:overflow-y-auto lg:border-l lg:border-slate-100 lg:pl-6 dark:lg:border-teal-800/50">
                    <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">
                      Konuşma payı
                    </p>
                    <ul className="space-y-2">
                      {speakers.map((item, index) => {
                        const editing = bulkEdit === item.name;
                        const active = filterSpeaker === item.name;
                        return (
                          <li key={item.name}>
                            {editing ? (
                              <div className="space-y-2 rounded-xl border border-teal-600 bg-teal-50 p-3 dark:bg-teal-900/50">
                                <input
                                  autoFocus
                                  value={bulkName}
                                  disabled={speakerBusy}
                                  onChange={(e) => setBulkName(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      void handleRenameSpeaker({
                                        speaker: bulkName,
                                        from_speaker: item.name,
                                      });
                                    }
                                    if (e.key === "Escape") setBulkEdit(null);
                                  }}
                                  placeholder="Yeni isim"
                                  className="h-9 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-sm font-medium text-slate-900 outline-none focus:border-teal-600 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                                />
                                {assignChoices(item.name).length ? (
                                  <div>
                                    <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                      Katılımcıya ata
                                    </p>
                                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                                      {assignChoices(item.name).map((name) => (
                                        <button
                                          key={name}
                                          type="button"
                                          disabled={speakerBusy}
                                          onClick={() =>
                                            void handleRenameSpeaker({
                                              speaker: name,
                                              from_speaker: item.name,
                                            })
                                          }
                                          className="h-7 max-w-full cursor-pointer truncate rounded-full border border-teal-200 bg-white px-2.5 text-xs font-medium text-teal-800 hover:bg-teal-100 disabled:opacity-50 dark:border-teal-800 dark:bg-teal-950/50 dark:text-teal-100 dark:hover:bg-teal-900/50"
                                        >
                                          {name}
                                        </button>
                                      ))}
                                    </div>
                                  </div>
                                ) : null}
                                <div className="flex gap-2">
                                  <button
                                    type="button"
                                    disabled={speakerBusy || !bulkName.trim()}
                                    onClick={() =>
                                      handleRenameSpeaker({
                                        speaker: bulkName,
                                        from_speaker: item.name,
                                      })
                                    }
                                    className="h-8 cursor-pointer rounded-lg bg-teal-700 px-2.5 text-xs font-medium text-white hover:bg-teal-800 disabled:opacity-50"
                                  >
                                    Kaydet
                                  </button>
                                  <button
                                    type="button"
                                    disabled={speakerBusy}
                                    onClick={() => setBulkEdit(null)}
                                    className="h-8 cursor-pointer rounded-lg px-2.5 text-xs font-medium text-slate-500 hover:bg-slate-50"
                                  >
                                    Vazgeç
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div
                                role="button"
                                tabIndex={0}
                                onClick={() =>
                                  setFilterSpeaker((current) => (current === item.name ? null : item.name))
                                }
                                onKeyDown={(event) => {
                                  if (isTypingTarget(event.target)) return;
                                  if (event.key === "Enter" || event.key === " ") {
                                    event.preventDefault();
                                    setFilterSpeaker((current) => (current === item.name ? null : item.name));
                                  }
                                }}
                                className={`w-full cursor-pointer rounded-xl border p-3 text-left transition-colors ${
                                  active
                                    ? "border-teal-600 bg-teal-50 dark:bg-teal-900/50"
                                    : "border-slate-200 hover:border-teal-400 hover:bg-slate-50 dark:border-teal-800 dark:hover:bg-teal-900/30"
                                }`}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <p className={`min-w-0 truncate text-sm font-semibold ${active ? "text-teal-800 dark:text-teal-200" : "text-slate-800 dark:text-slate-200"}`}>
                                    <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${talkColorClass(index)}`} />
                                    {item.name}
                                    {item.pending ? (
                                      <SpeakerGuessActions
                                        busy={speakerBusy}
                                        onConfirm={() => void handleSpeakerGuess(item.name, "confirm")}
                                        onReject={() => void handleSpeakerGuess(item.name, "reject")}
                                      />
                                    ) : null}
                                  </p>
                                  <p className="shrink-0 text-xs font-semibold tabular-nums text-teal-700 dark:text-teal-300">
                                    %{item.share}
                                  </p>
                                </div>
                                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-teal-950">
                                  <div
                                    className={`h-full rounded-full ${talkColorClass(index)}`}
                                    style={{ width: `${Math.min(100, item.share)}%` }}
                                  />
                                </div>
                                <p className="mt-1.5 text-xs text-slate-400">
                                  {formatDuration(item.seconds)} · {item.count} tur
                                </p>
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    openBulkEdit(item.name);
                                  }}
                                  className="mt-2 cursor-pointer text-xs font-medium text-slate-500 hover:text-teal-700"
                                >
                                  Adı değiştir
                                </button>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </aside>
                ) : null}
              </div>
              <TalkShareCard
                speakers={speakers}
                onPick={(name) => setFilterSpeaker(name)}
              />
              </div>
            )}
            </div>
          )}

          {tab === "summary" && (
            <>
              <div className="mb-4 flex items-center justify-between gap-3">
                <p className="text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">
                  Toplantı özeti
                </p>
                {summaryDraft == null && !analysisBusy ? (
                  <EditPencil onClick={() => setSummaryDraft(summary ?? "")} />
                ) : null}
              </div>
              {summaryDraft != null ? (
                <div className="space-y-3">
                  <textarea
                    autoFocus
                    rows={14}
                    value={summaryDraft}
                    onChange={(e) => setSummaryDraft(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-800 outline-none focus:border-teal-600 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={analysisEditBusy}
                      onClick={() => void handleSaveSummary()}
                      className="h-9 cursor-pointer rounded-lg bg-teal-700 px-3.5 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
                    >
                      {analysisEditBusy ? "Kaydediliyor…" : "Kaydet"}
                    </button>
                    <button
                      type="button"
                      disabled={analysisEditBusy}
                      onClick={() => setSummaryDraft(null)}
                      className="h-9 cursor-pointer rounded-lg px-3.5 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-teal-900/40"
                    >
                      Vazgeç
                    </button>
                  </div>
                </div>
              ) : analysisBusy ? (
                <p className="text-sm text-slate-400">{analysisPending}</p>
              ) : summary ? (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-5 dark:border-teal-800/50 dark:bg-teal-950/40">
                  <div className="space-y-4 text-sm leading-7 text-slate-800 dark:text-slate-200">
                    {summary
                      .split(/\n+/)
                      .map((para) => para.trim())
                      .filter(Boolean)
                      .map((para, index) => {
                        const heading = [
                          "çerçeve",
                          "gündem akışı",
                          "sonuç",
                          "context",
                          "agenda",
                          "outcome",
                        ].includes(para.toLocaleLowerCase("tr-TR"));
                        return heading ? (
                          <h3
                            key={index}
                            className="pt-5 text-[11px] font-semibold tracking-[0.16em] text-teal-800 uppercase first:pt-0 dark:text-teal-300"
                          >
                            {para}
                          </h3>
                        ) : (
                          <p key={index} className="text-sm leading-7">
                            {para}
                          </p>
                        );
                      })}
                  </div>
                </div>
              ) : meeting.status === "transcribed" && meeting.transcription?.error ? (
                <div>
                  <p className="text-sm text-rose-600">{meeting.transcription.error}</p>
                  <button
                    type="button"
                    onClick={() => void handleRetryAnalysis()}
                    className="mt-3 h-9 cursor-pointer rounded-lg bg-teal-700 px-3 text-sm font-medium text-white hover:bg-teal-800"
                  >
                    Tekrar dene
                  </button>
                </div>
              ) : (
                <p className="text-sm text-slate-400">
                  {meeting.status === "transcribed" || meeting.status === "uploaded" || analysisBusy
                    ? analysisPending
                    : "Özet henüz yok."}
                </p>
              )}
            </>
          )}

          {tab === "decisions" && decisionView && !analysisBusy ? (
            <>
              <button
                type="button"
                onClick={() => {
                  setDecisionEdit(null);
                  setDecisionView(null);
                }}
                className="cursor-pointer text-xs font-medium text-teal-700 hover:underline dark:text-teal-300"
              >
                ← Kararlar
              </button>
              <div className="mt-3 flex items-start justify-between gap-3">
                <p className="text-sm leading-6 text-slate-800 dark:text-teal-50">Karar</p>
                {decisionView.seq != null && decisionEdit?.seq !== decisionView.seq && !analysisBusy ? (
                  <EditPencil
                    onClick={() => setDecisionEdit({ seq: decisionView.seq as number, text: decisionView.text })}
                  />
                ) : null}
              </div>
              {decisionEdit && decisionEdit.seq === decisionView.seq ? (
                <div className="mt-2 space-y-3">
                  <textarea
                    autoFocus
                    rows={5}
                    value={decisionEdit.text}
                    onChange={(e) => setDecisionEdit({ ...decisionEdit, text: e.target.value })}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-800 outline-none focus:border-teal-600 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={analysisEditBusy}
                      onClick={() => void handleSaveDecision()}
                      className="h-9 cursor-pointer rounded-lg bg-teal-700 px-3.5 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
                    >
                      {analysisEditBusy ? "Kaydediliyor…" : "Kaydet"}
                    </button>
                    <button
                      type="button"
                      disabled={analysisEditBusy}
                      onClick={() => setDecisionEdit(null)}
                      className="h-9 cursor-pointer rounded-lg px-3.5 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-teal-900/40"
                    >
                      Vazgeç
                    </button>
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-sm leading-6 text-slate-800 dark:text-slate-200">{decisionView.text}</p>
              )}
              {(() => {
                const follow = followUpFor(decisionView, actionItems);
                return (
                  <div className="mt-4">
                    {follow ? (
                      <Link
                        href={`/tasks?task=${meeting.meeting_id}-${follow.seq}`}
                        className="inline-flex h-9 items-center rounded-lg bg-teal-700 px-3.5 text-sm font-medium text-white hover:bg-teal-800"
                      >
                        Görevi aç
                      </Link>
                    ) : (
                      <button
                        type="button"
                        onClick={() => startDecisionFollowUp(decisionView)}
                        className="h-9 cursor-pointer rounded-lg bg-teal-700 px-3.5 text-sm font-medium text-white hover:bg-teal-800"
                      >
                        Görev oluştur
                      </button>
                    )}
                  </div>
                );
              })()}
              <p className="mt-5 mb-4 text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">
                İlgili konuşma
                {formatDecisionSpan(decisionView) ? ` · ${formatDecisionSpan(decisionView)}` : ""}
              </p>
              {decisionLines.length === 0 ? (
                <p className="text-sm text-slate-400">Bu karara bağlanan transkript satırı yok.</p>
              ) : (
                <ul className="divide-y divide-slate-100 dark:divide-teal-900/40">
                  {decisionLines.map((line) => (
                    <li key={line.seq} className="first:pt-0 last:pb-0">
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => jumpToTranscript(line)}
                        onKeyDown={(event) => {
                          if (isTypingTarget(event.target)) return;
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            jumpToTranscript(line);
                          }
                        }}
                        className="w-full cursor-pointer rounded-xl px-2 py-4 text-left hover:bg-slate-50 dark:hover:bg-teal-900/20"
                      >
                        <div className="text-xs text-slate-400">
                          <span className="font-medium text-teal-600">{formatTimestamp(line.timestamp)}</span>
                          {line.speaker ? <>{" · "}{line.speaker}</> : null}
                        </div>
                        <p className="mt-1 text-sm leading-6 text-slate-800 dark:text-slate-200">{line.text}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : tab === "decisions" ? (
            <>
              <p className="mb-4 text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">Alınan kararlar</p>
              {analysisBusy || decisionList.length === 0 ? (
                <p className="text-sm text-slate-400">
                  {analysisBusy || meeting.status === "transcribed" || meeting.status === "uploaded"
                    ? analysisPending
                    : "Alınan karar yok."}
                </p>
              ) : (
                <ul className="space-y-3">
                  {decisionList.map((item, index) => {
                    const span = formatDecisionSpan(item);
                    const follow = followUpFor(item, actionItems);
                    const editing = item.seq != null && decisionEdit?.seq === item.seq;
                    return (
                    <li
                      key={item.seq ?? `${index}-${item.text}`}
                      role={editing ? undefined : "button"}
                      tabIndex={editing ? undefined : 0}
                      onClick={() => {
                        if (!editing) openDecision(item);
                      }}
                      onKeyDown={(e) => {
                        if (editing || isTypingTarget(e.target)) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openDecision(item);
                        }
                      }}
                      className={`flex gap-3 rounded-xl border px-4 py-3.5 ${
                        editing
                          ? "border-teal-600 bg-white dark:border-teal-500 dark:bg-[#0c1c1b]"
                          : "cursor-pointer border-slate-200 bg-slate-50 hover:border-teal-600 dark:border-teal-800/50 dark:bg-teal-950/40 dark:hover:border-teal-500"
                      }`}
                    >
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-semibold text-slate-600 dark:bg-teal-800 dark:text-teal-100">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        {editing ? (
                          <div className="space-y-3" onClick={(event) => event.stopPropagation()}>
                            <textarea
                              autoFocus
                              rows={4}
                              value={decisionEdit.text}
                              onChange={(e) => setDecisionEdit({ ...decisionEdit, text: e.target.value })}
                              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-800 outline-none focus:border-teal-600 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                            />
                            <div className="flex gap-2">
                              <button
                                type="button"
                                disabled={analysisEditBusy}
                                onClick={() => void handleSaveDecision()}
                                className="h-9 cursor-pointer rounded-lg bg-teal-700 px-3.5 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
                              >
                                {analysisEditBusy ? "Kaydediliyor…" : "Kaydet"}
                              </button>
                              <button
                                type="button"
                                disabled={analysisEditBusy}
                                onClick={() => setDecisionEdit(null)}
                                className="h-9 cursor-pointer rounded-lg px-3.5 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-teal-900/40"
                              >
                                Vazgeç
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-sm leading-6 text-slate-800 dark:text-slate-200">{item.text}</p>
                              {item.seq != null && !analysisBusy ? (
                                <EditPencil
                                  onClick={() => setDecisionEdit({ seq: item.seq as number, text: item.text })}
                                />
                              ) : null}
                            </div>
                            {span ? (
                              <p className="mt-2 text-xs font-medium text-teal-700 dark:text-teal-300">
                                İlgili konuşma · {span}
                              </p>
                            ) : null}
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                startDecisionFollowUp(item);
                              }}
                              className="mt-2 cursor-pointer text-xs font-medium text-teal-700 hover:text-teal-800 dark:text-teal-300"
                            >
                              {follow ? "Görevi aç" : "Görev oluştur"}
                            </button>
                          </>
                        )}
                      </div>
                    </li>
                    );
                  })}
                </ul>
              )}
            </>
          ) : null}

          <div className={tab === "ask" ? "" : "hidden"}>
            <MeetingAsk
              meetingId={meeting.meeting_id}
              hasTranscript={lines.length > 0}
              onJump={jumpToAskCite}
            />
          </div>

          {tab === "actions" && (
            <>
              <p className="mb-4 text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">
                Aksiyon maddeleri
              </p>
              {analysisBusy || actionItems.length === 0 ? (
                <p className="text-sm text-slate-400">
                  {analysisBusy || meeting.status === "transcribed" || meeting.status === "uploaded"
                    ? analysisPending
                    : "Aksiyon maddesi yok."}
                </p>
              ) : (
                <ul className="space-y-3">
                  {[...actionItems]
                    .sort((a, b) => {
                      const rank = (item: ActionItem) =>
                        item.task_status === "done" ? 2 : item.task_status === "in_progress" ? 1 : 0;
                      return rank(a) - rank(b);
                    })
                    .map((item) => {
                    const done = item.task_status === "done";
                    const tone = done ? "ok" : dueTone(item.due_date);
                    const extra = item.notes.trim() && item.notes.trim() !== item.description.trim();
                    return (
                    <li
                      key={item.seq}
                      role="button"
                      tabIndex={0}
                      onClick={() => openAction(item)}
                      onKeyDown={(e) => {
                        if (isTypingTarget(e.target)) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openAction(item);
                        }
                      }}
                      className={`flex cursor-pointer flex-col gap-3 rounded-xl border p-4 shadow-sm transition-shadow sm:flex-row sm:items-center sm:justify-between ${
                        done
                          ? "border-emerald-200 bg-emerald-50 hover:border-emerald-400 hover:shadow-[0_0_18px_rgba(16,185,129,0.45)] dark:border-emerald-800/50 dark:bg-emerald-950/40"
                          : !item.task_status
                            ? "border-teal-200 bg-teal-50 hover:border-teal-400 hover:shadow-[0_0_18px_rgba(13,148,136,0.5)] dark:border-teal-800/50 dark:bg-teal-950/40"
                            : tone === "overdue"
                              ? "border-rose-400 bg-rose-50 hover:border-rose-500 hover:shadow-[0_0_18px_rgba(244,63,94,0.45)] dark:border-rose-700 dark:bg-rose-950/50"
                              : tone === "soon"
                                ? "border-amber-200 bg-amber-50 hover:border-amber-400 hover:shadow-[0_0_18px_rgba(245,158,11,0.5)] dark:border-amber-800/50 dark:bg-amber-950/40"
                                : "border-sky-200 bg-sky-50 hover:border-sky-400 hover:shadow-[0_0_18px_rgba(14,165,233,0.5)] dark:border-sky-800/50 dark:bg-sky-950/40"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-slate-900 dark:text-teal-50">
                          {item.description}
                        </p>
                        {extra ? (
                          <p className="mt-1 line-clamp-2 text-sm text-slate-500">
                            {item.notes}
                          </p>
                        ) : null}
                        <p className="mt-2 text-xs text-slate-500">
                          Sorumlu: {item.assignee || "—"}
                        </p>
                        {item.task_status ? (
                          <DueHint dueDate={item.due_date} alert={item.task_status !== "done"} />
                        ) : null}
                      </div>
                      {item.task_status ? (
                        <div className="flex shrink-0 items-center gap-3">
                          <TaskBadge status={item.task_status} dueDate={item.due_date} />
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDismissAction(item);
                            }}
                            className="cursor-pointer text-sm font-medium text-rose-600 hover:text-rose-700"
                          >
                            Sil
                          </button>
                        </div>
                      ) : (
                        <div className="flex shrink-0 flex-col items-end gap-5">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDismissAction(item);
                            }}
                            className="cursor-pointer text-sm font-medium text-rose-600 hover:text-rose-700"
                          >
                            Sil
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openAction(item);
                            }}
                            className="cursor-pointer rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-800"
                          >
                            Görev oluştur
                          </button>
                        </div>
                      )}
                    </li>
                    );
                  })}
                </ul>
              )}
            </>
          )}
        </div>
      </div>

      <ExportMeetingDialog
        open={exportOpen}
        actions={actionItems}
        exporting={exporting}
        onClose={() => {
          if (!exporting) setExportOpen(false);
        }}
        onConfirm={(options) => {
          if (exporting) return;
          setExporting(true);
          void downloadMeetingReport(meeting, options)
            .then(() => {
              setExportOpen(false);
              toast(options.transcript === "attach" ? "Tutanak ve transkript indirildi" : "Dışa aktarıldı");
            })
            .catch(() => toast("Dışa aktarılamadı"))
            .finally(() => setExporting(false));
        }}
        onPreview={async (options) => {
          try {
            return await previewMeetingReport(meeting, options);
          } catch {
            toast("Önizleme açılamadı");
            throw new Error("preview failed");
          }
        }}
      />
      {selected && (
        <div className="fixed inset-0 z-20 flex justify-end bg-slate-950/30">
          <button type="button" className="h-full flex-1 cursor-pointer" aria-label="Kapat" onClick={() => setSelected(null)} />
          <aside className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-2xl dark:bg-[#0f2220] dark:text-teal-50">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-slate-400">Aksiyon detayı</p>
                <h2 className="mt-1 text-lg font-semibold text-slate-900 dark:text-teal-50">{selected.description}</h2>
              </div>
              <button type="button" onClick={() => setSelected(null)} className="cursor-pointer text-slate-400 hover:text-slate-700">
                ✕
              </button>
            </div>
            <div className="mt-6 space-y-4 text-sm">
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Başlık</span>
                <input
                  value={selected.description}
                  onChange={(e) => setSelected({ ...selected, description: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Sorumlu</span>
                <PersonPicker
                  attendeeNames={pickerAttendees}
                  people={meeting.people}
                  valueId={selected.assignee_id}
                  valueName={selected.assignee ?? ""}
                  onChange={(personId, name, note, speakerLabel) => {
                    setSelected({ ...selected, assignee_id: personId, assignee: name });
                    setActionNote(note ?? "");
                    setActionSpeaker(speakerLabel ?? null);
                  }}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Son tarih</span>
                <input
                  type="date"
                  required
                  min={
                    dateOnly(selected.due_date) && dateOnly(selected.due_date) < todayISO()
                      ? dateOnly(selected.due_date)
                      : todayISO()
                  }
                  value={dateOnly(selected.due_date) || todayISO()}
                  onChange={(e) => setSelected({ ...selected, due_date: e.target.value })}
                  className={field}
                />
                {selected.task_status ? (
                  <DueHint dueDate={selected.due_date} alert={selected.task_status !== "done"} />
                ) : null}
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Açıklama</span>
                <textarea
                  rows={4}
                  value={selected.notes}
                  onChange={(e) => setSelected({ ...selected, notes: e.target.value })}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                />
              </label>
            </div>
            <div className="mt-6 flex gap-3">
              {!selected.task_status ? (
                <button
                  type="button"
                  onClick={() => void handleCreateTask(selected, selected.due_date || todayISO())}
                  className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
                >
                  Görev oluştur
                </button>
              ) : null}
              <button
                type="button"
                onClick={saveSelected}
                className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
              >
                Kaydet
              </button>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-teal-900/40"
              >
                Kapat
              </button>
              <button
                type="button"
                onClick={() => handleDismissAction(selected)}
                className="ml-auto h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-rose-600 hover:bg-rose-50"
              >
                Sil
              </button>
            </div>
          </aside>
        </div>
      )}
      {decisionDraft && (
        <div className="fixed inset-0 z-20 flex justify-end bg-slate-950/30">
          <button
            type="button"
            className="h-full flex-1 cursor-pointer"
            aria-label="Kapat"
            onClick={() => {
              if (!decisionTaskSaving) setDecisionDraft(null);
            }}
          />
          <aside className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-2xl dark:bg-[#0f2220] dark:text-teal-50">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-slate-400">Karar takibi</p>
                <h2 className="mt-1 text-lg font-semibold text-slate-900 dark:text-teal-50">Görev oluştur</h2>
              </div>
              <button
                type="button"
                disabled={decisionTaskSaving}
                onClick={() => setDecisionDraft(null)}
                className="cursor-pointer text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">{decisionDraft.source.text}</p>
            <div className="mt-6 space-y-4 text-sm">
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Başlık</span>
                <input
                  value={decisionDraft.title}
                  onChange={(e) => setDecisionDraft({ ...decisionDraft, title: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Sorumlu</span>
                <PersonPicker
                  attendeeNames={pickerAttendees}
                  people={meeting.people}
                  valueId={decisionDraft.assignee_id}
                  valueName={decisionDraft.assignee}
                  onChange={(personId, name, note, speakerLabel) => {
                    setDecisionDraft({
                      ...decisionDraft,
                      assignee_id: personId,
                      assignee: name,
                      assigneeNote: note ?? "",
                      assigneeSpeaker: speakerLabel ?? null,
                    });
                  }}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Son tarih</span>
                <input
                  type="date"
                  required
                  min={todayISO()}
                  value={decisionDraft.due_date}
                  onChange={(e) => setDecisionDraft({ ...decisionDraft, due_date: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Açıklama</span>
                <textarea
                  rows={4}
                  value={decisionDraft.notes}
                  onChange={(e) => setDecisionDraft({ ...decisionDraft, notes: e.target.value })}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                />
              </label>
            </div>
            <div className="mt-6 flex gap-3">
              <button
                type="button"
                disabled={decisionTaskSaving}
                onClick={() => void handleCreateDecisionTask()}
                className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
              >
                {decisionTaskSaving ? "Oluşturuluyor…" : "Görev oluştur"}
              </button>
              <button
                type="button"
                disabled={decisionTaskSaving}
                onClick={() => setDecisionDraft(null)}
                className="h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-teal-900/40"
              >
                Vazgeç
              </button>
            </div>
          </aside>
        </div>
      )}
    </AppShell>
  );
}
