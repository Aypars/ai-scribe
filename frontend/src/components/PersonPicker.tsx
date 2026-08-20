"use client";

import { useState } from "react";

const field =
  "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

export function splitAttendeeNames(value?: string | null): string[] {
  if (!value) return [];
  const seen = new Set<string>();
  const names: string[] = [];
  for (const part of value.split(/[,;]+/)) {
    const name = part.trim();
    const key = name.toLocaleLowerCase("tr");
    if (!name || seen.has(key)) continue;
    seen.add(key);
    names.push(name);
  }
  return names;
}

export function PersonPicker({
  attendeeNames = [],
  valueId,
  valueName,
  onChange,
}: {
  attendeeNames?: string[];
  valueId: number | null | undefined;
  valueName: string;
  onChange: (personId: number | null, name: string, note?: string) => void;
}) {
  const [mode, setMode] = useState<"pick" | "new">(valueId || valueName ? "pick" : "pick");
  const [newName, setNewName] = useState("");
  const [newNote, setNewNote] = useState("");

  const selectedName = (valueName || "").trim();
  const selectedKey = selectedName.toLocaleLowerCase("tr");
  const attendeeMatch = attendeeNames.find((name) => name.toLocaleLowerCase("tr") === selectedKey);
  const selectValue =
    mode === "new"
      ? "__new__"
      : attendeeMatch
        ? `__attendee__:${attendeeMatch}`
        : valueId != null
          ? `__person__:${valueId}`
          : "";

  return (
    <div className="flex flex-col gap-1.5">
      <select
        value={selectValue}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "__new__") {
            setMode("new");
            onChange(null, newName, newNote);
            return;
          }
          setMode("pick");
          if (!raw) {
            onChange(null, "");
            return;
          }
          if (raw.startsWith("__attendee__:")) {
            onChange(null, raw.slice("__attendee__:".length));
            return;
          }
          if (raw.startsWith("__person__:")) {
            onChange(Number(raw.slice("__person__:".length)), selectedName);
          }
        }}
        className={`${field} cursor-pointer`}
      >
        <option value="">Sorumlu yok</option>
        {valueId != null && selectedName && !attendeeMatch ? (
          <option value={`__person__:${valueId}`}>{selectedName}</option>
        ) : null}
        {attendeeNames.length > 0 ? (
          <optgroup label="Katılımcılar">
            {attendeeNames.map((name) => (
              <option key={name} value={`__attendee__:${name}`}>
                {name}
              </option>
            ))}
          </optgroup>
        ) : null}
        <option value="__new__">+ Yeni kişi</option>
      </select>
      {mode === "new" ? (
        <div className="grid grid-cols-2 gap-2">
          <input
            value={newName}
            onChange={(e) => {
              setNewName(e.target.value);
              onChange(null, e.target.value, newNote);
            }}
            placeholder="Ad"
            className={field}
          />
          <input
            value={newNote}
            onChange={(e) => {
              setNewNote(e.target.value);
              onChange(null, newName, e.target.value);
            }}
            placeholder="örn. Satış (isteğe bağlı)"
            className={field}
          />
        </div>
      ) : null}
    </div>
  );
}
