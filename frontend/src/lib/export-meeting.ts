import type { ActionItem, Decision, MeetingDetail, TranscriptLine } from "@/lib/api";
import { formatDay, formatDuration, formatTimestamp } from "@/lib/demo-data";
import {
  type DocBlock,
  type ExportFormat,
  docxBytes,
  downloadDocx,
  downloadMarkdown,
  downloadZip,
  markdownBytes,
} from "@/lib/export-office";
import { speakerStats } from "@/lib/speaker-stats";
import { talkColorRgb } from "@/lib/talk-colors";
import {
  CONTENT_W,
  INK,
  MARGIN,
  MUTED,
  NUM_W,
  PAGE_W,
  RULE,
  TEAL,
  type Ctx,
  ensure,
  fileStem,
  measureMm,
  newDocument,
  readyMeasure,
  sectionHeading,
  setType,
  triggerDownload,
  wrapToWidth,
  writeCover,
  writeFooters,
  writeNumberedBody,
  writeWrapped,
} from "@/lib/export-pdf";

export type TranscriptMode = "include" | "attach" | "omit";

export type MeetingExportOptions = {
  format: ExportFormat;
  transcript: TranscriptMode;
  actionSeqs: number[];
  talkShare: boolean;
  notes?: string;
};

type ExportCopy = {
  locale: string;
  kicker: string;
  transcriptKicker: string;
  summary: string;
  summaryEmpty: string;
  decisions: string;
  decisionsEmpty: string;
  actions: string;
  actionsEmpty: string;
  transcript: string;
  transcriptEmpty: string;
  talkShare: string;
  attendees: string;
  duration: string;
  notes: string;
  dateMissing: string;
  timeJoin: string;
  owner: string;
  date: string;
  done: string;
  ongoing: string;
  suggested: string;
  report: string;
  meeting: string;
  stemFallback: string;
};

const COPY_TR: ExportCopy = {
  locale: "tr-TR",
  kicker: "TOPLANTI TUTANAĞI",
  transcriptKicker: "TRANSKRİPT",
  summary: "Özet",
  summaryEmpty: "Özet yok.",
  decisions: "Kararlar",
  decisionsEmpty: "Alınan karar yok.",
  actions: "Aksiyonlar",
  actionsEmpty: "Seçili aksiyon yok.",
  transcript: "Transkript",
  transcriptEmpty: "Transkript yok.",
  talkShare: "Kim ne kadar konuştu",
  attendees: "Katılanlar",
  duration: "Süre",
  notes: "Not",
  dateMissing: "Tarih belirtilmedi",
  timeJoin: ", saat ",
  owner: "Sorumlu",
  date: "Tarih",
  done: "Tamamlandı",
  ongoing: "Devam ediyor",
  suggested: "Öneri",
  report: "Rapor",
  meeting: "Toplantı",
  stemFallback: "tutanak",
};

const COPY_EN: ExportCopy = {
  locale: "en-US",
  kicker: "MEETING MINUTES",
  transcriptKicker: "TRANSCRIPT",
  summary: "Summary",
  summaryEmpty: "No summary.",
  decisions: "Decisions",
  decisionsEmpty: "No decisions taken.",
  actions: "Actions",
  actionsEmpty: "No actions selected.",
  transcript: "Transcript",
  transcriptEmpty: "No transcript.",
  talkShare: "Talk time",
  attendees: "Attendees",
  duration: "Duration",
  notes: "Notes",
  dateMissing: "Date not specified",
  timeJoin: ", ",
  owner: "Owner",
  date: "Due",
  done: "Done",
  ongoing: "In progress",
  suggested: "Suggested",
  report: "Report",
  meeting: "Meeting",
  stemFallback: "minutes",
};

function isEnglishMeeting(meeting: MeetingDetail): boolean {
  const lang = (meeting.language || "").trim().toLowerCase();
  if (lang === "en" || lang === "eng" || lang === "english") return true;
  const headings = (meeting.summary || "")
    .split(/\n+/)
    .map((part) => part.trim().toLowerCase());
  return headings.includes("context") && headings.includes("agenda");
}

function copyFor(meeting: MeetingDetail): ExportCopy {
  return isEnglishMeeting(meeting) ? COPY_EN : COPY_TR;
}

