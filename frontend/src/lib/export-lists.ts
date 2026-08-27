import type { Task } from "@/lib/api";
import { byDueDate, countDueAlerts, dueRemainingLabel, dueTone, formatDay, formatDate } from "@/lib/demo-data";
import {
  AMBER,
  AMBER_RULE,
  CONTENT_W,
  EMERALD,
  EMERALD_RULE,
  MARGIN,
  MUTED,
  NUM_W,
  ROSE,
  ROSE_RULE,
  TEAL,
  type Ctx,
  fileStem,
  newDocument,
  readyMeasure,
  sectionHeading,
  triggerDownload,
  writeCover,
  writeFooters,
  writeInline,
  writeNumberedBody,
  writeWrapped,
} from "@/lib/export-pdf";

export type PersonExportMeeting = {
  title: string;
  date: string | null;
};

export type PersonExportInput = {
  name: string;
  note: string | null;
  open: Task[];
  done: Task[];
  meetings: PersonExportMeeting[];
};

export type PeopleRosterRow = {
  name: string;
  note: string | null;
  open: Task[];
};

export type OpenTasksExportInput = {
  title?: string;
  subtitle?: string;
  tasks: Task[];
  showAssignee?: boolean;
};

function todayLine(): string {
  return formatDate(new Date().toISOString());
}

function splitOpen(tasks: Task[]): { overdue: Task[]; soon: Task[]; rest: Task[] } {
  const overdue: Task[] = [];
  const soon: Task[] = [];
  const rest: Task[] = [];
  for (const task of [...tasks].sort(byDueDate)) {
    const tone = dueTone(task.due_date);
    if (tone === "overdue") overdue.push(task);
    else if (tone === "soon") soon.push(task);
    else rest.push(task);
  }
  return { overdue, soon, rest };
}

function accentOf(task: Task): [number, number, number] {
  if (task.status === "done") return EMERALD;
  const tone = dueTone(task.due_date);
  if (tone === "overdue") return ROSE;
  if (tone === "soon") return AMBER;
  return TEAL;
}

function metaColorOf(task: Task): [number, number, number] {
  if (task.status === "done") return EMERALD;
  const tone = dueTone(task.due_date);
  if (tone === "overdue") return ROSE;
  if (tone === "soon") return AMBER;
  return MUTED;
}

function taskMeta(task: Task, showAssignee: boolean): string {
  const bits = [
    showAssignee ? (task.assignee?.trim() ? `Sorumlu: ${task.assignee.trim()}` : "Sorumlu yok") : null,
    task.due_date ? `Teslim: ${formatDay(task.due_date)}` : "Teslim tarihi yok",
    task.status === "done" ? "Tamamlandı" : dueRemainingLabel(task.due_date) || "Devam ediyor",
    task.meeting_title?.trim() || null,
  ].filter(Boolean);
  return bits.join(" · ");
}

function writeTaskList(ctx: Ctx, tasks: Task[], showAssignee: boolean, empty: string): void {
  if (!tasks.length) {
    writeWrapped(ctx, empty, 11, "normal", MUTED);
    return;
  }
  tasks.forEach((task, index) => {
    writeNumberedBody(ctx, index + 1, task.title.trim() || "Görev", accentOf(task));
    writeWrapped(ctx, taskMeta(task, showAssignee), 9, "normal", metaColorOf(task), 1.8, CONTENT_W - NUM_W, MARGIN + NUM_W);
    const extra = (task.description || task.notes || "").trim();
    if (extra && extra !== task.title.trim()) {
      writeWrapped(ctx, extra, 10, "normal", MUTED, 4.5, CONTENT_W - NUM_W, MARGIN + NUM_W);
    } else {
      ctx.y += 3.5;
    }
  });
}

function writeStatusLine(
  ctx: Ctx,
  open: Task[],
  extra?: { people?: number },
): void {
  const alerts = countDueAlerts(open);
  const parts: { text: string; color: [number, number, number]; bold?: boolean }[] = [];
  if (extra?.people != null) {
    parts.push({ text: `${extra.people} kişi`, color: MUTED });
    parts.push({ text: "  ·  ", color: MUTED });
  }
  parts.push({ text: `${open.length} açık`, color: MUTED });
  if (alerts.overdue) {
    parts.push({ text: "  ·  ", color: MUTED });
    parts.push({ text: `${alerts.overdue} gecikmiş`, color: ROSE, bold: true });
  }
  if (alerts.soon) {
    parts.push({ text: "  ·  ", color: MUTED });
    parts.push({ text: `${alerts.soon} yaklaşan`, color: AMBER, bold: true });
  }
  writeInline(ctx, parts);
}

