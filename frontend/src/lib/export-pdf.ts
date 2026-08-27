import type { jsPDF } from "jspdf";

export const PAGE_W = 210;
export const PAGE_H = 297;
export const MARGIN = 16;
export const FOOTER = 14;
export const CONTENT_W = PAGE_W - MARGIN * 2;
export const NUM_W = 10;

export const TEAL: [number, number, number] = [15, 118, 110];
export const INK: [number, number, number] = [18, 51, 47];
export const MUTED: [number, number, number] = [91, 113, 110];
export const RULE: [number, number, number] = [205, 229, 225];
export const ROSE: [number, number, number] = [190, 18, 60];
export const AMBER: [number, number, number] = [180, 83, 9];
export const EMERALD: [number, number, number] = [4, 120, 87];
export const ROSE_RULE: [number, number, number] = [252, 210, 216];
export const AMBER_RULE: [number, number, number] = [253, 224, 180];
export const EMERALD_RULE: [number, number, number] = [187, 227, 211];

export type Pdf = jsPDF;
export type Ctx = { doc: Pdf; y: number };

let fontPack: { regular: string; bold: string } | null = null;
let measureReady = false;
let measureCanvas: CanvasRenderingContext2D | null = null;

export function fileStem(title: string, fallback = "tutanak"): string {
  const clean = title
    .replace(/[<>:"/\\|?*]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  return clean || fallback;
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode(...bytes.subarray(i, i + step));
  }
  return btoa(binary);
}

async function fontBase64(path: string): Promise<string> {
  const response = await fetch(path);
  if (!response.ok) throw new Error("Font yüklenemedi");
  return toBase64(await response.arrayBuffer());
}

async function loadFonts(doc: Pdf): Promise<void> {
  if (!fontPack) {
    const [regular, bold] = await Promise.all([
      fontBase64("/fonts/NotoSans-Regular.ttf"),
      fontBase64("/fonts/NotoSans-Bold.ttf"),
    ]);
    fontPack = { regular, bold };
  }
  doc.addFileToVFS("NotoSans-Regular.ttf", fontPack.regular);
  doc.addFileToVFS("NotoSans-Bold.ttf", fontPack.bold);
  doc.addFont("NotoSans-Regular.ttf", "NotoSans", "normal", "Identity-H");
  doc.addFont("NotoSans-Bold.ttf", "NotoSans", "bold", "Identity-H");
  doc.setFont("NotoSans", "normal");
}

export async function readyMeasure(): Promise<void> {
  if (measureReady) return;
  const regular = new FontFace("NotoSansPdf", "url(/fonts/NotoSans-Regular.ttf)", { weight: "400" });
  const bold = new FontFace("NotoSansPdf", "url(/fonts/NotoSans-Bold.ttf)", { weight: "700" });
  await Promise.all([regular.load(), bold.load()]);
  document.fonts.add(regular);
  document.fonts.add(bold);
  const canvas = document.createElement("canvas");
  measureCanvas = canvas.getContext("2d");
  measureReady = true;
}

export function measureMm(text: string, sizePt: number, bold: boolean): number {
  if (!measureCanvas) return text.length * sizePt * 0.2;
  measureCanvas.font = `${bold ? 700 : 400} ${sizePt}pt "NotoSansPdf"`;
  return (measureCanvas.measureText(text).width / 96) * 25.4;
}

export function wrapToWidth(text: string, widthMm: number, sizePt: number, bold: boolean): string[] {
  const source = text.trim() || " ";
  const words = source.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  const limit = widthMm * 0.88;
  const fits = (value: string) => measureMm(value, sizePt, bold) <= limit;

  const breakWord = (word: string) => {
    let chunk = "";
    for (const ch of word) {
      const trial = chunk + ch;
      if (chunk && !fits(trial)) {
        lines.push(chunk);
        chunk = ch;
      } else {
        chunk = trial;
      }
    }
    current = chunk;
  };

  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (fits(next)) {
      current = next;
      continue;
    }
    if (current) lines.push(current);
    if (!fits(word)) breakWord(word);
    else current = word;
  }
  if (current) lines.push(current);
  return lines.length ? lines : [source];
}

export function ensure(ctx: Ctx, needed: number): void {
  if (ctx.y + needed <= PAGE_H - FOOTER) return;
  ctx.doc.addPage();
  ctx.y = MARGIN;
}

