"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { useConfirm } from "@/components/ConfirmDialog";
import { DueAlertLine, DueHint, TaskBadge } from "@/components/StatusBadge";
import { fetchMeetings, fetchPeople, fetchTasks, createPerson, createTask, updatePerson, deletePerson, type Meeting, type Person, type Task } from "@/lib/api";
import { SelectWrap } from "@/components/FilterSelect";
import { byDueDate, countDueAlerts, dateOnly, dueRemainingLabel, dueTone, formatDay, todayISO } from "@/lib/demo-data";
import { ExportFormatDialog } from "@/components/FormatPicker";
import { downloadPeopleRoster, downloadPersonReport } from "@/lib/export-lists";
import type { ExportFormat } from "@/lib/export-office";
import { useToast } from "@/components/Toast";

const field =
  "h-11 w-full min-w-0 max-w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function taskSurface(task: Task): string {
  if (task.status === "done") {
    return "border-zinc-300 bg-zinc-100 hover:border-zinc-400 hover:shadow-[0_0_18px_rgba(63,63,70,0.35)] dark:border-zinc-700/60 dark:bg-zinc-950/40";
  }
  const tone = dueTone(task.due_date);
  if (tone === "overdue") {
    return "border-rose-400 bg-rose-50 hover:border-rose-500 hover:shadow-[0_0_18px_rgba(244,63,94,0.45)] dark:border-rose-700 dark:bg-rose-950/50";
  }
  if (tone === "soon") {
    return "border-amber-300 bg-amber-50 hover:border-amber-400 hover:shadow-[0_0_18px_rgba(245,158,11,0.5)] dark:border-amber-700/70 dark:bg-amber-950/40";
  }
  return "border-sky-200 bg-sky-50 hover:border-sky-400 hover:shadow-[0_0_18px_rgba(14,165,233,0.5)] dark:border-sky-800/50 dark:bg-sky-950/40";
}

type PersonMeeting = { meeting_id: number; title: string; date: string | null };

type PersonStats = Person & {
  tasks: Task[];
  open: Task[];
  done: Task[];
  rate: number;
  alerts: { overdue: number; soon: number };
  nextDue: string | null;
  meetings: PersonMeeting[];
};

function nextDueOf(open: Task[]): string | null {
  const dated = open.filter((task) => dateOnly(task.due_date)).sort(byDueDate);
  return dated[0] ? dateOnly(dated[0].due_date) : null;
}

function meetingsOf(person: Person, assigned: Task[], catalog: Meeting[]): PersonMeeting[] {
  const seen = new Map<number, PersonMeeting>();
  for (const meeting of person.meetings ?? []) {
    seen.set(meeting.meeting_id, {
      meeting_id: meeting.meeting_id,
      title: meeting.title,
      date: meeting.date ?? null,
    });
  }
  for (const task of assigned) {
    if (seen.has(task.meeting_id)) continue;
    const meeting = catalog.find((row) => row.meeting_id === task.meeting_id);
    seen.set(task.meeting_id, {
      meeting_id: task.meeting_id,
      title: meeting?.title || task.meeting_title,
      date: meeting?.date ?? null,
    });
  }
  return [...seen.values()].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
}

function dueLineClass(iso: string): string {
  const tone = dueTone(iso);
  if (tone === "overdue") return "text-rose-600 dark:text-rose-300";
  if (tone === "soon") return "text-amber-700 dark:text-amber-300";
  return "text-slate-600 dark:text-teal-200";
}

