"use client";

import { useState } from "react";

const field =
  "h-11 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

export function parseAttendeeList(raw: string | null | undefined): string[] {
  return (raw ?? "")
    .split(/[,;\n]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function joinAttendeeList(names: string[]): string {
  return names.map((name) => name.trim()).filter(Boolean).join(", ");
}

export function AttendeeListEditor({
  names,
  onChange,
  hint,
}: {
  names: string[];
  onChange: (names: string[]) => void;
  hint?: string;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const name = draft.trim();
    if (!name) return;
    const key = name.toLocaleLowerCase("tr-TR");
    if (names.some((item) => item.toLocaleLowerCase("tr-TR") === key)) {
      setDraft("");
      return;
    }
    onChange([...names, name]);
    setDraft("");
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          className={field}
          placeholder="Örn. Ali Yılmaz"
        />
        <button
          type="button"
          onClick={add}
          disabled={!draft.trim()}
          className="h-11 shrink-0 cursor-pointer rounded-lg bg-teal-700 px-3 text-sm font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Onayla
        </button>
      </div>
      {names.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {names.map((name) => (
            <li
              key={name}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 py-0.5 pr-1 pl-2.5 text-xs font-medium text-slate-700 dark:bg-teal-900/55 dark:text-teal-100"
            >
              {name}
              <button
                type="button"
                onClick={() => onChange(names.filter((item) => item !== name))}
                className="inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded-full text-slate-500 hover:bg-slate-200 hover:text-slate-800 dark:hover:bg-teal-800 dark:hover:text-teal-50"
                aria-label={`${name} sil`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-slate-400">Henüz katılımcı eklenmedi.</p>
      )}
      {hint ? <p className="text-xs text-slate-400">{hint}</p> : null}
    </div>
  );
}
