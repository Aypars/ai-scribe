"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { DueHint, TaskBadge, DueAlertLine } from "@/components/StatusBadge";
import {
  createTask,
  deleteTask,
  dismissMeetingAction,
  ensurePerson,
  fetchMeetings,
  fetchTaskBoard,
  updateMeetingAction,
  updateTask,
  type Meeting,
  type Person,
  type SuggestedAction,
  type Task,
  type TaskStatus,
} from "@/lib/api";
import { FilterSelect, MeetingIcon, PersonIcon, SelectWrap } from "@/components/FilterSelect";
import { PersonPicker, splitAttendeeNames } from "@/components/PersonPicker";
import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";
import { byDueDate, countDueAlerts, dateOnly, dueTone, todayISO } from "@/lib/demo-data";

const columns: { id: TaskStatus; title: string; titleClass: string; check: string }[] = [
  {
    id: "in_progress",
    title: "Devam ediyor",
    titleClass: "text-sky-600 dark:text-sky-400",
    check:
      "border-sky-500 text-sky-700 hover:scale-110 hover:bg-sky-500 hover:text-white hover:shadow-[0_0_12px_rgba(14,165,233,0.75)] dark:text-sky-300 dark:hover:bg-sky-400 dark:hover:text-sky-950",
  },
  {
    id: "done",
    title: "Tamamlandı",
    titleClass: "text-zinc-700 dark:text-zinc-300",
    check:
      "border-zinc-500 bg-zinc-500 text-white hover:scale-110 hover:bg-zinc-400 hover:shadow-[0_0_12px_rgba(63,63,70,0.55)]",
  },
];

const field =
  "h-11 w-full min-w-0 max-w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

function AssigneeLine({ name }: { name?: string | null }) {
  const value = (name || "").trim();
  return (
    <p className="mt-1.5 text-sm font-semibold text-slate-700 dark:text-teal-100">
      {value ? `Sorumlu: ${value}` : "Sorumlu yok"}
    </p>
  );
}

