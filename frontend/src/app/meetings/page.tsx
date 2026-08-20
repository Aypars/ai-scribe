"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { useConfirm } from "@/components/ConfirmDialog";
import { MeetingBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import { deleteMeeting, fetchMeetings, type Meeting, type MeetingStatus } from "@/lib/api";
import { formatDay, formatDuration } from "@/lib/demo-data";

const filters: { value: "all" | MeetingStatus; label: string }[] = [
  { value: "all", label: "Tümü" },
  { value: "uploaded", label: "Yazıya çevriliyor" },
  { value: "transcribed", label: "Analiz ediliyor" },
  { value: "analyzed", label: "Hazır" },
  { value: "failed", label: "Başarısız" },
];

export default function MeetingsPage() {
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | MeetingStatus>("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    fetchMeetings()
      .then(setMeetings)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Liste alınamadı"))
      .finally(() => setLoading(false));
  }, []);

  const pendingTranscript = meetings.some((meeting) => meeting.status === "uploaded");

  useEffect(() => {
    if (!pendingTranscript) return;
    const timer = window.setInterval(() => {
      fetchMeetings()
        .then(setMeetings)
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [pendingTranscript]);

  const rows = useMemo(() => {
    return meetings.filter((meeting) => {
      const matchesStatus = status === "all" || meeting.status === status;
      const matchesQuery = [meeting.title, meeting.description ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(query.trim().toLowerCase());
      return matchesStatus && matchesQuery;
    });
  }, [meetings, query, status]);

  const filterCounts = useMemo(() => {
    const q = query.trim().toLowerCase();
    const searched = meetings.filter((meeting) =>
      [meeting.title, meeting.description ?? ""].join(" ").toLowerCase().includes(q),
    );
    const counts: Record<string, number> = { all: searched.length };
    for (const meeting of searched) {
      counts[meeting.status] = (counts[meeting.status] ?? 0) + 1;
    }
    return counts;
  }, [meetings, query]);

  async function handleDelete(meeting: Meeting) {
    const ok = await confirm({
      message: `“${meeting.title}” silinsin mi? Bu işlem geri alınamaz.`,
    });
    if (!ok) return;
    setBusyId(meeting.meeting_id);
    setError(null);
    try {
      await deleteMeeting(meeting.meeting_id);
      setMeetings((prev) => prev.filter((item) => item.meeting_id !== meeting.meeting_id));
      toast("Toplantı başarıyla silindi");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Silinemedi");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <AppShell
      title="Toplantılar"
      action={
        <Link
          href="/meetings/new"
          className="inline-flex h-10 items-center rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
        >
          + Yeni toplantı
        </Link>
      }
    >
      <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center dark:border-teal-900/40">
          <div className="relative max-w-md flex-1">
            <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />
              </svg>
            </span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Toplantı ara..."
              className="h-10 w-full rounded-lg border border-slate-200 bg-white pr-3 pl-9 text-sm outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
            />
          </div>
          <div className="flex min-w-0 max-w-full gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1 dark:bg-teal-950/70">
            {filters.map((item) => {
              const active = status === item.value;
              const count = filterCounts[item.value] ?? 0;
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setStatus(item.value)}
                  className={`flex shrink-0 cursor-pointer items-center rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    active
                      ? "bg-white text-slate-900 shadow-sm dark:bg-teal-700 dark:text-white"
                      : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-teal-100"
                  }`}
                >
                  {item.label}
                  <span
                    className={`ml-1.5 rounded-md px-1.5 py-0.5 text-[10px] font-semibold tabular-nums ${
                      active
                        ? "bg-teal-600 text-white dark:bg-teal-900/60"
                        : "bg-slate-200 text-slate-500 dark:bg-teal-900 dark:text-slate-400"
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-5 py-3 font-medium">Başlık</th>
              <th className="w-px whitespace-nowrap px-5 py-3 font-medium">Tarih</th>
              <th className="w-px whitespace-nowrap px-5 py-3 font-medium">Durum</th>
              <th className="w-px whitespace-nowrap px-5 py-3 font-medium">Süre</th>
              <th className="w-px whitespace-nowrap px-5 py-3 font-medium">İşlem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-teal-900/40">
            {rows.map((meeting) => (
              <tr
                key={meeting.meeting_id}
                onClick={() => router.push(`/meetings/${meeting.meeting_id}`)}
                className="cursor-pointer hover:bg-slate-50 dark:hover:bg-teal-900/30"
              >
                <td className="max-w-0 w-full overflow-hidden px-5 py-4">
                  <p className="truncate font-medium text-slate-900 dark:text-teal-50" title={meeting.title}>
                    {meeting.title}
                  </p>
                  {meeting.description ? (
                    <p className="mt-0.5 line-clamp-1 text-xs text-slate-500" title={meeting.description}>
                      {meeting.description}
                    </p>
                  ) : null}
                  <p className="truncate text-xs text-slate-400" title={meeting.attendees || undefined}>
                    {meeting.attendees || "Katılımcı belirtilmedi"}
                  </p>
                </td>
                <td className="w-px whitespace-nowrap px-5 py-4 text-slate-500">{formatDay(meeting.date)}</td>
                <td className="w-px whitespace-nowrap px-5 py-4">
                  <MeetingBadge status={meeting.status} />
                </td>
                <td className="w-px whitespace-nowrap px-5 py-4 text-slate-500">{formatDuration(meeting.duration)}</td>
                <td className="w-px whitespace-nowrap px-5 py-4" onClick={(event) => event.stopPropagation()}>
                  <div className="flex items-center gap-3">
                    <Link
                      href={`/meetings/${meeting.meeting_id}?edit=1`}
                      className="text-sm font-medium text-teal-700 hover:text-teal-800 dark:text-teal-300 dark:hover:text-teal-200"
                    >
                      Düzenle
                    </Link>
                    <button
                      type="button"
                      disabled={busyId === meeting.meeting_id}
                      onClick={() => handleDelete(meeting)}
                      className="cursor-pointer text-sm font-medium text-rose-600 hover:text-rose-700 disabled:opacity-50"
                    >
                      Sil
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {loading && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">
                  Yükleniyor…
                </td>
              </tr>
            )}
            {!loading && error && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-rose-600">
                  {error}
                </td>
              </tr>
            )}
            {!loading && !error && meetings.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">
                  Henüz toplantı yok. Yeni toplantı yükleyerek başlayın.
                </td>
              </tr>
            )}
            {!loading && !error && meetings.length > 0 && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">
                  Eşleşen toplantı yok.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