function heading(ctx: Ctx, title: string, locale: string): void {
  sectionHeading(ctx, title, TEAL, RULE, locale);
}

function clock(iso: string | null, locale: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

function trimmedNotes(options: MeetingExportOptions): string {
  return options.notes?.trim() ?? "";
}

function writeNotes(ctx: Ctx, notes: string, copy: ExportCopy): void {
  if (!notes) return;
  heading(ctx, copy.notes, copy.locale);
  writeWrapped(ctx, notes, 11, "normal", INK);
}

function writeSummary(ctx: Ctx, summary: string | null, copy: ExportCopy): void {
  heading(ctx, copy.summary, copy.locale);
  if (!summary?.trim()) {
    writeWrapped(ctx, copy.summaryEmpty, 11, "normal", MUTED);
    return;
  }
  const headings = new Set(["çerçeve", "gündem akışı", "sonuç", "context", "agenda", "outcome"]);
  for (const para of summary.split(/\n+/).map((part) => part.trim()).filter(Boolean)) {
    const key = para.toLocaleLowerCase("tr-TR");
    if (!headings.has(key)) {
      writeWrapped(ctx, para, 11, "normal", INK, 4);
      continue;
    }
    const label = key === "gündem akışı" ? "Gündem Akışı" : para;
    writeWrapped(ctx, label, 12, "bold", TEAL, 3);
  }
}

function stampRange(item: Decision): string {
  if (item.timestamp == null) return "";
  const start = formatTimestamp(item.timestamp);
  if (item.end_timestamp != null && item.end_timestamp !== item.timestamp) {
    return `${start}–${formatTimestamp(item.end_timestamp)}`;
  }
  return start;
}

function writeDecisions(ctx: Ctx, items: Decision[], copy: ExportCopy): void {
  heading(ctx, copy.decisions, copy.locale);
  if (!items.length) {
    writeWrapped(ctx, copy.decisionsEmpty, 11, "normal", MUTED);
    return;
  }
  items.forEach((item, index) => {
    writeNumberedBody(ctx, index + 1, item.text);
    const stamp = stampRange(item);
    if (stamp) writeWrapped(ctx, stamp, 9, "normal", MUTED, 5, CONTENT_W - NUM_W, MARGIN + NUM_W);
    else ctx.y += 3;
  });
}

function writeActions(ctx: Ctx, items: ActionItem[], copy: ExportCopy): void {
  heading(ctx, copy.actions, copy.locale);
  if (!items.length) {
    writeWrapped(ctx, copy.actionsEmpty, 11, "normal", MUTED);
    return;
  }
  items.forEach((item, index) => {
    writeNumberedBody(ctx, index + 1, item.description);
    const bits = [
      item.assignee?.trim() ? `${copy.owner}: ${item.assignee}` : null,
      item.due_date ? `${copy.date}: ${formatDay(item.due_date, copy.locale)}` : null,
      item.task_status === "done" ? copy.done : item.task_status ? copy.ongoing : copy.suggested,
    ].filter(Boolean);
    writeWrapped(ctx, bits.join(" · "), 9, "normal", MUTED, 1.8, CONTENT_W - NUM_W, MARGIN + NUM_W);
    if (item.notes.trim() && item.notes.trim() !== item.description.trim()) {
      writeWrapped(ctx, item.notes, 10, "normal", MUTED, 4.5, CONTENT_W - NUM_W, MARGIN + NUM_W);
    } else {
      ctx.y += 3.5;
    }
  });
}

function writeTranscriptLines(ctx: Ctx, lines: TranscriptLine[], copy: ExportCopy): void {
  if (!lines.length) {
    writeWrapped(ctx, copy.transcriptEmpty, 11, "normal", MUTED);
    return;
  }
  const size = 9;
  const lineH = size * 0.46;
  for (const line of lines) {
    const stamp = formatTimestamp(line.timestamp);
    const who = line.speaker || "—";
    const body = wrapToWidth(line.text || " ", CONTENT_W, size, false);
    ensure(ctx, lineH * (body.length + 1) + 10);
    ctx.y += 2;
    setType(ctx, "bold", size, TEAL);
    ctx.doc.text(stamp, MARGIN, ctx.y);
    setType(ctx, "bold", size, INK);
    ctx.doc.text(who, MARGIN + measureMm(stamp, size, true) + 2, ctx.y);
    ctx.y += lineH + 1.6;
    setType(ctx, "normal", size, INK);
    for (const text of body) {
      ensure(ctx, lineH + 1);
      ctx.doc.text(text, MARGIN, ctx.y);
      ctx.y += lineH;
    }
    ctx.y += 2;
    ctx.doc.setDrawColor(230, 239, 237);
    ctx.doc.setLineWidth(0.2);
    ctx.doc.line(MARGIN, ctx.y, PAGE_W - MARGIN, ctx.y);
    ctx.y += 3.2;
  }
}

function writeTranscriptDocument(ctx: Ctx, meeting: MeetingDetail): void {
  const copy = copyFor(meeting);
  writeHeader(ctx, meeting, copy.transcriptKicker);
  heading(ctx, copy.transcript, copy.locale);
  writeTranscriptLines(ctx, meeting.transcript, copy);
}

function writeTalkShare(ctx: Ctx, meeting: MeetingDetail): void {
  const copy = copyFor(meeting);
  const rows = speakerStats(meeting.transcript, meeting.duration, () => false);
  if (!rows.length) return;
  heading(ctx, copy.talkShare, copy.locale);
  const barH = 3.2;
  const gap = 0.4;
  const visible = rows.filter((row) => row.share >= 1);
  ensure(ctx, barH + 10);
  if (visible.length) {
    const total = visible.reduce((sum, row) => sum + row.share, 0) || 1;
    const inner = CONTENT_W - gap * Math.max(0, visible.length - 1);
    let x = MARGIN;
    for (const row of visible) {
      const index = rows.indexOf(row);
      const width = (row.share / total) * inner;
      ctx.doc.setFillColor(...talkColorRgb(index));
      ctx.doc.rect(x, ctx.y, Math.max(width, 0.8), barH, "F");
      x += width + gap;
    }
  }
  ctx.y += barH + 6;

  const colGap = 8;
  const colW = (CONTENT_W - colGap) / 2;
  rows.forEach((row, index) => {
    const col = index % 2;
    if (col === 0) ensure(ctx, 8);
    const x0 = MARGIN + col * (colW + colGap);
    const y = ctx.y;
    ctx.doc.setFillColor(...talkColorRgb(index));
    ctx.doc.circle(x0 + 1.5, y - 1, 1.2, "F");
    const stats = `${formatDuration(row.seconds, copy.locale)} · %${row.share}`;
    setType(ctx, "normal", 8, MUTED);
    const statsW = measureMm(stats, 8, false);
    const nameW = colW - statsW - 8;
    const name = wrapToWidth(row.name, nameW, 10, true)[0] || row.name;
    setType(ctx, "bold", 10, INK);
    ctx.doc.text(name, x0 + 4.4, y);
    setType(ctx, "normal", 8, MUTED);
    ctx.doc.text(stats, x0 + colW, y, { align: "right" });
    if (col === 1 || index === rows.length - 1) ctx.y = y + 6.4;
  });
  ctx.y += 2;
}

function writeHeader(ctx: Ctx, meeting: MeetingDetail, kicker?: string): void {
  const copy = copyFor(meeting);
  const when = [formatDay(meeting.date, copy.locale), clock(meeting.date, copy.locale)]
    .filter(Boolean)
    .join(copy.timeJoin);
  writeCover(ctx, kicker || copy.kicker, meeting.title, [
    `${when || copy.dateMissing}  ·  ${copy.duration}: ${formatDuration(meeting.duration, copy.locale)}`,
    `${copy.attendees}: ${(meeting.named_attendees || meeting.attendees || "").trim() || "—"}`,
  ]);
}

function selectedActions(meeting: MeetingDetail, seqs: number[]): ActionItem[] {
  const allow = new Set(seqs);
  return meeting.actions.filter((item) => allow.has(item.seq));
}

function meetingMetaLines(meeting: MeetingDetail): string[] {
  const copy = copyFor(meeting);
  const when = [formatDay(meeting.date, copy.locale), clock(meeting.date, copy.locale)]
    .filter(Boolean)
    .join(copy.timeJoin);
  return [
    `${when || copy.dateMissing}  ·  ${copy.duration}: ${formatDuration(meeting.duration, copy.locale)}`,
    `${copy.attendees}: ${(meeting.named_attendees || meeting.attendees || "").trim() || "—"}`,
  ];
}

function summaryBlocks(summary: string | null, copy: ExportCopy): DocBlock[] {
  const blocks: DocBlock[] = [{ kind: "h2", text: copy.summary }];
  if (!summary?.trim()) {
    blocks.push({ kind: "p", text: copy.summaryEmpty });
    return blocks;
  }
  const headings = new Set(["çerçeve", "gündem akışı", "sonuç", "context", "agenda", "outcome"]);
  for (const para of summary.split(/\n+/).map((part) => part.trim()).filter(Boolean)) {
    const key = para.toLocaleLowerCase("tr-TR");
    if (headings.has(key)) {
      blocks.push({ kind: "h2", text: key === "gündem akışı" ? "Gündem Akışı" : para });
      continue;
    }
    blocks.push({ kind: "p", text: para });
  }
  return blocks;
}

function actionMeta(item: ActionItem, copy: ExportCopy): string {
  return [
    item.assignee?.trim() ? `${copy.owner}: ${item.assignee}` : null,
    item.due_date ? `${copy.date}: ${formatDay(item.due_date, copy.locale)}` : null,
    item.task_status === "done" ? copy.done : item.task_status ? copy.ongoing : copy.suggested,
  ]
    .filter(Boolean)
    .join(" · ");
}

function transcriptBlocks(lines: TranscriptLine[], copy: ExportCopy): DocBlock[] {
  if (!lines.length) return [{ kind: "p", text: copy.transcriptEmpty }];
  const blocks: DocBlock[] = [];
  for (const line of lines) {
    const who = line.speaker || "—";
    blocks.push({ kind: "p", text: `${formatTimestamp(line.timestamp)}  ${who}\n${(line.text || "").trim()}` });
  }
  return blocks;
}

function talkShareBlocks(meeting: MeetingDetail): DocBlock[] {
  const copy = copyFor(meeting);
  const rows = speakerStats(meeting.transcript, meeting.duration, () => false);
  if (!rows.length) return [];
  return [
    { kind: "h2", text: copy.talkShare },
    ...rows.map((row) => ({
      kind: "p" as const,
      text: `${row.name}: ${formatDuration(row.seconds, copy.locale)} · %${row.share}`,
    })),
  ];
}

function reportBlocks(meeting: MeetingDetail, options: MeetingExportOptions): DocBlock[] {
  const copy = copyFor(meeting);
  const actions = selectedActions(meeting, options.actionSeqs);
  const blocks: DocBlock[] = [
    { kind: "kicker", text: copy.kicker },
    { kind: "title", text: meeting.title.trim() || copy.meeting },
    ...meetingMetaLines(meeting).map((text) => ({ kind: "meta" as const, text })),
    ...(trimmedNotes(options)
      ? ([{ kind: "h2" as const, text: copy.notes }, { kind: "p" as const, text: trimmedNotes(options) }] as DocBlock[])
      : []),
    ...summaryBlocks(meeting.summary, copy),
    { kind: "h2", text: copy.decisions },
  ];
  if (!meeting.decisions.length) {
    blocks.push({ kind: "p", text: copy.decisionsEmpty });
  } else {
    meeting.decisions.forEach((item: Decision, index) => {
      blocks.push({
        kind: "item",
        n: index + 1,
        text: item.text,
        meta: stampRange(item) || undefined,
      });
    });
  }
  blocks.push({ kind: "h2", text: copy.actions });
  if (!actions.length) {
    blocks.push({ kind: "p", text: copy.actionsEmpty });
  } else {
    actions.forEach((item, index) => {
      const extra = item.notes.trim() && item.notes.trim() !== item.description.trim() ? item.notes : undefined;
      blocks.push({ kind: "item", n: index + 1, text: item.description, meta: actionMeta(item, copy), extra });
    });
  }
  if (options.transcript === "include") {
    if (options.talkShare) blocks.push(...talkShareBlocks(meeting));
    blocks.push({ kind: "h2", text: copy.transcript });
    blocks.push(...transcriptBlocks(meeting.transcript, copy));
  }
  return blocks;
}

function transcriptOnlyBlocks(meeting: MeetingDetail): DocBlock[] {
  const copy = copyFor(meeting);
  return [
    { kind: "kicker", text: copy.transcript },
    { kind: "title", text: meeting.title.trim() || copy.meeting },
    ...meetingMetaLines(meeting).map((text) => ({ kind: "meta" as const, text })),
    { kind: "h2", text: copy.transcript },
    ...transcriptBlocks(meeting.transcript, copy),
  ];
}

function transcriptPlainText(meeting: MeetingDetail): string {
  const body = meeting.transcript.map((line) => {
    const who = line.speaker || "—";
    return `${formatTimestamp(line.timestamp)}  ${who}\n${line.text.trim()}`;
  });
  return `\uFEFF${[meeting.title.trim(), "", ...body].join("\n\n")}\n`;
}

async function buildTranscriptPdf(meeting: MeetingDetail): Promise<Uint8Array> {
  const extra = await newDocument();
  writeTranscriptDocument(extra.ctx, meeting);
  writeFooters(extra.doc);
  return new Uint8Array(extra.doc.output("arraybuffer"));
}

async function buildMeetingPdfBytes(meeting: MeetingDetail, options: MeetingExportOptions): Promise<Uint8Array> {
  await readyMeasure();
  const copy = copyFor(meeting);
  const actions = selectedActions(meeting, options.actionSeqs);
  const { doc, ctx } = await newDocument();
  writeHeader(ctx, meeting);
  writeNotes(ctx, trimmedNotes(options), copy);
  writeSummary(ctx, meeting.summary, copy);
  writeDecisions(ctx, meeting.decisions, copy);
  writeActions(ctx, actions, copy);
  if (options.transcript === "include") {
    if (options.talkShare) writeTalkShare(ctx, meeting);
    heading(ctx, copy.transcript, copy.locale);
    writeTranscriptLines(ctx, meeting.transcript, copy);
  }
  writeFooters(doc);
  return new Uint8Array(doc.output("arraybuffer"));
}

export async function previewMeetingReport(
  meeting: MeetingDetail,
  options: MeetingExportOptions,
): Promise<Blob> {
  const bytes = await buildMeetingPdfBytes(meeting, options);
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return new Blob([copy], { type: "application/pdf" });
}

export async function downloadMeetingReport(
  meeting: MeetingDetail,
  options: MeetingExportOptions,
): Promise<void> {
  const copy = copyFor(meeting);
  const stem = fileStem(meeting.title, copy.stemFallback);
  const reportName = `${stem} ${copy.report}`;
  const transcriptName = `${stem} ${copy.transcript}`;
  if (options.format !== "pdf") {
    const report = reportBlocks(meeting, options);
    if (options.transcript === "attach") {
      const extra = transcriptOnlyBlocks(meeting);
      if (options.format === "markdown") {
        await downloadZip(
          {
            [`${reportName}.md`]: markdownBytes(report),
            [`${transcriptName}.md`]: markdownBytes(extra),
          },
          `${reportName}.zip`,
        );
        return;
      }
      await downloadZip(
        {
          [`${reportName}.docx`]: await docxBytes(report),
          [`${transcriptName}.docx`]: await docxBytes(extra),
        },
        `${reportName}.zip`,
      );
      return;
    }
    if (options.format === "markdown") {
      downloadMarkdown(report, `${reportName}.md`);
      return;
    }
    await downloadDocx(report, `${reportName}.docx`);
    return;
  }

  const reportBytes = await buildMeetingPdfBytes(meeting, options);
  if (options.transcript === "attach") {
    const transcriptFile = await buildTranscriptPdf(meeting);
    const { strToU8, zipSync } = await import("fflate");
    const zipped = zipSync({
      [`${reportName}.pdf`]: reportBytes,
      [`${transcriptName}.pdf`]: transcriptFile,
      [`${transcriptName}.txt`]: strToU8(transcriptPlainText(meeting)),
    });
    triggerDownload(zipped, `${reportName}.zip`, "application/zip");
    return;
  }

  triggerDownload(reportBytes, `${reportName}.pdf`);
}
