"use client";

import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={key} className="font-semibold text-slate-900 dark:text-teal-50">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`")) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-slate-200/80 px-1 py-0.5 font-mono text-[0.85em] dark:bg-teal-900/60"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(
        <em key={key} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    }
    key += 1;
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function headingLevel(line: string): 1 | 2 | 3 | null {
  if (line.startsWith("### ")) return 3;
  if (line.startsWith("## ")) return 2;
  if (line.startsWith("# ")) return 1;
  return null;
}

function isBullet(line: string): boolean {
  return /^[-*]\s+/.test(line);
}

function isNumbered(line: string): boolean {
  return /^\d+\.\s+/.test(line);
}

function stripBullet(line: string): string {
  return line.replace(/^[-*]\s+/, "").replace(/^\d+\.\s+/, "");
}

export function MarkdownBody({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const heading = headingLevel(line);
    if (heading) {
      const body = line.replace(/^#+\s+/, "");
      const cls =
        heading === 1
          ? "text-base font-semibold text-slate-900 dark:text-teal-50"
          : heading === 2
            ? "pt-1 text-sm font-semibold text-slate-800 dark:text-teal-100"
            : "pt-1 text-[13px] font-semibold tracking-wide text-teal-800 uppercase dark:text-teal-300";
      const Tag = heading === 1 ? "h3" : heading === 2 ? "h4" : "h5";
      blocks.push(
        <Tag key={`h-${index}`} className={cls}>
          {inline(body)}
        </Tag>,
      );
      index += 1;
      continue;
    }

    if (isBullet(line) || isNumbered(line)) {
      const numbered = isNumbered(line);
      const items: string[] = [];
      while (index < lines.length && (numbered ? isNumbered(lines[index]) : isBullet(lines[index]))) {
        items.push(stripBullet(lines[index]));
        index += 1;
      }
      const List = numbered ? "ol" : "ul";
      blocks.push(
        <List
          key={`l-${index}`}
          className={
            numbered
              ? "list-decimal space-y-1 pl-5 text-sm leading-7"
              : "list-disc space-y-1 pl-5 text-sm leading-7"
          }
        >
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{inline(item)}</li>
          ))}
        </List>,
      );
      continue;
    }

    const paras: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !headingLevel(lines[index]) &&
      !isBullet(lines[index]) &&
      !isNumbered(lines[index])
    ) {
      paras.push(lines[index].replace(/^>\s?/, ""));
      index += 1;
    }
    blocks.push(
      <p key={`p-${index}`} className="text-sm leading-7">
        {inline(paras.join(" "))}
      </p>,
    );
  }

  if (!blocks.length) return null;
  return <div className="space-y-2.5 break-words text-slate-800 dark:text-slate-100">{blocks}</div>;
}
