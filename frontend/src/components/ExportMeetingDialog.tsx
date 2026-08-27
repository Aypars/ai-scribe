"use client";

import { useEffect, useState } from "react";

import type { ActionItem } from "@/lib/api";
import { FormatPicker } from "@/components/FormatPicker";
import type { ExportFormat } from "@/lib/export-office";
import type { MeetingExportOptions, TranscriptMode } from "@/lib/export-meeting";

type Props = {
  open: boolean;
  actions: ActionItem[];
  exporting: boolean;
  onClose: () => void;
  onConfirm: (options: MeetingExportOptions) => void;
};

const transcriptChoices: { id: TranscriptMode; title: string; hint: string }[] = [
  { id: "include", title: "Rapora dahil et", hint: "Transkript tutanağın içinde yer alır." },
  { id: "attach", title: "Ayrı ek", hint: "Transkript ayrı dosya olarak iner." },
  { id: "omit", title: "Transkript olmasın", hint: "Tutanağa transkript eklenmez." },
];

export function ExportMeetingDialog({ open, actions, exporting, onClose, onConfirm }: Props) {
  const [transcript, setTranscript] = useState<TranscriptMode>("include");
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const [selected, setSelected] = useState<number[]>([]);
  const [talkShare, setTalkShare] = useState(true);

  useEffect(() => {
    if (!open) return;
    setTranscript("include");
    setFormat("pdf");
    setTalkShare(true);
    setSelected(actions.map((item) => item.seq));
    // Snapshot at open; don't reset if the meeting poll refreshes the list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" || exporting) return;
      onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, exporting, onClose]);

  if (!open) return null;

  function toggleAction(seq: number) {
    setSelected((prev) => (prev.includes(seq) ? prev.filter((id) => id !== seq) : [...prev, seq]));
  }

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/55 p-4"
      onClick={() => {
        if (!exporting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-title"
        className="max-h-[min(92vh,720px)] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220]"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="export-title" className="text-lg font-semibold text-slate-900 dark:text-teal-50">
          Dışa aktar
        </h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Biçimi ve tutanağa nelerin gireceğini seç.</p>

        <h3 className="mt-5 text-xs font-semibold tracking-[0.14em] text-teal-700 uppercase dark:text-teal-300">
          Biçim
        </h3>
        <div className="mt-2">
          <FormatPicker name="meeting-export-format" value={format} onChange={setFormat} />
        </div>

        <h3 className="mt-5 text-xs font-semibold tracking-[0.14em] text-teal-700 uppercase dark:text-teal-300">
          Transkript
        </h3>
        <div className="mt-2 space-y-2">
          {transcriptChoices.map((choice) => {
            const active = transcript === choice.id;
            return (
              <label
                key={choice.id}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5 ${
                  active
                    ? "border-teal-600 bg-teal-50/80 dark:border-teal-500 dark:bg-teal-950/50"
                    : "border-slate-200 hover:bg-slate-50 dark:border-teal-800 dark:hover:bg-teal-950/40"
                }`}
              >
                <input
                  type="radio"
                  name="transcript-mode"
                  className="mt-1 accent-teal-700"
                  checked={active}
                  onChange={() => {
                    setTranscript(choice.id);
                    if (choice.id === "include") setTalkShare(true);
                    else setTalkShare(false);
                  }}
                />
                <span>
                  <span className="block text-sm font-medium text-slate-800 dark:text-teal-50">{choice.title}</span>
                  <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">{choice.hint}</span>
                </span>
              </label>
            );
          })}
        </div>

        {transcript === "include" ? (
          <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 px-3 py-2.5 hover:bg-slate-50 dark:border-teal-800 dark:hover:bg-teal-950/40">
            <input
              type="checkbox"
              className="mt-1 accent-teal-700"
              checked={talkShare}
              onChange={() => setTalkShare((prev) => !prev)}
            />
            <span>
              <span className="block text-sm font-medium text-slate-800 dark:text-teal-50">Konuşma payı eklensin</span>
              <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">
                Kim ne kadar konuştu, transkriptin hemen üstünde yer alır.
              </span>
            </span>
          </label>
        ) : null}

        <div className="mt-5 flex items-center justify-between gap-3">
          <h3 className="text-xs font-semibold tracking-[0.14em] text-teal-700 uppercase dark:text-teal-300">
            Aksiyonlar
          </h3>
          {actions.length ? (
            <button
              type="button"
              className="cursor-pointer text-xs font-medium text-teal-700 hover:underline dark:text-teal-300"
              onClick={() =>
                setSelected(selected.length === actions.length ? [] : actions.map((item) => item.seq))
              }
            >
              {selected.length === actions.length ? "Hiçbirini seçme" : "Tümünü seç"}
            </button>
          ) : null}
        </div>
        {actions.length ? (
          <div className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2 dark:border-teal-800">
            {actions.map((item, index) => {
              const checked = selected.includes(item.seq);
              return (
                <label
                  key={item.seq}
                  className="flex cursor-pointer items-start gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50 dark:hover:bg-teal-950/40"
                >
                  <input
                    type="checkbox"
                    className="mt-1 accent-teal-700"
                    checked={checked}
                    onChange={() => toggleAction(item.seq)}
                  />
                  <span className="text-sm leading-5 text-slate-700 dark:text-slate-200">
                    <span className="font-semibold text-teal-700 dark:text-teal-300">{index + 1}.</span> {item.description}
                  </span>
                </label>
              );
            })}
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-500">Aksiyon maddesi yok.</p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            disabled={exporting}
            onClick={onClose}
            className="h-11 cursor-pointer rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 dark:border-teal-800 dark:text-teal-100 dark:hover:bg-teal-950/60"
          >
            Vazgeç
          </button>
          <button
            type="button"
            disabled={exporting}
            onClick={() =>
              onConfirm({
                format,
                transcript,
                actionSeqs: selected,
                talkShare: transcript === "include" && talkShare,
              })
            }
            className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
          >
            {exporting ? "Hazırlanıyor…" : "Dışa aktar"}
          </button>
        </div>
      </div>
    </div>
  );
}
