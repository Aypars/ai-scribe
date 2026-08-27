import type { Task } from "@/lib/api";
import { byDueDate, countDueAlerts, dueRemainingLabel, dueTone, formatDay, formatDate } from "@/lib/demo-data";
import {
  type DocBlock,
  type ExportFormat,
  downloadDocx,
  downloadMarkdown,
} from "@/lib/export-office";
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

function statusLine(open: Task[], extra?: { people?: number }): string {
  const alerts = countDueAlerts(open);
  const parts = [
    extra?.people != null ? `${extra.people} kişi` : null,
    `${open.length} açık`,
    alerts.overdue ? `${alerts.overdue} gecikmiş` : null,
    alerts.soon ? `${alerts.soon} yaklaşan` : null,
  ].filter(Boolean);
  return parts.join(" · ");
}

function taskBlocks(tasks: Task[], showAssignee: boolean, empty: string): DocBlock[] {
  if (!tasks.length) return [{ kind: "p", text: empty }];
  return tasks.map((task, index) => {
    const extra = (task.description || task.notes || "").trim();
    return {
      kind: "item" as const,
      n: index + 1,
      text: task.title.trim() || "Görev",
      meta: taskMeta(task, showAssignee),
      extra: extra && extra !== task.title.trim() ? extra : undefined,
    };
  });
}

function openGroupBlocks(tasks: Task[], showAssignee: boolean): DocBlock[] {
  const { overdue, soon, rest } = splitOpen(tasks);
  if (!tasks.length) return [{ kind: "p", text: "Açık görev yok." }];
  const blocks: DocBlock[] = [];
  if (overdue.length) {
    blocks.push({ kind: "h2", text: "Süresi geçen" });
    blocks.push(...taskBlocks(overdue, showAssignee, ""));
  }
  if (soon.length) {
    blocks.push({ kind: "h2", text: "Yaklaşan" });
    blocks.push(...taskBlocks(soon, showAssignee, ""));
  }
  if (rest.length) {
    blocks.push({ kind: "h2", text: overdue.length || soon.length ? "Diğer açık görevler" : "Açık görevler" });
    blocks.push(...taskBlocks(rest, showAssignee, ""));
  }
  return blocks;
}

async function downloadBlocks(blocks: DocBlock[], format: ExportFormat, filename: string): Promise<void> {
  if (format === "markdown") {
    downloadMarkdown(blocks, `${filename}.md`);
    return;
  }
  if (format === "docx") {
    await downloadDocx(blocks, `${filename}.docx`);
    return;
  }
}

function personBlocks(person: PersonExportInput): DocBlock[] {
  const open = [...person.open].sort(byDueDate);
  const done = [...person.done].sort(byDueDate);
  const blocks: DocBlock[] = [
    { kind: "kicker", text: "Kişi raporu" },
    { kind: "title", text: person.name },
    { kind: "meta", text: todayLine() },
  ];
  if (person.note?.trim()) blocks.push({ kind: "meta", text: person.note.trim() });
  blocks.push({ kind: "p", text: statusLine(open) });
  blocks.push(...openGroupBlocks(open, false));
  blocks.push({ kind: "h2", text: "Tamamlanan görevler" });
  blocks.push(...taskBlocks(done, false, "Tamamlanan görev yok."));
  if (person.meetings.length) {
    blocks.push({ kind: "h2", text: "Toplantılar" });
    person.meetings.forEach((meeting, index) => {
      blocks.push({
        kind: "item",
        n: index + 1,
        text: meeting.title,
        meta: meeting.date ? formatDay(meeting.date) : "Tarih yok",
      });
    });
  }
  return blocks;
}

function rosterBlocks(rows: PeopleRosterRow[]): DocBlock[] {
  const withOpen = rows.filter((row) => row.open.length > 0);
  const openTasks = withOpen.flatMap((row) => row.open);
  const blocks: DocBlock[] = [
    { kind: "kicker", text: "Kişiler raporu" },
    { kind: "title", text: "Kişiler ve açık görevler" },
    { kind: "meta", text: todayLine() },
    { kind: "p", text: statusLine(openTasks, { people: withOpen.length }) },
  ];
  if (!withOpen.length) {
    blocks.push({ kind: "p", text: "Listede açık görev yok." });
    return blocks;
  }
  for (const row of withOpen) {
    blocks.push({ kind: "h2", text: row.name });
    if (row.note?.trim()) blocks.push({ kind: "p", text: row.note.trim() });
    blocks.push({ kind: "p", text: statusLine(row.open) });
    blocks.push(...taskBlocks([...row.open].sort(byDueDate), false, "Açık görev yok."));
  }
  return blocks;
}

function openTasksBlocks(input: OpenTasksExportInput): DocBlock[] {
  const tasks = [...input.tasks].sort(byDueDate);
  const title = input.title?.trim() || "Açık görevler";
  const blocks: DocBlock[] = [
    { kind: "kicker", text: "Görev raporu" },
    { kind: "title", text: title },
    { kind: "meta", text: todayLine() },
  ];
  if (input.subtitle?.trim()) blocks.push({ kind: "meta", text: input.subtitle.trim() });
  blocks.push({ kind: "p", text: statusLine(tasks) });
  blocks.push(...openGroupBlocks(tasks, input.showAssignee !== false));
  return blocks;
}

export async function downloadPersonReport(person: PersonExportInput, format: ExportFormat = "pdf"): Promise<void> {
  const stem = `${fileStem(person.name)} Görevler Rapor`;
  if (format !== "pdf") {
    await downloadBlocks(personBlocks(person), format, stem);
    return;
  }
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
  triggerDownload(new Uint8Array(doc.output("arraybuffer")), `${stem}.pdf`);
}

export async function downloadPeopleRoster(rows: PeopleRosterRow[], format: ExportFormat = "pdf"): Promise<void> {
  const stem = "Kişiler Açık Görevler Rapor";
  if (format !== "pdf") {
    await downloadBlocks(rosterBlocks(rows), format, stem);
    return;
  }
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
  triggerDownload(new Uint8Array(doc.output("arraybuffer")), `${stem}.pdf`);
}

export async function downloadOpenTasksReport(input: OpenTasksExportInput, format: ExportFormat = "pdf"): Promise<void> {
  const title = input.title?.trim() || "Açık görevler";
  const stem = `${fileStem(title)} Rapor`;
  if (format !== "pdf") {
    await downloadBlocks(openTasksBlocks(input), format, stem);
    return;
  }
  await readyMeasure();
  const { doc, ctx } = await newDocument();
  const tasks = [...input.tasks].sort(byDueDate);
  writeCover(ctx, "GÖREV RAPORU", title, [todayLine(), input.subtitle?.trim() || ""]);
  writeStatusLine(ctx, tasks);
  writeOpenGroups(ctx, tasks, input.showAssignee !== false);
  writeFooters(doc);
  triggerDownload(new Uint8Array(doc.output("arraybuffer")), `${stem}.pdf`);
}