export function setType(
  ctx: Ctx,
  style: "normal" | "bold",
  size: number,
  color: [number, number, number],
): void {
  ctx.doc.setFont("NotoSans", style);
  ctx.doc.setFontSize(size);
  ctx.doc.setTextColor(...color);
}

export function lineHeight(size: number): number {
  return size * 0.52;
}

export function writeWrapped(
  ctx: Ctx,
  text: string,
  size: number,
  style: "normal" | "bold",
  color: [number, number, number],
  gap = 3.2,
  width = CONTENT_W,
  x = MARGIN,
): void {
  if (!text) return;
  setType(ctx, style, size, color);
  const lines = wrapToWidth(text, width, size, style === "bold");
  const lineH = lineHeight(size);
  for (const line of lines) {
    ensure(ctx, lineH + 1.2);
    ctx.doc.text(line, x, ctx.y);
    ctx.y += lineH;
  }
  ctx.y += gap;
}

export function sectionHeading(
  ctx: Ctx,
  title: string,
  color: [number, number, number] = TEAL,
  rule: [number, number, number] = RULE,
  locale = "tr-TR",
): void {
  ensure(ctx, 18);
  ctx.y += 6;
  setType(ctx, "bold", 10, color);
  ctx.doc.text(title.toLocaleUpperCase(locale), MARGIN, ctx.y);
  ctx.y += 2.6;
  ctx.doc.setDrawColor(...rule);
  ctx.doc.setLineWidth(0.35);
  ctx.doc.line(MARGIN, ctx.y, PAGE_W - MARGIN, ctx.y);
  ctx.y += 8;
}

export function writeCover(ctx: Ctx, kicker: string, title: string, lines: string[]): void {
  setType(ctx, "bold", 9, TEAL);
  ctx.doc.text(kicker, MARGIN, ctx.y);
  ctx.y += 8;
  writeWrapped(ctx, title, 16, "bold", INK, 4);
  for (const line of lines.filter((item) => item.trim())) {
    writeWrapped(ctx, line, 10, "normal", MUTED, 2.2);
  }
}

export function writeInline(
  ctx: Ctx,
  parts: { text: string; color: [number, number, number]; bold?: boolean }[],
  size = 10,
  gap = 2.2,
): void {
  const visible = parts.filter((part) => part.text);
  if (!visible.length) return;
  const lineH = lineHeight(size);
  ensure(ctx, lineH + 2);
  let x = MARGIN;
  for (const part of visible) {
    setType(ctx, part.bold ? "bold" : "normal", size, part.color);
    ctx.doc.text(part.text, x, ctx.y);
    x += measureMm(part.text, size, !!part.bold);
  }
  ctx.y += lineH + gap;
}

export function writeNumberedBody(
  ctx: Ctx,
  index: number,
  text: string,
  accent: [number, number, number] = TEAL,
): void {
  const prefix = `${index}.`;
  const body = wrapToWidth(text, CONTENT_W - NUM_W, 11, false);
  const lineH = lineHeight(11);
  ensure(ctx, lineH * body.length + 4);
  setType(ctx, "bold", 11, accent);
  ctx.doc.text(prefix, MARGIN, ctx.y);
  setType(ctx, "normal", 11, INK);
  body.forEach((line, lineIndex) => {
    if (lineIndex > 0) {
      ctx.y += lineH;
      ensure(ctx, lineH);
    }
    ctx.doc.text(line, MARGIN + NUM_W, ctx.y);
  });
  ctx.y += lineH + 1.6;
}

export function writeFooters(doc: Pdf): void {
  const total = doc.getNumberOfPages();
  for (let page = 1; page <= total; page += 1) {
    doc.setPage(page);
    doc.setFont("NotoSans", "normal");
    doc.setFontSize(8);
    doc.setTextColor(...MUTED);
    doc.text(`${page} / ${total}`, PAGE_W / 2, PAGE_H - 7, { align: "center" });
  }
}

export async function newDocument(): Promise<{ doc: Pdf; ctx: Ctx }> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4", compress: true });
  await loadFonts(doc);
  return { doc, ctx: { doc, y: MARGIN } };
}

export function triggerDownload(bytes: Uint8Array, filename: string, mime = "application/pdf"): void {
  const blob = new Blob([bytes as BlobPart], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}
