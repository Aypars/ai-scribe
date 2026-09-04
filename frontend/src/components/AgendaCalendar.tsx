"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { DueHint } from "@/components/StatusBadge";
import type { Meeting, Task } from "@/lib/api";
import { dateOnly, dueTone, formatDay, type DueTone } from "@/lib/dates";

const WEEKDAYS = ["Pt", "Sa", "Ça", "Pe", "Cu", "Ct", "Pz"];
const card =
  "rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]";

export type CalendarEvent = {
  key: string;
  day: string;
  kind: "meeting" | "task";
  title: string;
  href: string;
  tone?: DueTone;
  assignee?: string;
  subtitle?: string;
  description?: string;
  dueDate?: string;
};

function ymd(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function todayKey(): string {
  const now = new Date();
  return ymd(now.getFullYear(), now.getMonth(), now.getDate());
}

function monthLabel(year: number, month: number): string {
  return new Date(year, month, 1).toLocaleDateString("tr-TR", { month: "long", year: "numeric" });
}

function buildEvents(meetings: Meeting[], tasks: Task[]): CalendarEvent[] {
  const items: CalendarEvent[] = [];
  for (const meeting of meetings) {
    const day = dateOnly(meeting.date);
    if (!day) continue;
    items.push({
      key: `m-${meeting.meeting_id}`,
      day,
      kind: "meeting",
      title: meeting.title,
      href: `/meetings/${meeting.meeting_id}`,
      subtitle: (meeting.named_attendees || meeting.attendees || "").trim() || undefined,
      description: meeting.description?.trim() || undefined,
    });
  }
  for (const task of tasks) {
    if (task.status === "done") continue;
    const day = dateOnly(task.due_date);
    if (!day) continue;
    items.push({
      key: `t-${task.meeting_id}-${task.action_seq}`,
      day,
      kind: "task",
      title: task.title,
      href: `/tasks?task=${task.meeting_id}-${task.action_seq}`,
      tone: dueTone(task.due_date),
      assignee: task.assignee?.trim() || undefined,
      subtitle: task.meeting_title?.trim() || undefined,
      dueDate: day,
    });
  }
  return items;
}

function dotClass(event: CalendarEvent): string {
  if (event.kind === "meeting") return "bg-teal-600";
  if (event.tone === "overdue") return "bg-rose-500";
  if (event.tone === "soon") return "bg-amber-500";
  return "bg-sky-500";
}

function cellEvents(events: CalendarEvent[], day: string): CalendarEvent[] {
  return events.filter((item) => item.day === day);
}

function eventCardClass(event: CalendarEvent): string {
  if (event.kind === "meeting") return "border-teal-200 bg-teal-50/70 dark:border-teal-800/60 dark:bg-teal-950/40";
  if (event.tone === "overdue") return "border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/40";
  if (event.tone === "soon") return "border-amber-300 bg-amber-50 dark:border-amber-800/70 dark:bg-amber-950/40";
  return "border-sky-200 bg-sky-50 dark:border-sky-800/50 dark:bg-sky-950/40";
}

function EventLink({ event }: { event: CalendarEvent }) {
  return (
    <Link
      href={event.href}
      className={`block rounded-xl border p-4 hover:border-teal-500 dark:hover:border-teal-500 ${eventCardClass(event)}`}
    >
      <p className="break-words text-base font-semibold text-slate-900 dark:text-teal-50">{event.title}</p>
      {event.description ? (
        <p className="mt-1.5 line-clamp-3 text-sm leading-5 text-slate-600 dark:text-teal-100/80">{event.description}</p>
      ) : null}
      {event.kind === "task" ? (
        <p className="mt-1.5 text-sm font-semibold text-slate-700 dark:text-teal-100">
          {event.assignee ? `Sorumlu: ${event.assignee}` : "Sorumlu yok"}
        </p>
      ) : null}
      {event.subtitle ? (
        <p className="mt-1.5 truncate text-xs font-medium text-slate-500" title={event.subtitle}>
          {event.kind === "meeting" ? `Katılanlar: ${event.subtitle}` : `Toplantı: ${event.subtitle}`}
        </p>
      ) : null}
      {event.dueDate ? <DueHint dueDate={event.dueDate} /> : null}
    </Link>
  );
}

export function AgendaCalendar({ meetings, tasks }: { meetings: Meeting[]; tasks: Task[] }) {
  const now = new Date();
  const [cursor, setCursor] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [selected, setSelected] = useState(todayKey());
  const [tab, setTab] = useState<"meeting" | "task">("meeting");
  const events = useMemo(() => buildEvents(meetings, tasks), [meetings, tasks]);
  const today = todayKey();

  const cells = useMemo(() => {
    const first = new Date(cursor.year, cursor.month, 1);
    const startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(cursor.year, cursor.month + 1, 0).getDate();
    const prevDays = new Date(cursor.year, cursor.month, 0).getDate();
    const items: { key: string; inMonth: boolean; label: number }[] = [];
    for (let i = startPad - 1; i >= 0; i -= 1) {
      const date = new Date(cursor.year, cursor.month - 1, prevDays - i);
      items.push({ key: ymd(date.getFullYear(), date.getMonth(), date.getDate()), inMonth: false, label: date.getDate() });
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      items.push({ key: ymd(cursor.year, cursor.month, day), inMonth: true, label: day });
    }
    while (items.length % 7 !== 0) {
      const extra = items.length - (startPad + daysInMonth) + 1;
      const date = new Date(cursor.year, cursor.month + 1, extra);
      items.push({ key: ymd(date.getFullYear(), date.getMonth(), date.getDate()), inMonth: false, label: date.getDate() });
    }
    return items;
  }, [cursor]);

  const selectedLabel = selected === today ? "Bugün" : formatDay(selected);
  const visible = events.filter((item) => item.day === selected && item.kind === tab);

  function shiftMonth(delta: number) {
    setCursor((prev) => {
      const date = new Date(prev.year, prev.month + delta, 1);
      return { year: date.getFullYear(), month: date.getMonth() };
    });
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <section className={`${card} p-5`}>
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-xs font-semibold tracking-[0.14em] text-slate-600 uppercase dark:text-teal-300">Takvim</h2>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  const stamp = new Date();
                  setCursor({ year: stamp.getFullYear(), month: stamp.getMonth() });
                  setSelected(todayKey());
                }}
                className="mr-1 h-8 cursor-pointer rounded-lg px-2 text-xs font-medium text-teal-700 hover:bg-teal-50 dark:text-teal-300 dark:hover:bg-teal-900/50"
              >
                Bugün
              </button>
              <button
                type="button"
                onClick={() => shiftMonth(-1)}
                className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-teal-900/50"
                aria-label="Önceki ay"
              >
                ‹
              </button>
              <p className="min-w-[9.5rem] text-center text-sm font-semibold capitalize text-slate-900 dark:text-teal-50">
                {monthLabel(cursor.year, cursor.month)}
              </p>
              <button
                type="button"
                onClick={() => shiftMonth(1)}
                className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-teal-900/50"
                aria-label="Sonraki ay"
              >
                ›
              </button>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-7 gap-1 text-center text-[11px] font-medium text-slate-400">
            {WEEKDAYS.map((day) => (
              <div key={day} className="py-1">
                {day}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((cell) => {
              const dayEvents = cellEvents(events, cell.key);
              const isSelected = selected === cell.key;
              const isToday = today === cell.key;
              const hasOverdue = dayEvents.some((item) => item.tone === "overdue");
              const visibleDots = dayEvents.slice(0, 3);
              return (
                <button
                  key={cell.key}
                  type="button"
                  onClick={() => {
                    setSelected(cell.key);
                    const dayItems = cellEvents(events, cell.key);
                    const hasMeetings = dayItems.some((item) => item.kind === "meeting");
                    const hasTasks = dayItems.some((item) => item.kind === "task");
                    if (tab === "meeting" && !hasMeetings && hasTasks) setTab("task");
                    if (tab === "task" && !hasTasks && hasMeetings) setTab("meeting");
                    if (!cell.inMonth) {
                      const [year, month] = cell.key.split("-").map(Number);
                      setCursor({ year, month: month - 1 });
                    }
                  }}
                  className={`flex min-h-[3.1rem] cursor-pointer flex-col items-center rounded-xl px-0.5 py-1 text-xs transition ${
                    isSelected
                      ? "bg-teal-700 text-white"
                      : isToday
                        ? "bg-teal-50 text-teal-900 dark:bg-teal-900/50 dark:text-teal-50"
                        : cell.inMonth
                          ? "text-slate-700 hover:bg-slate-50 dark:text-teal-100 dark:hover:bg-teal-900/30"
                          : "text-slate-300 hover:bg-slate-50 dark:text-slate-600 dark:hover:bg-teal-900/20"
                  }`}
                >
                  <span className={`font-semibold tabular-nums ${hasOverdue && !isSelected ? "text-rose-600 dark:text-rose-300" : ""}`}>
                    {cell.label}
                  </span>
                  {visibleDots.length ? (
                    <span className="mt-0.5 flex items-center justify-center gap-0.5">
                      {visibleDots.map((event) => (
                        <span
                          key={event.key}
                          className={`h-1.5 w-1.5 rounded-full ${isSelected ? "bg-white" : dotClass(event)}`}
                        />
                      ))}
                      {dayEvents.length > 3 ? (
                        <span className={`text-[9px] ${isSelected ? "text-teal-100" : "text-slate-400"}`}>+</span>
                      ) : null}
                    </span>
                  ) : (
                    <span className="mt-0.5 h-1.5" />
                  )}
                </button>
              );
            })}
          </div>

          <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500 dark:text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-teal-600" /> Toplantı
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-500" /> Görev
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> Yaklaşan
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-rose-500" /> Geciken
            </span>
          </div>
        </section>

        <section className={`relative min-h-[24rem] ${card} lg:min-h-0`}>
          <div className="flex h-full flex-col p-5 lg:absolute lg:inset-0">
            <div className="flex rounded-xl bg-slate-100 p-1 dark:bg-teal-950/80">
              <button
                type="button"
                onClick={() => setTab("meeting")}
                className={`h-10 flex-1 cursor-pointer rounded-lg text-sm font-semibold ${
                  tab === "meeting"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-teal-800 dark:text-teal-50"
                    : "text-slate-500 hover:text-slate-800 dark:text-teal-300 dark:hover:text-teal-50"
                }`}
              >
                Toplantılar
              </button>
              <button
                type="button"
                onClick={() => setTab("task")}
                className={`h-10 flex-1 cursor-pointer rounded-lg text-sm font-semibold ${
                  tab === "task"
                    ? "bg-white text-slate-900 shadow-sm dark:bg-teal-800 dark:text-teal-50"
                    : "text-slate-500 hover:text-slate-800 dark:text-teal-300 dark:hover:text-teal-50"
                }`}
              >
                Görevler
              </button>
            </div>
            <p className="mt-3 text-xs font-medium text-slate-500 dark:text-slate-400">{selectedLabel}</p>
            <ul className="mt-3 min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
              {visible.map((event) => (
                <li key={event.key}>
                  <EventLink event={event} />
                </li>
              ))}
              {visible.length === 0 ? (
                <li className="text-sm text-slate-400">
                  {tab === "meeting" ? "Bu günde toplantı yok." : "Bu günde görev yok."}
                </li>
              ) : null}
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}
