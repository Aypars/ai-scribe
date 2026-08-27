import type { ActionItem, Decision, MeetingDetail, TranscriptLine } from "@/lib/api";
import { formatDay, formatDuration, formatTimestamp } from "@/lib/demo-data";
import {
  CONTENT_W,
  INK,
  MARGIN,
  MUTED,
  NUM_W,
  PAGE_W,
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
  transcript: TranscriptMode;
  actionSeqs: number[];
};

function clock(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function writeSummary(ctx: Ctx, summary: string | null): void {
  sectionHeading(ctx, "Özet");
  if (!summary?.trim()) {
    writeWrapped(ctx, "Özet yok.", 11, "normal", MUTED);
    return;
  }
  const headings = new Set(["çerçeve", "gündem akışı", "sonuç"]);
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

function writeDecisions(ctx: Ctx, items: Decision[]): void {
  sectionHeading(ctx, "Kararlar");
  if (!items.length) {
    writeWrapped(ctx, "Alınan karar yok.", 11, "normal", MUTED);
    return;
  }
  items.forEach((item, index) => {
    writeNumberedBody(ctx, index + 1, item.text);
    const stamp = stampRange(item);
    if (stamp) writeWrapped(ctx, stamp, 9, "normal", MUTED, 5, CONTENT_W - NUM_W, MARGIN + NUM_W);
    else ctx.y += 3;
  });
}

function writeActions(ctx: Ctx, items: ActionItem[]): void {
  sectionHeading(ctx, "Aksiyonlar");
  if (!items.length) {
    writeWrapped(ctx, "Seçili aksiyon yok.", 11, "normal", MUTED);
    return;
  }
  items.forEach((item, index) => {
    writeNumberedBody(ctx, index + 1, item.description);
    const bits = [
      item.assignee?.trim() ? `Sorumlu: ${item.assignee}` : null,
      item.due_date ? `Tarih: ${formatDay(item.due_date)}` : null,
      item.task_status === "done" ? "Tamamlandı" : item.task_status ? "Devam ediyor" : "Öneri",
    ].filter(Boolean);
    writeWrapped(ctx, bits.join(" · "), 9, "normal", MUTED, 1.8, CONTENT_W - NUM_W, MARGIN + NUM_W);
    if (item.notes.trim() && item.notes.trim() !== item.description.trim()) {
      writeWrapped(ctx, item.notes, 10, "normal", MUTED, 4.5, CONTENT_W - NUM_W, MARGIN + NUM_W);
    } else {
      ctx.y += 3.5;
    }
  });
}

function writeTranscriptLines(ctx: Ctx, lines: TranscriptLine[]): void {
  if (!lines.length) {
    writeWrapped(ctx, "Transkript yok.", 11, "normal", MUTED);
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

function writeTranscriptDocument(ctx: Ctx, meeting: MeetingDetail, kicker = "TRANSKRİPT"): void {
  writeHeader(ctx, meeting, kicker);
  sectionHeading(ctx, "Transkript");
  writeTranscriptLines(ctx, meeting.transcript);
}

function writeHeader(ctx: Ctx, meeting: MeetingDetail, kicker = "TOPLANTI TUTANAĞI"): void {
  const when = [formatDay(meeting.date), clock(meeting.date)].filter(Boolean).join(", saat ");
  writeCover(ctx, kicker, meeting.title, [
    `${when || "Tarih belirtilmedi"}  ·  Süre: ${formatDuration(meeting.duration)}`,
    `Katılanlar: ${(meeting.named_attendees || meeting.attendees || "").trim() || "—"}`,
  ]);
}

function selectedActions(meeting: MeetingDetail, seqs: number[]): ActionItem[] {
  const allow = new Set(seqs);
  return meeting.actions.filter((item) => allow.has(item.seq));
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

export async function downloadMeetingReport(
  meeting: MeetingDetail,
  options: MeetingExportOptions,
): Promise<void> {
  await readyMeasure();
  const stem = fileStem(meeting.title);
  const actions = selectedActions(meeting, options.actionSeqs);
  const { doc, ctx } = await newDocument();
  writeHeader(ctx, meeting);
  writeSummary(ctx, meeting.summary);
  writeDecisions(ctx, meeting.decisions);
  writeActions(ctx, actions);

  if (options.transcript === "include") {
    sectionHeading(ctx, "Transkript");
    writeTranscriptLines(ctx, meeting.transcript);
    writeFooters(doc);
    triggerDownload(new Uint8Array(doc.output("arraybuffer")), `${stem} Rapor.pdf`);
    return;
  }

  if (options.transcript === "attach") {
    writeFooters(doc);
    const reportBytes = new Uint8Array(doc.output("arraybuffer"));
    const transcriptBytes = await buildTranscriptPdf(meeting);
    const { strToU8, zipSync } = await import("fflate");
    const zipped = zipSync({
      [`${stem} Rapor.pdf`]: reportBytes,
      [`${stem} Transkript.pdf`]: transcriptBytes,
      [`${stem} Transkript.txt`]: strToU8(transcriptPlainText(meeting)),
    });
    triggerDownload(zipped, `${stem} Rapor.zip`, "application/zip");
    return;
  }

  writeFooters(doc);
  triggerDownload(new Uint8Array(doc.output("arraybuffer")), `${stem} Rapor.pdf`);
}
