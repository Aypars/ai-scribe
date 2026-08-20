import type { MeetingStatus, TaskStatus } from "@/lib/api";
import { dueRemainingLabel, dueTone, formatDay } from "@/lib/demo-data";

const meetingStyles: Record<MeetingStatus, string> = {
  uploaded: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200",
  transcribed: "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200",
  analyzed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200",
  failed: "bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200",
};

const meetingLabels: Record<MeetingStatus, string> = {
  uploaded: "Yazıya çevriliyor",
  transcribed: "Analiz ediliyor",
  analyzed: "Hazır",
  failed: "Başarısız",
};

const progressStyles = {
  overdue: "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200",
  soon: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200",
  ok: "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200",
};

const taskLabels: Record<TaskStatus, string> = {
  in_progress: "Devam ediyor",
  done: "Tamamlandı",
};

export function MeetingBadge({ status }: { status: MeetingStatus }) {
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${meetingStyles[status]}`}
    >
      {meetingLabels[status]}
    </span>
  );
}

export function TaskBadge({
  status,
  dueDate,
}: {
  status: TaskStatus;
  dueDate?: string | null;
}) {
  const tone = dueTone(dueDate);
  const style =
    status === "done"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200"
      : progressStyles[tone === "overdue" || tone === "soon" ? tone : "ok"];
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${style}`}>
      {taskLabels[status]}
    </span>
  );
}

export function DueAlertLine({
  overdue,
  soon,
  className = "",
}: {
  overdue: number;
  soon: number;
  className?: string;
}) {
  if (overdue < 1 && soon < 1) return null;
  return (
    <p className={`flex flex-wrap items-center gap-x-1.5 text-[11px] font-medium ${className}`}>
      {overdue > 0 ? (
        <span className="text-rose-600 dark:text-rose-300">
          {overdue} süresi geçti
        </span>
      ) : null}
      {overdue > 0 && soon > 0 ? <span className="text-slate-400">·</span> : null}
      {soon > 0 ? (
        <span className="text-amber-600 dark:text-amber-300">
          {soon} yaklaşıyor
        </span>
      ) : null}
    </p>
  );
}

export function DueHint({
  dueDate,
  alert = true,
}: {
  dueDate: string | null;
  alert?: boolean;
}) {
  if (!dueDate) {
    return <p className="mt-1 text-xs text-slate-400">Teslim tarihi yok</p>;
  }
  const iso = dueDate.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    return <p className="mt-1 text-xs text-slate-400">Teslim tarihi yok</p>;
  }
  const tone = dueTone(iso);
  const remaining = dueRemainingLabel(iso);
  const dateLabel = formatDay(iso);
  if (!alert || tone === "none") {
    return (
      <p className="mt-1 text-xs font-medium text-slate-600 dark:text-teal-200">
        {dateLabel}
        {remaining ? ` · ${remaining}` : ""}
      </p>
    );
  }
  if (tone === "overdue") {
    return (
      <div className="mt-2">
        <p className="text-xs text-rose-700 dark:text-rose-300">{dateLabel}</p>
        <p className="mt-1 rounded-lg bg-rose-600 px-2.5 py-1.5 text-sm font-semibold text-white shadow-sm">
          Süresi geçti · {remaining}
        </p>
      </div>
    );
  }
  if (tone === "soon") {
    return (
      <div className="mt-2">
        <p className="text-xs font-medium text-amber-800 dark:text-amber-200">{dateLabel}</p>
        <p className="mt-1 rounded-lg bg-amber-400 px-2.5 py-1.5 text-sm font-semibold text-amber-950 shadow-sm dark:bg-amber-400">
          Yaklaşıyor · {remaining}
        </p>
      </div>
    );
  }
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-sky-800 dark:text-sky-200">{dateLabel}</p>
      <p className="mt-1 rounded-lg bg-sky-600 px-2.5 py-1.5 text-sm font-semibold text-white shadow-sm">
        {remaining}
      </p>
    </div>
  );
}
