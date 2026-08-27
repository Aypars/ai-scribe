import type { TranscriptLine } from "@/lib/api";

export type SpeakerStat = {
  name: string;
  count: number;
  pending: boolean;
  seconds: number;
  share: number;
};

function spokenGuess(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1.5, Math.min(40, words * 0.45));
}

function turnSeconds(line: TranscriptLine, nextTs: number | null, meetingDuration: number | null): number {
  const guessed = spokenGuess(line.text);
  const fallbackEnd = meetingDuration != null && meetingDuration > line.timestamp
    ? meetingDuration
    : line.timestamp + guessed;
  const end = nextTs ?? fallbackEnd;
  const gap = end - line.timestamp;
  if (!Number.isFinite(gap) || gap <= 0) return guessed;
  return Math.min(gap, Math.max(guessed, 12));
}

export function speakerStats(
  lines: TranscriptLine[],
  meetingDuration: number | null,
  pendingOf: (name: string) => boolean,
): SpeakerStat[] {
  const timed = [...lines].sort((a, b) => a.seq - b.seq);
  const seconds = new Map<string, number>();
  const counts = new Map<string, number>();
  const order: string[] = [];

  for (let i = 0; i < timed.length; i += 1) {
    const line = timed[i];
    const name = (line.speaker || "").trim();
    if (!name) continue;
    if (!seconds.has(name)) {
      order.push(name);
      seconds.set(name, 0);
      counts.set(name, 0);
    }
    const next = timed[i + 1];
    const nextTs = next && next.timestamp > line.timestamp ? next.timestamp : null;
    seconds.set(name, (seconds.get(name) ?? 0) + turnSeconds(line, nextTs, meetingDuration));
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }

  const total = [...seconds.values()].reduce((sum, value) => sum + value, 0);
  return order
    .map((name) => {
      const secs = seconds.get(name) ?? 0;
      return {
        name,
        count: counts.get(name) ?? 0,
        pending: pendingOf(name),
        seconds: Math.round(secs),
        share: total > 0 ? Math.round((secs / total) * 100) : 0,
      };
    })
    .sort((a, b) => b.seconds - a.seconds || b.count - a.count);
}
