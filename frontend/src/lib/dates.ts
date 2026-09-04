function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function todayISO(): string {
  const date = new Date();
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/** Native datetime-local value for the current local time. */
export function nowDatetimeLocal(): string {
  const date = new Date();
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

/** Native date inputs need YYYY-MM-DD; API values may include a time. */
export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "";
  const match = String(iso).match(/^(\d{4}-\d{2}-\d{2})/);
  return match?.[1] ?? "";
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const [year, month, day] = dateOnly(iso).split("-").map(Number);
  if (!year || !month || !day) return null;
  const due = new Date(year, month - 1, day);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / 86_400_000);
}

export type DueTone = "none" | "ok" | "soon" | "overdue";

export function dueTone(iso: string | null | undefined): DueTone {
  const days = daysUntil(iso);
  if (days == null) return "none";
  if (days < 0) return "overdue";
  if (days <= 3) return "soon";
  return "ok";
}

export function countDueAlerts(tasks: { due_date?: string | null }[]): { overdue: number; soon: number } {
  let overdue = 0;
  let soon = 0;
  for (const task of tasks) {
    const tone = dueTone(task.due_date);
    if (tone === "overdue") overdue += 1;
    else if (tone === "soon") soon += 1;
  }
  return { overdue, soon };
}

export function dueRemainingLabel(iso: string | null | undefined): string {
  const days = daysUntil(iso);
  if (days == null) return "";
  if (days < 0) {
    const late = Math.abs(days);
    return late === 1 ? "1 gün gecikti" : `${late} gün gecikti`;
  }
  if (days === 0) return "Bugün teslim";
  if (days === 1) return "1 gün kaldı";
  return `${days} gün kaldı`;
}

export function byDueDate(a: { due_date?: string | null }, b: { due_date?: string | null }): number {
  const left = dateOnly(a.due_date);
  const right = dateOnly(b.due_date);
  if (!left && !right) return 0;
  if (!left) return 1;
  if (!right) return -1;
  return left.localeCompare(right);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDay(iso: string | null | undefined, locale = "tr-TR"): string {
  if (!iso) return "—";
  const dayPart = iso.slice(0, 10);
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" };
  if (/^\d{4}-\d{2}-\d{2}$/.test(dayPart)) {
    const [year, month, day] = dayPart.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString(locale, opts);
  }
  return new Date(iso).toLocaleDateString(locale, opts);
}

export function formatDuration(seconds: number | null, locale = "tr-TR"): string {
  if (seconds == null) return "—";
  const en = locale.toLowerCase().startsWith("en");
  if (seconds < 60) return en ? `${seconds}s` : `${seconds}sn`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (en) {
    if (hours) {
      if (mins && secs) return `${hours}h ${mins}m ${secs}s`;
      if (mins) return `${hours}h ${mins}m`;
      return `${hours}h`;
    }
    if (secs) return `${mins}m ${secs}s`;
    return `${mins}m`;
  }
  if (hours) {
    if (mins && secs) return `${hours}s ${mins}dk ${secs}sn`;
    if (mins) return `${hours}s ${mins}dk`;
    return `${hours}s`;
  }
  if (secs) return `${mins}dk ${secs}sn`;
  return `${mins}dk`;
}

export function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
