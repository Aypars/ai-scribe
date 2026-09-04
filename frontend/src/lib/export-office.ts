import { Document, HeadingLevel, Packer, Paragraph, TextRun } from "docx";

import { triggerDownload } from "@/lib/export-pdf";

export type ExportFormat = "pdf" | "docx" | "markdown";

export const FORMAT_CHOICES: { id: ExportFormat; title: string }[] = [
  { id: "pdf", title: "PDF" },
  { id: "docx", title: "Word" },
  { id: "markdown", title: "Markdown" },
];

export type DocBlock =
  | { kind: "kicker"; text: string }
  | { kind: "title"; text: string }
  | { kind: "meta"; text: string }
  | { kind: "h2"; text: string }
  | { kind: "h3"; text: string }
  | { kind: "p"; text: string }
  | { kind: "quote"; kicker: string; text: string }
  | { kind: "bullets"; items: string[] }
  | { kind: "item"; n: number; text: string; meta?: string; extra?: string };

function mdHeading(text: string): string {
  return text.replace(/^#+\s*/, "").trim();
}

function blank(lines: string[]): void {
  if (lines.length && lines[lines.length - 1] !== "") lines.push("");
}

export function blocksToMarkdown(blocks: DocBlock[]): string {
  const lines: string[] = [];
  for (const block of blocks) {
    if (block.kind === "kicker") {
      lines.push(`*${block.text}*`);
      lines.push("");
    } else if (block.kind === "title") {
      lines.push(`# ${mdHeading(block.text)}`);
      lines.push("");
    } else if (block.kind === "meta") {
      if (!block.text.trim()) continue;
      lines.push(`*${block.text}*`);
      lines.push("");
    } else if (block.kind === "h2") {
      blank(lines);
      lines.push("---");
      lines.push("");
      lines.push(`## ${mdHeading(block.text)}`);
      lines.push("");
    } else if (block.kind === "h3") {
      lines.push(`### ${mdHeading(block.text)}`);
      lines.push("");
    } else if (block.kind === "p") {
      const paras = block.text.split(/\n+/).map((part) => part.trim()).filter(Boolean);
      if (!paras.length) continue;
      lines.push(paras.join("\n\n"));
      lines.push("");
    } else if (block.kind === "quote") {
      lines.push(`**${block.kicker}**`);
      lines.push("");
      const body = block.text.trim() || " ";
      lines.push(
        body
          .split("\n")
          .map((line) => `> ${line || " "}`)
          .join("\n"),
      );
      lines.push("");
    } else if (block.kind === "bullets") {
      for (const item of block.items) {
        const cut = item.indexOf(" — ");
        if (cut > 0) {
          lines.push(`- **${item.slice(0, cut)}** — ${item.slice(cut + 3)}`);
        } else {
          lines.push(`- ${item}`);
        }
      }
      lines.push("");
    } else {
      lines.push(`${block.n}. **${block.text}**`);
      if (block.meta) {
        lines.push("");
        lines.push(`   *${block.meta}*`);
      }
      if (block.extra) {
        lines.push("");
        for (const extra of block.extra.split(/\n+/).map((part) => part.trim()).filter(Boolean)) {
          lines.push(`   ${extra}`);
        }
      }
      lines.push("");
    }
  }
  return `${lines.join("\n").trim()}\n`;
}

function runs(text: string, opts: { bold?: boolean; size?: number; color?: string; italics?: boolean } = {}): TextRun {
  return new TextRun({
    text,
    bold: opts.bold,
    italics: opts.italics,
    size: opts.size ?? 22,
    font: "Calibri",
    color: opts.color,
  });
}

export function blocksToParagraphs(blocks: DocBlock[]): Paragraph[] {
  const out: Paragraph[] = [];
  for (const block of blocks) {
    if (block.kind === "kicker") {
      out.push(new Paragraph({ spacing: { after: 80 }, children: [runs(block.text, { bold: true, size: 20, color: "0F766E" })] }));
    } else if (block.kind === "title") {
      out.push(
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          spacing: { after: 200 },
          children: [runs(block.text, { bold: true, size: 36 })],
        }),
      );
    } else if (block.kind === "meta") {
      if (!block.text.trim()) continue;
      out.push(new Paragraph({ spacing: { after: 80 }, children: [runs(block.text, { size: 20, color: "64748B" })] }));
    } else if (block.kind === "h2") {
      out.push(
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 280, after: 140 },
          children: [runs(block.text, { bold: true, size: 28, color: "0F766E" })],
        }),
      );
    } else if (block.kind === "h3") {
      out.push(
        new Paragraph({
          heading: HeadingLevel.HEADING_3,
          spacing: { before: 200, after: 100 },
          children: [runs(block.text, { bold: true, size: 24, color: "0F766E" })],
        }),
      );
    } else if (block.kind === "p") {
      for (const line of block.text.split("\n")) {
        out.push(new Paragraph({ spacing: { after: 120 }, children: [runs(line || " ", { size: 22 })] }));
      }
    } else if (block.kind === "quote") {
      out.push(
        new Paragraph({
          spacing: { before: 80, after: 40 },
          children: [runs(block.kicker, { bold: true, size: 20, color: "0F766E" })],
        }),
      );
      for (const line of block.text.split("\n")) {
        out.push(
          new Paragraph({
            spacing: { after: 80 },
            indent: { left: 240 },
            children: [runs(line || " ", { size: 22, italics: true })],
          }),
        );
      }
    } else if (block.kind === "bullets") {
      for (const item of block.items) {
        out.push(
          new Paragraph({
            bullet: { level: 0 },
            spacing: { after: 80 },
            children: [runs(item, { size: 22 })],
          }),
        );
      }
    } else {
      out.push(new Paragraph({ spacing: { before: 80, after: 40 }, children: [runs(`${block.n}. ${block.text}`, { size: 22 })] }));
      if (block.meta) {
        out.push(new Paragraph({ spacing: { after: 40 }, indent: { left: 360 }, children: [runs(block.meta, { size: 18, color: "64748B" })] }));
      }
      if (block.extra) {
        out.push(new Paragraph({ spacing: { after: 80 }, indent: { left: 360 }, children: [runs(block.extra, { size: 20 })] }));
      }
    }
  }
  return out;
}

export async function docxBytes(blocks: DocBlock[]): Promise<Uint8Array> {
  const doc = new Document({
    sections: [{ children: blocksToParagraphs(blocks) }],
  });
  const blob = await Packer.toBlob(doc);
  return new Uint8Array(await blob.arrayBuffer());
}

export function markdownBytes(blocks: DocBlock[]): Uint8Array {
  return new TextEncoder().encode(blocksToMarkdown(blocks));
}

export function downloadMarkdown(blocks: DocBlock[], filename: string): void {
  triggerDownload(markdownBytes(blocks), filename, "text/markdown;charset=utf-8");
}

export async function downloadDocx(blocks: DocBlock[], filename: string): Promise<void> {
  triggerDownload(await docxBytes(blocks), filename, "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
}

export async function downloadZip(files: Record<string, Uint8Array>, filename: string): Promise<void> {
  const { zipSync } = await import("fflate");
  triggerDownload(zipSync(files), filename, "application/zip");
}
