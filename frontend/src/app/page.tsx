"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AgendaCalendar } from "@/components/AgendaCalendar";
import { AppShell } from "@/components/AppShell";
import { MeetingBadge, DueAlertLine } from "@/components/StatusBadge";
import { fetchMeetings, fetchTasks, type Meeting, type Task } from "@/lib/api";
import { countDueAlerts, formatDay, formatDuration } from "@/lib/dates";

export default function DashboardPage() {
  const router = useRouter();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchMeetings(), fetchTasks()])
      .then(([meetingList, taskList]) => {
        setMeetings(meetingList);
        setTasks(taskList);
      })
      .catch(() => {
        setMeetings([]);
        setTasks([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const analyzed = meetings.filter((m) => m.status === "analyzed").length;
  const openTasks = tasks.filter((t) => t.status !== "done");
  const recent = meetings.slice(0, 4);
  const rate = meetings.length ? Math.round((analyzed / meetings.length) * 1000) / 10 : 0;
  const alerts = countDueAlerts(openTasks);

  return (
    <AppShell title="Dashboard">
      <div className="grid gap-4 sm:grid-cols-3">
        <article className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
          <div className="flex items-start justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">Toplam toplantı</p>
            <span className="rounded-lg bg-teal-50 p-1.5 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 0 0 6-6v-3a6 6 0 1 0-12 0v3a6 6 0 0 0 6 6Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 21h8" />
              </svg>
            </span>
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">{loading ? "—" : meetings.length}</p>
          <p className="mt-1 text-xs text-slate-400">Kayıtlı toplantılar</p>
        </article>
        <article className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
          <div className="flex items-start justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">Tamamlanan analiz</p>
            <span className="rounded-lg bg-teal-100 p-1.5 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
            </span>
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">{loading ? "—" : analyzed}</p>
          <p className="mt-1 text-xs text-slate-400">%{rate} analiz oranı</p>
        </article>
        <article
          className={`rounded-2xl border p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${
            alerts.overdue > 0
              ? "border-rose-300 bg-rose-50 dark:border-rose-800/70 dark:bg-rose-950/40"
              : alerts.soon > 0
                ? "border-amber-300 bg-amber-50 dark:border-amber-800/70 dark:bg-amber-950/40"
                : "border-slate-200/80 bg-white dark:border-teal-800/40 dark:bg-[#0f2220]"
          }`}
        >
          <div className="flex items-start justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">Açık görev</p>
            <span
              className={`rounded-lg p-1.5 ${
                alerts.overdue > 0
                  ? "bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200"
                  : alerts.soon > 0
                    ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200"
                    : "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300"
              }`}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6M7 4h10a2 2 0 0 1 2 2v14l-7-3-7 3V6a2 2 0 0 1 2-2Z" />
              </svg>
            </span>
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">{loading ? "—" : openTasks.length}</p>
          {loading ? (
            <p className="mt-1 text-xs text-slate-400">Teslim tarihi yaklaşan işler</p>
          ) : alerts.overdue > 0 || alerts.soon > 0 ? (
            <DueAlertLine overdue={alerts.overdue} soon={alerts.soon} className="mt-1.5 text-xs" />
          ) : (
            <p className="mt-1 text-xs text-slate-400">Süresi geçen veya yaklaşan iş yok</p>
          )}
        </article>
      </div>

      <div className="mt-6">
        <AgendaCalendar meetings={meetings} tasks={openTasks} />
      </div>

      <div className="mt-6">
        <section className="min-w-0 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
          <div className="flex items-center justify-between px-5 py-4">
            <h2 className="font-semibold text-slate-900 dark:text-teal-50">Son toplantılar</h2>
            <Link href="/meetings" className="text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-teal-200">
              Tümünü gör
            </Link>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-5 pb-2 font-medium">Başlık</th>
                <th className="w-px whitespace-nowrap px-5 pb-2 font-medium">Tarih</th>
                <th className="w-px whitespace-nowrap px-5 pb-2 font-medium">Durum</th>
                <th className="w-px whitespace-nowrap px-5 pb-2 font-medium">Süre</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-teal-900/40">
              {recent.map((meeting) => (
                <tr
                  key={meeting.meeting_id}
                  onClick={() => router.push(`/meetings/${meeting.meeting_id}`)}
                  className="cursor-pointer hover:bg-slate-50 dark:hover:bg-teal-900/30"
                >
                  <td className="max-w-0 w-full overflow-hidden px-5 py-3 font-medium text-slate-900 dark:text-teal-50">
                    <p className="truncate" title={meeting.title}>
                      {meeting.title}
                    </p>
                  </td>
                  <td className="w-px whitespace-nowrap px-5 py-3 text-slate-500">{formatDay(meeting.date)}</td>
                  <td className="w-px whitespace-nowrap px-5 py-3">
                    <MeetingBadge status={meeting.status} />
                  </td>
                  <td className="w-px whitespace-nowrap px-5 py-3 text-slate-500">{formatDuration(meeting.duration)}</td>
                </tr>
              ))}
              {!loading && recent.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-slate-400">
                    Henüz toplantı yok.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      </div>

      <Link
        href="/meetings/new"
        className="fixed right-6 bottom-6 inline-flex items-center gap-2 rounded-full bg-teal-700 px-5 py-3 text-sm font-semibold text-white shadow-lg hover:bg-teal-800"
      >
        + Yeni toplantı yükle
      </Link>
    </AppShell>
  );
}