export default function TasksPage() {
  const toast = useToast();
  const confirm = useConfirm();
  const [items, setItems] = useState<Task[]>([]);
  const [suggestions, setSuggestions] = useState<SuggestedAction[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selected, setSelected] = useState<Task | null>(null);
  const [selectedSuggestion, setSelectedSuggestion] = useState<SuggestedAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [people, setPeople] = useState<Person[]>([]);
  const [personFilter, setPersonFilter] = useState<number | "all">("all");
  const [draft, setDraft] = useState({
    meeting_id: 0,
    title: "",
    assignee: "",
    assignee_id: null as number | null,
    assigneeNote: "",
    due_date: "",
    description: "",
  });
  const [query, setQuery] = useState("");
  const [meetingFilter, setMeetingFilter] = useState<number | "all">("all");
  const [convertDue, setConvertDue] = useState("");
  const [convertNote, setConvertNote] = useState("");
  const [selectedNote, setSelectedNote] = useState("");
  const [boardView, setBoardView] = useState<"suggestions" | TaskStatus>("suggestions");
  const [boardLayout, setBoardLayout] = useState<"focus" | "board">("focus");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = Number(params.get("person"));
    if (Number.isInteger(id) && id > 0) setPersonFilter(id);
    if (params.get("layout") === "board") setBoardLayout("board");
    const view = params.get("view");
    if (view === "in_progress" || view === "done" || view === "suggestions") {
      setBoardView(view);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchTaskBoard(), fetchMeetings()])
      .then(([board, meetingList]) => {
        setItems(board.items);
        setSuggestions(board.suggestions);
        setPeople(board.people);
        setMeetings(meetingList);
        if (meetingList[0]) {
          setDraft((prev) => ({ ...prev, meeting_id: meetingList[0].meeting_id }));
        }
        const params = new URLSearchParams(window.location.search);
        const taskKey = params.get("task");
        const match = taskKey?.match(/^(\d+)-(\d+)$/);
        if (!match) return;
        const meetingId = Number(match[1]);
        const actionSeq = Number(match[2]);
        const found = board.items.find(
          (item) => item.meeting_id === meetingId && item.action_seq === actionSeq,
        );
        if (!found) return;
        setSelected({ ...found, due_date: dateOnly(found.due_date) || found.due_date });
        setSelectedNote("");
        setBoardView(found.status);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Görevler alınamadı"));
  }, []);

  function meetingName(task: { meeting_id: number; meeting_title?: string }): string {
    return task.meeting_title || meetings.find((m) => m.meeting_id === task.meeting_id)?.title || "Toplantı";
  }

  function attendeesFor(meetingId: number): string[] {
    return splitAttendeeNames(meetings.find((row) => row.meeting_id === meetingId)?.attendees);
  }

  function rememberPerson(personId: number | null, name: string) {
    if (!personId || !name) return;
    setPeople((prev) =>
      prev.some((row) => row.person_id === personId)
        ? prev
        : [...prev, { person_id: personId, name, label: name, note: null }],
    );
  }

  function matchesFilter(item: {
    meeting_id: number;
    meeting_title?: string;
    title: string;
    assignee: string | null;
    assignee_id?: number | null;
  }): boolean {
    if (meetingFilter !== "all" && item.meeting_id !== meetingFilter) return false;
    if (personFilter !== "all" && item.assignee_id !== personFilter) return false;
    const needle = query.trim().toLocaleLowerCase("tr");
    if (!needle) return true;
    const meeting = meetings.find((row) => row.meeting_id === item.meeting_id);
    const hay = [
      meetingName(item),
      item.title,
      item.assignee ?? "",
      meeting?.attendees ?? "",
    ]
      .join(" ")
      .toLocaleLowerCase("tr");
    return hay.includes(needle);
  }

  const visibleSuggestions = useMemo(
    () => suggestions.filter((item) => matchesFilter(item)),
    [suggestions, meetingFilter, personFilter, query, meetings],
  );

  const grouped = useMemo(() => {
    const visible = items.filter((item) => matchesFilter(item)).sort(byDueDate);
    return {
      in_progress: visible.filter((t) => t.status === "in_progress"),
      done: visible.filter((t) => t.status === "done"),
    };
  }, [items, meetingFilter, personFilter, query, meetings]);

  const progressAlerts = useMemo(() => countDueAlerts(grouped.in_progress), [grouped]);

  function replaceTask(next: Task) {
    setItems((prev) =>
      prev.map((item) =>
        item.meeting_id === next.meeting_id && item.action_seq === next.action_seq ? next : item,
      ),
    );
    setSelected((current) =>
      current && current.meeting_id === next.meeting_id && current.action_seq === next.action_seq
        ? next
        : current,
    );
  }

  async function toggleDone(task: Task) {
    try {
      const next = await updateTask(task.meeting_id, task.action_seq, {
        status: task.status === "done" ? "in_progress" : "done",
      });
      replaceTask(next);
      toast(task.status === "done" ? "Görev başarıyla devam ediyor olarak işaretlendi" : "Görev başarıyla tamamlandı");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Güncellenemedi");
    }
  }

  async function saveSelected() {
    if (!selected) return;
    const due = dateOnly(selected.due_date);
    if (!due) {
      setError("Teslim tarihi gerekli");
      return;
    }
    const previousDue = dateOnly(
      items.find(
        (item) => item.meeting_id === selected.meeting_id && item.action_seq === selected.action_seq,
      )?.due_date,
    );
    if (due < todayISO() && due !== previousDue) {
      setError("Teslim tarihi geçmiş olamaz");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const assigned = await ensurePerson(selected.assignee_id, selected.assignee ?? "", selectedNote);
      const next = await updateTask(selected.meeting_id, selected.action_seq, {
        title: selected.title,
        status: selected.status,
        assignee: assigned.assignee || null,
        assignee_id: assigned.assignee_id,
        due_date: due,
        description: selected.description,
      });
      replaceTask(next);
      rememberPerson(next.assignee_id, next.assignee ?? "");
      setSelected(null);
      toast("Görev başarıyla kaydedildi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(task: Task) {
    const ok = await confirm({
      message: `“${task.title}” silinsin mi? Bu işlem geri alınamaz.`,
    });
    if (!ok) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteTask(task.meeting_id, task.action_seq);
      setItems((prev) =>
        prev.filter((item) => !(item.meeting_id === task.meeting_id && item.action_seq === task.action_seq)),
      );
      setSelected(null);
      toast("Görev başarıyla silindi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Silinemedi");
    } finally {
      setDeleting(false);
    }
  }

  async function handleCreate() {
    if (!draft.meeting_id || !draft.title.trim()) {
      setError("Toplantı ve görev adı gerekli");
      return;
    }
    if (!draft.due_date) {
      setError("Teslim tarihi gerekli");
      return;
    }
    if (draft.due_date < todayISO()) {
      setError("Teslim tarihi geçmiş olamaz");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const assigned = await ensurePerson(draft.assignee_id, draft.assignee, draft.assigneeNote);
      const created = await createTask({
        ...draft,
        assignee: assigned.assignee,
        assignee_id: assigned.assignee_id,
      });
      setItems((prev) => [created, ...prev]);
      setCreating(false);
      setBoardView("in_progress");
      setDraft((prev) => ({
        ...prev,
        title: "",
        assignee: "",
        assignee_id: null,
        assigneeNote: "",
        due_date: "",
        description: "",
      }));
      rememberPerson(created.assignee_id, created.assignee ?? "");
      toast("Görev başarıyla oluşturuldu");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Görev oluşturulamadı");
    } finally {
      setSaving(false);
    }
  }

  async function promoteSuggestion(item: SuggestedAction, dueDate: string) {
    const due = dateOnly(dueDate);
    if (!due) {
      setError("Görev oluşturmak için teslim tarihi gerekli");
      return;
    }
    if (due < todayISO()) {
      setError("Teslim tarihi geçmiş olamaz");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const assigned = await ensurePerson(item.assignee_id, item.assignee ?? "", convertNote);
      await updateMeetingAction(item.meeting_id, {
        seq: item.action_seq,
        description: item.title.trim() || item.description,
        assignee: assigned.assignee || null,
        assignee_id: assigned.assignee_id,
        notes: item.description,
      });
      const created = await createTask({
        meeting_id: item.meeting_id,
        title: item.title.trim() || item.description || "Görev",
        assignee: assigned.assignee,
        assignee_id: assigned.assignee_id,
        due_date: due,
        description: item.description,
        action_seq: item.action_seq,
      });
      setSuggestions((prev) =>
        prev.filter((row) => !(row.meeting_id === item.meeting_id && row.action_seq === item.action_seq)),
      );
      setItems((prev) => [created, ...prev]);
      setSelectedSuggestion(null);
      setBoardView("in_progress");
      rememberPerson(created.assignee_id, created.assignee ?? "");
      toast("Görev başarıyla oluşturuldu");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Görev oluşturulamadı");
    } finally {
      setSaving(false);
    }
  }

  async function saveSuggestion() {
    if (!selectedSuggestion) return;
    setSaving(true);
    setError(null);
    try {
      const name = (selectedSuggestion.assignee ?? "").trim() || null;
      await updateMeetingAction(selectedSuggestion.meeting_id, {
        seq: selectedSuggestion.action_seq,
        description: selectedSuggestion.title.trim() || selectedSuggestion.description,
        assignee: name,
        assignee_id: null,
        notes: selectedSuggestion.description,
      });
      setSuggestions((prev) =>
        prev.map((row) =>
          row.meeting_id === selectedSuggestion.meeting_id && row.action_seq === selectedSuggestion.action_seq
            ? { ...selectedSuggestion, assignee: name, assignee_id: null }
            : row,
        ),
      );
      setSelectedSuggestion(null);
      toast("Öneri başarıyla kaydedildi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  }

  async function dismissSuggestion(item: SuggestedAction) {
    const ok = await confirm({
      title: "Öneriyi sil",
      message: `“${item.title}” önerilerden silinsin mi?`,
    });
    if (!ok) return;
    try {
      await dismissMeetingAction(item.meeting_id, item.action_seq);
      setSuggestions((prev) =>
        prev.filter((row) => !(row.meeting_id === item.meeting_id && row.action_seq === item.action_seq)),
      );
      setSelectedSuggestion(null);
      toast("Öneri başarıyla silindi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Silinemedi");
    }
  }

  const filterActive = meetingFilter !== "all" || personFilter !== "all" || query.trim().length > 0;

  return (
    <AppShell
      title="Görev panosu"
      action={
        <button
          type="button"
          onClick={() => {
            setCreating(true);
          }}
          className="h-10 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
        >
          + Görev
        </button>
      }
    >
      {error ? <p className="mb-4 text-sm text-rose-600">{error}</p> : null}
      <div className="mb-5 flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white p-4 sm:flex-row sm:items-center dark:border-teal-800/40 dark:bg-[#0f2220]">
        <div className="relative min-w-0 flex-1">
          <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />
            </svg>
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Toplantı, görev veya katılımcı ara…"
            className="h-10 w-full rounded-lg border border-slate-200 bg-white pr-3 pl-9 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
          />
        </div>
        <FilterSelect
          icon={<MeetingIcon />}
          active={meetingFilter !== "all"}
          value={meetingFilter === "all" ? "all" : String(meetingFilter)}
          onChange={(e) => {
            const value = e.target.value;
            setMeetingFilter(value === "all" ? "all" : Number(value));
          }}
          className="w-full sm:w-64 sm:shrink-0"
        >
          <option value="all">Tüm toplantılar</option>
          {meetings.map((meeting) => (
            <option key={meeting.meeting_id} value={meeting.meeting_id}>
              {meeting.title}
            </option>
          ))}
        </FilterSelect>
        <FilterSelect
          icon={<PersonIcon />}
          active={personFilter !== "all"}
          value={personFilter === "all" ? "all" : String(personFilter)}
          onChange={(e) => {
            const value = e.target.value;
            setPersonFilter(value === "all" ? "all" : Number(value));
          }}
          className="w-full sm:w-56 sm:shrink-0"
        >
          <option value="all">Tüm kişiler</option>
          {people.map((person) => (
            <option key={person.person_id} value={person.person_id}>
              {person.label}
            </option>
          ))}
        </FilterSelect>
        <div className="flex h-10 shrink-0 rounded-xl bg-slate-100 p-1 dark:bg-teal-950/70">
          <button
            type="button"
            onClick={() => setBoardLayout("focus")}
            className={`cursor-pointer rounded-lg px-3 text-sm font-medium transition ${
              boardLayout === "focus"
                ? "bg-white text-slate-900 shadow-sm dark:bg-teal-700 dark:text-white"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-teal-100"
            }`}
          >
            Odak
          </button>
          <button
            type="button"
            onClick={() => setBoardLayout("board")}
            className={`cursor-pointer rounded-lg px-3 text-sm font-medium transition ${
              boardLayout === "board"
                ? "bg-white text-slate-900 shadow-sm dark:bg-teal-700 dark:text-white"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-teal-100"
            }`}
          >
            Pano
          </button>
        </div>
        {filterActive ? (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setMeetingFilter("all");
              setPersonFilter("all");
            }}
            className="h-10 shrink-0 cursor-pointer rounded-lg px-3 text-sm font-medium text-slate-500 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-teal-900/40"
          >
            Temizle
          </button>
        ) : null}
      </div>
      <div className={boardLayout === "board" ? "grid gap-5 lg:grid-cols-3" : "flex flex-col gap-4 lg:flex-row lg:items-start"}>
        {boardLayout === "focus" ? (
        <aside className="grid grid-cols-3 gap-2 lg:w-56 lg:shrink-0 lg:grid-cols-1">
          {(
            [
              {
                id: "suggestions" as const,
                title: "Öneriler",
                count: visibleSuggestions.length,
                idle: "text-teal-700 dark:text-teal-300",
                active: "bg-teal-50 text-teal-800 ring-1 ring-teal-400 dark:bg-teal-950/70 dark:text-teal-100 dark:ring-teal-500",
                badge: "bg-teal-600 text-white",
              },
              {
                id: "in_progress" as const,
                title: "Devam ediyor",
                count: grouped.in_progress.length,
                idle: "text-sky-700 dark:text-sky-300",
                active: "bg-sky-50 text-sky-800 ring-1 ring-sky-400 dark:bg-sky-950/50 dark:text-sky-100 dark:ring-sky-500",
                badge: "bg-sky-600 text-white",
              },
              {
                id: "done" as const,
                title: "Tamamlandı",
                count: grouped.done.length,
                idle: "text-zinc-700 dark:text-zinc-300",
                active: "bg-zinc-100 text-zinc-800 ring-1 ring-zinc-400 dark:bg-zinc-950/50 dark:text-zinc-100 dark:ring-zinc-500",
                badge: "bg-zinc-600 text-white",
              },
            ] as const
          ).map((view) => {
            const selectedView = boardView === view.id;
            return (
              <button
                key={view.id}
                type="button"
                onClick={() => setBoardView(view.id)}
                className={`cursor-pointer rounded-2xl px-3 py-3 text-left transition ${
                  selectedView
                    ? view.active
                    : `bg-white ring-1 ring-slate-200 hover:ring-slate-300 dark:bg-[#0f2220] dark:ring-teal-800/50 dark:hover:ring-teal-700 ${view.idle}`
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold">{view.title}</p>
                  <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-semibold tabular-nums ${view.badge}`}>
                    {view.count}
                  </span>
                </div>
                {view.id === "in_progress" ? (
                  <DueAlertLine overdue={progressAlerts.overdue} soon={progressAlerts.soon} className="mt-2" />
                ) : null}
              </button>
            );
          })}
        </aside>
        ) : null}

        {(boardLayout === "board" || boardView === "suggestions") && (
          <section className={`${boardLayout === "focus" ? "min-w-0 flex-1" : ""} rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-teal-800/40 dark:bg-teal-950/30`}>
            <div className="mb-3 flex items-center justify-between px-1">
              <h2 className="text-sm font-semibold text-teal-700 dark:text-teal-300">Öneriler</h2>
              <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-500 dark:bg-teal-950 dark:text-slate-400">
                {visibleSuggestions.length}
              </span>
            </div>
            <div className={boardLayout === "board" ? "space-y-3" : "grid gap-3 sm:grid-cols-2"}>
              {visibleSuggestions.map((item) => (
                <div
                  key={`${item.meeting_id}-${item.action_seq}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    setSelectedSuggestion(item);
                    setConvertDue(todayISO());
                    setConvertNote("");
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedSuggestion(item);
                      setConvertDue(todayISO());
                      setConvertNote("");
                    }
                  }}
                  className="flex cursor-pointer gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4 shadow-sm transition-shadow hover:border-teal-400 hover:shadow-[0_0_18px_rgba(13,148,136,0.5)] dark:border-teal-800/50 dark:bg-teal-950/40"
                >
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-base font-semibold text-slate-900 dark:text-teal-50">{item.title}</p>
                    <AssigneeLine name={item.assignee} />
                    <p className="mt-2 truncate text-xs font-medium text-slate-500" title={`Toplantı: ${meetingName(item)}`}>
                      Toplantı: {meetingName(item)}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-5">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        dismissSuggestion(item);
                      }}
                      className="cursor-pointer text-xs font-medium text-rose-600 hover:text-rose-700"
                    >
                      Sil
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedSuggestion(item);
                        setConvertDue(todayISO());
                        setConvertNote("");
                      }}
                      className="mt-auto cursor-pointer rounded-lg bg-teal-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-800"
                    >
                      Görev oluştur
                    </button>
                  </div>
                </div>
              ))}
              {visibleSuggestions.length === 0 && (
                <p className="px-1 py-6 text-center text-sm text-slate-400 sm:col-span-2">
                  {filterActive ? "Aramaya uyan öneri yok." : "Önerilen aksiyon yok."}
                </p>
              )}
            </div>
          </section>
        )}
          {columns
            .filter((column) => boardLayout === "board" || column.id === boardView)
            .map((column) => (
          <section key={column.id} className={`${boardLayout === "focus" ? "min-w-0 flex-1" : ""} rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-teal-800/40 dark:bg-teal-950/30`}>
            <div className="mb-3 flex items-start justify-between gap-3 px-1">
              <div>
                <h2 className={`text-sm font-semibold ${column.titleClass}`}>{column.title}</h2>
                {column.id === "in_progress" ? (
                  <DueAlertLine overdue={progressAlerts.overdue} soon={progressAlerts.soon} className="mt-1" />
                ) : null}
              </div>
              <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-500 dark:bg-teal-950 dark:text-slate-400">
                {grouped[column.id].length}
              </span>
            </div>
            <div className={boardLayout === "board" ? "space-y-3" : "grid gap-3 sm:grid-cols-2"}>
              {grouped[column.id].map((task) => {
                const done = task.status === "done";
                const tone = done ? "ok" : dueTone(task.due_date);
                const checkClass = done
                  ? column.check
                  : tone === "overdue"
                    ? "border-rose-500 text-rose-700 hover:scale-110 hover:bg-rose-500 hover:text-white hover:shadow-[0_0_12px_rgba(244,63,94,0.75)] dark:text-rose-300 dark:hover:bg-rose-400 dark:hover:text-rose-950"
                    : tone === "soon"
                      ? "border-amber-500 text-amber-700 hover:scale-110 hover:bg-amber-500 hover:text-white hover:shadow-[0_0_12px_rgba(245,158,11,0.75)] dark:text-amber-300 dark:hover:bg-amber-400 dark:hover:text-amber-950"
                      : column.check;
                return (
                  <div
                    key={`${task.meeting_id}-${task.action_seq}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      setSelected({ ...task, due_date: dateOnly(task.due_date) || task.due_date });
                      setSelectedNote("");
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelected(task);
                      }
                    }}
                    className={`flex cursor-pointer gap-3 rounded-xl border p-4 shadow-sm transition-shadow ${
                      done
                        ? "border-zinc-300 bg-zinc-100 hover:border-zinc-400 hover:shadow-[0_0_18px_rgba(63,63,70,0.35)] dark:border-zinc-700/60 dark:bg-zinc-950/40"
                        : tone === "overdue"
                          ? "border-rose-400 bg-rose-50 hover:border-rose-500 hover:shadow-[0_0_18px_rgba(244,63,94,0.45)] dark:border-rose-700 dark:bg-rose-950/50"
                          : tone === "soon"
                            ? "border-amber-300 bg-amber-50 hover:border-amber-400 hover:shadow-[0_0_18px_rgba(245,158,11,0.5)] dark:border-amber-700/70 dark:bg-amber-950/40"
                            : "border-sky-200 bg-sky-50 hover:border-sky-400 hover:shadow-[0_0_18px_rgba(14,165,233,0.5)] dark:border-sky-800/50 dark:bg-sky-950/40"
                    }`}
                  >
                    <button
                      type="button"
                      aria-label={done ? "Tamamlanmadı işaretle" : "Tamamlandı işaretle"}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleDone(task);
                      }}
                      className={`group mt-0.5 flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded border-2 transition duration-150 ${checkClass}`}
                    >
                      {done ? (
                        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" aria-hidden>
                          <path
                            d="M3.5 8.5 6.5 11.5 12.5 4.5"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" fill="none" aria-hidden>
                          <path
                            d="M3.5 8.5 6.5 11.5 12.5 4.5"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className={`break-words text-base font-semibold text-slate-900 dark:text-teal-50 ${done ? "line-through" : ""}`}>
                        {task.title}
                      </p>
                      <AssigneeLine name={task.assignee} />
                      <p className="mt-2 truncate text-xs font-medium text-slate-500" title={`Toplantı: ${meetingName(task)}`}>
                        Toplantı: {meetingName(task)}
                      </p>
                      <DueHint dueDate={dateOnly(task.due_date) || task.due_date} alert={!done} />
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(task);
                      }}
                      className="self-start cursor-pointer text-xs font-medium text-rose-600 hover:text-rose-700"
                    >
                      Sil
                    </button>
                  </div>
                );
              })}
              {grouped[column.id].length === 0 && (
                <p className="px-1 py-6 text-center text-sm text-slate-400 sm:col-span-2">
                  {filterActive ? "Aramaya uyan görev yok." : "Bu kolonda görev yok."}
                </p>
              )}
            </div>
          </section>
            ))}
      </div>

      {creating && (
        <div
          className="fixed inset-0 z-20 flex items-center justify-center bg-slate-950/40 p-4"
          onClick={() => {
            if (!saving) setCreating(false);
          }}
        >
          <div
            className="max-h-[90vh] w-full min-w-0 max-w-xl overflow-x-hidden overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220] dark:text-teal-50"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold text-slate-900 dark:text-teal-50">Yeni görev</h2>
            <div className="mt-4 space-y-4 text-sm">
              <label className="flex min-w-0 flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-200">Toplantı</span>
                <div className="grid min-w-0 w-full">
                  <SelectWrap>
                    <select
                      value={draft.meeting_id}
                      onChange={(e) => {
                        const meetingId = Number(e.target.value);
                        setDraft({ ...draft, meeting_id: meetingId, assignee: "", assignee_id: null, assigneeNote: "" });
                      }}
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
                </div>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-200">Görev adı</span>
                <input
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-200">Sorumlu</span>
                <PersonPicker
                  attendeeNames={attendeesFor(draft.meeting_id)}
                  people={people}
                  valueId={draft.assignee_id}
                  valueName={draft.assignee}
                  onChange={(personId, name, note) =>
                    setDraft({ ...draft, assignee_id: personId, assignee: name, assigneeNote: note ?? "" })
                  }
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-200">Son tarih</span>
                <input
                  type="date"
                  required
                  min={todayISO()}
                  value={draft.due_date}
                  onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700 dark:text-teal-200">Açıklama</span>
                <textarea
                  rows={3}
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                />
              </label>
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                disabled={saving}
                onClick={handleCreate}
                className="h-10 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
              >
                {saving ? "Kaydediliyor…" : "Oluştur"}
              </button>
              <button
                type="button"
                onClick={() => setCreating(false)}
                className="h-10 cursor-pointer rounded-lg px-3 text-sm font-medium text-slate-500 hover:bg-slate-50 dark:hover:bg-teal-900/40"
              >
                Vazgeç
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedSuggestion && (
        <div className="fixed inset-0 z-20 flex justify-end bg-slate-950/30">
          <button
            type="button"
            className="h-full flex-1 cursor-pointer"
            aria-label="Kapat"
            onClick={() => setSelectedSuggestion(null)}
          />
          <aside className="h-full w-full max-w-xl overflow-x-hidden overflow-y-auto bg-white p-6 shadow-2xl dark:bg-[#0f2220] dark:text-teal-50">
            <div className="mb-6 flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-slate-400">Öneri detayı</p>
                <h2 className="mt-1 break-words text-lg font-semibold text-slate-900 dark:text-teal-50">{selectedSuggestion.title}</h2>
                <Link
                  href={`/meetings/${selectedSuggestion.meeting_id}`}
                  className="mt-2 block break-words text-sm font-medium text-teal-700 hover:text-teal-800"
                >
                  Toplantı: {meetingName(selectedSuggestion)}
                </Link>
              </div>
              <button
                type="button"
                onClick={() => setSelectedSuggestion(null)}
                className="cursor-pointer text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <div className="space-y-4 text-sm">
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Görev adı</span>
                <input
                  value={selectedSuggestion.title}
                  onChange={(e) => setSelectedSuggestion({ ...selectedSuggestion, title: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Sorumlu</span>
                <PersonPicker
                  attendeeNames={attendeesFor(selectedSuggestion.meeting_id)}
                  people={people}
                  valueId={selectedSuggestion.assignee_id}
                  valueName={selectedSuggestion.assignee ?? ""}
                  onChange={(personId, name, note) => {
                    setSelectedSuggestion((prev) =>
                      prev ? { ...prev, assignee_id: personId, assignee: name } : prev,
                    );
                    setConvertNote(note ?? "");
                  }}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Teslim tarihi</span>
                <input
                  type="date"
                  required
                  min={todayISO()}
                  value={convertDue || todayISO()}
                  onChange={(e) => setConvertDue(e.target.value)}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Açıklama</span>
                <textarea
                  rows={4}
                  value={selectedSuggestion.description}
                  onChange={(e) => setSelectedSuggestion({ ...selectedSuggestion, description: e.target.value })}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                />
              </label>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                disabled={saving}
                onClick={() => void promoteSuggestion(selectedSuggestion, convertDue || todayISO())}
                className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
              >
                {saving ? "Oluşturuluyor…" : "Görev oluştur"}
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={saveSuggestion}
                className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
              >
                {saving ? "Kaydediliyor…" : "Kaydet"}
              </button>
              <button
                type="button"
                onClick={() => dismissSuggestion(selectedSuggestion)}
                className="h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-rose-600 hover:bg-rose-50"
              >
                Sil
              </button>
            </div>
          </aside>
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 z-20 flex justify-end bg-slate-950/30">
          <button type="button" className="h-full flex-1 cursor-pointer" aria-label="Kapat" onClick={() => setSelected(null)} />
          <aside className="h-full w-full max-w-xl overflow-x-hidden overflow-y-auto bg-white p-6 shadow-2xl dark:bg-[#0f2220] dark:text-teal-50">
            <div className="mb-6 flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-slate-400">Görev detayı</p>
                <h2 className="mt-1 break-words text-lg font-semibold text-slate-900 dark:text-teal-50">{selected.title}</h2>
                <Link
                  href={`/meetings/${selected.meeting_id}`}
                  className="mt-2 block break-words text-sm font-medium text-teal-700 hover:text-teal-800"
                >
                  Toplantı: {meetingName(selected)}
                </Link>
              </div>
              <div className="flex items-center gap-2">
                <TaskBadge status={selected.status} dueDate={selected.due_date} />
                <button type="button" onClick={() => setSelected(null)} className="cursor-pointer text-slate-400 hover:text-slate-700">
                  ✕
                </button>
              </div>
            </div>
            <div className="space-y-4 text-sm">
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Görev adı</span>
                <input
                  value={selected.title}
                  onChange={(e) => setSelected({ ...selected, title: e.target.value })}
                  className={field}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Sorumlu</span>
                <PersonPicker
                  attendeeNames={attendeesFor(selected.meeting_id)}
                  people={people}
                  valueId={selected.assignee_id}
                  valueName={selected.assignee ?? ""}
                  onChange={(personId, name, note) => {
                    setSelected((prev) => (prev ? { ...prev, assignee_id: personId, assignee: name } : prev));
                    setSelectedNote(note ?? "");
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
                  value={dateOnly(selected.due_date)}
                  onChange={(e) => setSelected({ ...selected, due_date: e.target.value })}
                  className={field}
                />
                <DueHint dueDate={selected.due_date} alert={selected.status !== "done"} />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-medium text-slate-700">Açıklama</span>
                <textarea
                  rows={4}
                  value={selected.description}
                  onChange={(e) => setSelected({ ...selected, description: e.target.value })}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
                />
              </label>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                disabled={saving}
                onClick={saveSelected}
                className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
              >
                {saving ? "Kaydediliyor…" : "Kaydet"}
              </button>
              <button
                type="button"
                onClick={() => void toggleDone(selected)}
                className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
              >
                {selected.status === "done" ? "Devam ediyor olarak işaretle" : "Tamamlandı olarak işaretle"}
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={() => handleDelete(selected)}
                className="h-11 cursor-pointer rounded-lg px-4 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50"
              >
                Sil
              </button>
            </div>
          </aside>
        </div>
      )}
    </AppShell>
  );
}
