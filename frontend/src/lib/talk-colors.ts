export const TALK_COLORS: { className: string; rgb: [number, number, number] }[] = [
  { className: "bg-sky-500", rgb: [14, 165, 233] },
  { className: "bg-amber-500", rgb: [245, 158, 11] },
  { className: "bg-rose-500", rgb: [244, 63, 94] },
  { className: "bg-violet-500", rgb: [139, 92, 246] },
  { className: "bg-orange-500", rgb: [249, 115, 22] },
  { className: "bg-lime-500", rgb: [132, 204, 22] },
  { className: "bg-indigo-500", rgb: [99, 102, 241] },
  { className: "bg-fuchsia-500", rgb: [217, 70, 239] },
  { className: "bg-yellow-400", rgb: [250, 204, 21] },
  { className: "bg-blue-800", rgb: [30, 64, 175] },
  { className: "bg-stone-500", rgb: [120, 113, 108] },
  { className: "bg-red-600", rgb: [220, 38, 38] },
];

export function talkColorClass(index: number): string {
  return TALK_COLORS[index % TALK_COLORS.length].className;
}

export function talkColorRgb(index: number): [number, number, number] {
  return TALK_COLORS[index % TALK_COLORS.length].rgb;
}
