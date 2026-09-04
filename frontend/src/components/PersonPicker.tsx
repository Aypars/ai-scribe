"use client";

import { useEffect, useMemo, useState } from "react";

import { fetchPeople, type Person } from "@/lib/api";
import { SelectWrap } from "@/components/FilterSelect";

const field =
  "h-11 w-full min-w-0 max-w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

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
  people = [],
  valueId,
  valueName,
  onChange,
}: {
  attendeeNames?: string[];
  people?: Person[];
  valueId: number | null | undefined;
  valueName: string;
  onChange: (personId: number | null, name: string, note?: string, speakerLabel?: string | null) => void;
}) {
  const [mode, setMode] = useState<"pick" | "new" | "search">("pick");
  const [fromAttendee, setFromAttendee] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newNote, setNewNote] = useState("");
  const [search, setSearch] = useState("");
  const [directory, setDirectory] = useState<Person[]>(people);
  const [loadingPeople, setLoadingPeople] = useState(false);

  useEffect(() => {
    if (people.length) setDirectory(people);
  }, [people]);

  const selectedName = (valueName || "").trim();
  const selectedPerson = directory.find((row) => row.person_id === valueId);
  const selectedLabel = selectedPerson?.label || selectedName;
  const namedValue = !valueId && selectedName ? "__named__" : "";
  const selectValue =
    mode === "search"
      ? "__search__"
      : mode === "new"
        ? fromAttendee
          ? `__attendee__:${fromAttendee}`
          : "__new__"
        : valueId != null
          ? `__person__:${valueId}`
          : namedValue;

  const searchMatches = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("tr");
    if (needle.length < 1) return [];
    return directory
      .filter((row) =>
        [row.name, row.note ?? "", row.label].join(" ").toLocaleLowerCase("tr").includes(needle),
      )
      .slice(0, 8);
  }, [directory, search]);

  const linkSuggestions = useMemo(() => {
    if (mode !== "new") return [];
    const needle = newName.trim().toLocaleLowerCase("tr");
    if (needle.length < 2) return [];
    return directory
      .filter((row) => {
        const name = row.name.toLocaleLowerCase("tr");
        const label = row.label.toLocaleLowerCase("tr");
        return name === needle || name.startsWith(needle) || label.includes(needle);
      })
      .slice(0, 3);
  }, [directory, mode, newName]);

  async function ensureDirectory() {
    if (directory.length || loadingPeople) return;
    setLoadingPeople(true);
    try {
      setDirectory(await fetchPeople());
    } catch {
      setDirectory([]);
    } finally {
      setLoadingPeople(false);
    }
  }

  function openNew(name = "") {
    setMode("new");
    setFromAttendee(name || null);
    setNewName(name);
    setNewNote("");
    onChange(null, name, "", name || null);
    void ensureDirectory();
  }

  function linkPerson(person: Person) {
    const bind = fromAttendee;
    setMode("pick");
    setFromAttendee(null);
    setNewName("");
    setNewNote("");
    onChange(person.person_id, person.name, undefined, bind);
  }

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="grid min-w-0 w-full">
      <SelectWrap>
      <select
        value={selectValue}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "__new__") {
            openNew("");
            return;
          }
          if (raw === "__search__") {
            setMode("search");
            setFromAttendee(null);
            setSearch("");
            void ensureDirectory();
            return;
          }
          if (!raw) {
            setMode("pick");
            setFromAttendee(null);
            onChange(null, "");
            return;
          }
          if (raw === "__named__") {
            setMode("pick");
            onChange(null, selectedName);
            return;
          }
          if (raw.startsWith("__attendee__:")) {
            openNew(raw.slice("__attendee__:".length));
            return;
          }
          if (raw.startsWith("__person__:")) {
            const personId = Number(raw.slice("__person__:".length));
            const person = directory.find((row) => row.person_id === personId);
            setMode("pick");
            setFromAttendee(null);
            onChange(personId, person?.name || selectedName);
          }
        }}
        className={`${field} cursor-pointer appearance-none pr-9`}
      >
        <option value="">Sorumlu yok</option>
        {valueId != null && selectedLabel ? (
          <option value={`__person__:${valueId}`}>{selectedLabel}</option>
        ) : selectedName ? (
          <option value="__named__">{selectedName}</option>
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
        <option value="__search__">Mevcut kişi ara…</option>
        <option value="__new__">+ Yeni kişi</option>
      </select>
      </SelectWrap>
      </div>
      {mode === "search" ? (
        <div className="space-y-1.5">
          <input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Kişi adı yaz…"
            className={field}
          />
          {loadingPeople ? (
            <p className="text-xs text-slate-400">Kişiler yükleniyor…</p>
          ) : search.trim() ? (
            searchMatches.length > 0 ? (
              <ul className="overflow-hidden rounded-lg border border-slate-200 dark:border-teal-800">
                {searchMatches.map((person) => (
                  <li key={person.person_id}>
                    <button
                      type="button"
                      onClick={() => linkPerson(person)}
                      className="block w-full cursor-pointer truncate px-3 py-2 text-left text-sm text-slate-800 hover:bg-slate-50 dark:text-teal-50 dark:hover:bg-teal-900/40"
                    >
                      {person.label}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-400">Eşleşen kişi yok. Yeni kişi oluşturabilirsin.</p>
            )
          ) : (
            <p className="text-xs text-slate-400">Ad yazınca eşleşen mevcut kişiler çıkar.</p>
          )}
        </div>
      ) : null}
      {mode === "new" ? (
        <div className="space-y-1.5">
          <div className="grid grid-cols-1 gap-2">
            <input
              autoFocus={!fromAttendee}
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value);
                onChange(null, e.target.value, newNote, fromAttendee);
              }}
              placeholder="Ad"
              className={field}
            />
            <input
              value={newNote}
              onChange={(e) => {
                setNewNote(e.target.value);
                onChange(null, newName, e.target.value, fromAttendee);
              }}
              placeholder="örn. Satış (isteğe bağlı)"
              className={field}
            />
          </div>
          {linkSuggestions.length > 0 ? (
            <div className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 dark:border-teal-800/70 dark:bg-teal-950/40">
              <p className="text-[11px] font-medium text-teal-800 dark:text-teal-200">
                Bu isimde kayıtlı kişi var
              </p>
              <div className="mt-1.5 flex flex-col gap-1">
                {linkSuggestions.map((person) => (
                  <button
                    key={person.person_id}
                    type="button"
                    onClick={() => linkPerson(person)}
                    className="cursor-pointer rounded-md px-2 py-1.5 text-left text-sm font-medium text-teal-800 hover:bg-teal-100 dark:text-teal-100 dark:hover:bg-teal-900/50"
                  >
                    {person.label} olarak seç
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
