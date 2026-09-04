"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { askMeeting, type AskResult } from "@/lib/api";
import { formatTimestamp } from "@/lib/dates";
import { MarkdownBody } from "@/components/MarkdownBody";

type Turn = {
  question: string;
  result?: AskResult;
  error?: string;
};

function storageKey(meetingId: number): string {
  return `ai-scribe-ask:${meetingId}`;
}

function loadTurns(meetingId: number): Turn[] {
  try {
    const raw = sessionStorage.getItem(storageKey(meetingId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Turn[];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((turn) => Boolean(turn?.question && (turn.result || turn.error)));
  } catch {
    return [];
  }
}

function saveTurns(meetingId: number, turns: Turn[]): void {
  try {
    const keep = turns.filter((turn) => turn.result || turn.error);
    sessionStorage.setItem(storageKey(meetingId), JSON.stringify(keep));
  } catch {
    /* ignore quota / private mode */
  }
}

export function MeetingAsk({
  meetingId,
  hasTranscript,
  onJump,
}: {
  meetingId: number;
  hasTranscript: boolean;
  onJump: (seq: number, timestamp: number) => void;
}) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>(() => loadTurns(meetingId));
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTurns(loadTurns(meetingId));
    setQuestion("");
    setBusy(false);
  }, [meetingId]);

  useEffect(() => {
    saveTurns(meetingId, turns);
  }, [meetingId, turns]);

  useEffect(() => {
    const el = threadRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, busy]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy || !hasTranscript) return;
    setQuestion("");
    setBusy(true);
    setTurns((prev) => [...prev, { question: text }]);
    try {
      const result = await askMeeting(meetingId, text);
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = { question: text, result };
        return next;
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Yanıt alınamadı";
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = { question: text, error: message };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[min(32rem,calc(100vh-18rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-teal-800 dark:bg-[#0c1c1b]">
      <div ref={threadRef} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {turns.length === 0 && hasTranscript ? (
          <p className="pt-10 text-center text-sm text-slate-400 dark:text-slate-500">
            Toplantı hakkında bir soru sor.
          </p>
        ) : null}
        {!hasTranscript ? (
          <p className="pt-10 text-center text-sm text-slate-400">Transkript henüz yok.</p>
        ) : null}

        {turns.map((turn, index) => {
          const pending = busy && index === turns.length - 1 && !turn.result && !turn.error;
          return (
            <div key={`${index}-${turn.question}`} className="space-y-3">
              <div className="flex justify-end">
                <p className="max-w-[min(36rem,88%)] rounded-2xl rounded-br-md bg-teal-700 px-3.5 py-2.5 text-sm leading-6 break-words text-white">
                  {turn.question}
                </p>
              </div>

              {turn.error ? (
                <div className="flex justify-start">
                  <p className="max-w-[min(36rem,88%)] rounded-2xl rounded-bl-md border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm leading-6 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200">
                    {turn.error}
                  </p>
                </div>
              ) : null}

              {pending ? (
                <div className="flex justify-start">
                  <p className="rounded-2xl rounded-bl-md border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-400 dark:border-teal-800/50 dark:bg-teal-950/40 dark:text-slate-500">
                    …
                  </p>
                </div>
              ) : null}

              {turn.result ? (
                <div className="flex justify-start">
                  <div className="max-w-[min(40rem,92%)] rounded-2xl rounded-bl-md border border-slate-200 bg-slate-50 px-4 py-3 dark:border-teal-800/50 dark:bg-teal-950/50">
                    <MarkdownBody text={turn.result.answer} />
                    {turn.result.cites.length ? (
                      <ul className="mt-3 divide-y divide-slate-200/80 border-t border-slate-200/80 dark:divide-teal-900/50 dark:border-teal-900/50">
                        {turn.result.cites.map((cite, index) => (
                          <li key={`${cite.seq}-${index}`}>
                            <button
                              type="button"
                              onClick={() => onJump(cite.seq, cite.timestamp)}
                              className="w-full cursor-pointer px-0.5 py-2.5 text-left transition hover:bg-white/80 dark:hover:bg-teal-900/30"
                            >
                              <span className="text-[11px] font-medium tabular-nums text-teal-700 dark:text-teal-300">
                                {formatTimestamp(cite.timestamp)}
                                {cite.speaker ? ` · ${cite.speaker}` : ""}
                              </span>
                              <span className="mt-0.5 block text-[13px] leading-6 text-slate-600 dark:text-slate-300">
                                {cite.text}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <form
        onSubmit={(event) => void submit(event)}
        className="flex shrink-0 items-end gap-2 border-t border-slate-200 bg-slate-50 px-3 py-3 dark:border-teal-800 dark:bg-teal-950/40"
      >
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          disabled={!hasTranscript || busy}
          maxLength={2000}
          rows={1}
          placeholder="Soru"
          className="max-h-24 min-h-11 min-w-0 flex-1 resize-none overflow-y-auto rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm leading-5 text-slate-900 outline-none placeholder:text-slate-400 focus:border-teal-600 disabled:opacity-60 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:placeholder:text-slate-500 dark:focus:border-teal-500"
        />
        <button
          type="submit"
          disabled={!hasTranscript || busy || !question.trim()}
          className="h-11 shrink-0 cursor-pointer rounded-xl bg-teal-700 px-4 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-50"
        >
          Gönder
        </button>
      </form>
    </div>
  );
}