export default function PeoplePage() {
  const toast = useToast();
  const confirm = useConfirm();
  const [people, setPeople] = useState<Person[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PersonStats | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftNote, setDraftNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createNote, setCreateNote] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [taskSaving, setTaskSaving] = useState(false);
  const [taskDraft, setTaskDraft] = useState({
    meeting_id: 0,
    title: "",
    due_date: "",
    description: "",
  });
  const [exporting, setExporting] = useState(false);
  const [exportingPerson, setExportingPerson] = useState(false);
  const [exportTarget, setExportTarget] = useState<"roster" | "person" | null>(null);

  useEffect(() => {
    Promise.all([fetchPeople(), fetchTasks(), fetchMeetings()])
      .then(([personList, taskList, meetingList]) => {
        setPeople(personList);
        setTasks(taskList);
        setMeetings(meetingList);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Liste alınamadı"))
      .finally(() => setLoading(false));
  }, []);

  const rows = useMemo<PersonStats[]>(() => {
    return people.map((person) => {
      const assigned = tasks.filter((task) => task.assignee_id === person.person_id);
      const open = assigned.filter((task) => task.status !== "done");
      const done = assigned.filter((task) => task.status === "done");
      const rate = assigned.length ? Math.round((done.length / assigned.length) * 100) : 0;
      return {
        ...person,
        tasks: assigned,
        open,
        done,
        rate,
        alerts: countDueAlerts(open),
        nextDue: nextDueOf(open),
        meetings: meetingsOf(person, assigned, meetings),
      };
    });
  }, [people, tasks, meetings]);

  useEffect(() => {
    if (!selected) return;
    const next = rows.find((row) => row.person_id === selected.person_id);
    if (next) setSelected(next);
  }, [rows, selected?.person_id]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? rows.filter(
          (row) =>
            row.name.toLowerCase().includes(q) ||
            (row.note ?? "").toLowerCase().includes(q) ||
            row.label.toLowerCase().includes(q),
        )
      : rows;
    return [...list].sort((a, b) => {
      if (b.open.length !== a.open.length) return b.open.length - a.open.length;
      if (b.tasks.length !== a.tasks.length) return b.tasks.length - a.tasks.length;
      return a.name.localeCompare(b.name, "tr");
    });
  }, [rows, query]);

  const totals = useMemo(() => {
    const assigned = tasks.filter((task) => task.assignee_id != null);
    const open = assigned.filter((task) => task.status !== "done");
    const done = assigned.filter((task) => task.status === "done");
    const rate = assigned.length ? Math.round((done.length / assigned.length) * 100) : 0;
    return {
      people: people.length,
      open: open.length,
      done: done.length,
      total: assigned.length,
      rate,
      alerts: countDueAlerts(open),
    };
  }, [people, tasks]);

  function openPerson(row: PersonStats) {
    setSelected(row);
    setSelectedTask(null);
    setDraftName(row.name);
    setDraftNote(row.note ?? "");
  }

  function closePerson() {
    setSelected(null);
    setSelectedTask(null);
    setAssigning(false);
  }

  function openAssign() {
    if (!selected) return;
    const preferred = selected.meetings[0]?.meeting_id || meetings[0]?.meeting_id || 0;
    setTaskDraft({
      meeting_id: preferred,
      title: "",
      due_date: todayISO(),
      description: "",
    });
    setAssigning(true);
  }

  async function assignTask() {
    if (!selected) return;
    if (!taskDraft.meeting_id || !taskDraft.title.trim()) {
      toast("Toplantı ve görev adı gerekli");
      return;
    }
    if (!taskDraft.due_date) {
      toast("Teslim tarihi gerekli");
      return;
    }
    if (taskDraft.due_date < todayISO()) {
      toast("Teslim tarihi geçmiş olamaz");
      return;
    }
    setTaskSaving(true);
    try {
      const created = await createTask({
        meeting_id: taskDraft.meeting_id,
        title: taskDraft.title.trim(),
        assignee: selected.name,
        assignee_id: selected.person_id,
        due_date: taskDraft.due_date,
        description: taskDraft.description.trim(),
      });
      setTasks((prev) => [created, ...prev]);
      setAssigning(false);
      toast("Görev oluşturuldu");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Görev oluşturulamadı");
    } finally {
      setTaskSaving(false);
    }
  }

  async function savePerson() {
    if (!selected) return;
    const name = draftName.trim();
    if (!name) {
      toast("İsim gerekli");
      return;
    }
    setSaving(true);
    try {
      const next = await updatePerson(selected.person_id, {
        name,
        note: draftNote.trim() || null,
      });
      setPeople((prev) => prev.map((person) => (person.person_id === next.person_id ? next : person)));
      setSelected((prev) => (prev && prev.person_id === next.person_id ? { ...prev, ...next } : prev));
      toast("Kişi güncellendi");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  }

  async function removePerson() {
    if (!selected) return;
    const ok = await confirm({
      message: `“${selected.name}” silinsin mi? Görevler kalır, atama kalkar.`,
    });
    if (!ok) return;
    setDeleting(true);
    try {
      const personId = selected.person_id;
      await deletePerson(personId);
      setPeople((prev) => prev.filter((person) => person.person_id !== personId));
      setTasks((prev) =>
        prev.map((task) => (task.assignee_id === personId ? { ...task, assignee_id: null } : task)),
      );
      closePerson();
      toast("Kişi silindi");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Silinemedi");
    } finally {
      setDeleting(false);
    }
  }

  async function addPerson() {
    const name = createName.trim();
    if (!name) {
      toast("İsim gerekli");
      return;
    }
    setSaving(true);
    try {
      const created = await createPerson({ name, note: createNote.trim() || undefined });
      setPeople((prev) => [...prev, created]);
      setCreating(false);
      setCreateName("");
      setCreateNote("");
      toast("Kişi eklendi");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Eklenemedi");
    } finally {
      setSaving(false);
    }
  }

  async function exportRoster(format: ExportFormat) {
    if (exporting) return;
    setExporting(true);
    try {
      await downloadPeopleRoster(
        filtered.map((row) => ({
          name: row.name,
          note: row.note,
          open: row.open,
        })),
        format,
      );
      setExportTarget(null);
      toast("Dışa aktarıldı");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Dışa aktarılamadı");
    } finally {
      setExporting(false);
    }
  }

  async function exportSelectedPerson(format: ExportFormat) {
    if (!selected || exportingPerson) return;
    setExportingPerson(true);
    try {
      await downloadPersonReport({
        name: selected.name,
        note: selected.note,
        open: selected.open,
        done: selected.done,
        meetings: selected.meetings,
      }, format);
      setExportTarget(null);
      toast("Dışa aktarıldı");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Dışa aktarılamadı");
    } finally {
      setExportingPerson(false);
    }
  }

  const selectedTasks = selected ? [...selected.open, ...selected.done] : [];

  return (
    <AppShell
      title="Kişiler"
      action={
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={loading || exporting}
            onClick={() => setExportTarget("roster")}
            className="h-10 cursor-pointer rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-slate-200 dark:hover:bg-teal-900/40"
          >
            {exporting ? "Hazırlanıyor…" : "Dışa aktar"}
          </button>
          <button
            type="button"
            onClick={() => {
              setCreateName("");
              setCreateNote("");
              setCreating(true);
            }}
            className="h-10 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
          >
            + Kişi
          </button>
        </div>
      }
    >
      {error ? <p className="mb-4 text-sm text-rose-600">{error}</p> : null}

      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <article className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
          <div className="flex items-start justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">Kişi</p>
            <span className="rounded-lg bg-teal-50 p-1.5 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 7.5a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5a7.5 7.5 0 0 1 15 0" />
              </svg>
            </span>
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">
            {loading ? "—" : totals.people}
          </p>
          <p className="mt-1 text-xs text-slate-400">Kayıtlı kişiler</p>
        </article>
        <article
          className={`rounded-2xl border p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${
            totals.alerts.overdue > 0
              ? "border-rose-300 bg-rose-50 dark:border-rose-800/70 dark:bg-rose-950/40"
              : totals.alerts.soon > 0
                ? "border-amber-300 bg-amber-50 dark:border-amber-800/70 dark:bg-amber-950/40"
                : "border-slate-200/80 bg-white dark:border-teal-800/40 dark:bg-[#0f2220]"
          }`}
        >
          <div className="flex items-start justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">Açık görev</p>
            <span
              className={`rounded-lg p-1.5 ${
                totals.alerts.overdue > 0
                  ? "bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200"
                  : totals.alerts.soon > 0
                    ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200"
                    : "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300"
              }`}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6M7 4h10a2 2 0 0 1 2 2v14l-7-3-7 3V6a2 2 0 0 1 2-2Z" />
              </svg>
            </span>
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">
            {loading ? "—" : `${totals.open}/${totals.total}`}
          </p>
          {loading ? (
            <p className="mt-1 text-xs text-slate-400">Atanmış açık işler</p>
          ) : totals.alerts.overdue > 0 || totals.alerts.soon > 0 ? (
            <DueAlertLine overdue={totals.alerts.overdue} soon={totals.alerts.soon} className="mt-1.5 text-xs" />
          ) : (
            <p className="mt-1 text-xs text-slate-400">Atanmış açık işler</p>
          )}
        </article>
        <article className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
          <div className="flex items-start justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">Tamamlanan</p>
            <span className="rounded-lg bg-emerald-50 p-1.5 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
            </span>
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">
            {loading ? "—" : `${totals.done}/${totals.total}`}
          </p>
          <p className="mt-1 text-xs text-slate-400">{loading ? "Bitmiş görevler" : `%${totals.rate} tamamlanma`}</p>
        </article>
      </div>

      <div className="relative mb-5">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />
          </svg>
        </span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="İsim veya not ara…"
          className="h-10 w-full rounded-lg border border-slate-200 bg-white pr-3 pl-9 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
        />
      </div>

      {loading ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Yükleniyor…</p>
      ) : filtered.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500 dark:border-teal-800 dark:bg-[#0f2220] dark:text-slate-400">
          {people.length === 0
            ? "Henüz kişi yok. Kişi ekleyebilir veya görev atayabilirsin."
            : "Aramaya uyan kişi yok."}
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((row) => (
            <button
              key={row.person_id}
              type="button"
              onClick={() => openPerson(row)}
              className={`cursor-pointer rounded-2xl border p-5 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:border-teal-400 dark:hover:border-teal-500 ${
                row.alerts.overdue > 0
                  ? "border-rose-200 bg-white dark:border-rose-900/60 dark:bg-[#0f2220]"
                  : "border-slate-200/80 bg-white dark:border-teal-800/40 dark:bg-[#0f2220]"
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-teal-700 text-sm font-semibold text-teal-50">
                  {initials(row.name) || "?"}
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-base font-semibold text-slate-900 dark:text-teal-50">{row.name}</h2>
                  {row.note?.trim() ? (
                    <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">{row.note.trim()}</p>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 flex items-end justify-between gap-3">
                <div>
                  <p className="text-2xl font-semibold tabular-nums text-slate-900 dark:text-teal-50">%{row.rate}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {row.done.length}/{row.tasks.length || 0} tamamlandı
                  </p>
                </div>
                <p className="text-xs font-medium text-slate-600 dark:text-teal-200">
                  {row.open.length} açık
                </p>
              </div>

              <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-teal-950">
                <div
                  className="h-full rounded-full bg-teal-600"
                  style={{ width: `${row.rate}%` }}
                />
              </div>
              {row.nextDue ? (
                <p className={`mt-2 text-xs font-medium ${dueLineClass(row.nextDue)}`}>
                  Sıradaki: {formatDay(row.nextDue)}
                  {dueRemainingLabel(row.nextDue) ? ` · ${dueRemainingLabel(row.nextDue)}` : ""}
                </p>
              ) : null}
              <DueAlertLine overdue={row.alerts.overdue} soon={row.alerts.soon} className="mt-1" />
            </button>
          ))}
        </div>
      )}

      {selected ? (
        <div
          className="fixed inset-0 z-20 flex items-center justify-center bg-slate-950/40 p-4"
          onClick={closePerson}
        >
          <div
            className="max-h-[90vh] w-full min-w-0 max-w-2xl overflow-x-hidden overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220] dark:text-teal-50"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-6 flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-teal-700 text-sm font-semibold text-teal-50">
                  {initials(selected.name) || "?"}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-slate-400">Kişi detayı</p>
                  <h2 className="mt-1 break-words text-lg font-semibold text-slate-900 dark:text-teal-50">
                    {selected.name}
                  </h2>
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    %{selected.rate} tamamlandı · {selected.open.length} açık · {selected.done.length} bitti
                  </p>
                  {selected.nextDue ? (
                    <p className={`mt-1 text-sm font-medium ${dueLineClass(selected.nextDue)}`}>
                      Sıradaki: {formatDay(selected.nextDue)}
                      {dueRemainingLabel(selected.nextDue) ? ` · ${dueRemainingLabel(selected.nextDue)}` : ""}
                    </p>
                  ) : null}
                  <DueAlertLine overdue={selected.alerts.overdue} soon={selected.alerts.soon} className="mt-1" />
                </div>
              </div>
              <button
                type="button"
                onClick={closePerson}
                className="cursor-pointer text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">İsim</span>
                <input value={draftName} onChange={(e) => setDraftName(e.target.value)} className={field} />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Not</span>
                <input
                  value={draftNote}
                  onChange={(e) => setDraftNote(e.target.value)}
                  placeholder="Ünvan, ekip…"
                  className={field}
                />
              </label>
              <div className="flex flex-wrap justify-end gap-3">
                <button
                  type="button"
                  disabled={exportingPerson}
                  onClick={() => setExportTarget("person")}
                  className="h-11 cursor-pointer rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-slate-200 dark:hover:bg-teal-900/40"
                >
                  {exportingPerson ? "Hazırlanıyor…" : "Dışa aktar"}
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={savePerson}
                  className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                >
                  {saving ? "Kaydediliyor…" : "Kaydet"}
                </button>
                <button
                  type="button"
                  disabled={deleting}
                  onClick={() => void removePerson()}
                  className="h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50 dark:hover:bg-rose-950/40"
                >
                  {deleting ? "Siliniyor…" : "Sil"}
                </button>
              </div>
            </div>

            {selected.meetings.length > 0 ? (
              <div className="mt-8">
                <h3 className="text-sm font-semibold text-slate-800 dark:text-teal-50">Toplantılar</h3>
                <ul className="mt-3 space-y-2">
                  {selected.meetings.map((meeting) => (
                    <li key={meeting.meeting_id}>
                      <Link
                        href={`/meetings/${meeting.meeting_id}`}
                        className="block rounded-xl border border-slate-200 px-3 py-2 hover:border-teal-400 dark:border-teal-800 dark:hover:border-teal-500"
                      >
                        <p className="truncate text-sm font-medium text-slate-800 dark:text-teal-50">{meeting.title}</p>
                        {meeting.date ? (
                          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{formatDay(meeting.date)}</p>
                        ) : null}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="mt-8">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-800 dark:text-teal-50">Görevler</h3>
                <Link
                  href={`/tasks?person=${selected.person_id}&layout=board`}
                  className="text-sm font-medium text-teal-700 hover:text-teal-800 dark:text-teal-300"
                >
                  Görevlerde göster
                </Link>
              </div>
              {selectedTasks.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Bu kişiye atanmış görev yok.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {selectedTasks.map((task) => {
                    const done = task.status === "done";
                    return (
                      <li key={`${task.meeting_id}-${task.action_seq}`}>
                        <button
                          type="button"
                          onClick={() => setSelectedTask(task)}
                          className={`w-full cursor-pointer rounded-xl border p-4 text-left shadow-sm transition-shadow ${taskSurface(task)}`}
                        >
                          <p
                            className={`break-words text-base font-semibold text-slate-900 dark:text-teal-50 ${done ? "line-through" : ""}`}
                          >
                            {task.title}
                          </p>
                          <p className="mt-2 truncate text-xs font-medium text-slate-500" title={`Toplantı: ${task.meeting_title}`}>
                            Toplantı: {task.meeting_title}
                          </p>
                          <DueHint dueDate={dateOnly(task.due_date) || task.due_date} alert={!done} />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              <button
                type="button"
                onClick={openAssign}
                className="mt-4 h-11 w-full cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
              >
                Bu kişiye görev ver
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {selectedTask ? (
        <div
          className="fixed inset-0 z-30 flex items-center justify-center bg-slate-950/40 p-4"
          onClick={() => setSelectedTask(null)}
        >
          <div
            className="max-h-[90vh] w-full min-w-0 max-w-xl overflow-x-hidden overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220] dark:text-teal-50"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs text-slate-400">Görev detayı</p>
                <h2 className="mt-1 break-words text-lg font-semibold text-slate-900 dark:text-teal-50">
                  {selectedTask.title}
                </h2>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <TaskBadge status={selectedTask.status} dueDate={selectedTask.due_date} />
                <button
                  type="button"
                  onClick={() => setSelectedTask(null)}
                  className="cursor-pointer text-slate-400 hover:text-slate-700"
                >
                  ✕
                </button>
              </div>
            </div>

            <div className="mt-5 space-y-4 text-sm">
              <div>
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Toplantı</p>
                <Link
                  href={`/meetings/${selectedTask.meeting_id}`}
                  className="mt-1 block break-words font-medium text-teal-700 hover:text-teal-800 dark:text-teal-300"
                >
                  {selectedTask.meeting_title}
                </Link>
              </div>
              <div>
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Sorumlu</p>
                <p className="mt-1 font-medium text-slate-800 dark:text-teal-50">
                  {selectedTask.assignee?.trim() || selected?.name || "Sorumlu yok"}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Teslim tarihi</p>
                <DueHint dueDate={dateOnly(selectedTask.due_date) || selectedTask.due_date} alert={selectedTask.status !== "done"} />
              </div>
              {selectedTask.description?.trim() ? (
                <div>
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Açıklama</p>
                  <p className="mt-1 whitespace-pre-wrap break-words text-slate-800 dark:text-teal-100">
                    {selectedTask.description}
                  </p>
                </div>
              ) : null}
            </div>

            <div className="mt-6 flex justify-end">
              <Link
                href={`/tasks?person=${selected?.person_id ?? ""}&task=${selectedTask.meeting_id}-${selectedTask.action_seq}`}
                className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
              >
                Düzenle
              </Link>
            </div>
          </div>
        </div>
      ) : null}

      {creating ? (
        <div
          className="fixed inset-0 z-30 flex items-center justify-center bg-slate-950/40 p-4"
          onClick={() => {
            if (!saving) setCreating(false);
          }}
        >
          <div
            className="w-full min-w-0 max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220] dark:text-teal-50"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-base font-semibold text-slate-900 dark:text-teal-50">Yeni kişi</h2>
              <button
                type="button"
                onClick={() => setCreating(false)}
                className="cursor-pointer text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <form
              className="mt-4 space-y-4 text-sm"
              onSubmit={(e) => {
                e.preventDefault();
                void addPerson();
              }}
            >
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">İsim</span>
                <input
                  autoFocus
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  className={field}
                  placeholder="örn. Ayşe Yılmaz"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Not</span>
                <input
                  value={createNote}
                  onChange={(e) => setCreateNote(e.target.value)}
                  className={field}
                  placeholder="Ünvan, ekip…"
                />
              </label>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setCreating(false)}
                  className="h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-teal-900/40"
                >
                  Vazgeç
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                >
                  {saving ? "Ekleniyor…" : "Ekle"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {assigning && selected ? (
        <div
          className="fixed inset-0 z-30 flex items-center justify-center bg-slate-950/40 p-4"
          onClick={() => {
            if (!taskSaving) setAssigning(false);
          }}
        >
          <div
            className="max-h-[90vh] w-full min-w-0 max-w-xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220] dark:text-teal-50"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs text-slate-400">Yeni görev</p>
                <h2 className="mt-1 text-base font-semibold text-slate-900 dark:text-teal-50">
                  {selected.name}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setAssigning(false)}
                className="cursor-pointer text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <form
              className="mt-4 space-y-4 text-sm"
              onSubmit={(e) => {
                e.preventDefault();
                void assignTask();
              }}
            >
              <label className="flex min-w-0 flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Toplantı</span>
                <SelectWrap>
                <select
                  value={taskDraft.meeting_id}
                  onChange={(e) => setTaskDraft({ ...taskDraft, meeting_id: Number(e.target.value) })}
                  className={`${field} cursor-pointer appearance-none truncate pr-9`}
                >
                  {meetings.length === 0 ? <option value={0}>Önce toplantı ekleyin</option> : null}
                  {meetings.map((meeting) => (
                    <option key={meeting.meeting_id} value={meeting.meeting_id}>
                      {meeting.title}
                    </option>
                  ))}
                </select>
                </SelectWrap>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Görev adı</span>
                <input
                  autoFocus
                  value={taskDraft.title}
                  onChange={(e) => setTaskDraft({ ...taskDraft, title: e.target.value })}
                  className={field}
                />
              </label>
              <div>
                <p className="font-medium text-slate-700 dark:text-teal-100">Sorumlu</p>
                <p className="mt-1.5 text-sm font-semibold text-slate-800 dark:text-teal-50">{selected.name}</p>
              </div>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Son tarih</span>
                <input
                  type="date"
                  required
                  min={todayISO()}
                  value={taskDraft.due_date}
                  onChange={(e) => setTaskDraft({ ...taskDraft, due_date: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-100">Açıklama</span>
                <textarea
                  rows={3}
                  value={taskDraft.description}
                  onChange={(e) => setTaskDraft({ ...taskDraft, description: e.target.value })}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                />
              </label>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setAssigning(false)}
                  className="h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-teal-900/40"
                >
                  Vazgeç
                </button>
                <button
                  type="submit"
                  disabled={taskSaving}
                  className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                >
                  {taskSaving ? "Oluşturuluyor…" : "Oluştur"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
      <ExportFormatDialog
        open={exportTarget !== null}
        exporting={exporting || exportingPerson}
        onClose={() => {
          if (!exporting && !exportingPerson) setExportTarget(null);
        }}
        onConfirm={(format) => {
          if (exportTarget === "person") void exportSelectedPerson(format);
          else void exportRoster(format);
        }}
      />
    </AppShell>
  );
}