function writeOpenGroups(ctx: Ctx, tasks: Task[], showAssignee: boolean): void {
  const { overdue, soon, rest } = splitOpen(tasks);
  if (!tasks.length) {
    writeWrapped(ctx, "Açık görev yok.", 11, "normal", MUTED);
    return;
  }
  if (overdue.length) {
    sectionHeading(ctx, "Süresi geçen", ROSE, ROSE_RULE);
    writeTaskList(ctx, overdue, showAssignee, "");
  }
  if (soon.length) {
    sectionHeading(ctx, "Yaklaşan", AMBER, AMBER_RULE);
    writeTaskList(ctx, soon, showAssignee, "");
  }
  if (rest.length) {
    sectionHeading(ctx, overdue.length || soon.length ? "Diğer açık görevler" : "Açık görevler");
    writeTaskList(ctx, rest, showAssignee, "");
  }
}

export async function downloadPersonReport(person: PersonExportInput): Promise<void> {
  await readyMeasure();
  const { doc, ctx } = await newDocument();
  const open = [...person.open].sort(byDueDate);
  const done = [...person.done].sort(byDueDate);
  writeCover(ctx, "KİŞİ RAPORU", person.name, [todayLine(), person.note?.trim() || ""]);
  writeStatusLine(ctx, open);
  writeOpenGroups(ctx, open, false);
  sectionHeading(ctx, "Tamamlanan görevler", EMERALD, EMERALD_RULE);
  writeTaskList(ctx, done, false, "Tamamlanan görev yok.");
  if (person.meetings.length) {
    sectionHeading(ctx, "Toplantılar");
    person.meetings.forEach((meeting, index) => {
      writeNumberedBody(ctx, index + 1, meeting.title);
      writeWrapped(
        ctx,
        meeting.date ? formatDay(meeting.date) : "Tarih yok",
        9,
        "normal",
        MUTED,
        4,
        CONTENT_W - NUM_W,
        MARGIN + NUM_W,
      );
    });
  }
  writeFooters(doc);
  triggerDownload(new Uint8Array(doc.output("arraybuffer")), `${fileStem(person.name)} Görevler Rapor.pdf`);
}

export async function downloadPeopleRoster(rows: PeopleRosterRow[]): Promise<void> {
  await readyMeasure();
  const { doc, ctx } = await newDocument();
  const withOpen = rows.filter((row) => row.open.length > 0);
  const openTasks = withOpen.flatMap((row) => row.open);
  writeCover(ctx, "KİŞİLER RAPORU", "Kişiler ve açık görevler", [todayLine()]);
  writeStatusLine(ctx, openTasks, { people: withOpen.length });
  if (!withOpen.length) {
    writeWrapped(ctx, "Listede açık görev yok.", 11, "normal", MUTED);
  } else {
    for (const row of withOpen) {
      const alerts = countDueAlerts(row.open);
      sectionHeading(
        ctx,
        row.name,
        alerts.overdue ? ROSE : alerts.soon ? AMBER : TEAL,
        alerts.overdue ? ROSE_RULE : alerts.soon ? AMBER_RULE : undefined,
      );
      const intro = row.note?.trim() || "";
      if (intro) writeWrapped(ctx, intro, 10, "normal", MUTED, 1.4);
      writeStatusLine(ctx, row.open);
      writeTaskList(ctx, [...row.open].sort(byDueDate), false, "Açık görev yok.");
    }
  }
  writeFooters(doc);
  triggerDownload(new Uint8Array(doc.output("arraybuffer")), "Kişiler Açık Görevler Rapor.pdf");
}

export async function downloadOpenTasksReport(input: OpenTasksExportInput): Promise<void> {
  await readyMeasure();
  const { doc, ctx } = await newDocument();
  const tasks = [...input.tasks].sort(byDueDate);
  const title = input.title?.trim() || "Açık görevler";
  writeCover(ctx, "GÖREV RAPORU", title, [todayLine(), input.subtitle?.trim() || ""]);
  writeStatusLine(ctx, tasks);
  writeOpenGroups(ctx, tasks, input.showAssignee !== false);
  writeFooters(doc);
  triggerDownload(new Uint8Array(doc.output("arraybuffer")), `${fileStem(title)} Rapor.pdf`);
}
