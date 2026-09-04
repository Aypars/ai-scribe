import type { ActionItem, Decision } from "@/lib/api";

export function formatClock(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

export function foldText(value: string): string {
  return value.toLocaleLowerCase("tr").replace(/\s+/g, " ").trim();
}

export function followUpFor(decision: Decision, actions: ActionItem[]): ActionItem | undefined {
  const key = foldText(decision.text);
  if (!key) return undefined;
  return actions.find((item) => item.task_status && foldText(item.description) === key);
}

export function suggestionFor(decision: Decision, actions: ActionItem[]): ActionItem | undefined {
  const key = foldText(decision.text);
  if (!key) return undefined;
  return actions.find((item) => !item.task_status && foldText(item.description) === key);
}
