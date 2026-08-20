export type MeetingStatus = "uploaded" | "transcribed" | "analyzing" | "analyzed" | "failed";
export type TaskStatus = "in_progress" | "done";

export type Meeting = {
  meeting_id: number;
  title: string;
  date: string;
  status: MeetingStatus;
  duration: number | null;
  attendees: string;
  audio_path: string | null;
};

export type TranscriptLine = {
  seq: number;
  timestamp: number;
  speaker: string;
  text: string;
};

export type Task = {
  meeting_id: number;
  action_seq: number;
  title: string;
  status: TaskStatus;
  assignee: string;
  due_date: string;
  description: string;
};

export const meetings: Meeting[] = [
  {
    meeting_id: 1,
    title: "Q3 Ürün Yol Haritası Görüşmesi",
    date: "2026-08-12T10:00:00",
    status: "analyzed",
    duration: 83,
    attendees: "Ayşe Y., Murat K., Selin A.",
    audio_path: "uploads/q3.m4a",
  },
  {
    meeting_id: 2,
    title: "Pazarlama Strateji Toplantısı",
    date: "2026-08-11T14:30:00",
    status: "analyzing",
    duration: 48,
    attendees: "Ayşe Y., Murat K.",
    audio_path: "uploads/pazarlama.mp3",
  },
  {
    meeting_id: 3,
    title: "Sprint 22 Retrospektif",
    date: "2026-08-10T09:00:00",
    status: "analyzed",
    duration: 56,
    attendees: "Geliştirme ekibi",
    audio_path: "uploads/sprint22.mp3",
  },
  {
    meeting_id: 4,
    title: "Müşteri Başarı Değerlendirmesi",
    date: "2026-08-08T11:00:00",
    status: "transcribed",
    duration: 65,
    attendees: "Ayşe Y., Selin A., Müşteri",
    audio_path: "uploads/musteri.m4a",
  },
  {
    meeting_id: 5,
    title: "Haftalık Genel Senkronizasyon",
    date: "2026-08-07T09:30:00",
    status: "analyzed",
    duration: 32,
    attendees: "Tüm ekip",
    audio_path: "uploads/sync.mp3",
  },
  {
    meeting_id: 6,
    title: "Güvenlik Denetim Toplantısı",
    date: "2026-08-05T15:00:00",
    status: "failed",
    duration: 72,
    attendees: "Murat K., Güvenlik ekibi",
    audio_path: "uploads/guvenlik.wav",
  },
  {
    meeting_id: 7,
    title: "Yatırımcı Güncelleme Görüşmesi",
    date: "2026-08-03T13:00:00",
    status: "analyzed",
    duration: 45,
    attendees: "Ayşe Y., Yönetim",
    audio_path: "uploads/yatirimci.m4a",
  },
  {
    meeting_id: 8,
    title: "Tasarım İnceleme Toplantısı",
    date: "2026-08-01T16:00:00",
    status: "uploaded",
    duration: 38,
    attendees: "Selin A., Tasarım ekibi",
    audio_path: "uploads/tasarim.mp3",
  },
];

export const transcripts: Record<number, TranscriptLine[]> = {
  1: [
    { seq: 1, timestamp: 30, speaker: "Ayşe Yılmaz", text: "Projeyi bu hafta kapsamı netleştirip başlayalım." },
    { seq: 2, timestamp: 42, speaker: "Mehmet Demir", text: "Ben API taslağını hazırlarım, şemayı da onaylatırız." },
    { seq: 3, timestamp: 71, speaker: "Ayşe Yılmaz", text: "Mockup’lar üzerinden ekranları kilitleyelim." },
    { seq: 4, timestamp: 110, speaker: "Mehmet Demir", text: "Aksiyonları görev kartına çevirelim, panodan takip ederiz." },
  ],
  3: [
    { seq: 1, timestamp: 12, speaker: "Ayşe Yılmaz", text: "Bu sprintte toplantı CRUD’unu bitirelim." },
    { seq: 2, timestamp: 40, speaker: "Mehmet Demir", text: "Whisper entegrasyonu sonraki sprintte kalsın." },
  ],
};

export const summaries: Record<number, string> = {
  1: "Keşif toplantısında kapsam netleştirildi. API taslağı, ekran mockup’ları ve veritabanı şeması bu hafta tamamlanacak. Aksiyonlar görev panosundan izlenecek.",
};

export const decisions: Record<number, string[]> = {
  1: [
    "İlk sürümde yerel dosya depolama kullanılacak.",
    "Görevler aksiyon maddelerinden üretilecek.",
    "Analiz çıktısı özet, karar ve aksiyon olarak ayrılacak.",
  ],
};

export type ActionItem = {
  seq: number;
  description: string;
  notes: string;
  assignee: string;
  due_date: string;
};

export const actions: Record<number, ActionItem[]> = {
  1: [
    {
      seq: 1,
      description: "Fiyatlandırma modelini güncelle",
      notes: "Q3 yol haritasına göre fiyat katmanlarını netleştir.",
      assignee: "Ayşe Yılmaz",
      due_date: "2026-08-14",
    },
    {
      seq: 2,
      description: "Tasarım ekibine UX geri bildirimi ver",
      notes: "Toplantıdaki ekran notlarını tasarım ekibine ilet.",
      assignee: "Murat Kaya",
      due_date: "2026-08-15",
    },
    {
      seq: 3,
      description: "Entegrasyon API dokümantasyonu hazırla",
      notes: "Toplantı ve görev uçlarını dokümante et.",
      assignee: "Selin Arslan",
      due_date: "2026-08-18",
    },
    {
      seq: 4,
      description: "Yatırımcı sunumu için slayt hazırla",
      notes: "Güncel metrikleri slayta aktar.",
      assignee: "Ayşe Yılmaz",
      due_date: "2026-08-20",
    },
  ],
};

export const tasks: Task[] = [
  {
    meeting_id: 1,
    action_seq: 1,
    title: "Fiyatlandırma modelini güncelle",
    status: "in_progress",
    assignee: "Ayşe Yılmaz",
    due_date: "2026-08-14",
    description: "Q3 yol haritasına göre fiyat katmanlarını netleştir.",
  },
  {
    meeting_id: 1,
    action_seq: 2,
    title: "Tasarım ekibine UX geri bildirimi ver",
    status: "in_progress",
    assignee: "Murat Kaya",
    due_date: "2026-08-15",
    description: "Toplantıdaki ekran notlarını tasarım ekibine ilet.",
  },
  {
    meeting_id: 1,
    action_seq: 3,
    title: "Entegrasyon API dokümantasyonu hazırla",
    status: "in_progress",
    assignee: "Selin Arslan",
    due_date: "2026-08-18",
    description: "Toplantı ve görev uçlarını dokümante et.",
  },
  {
    meeting_id: 7,
    action_seq: 1,
    title: "Yatırımcı sunumu için slayt hazırla",
    status: "done",
    assignee: "Ayşe Yılmaz",
    due_date: "2026-08-20",
    description: "Güncel metrikleri slayta aktar.",
  },
  {
    meeting_id: 3,
    action_seq: 1,
    title: "Sprint notlarını paylaş",
    status: "done",
    assignee: "Mehmet Demir",
    due_date: "2026-08-16",
    description: "Retrospektif çıktısını ekibe ilet.",
  },
];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function todayISO(): string {
  const date = new Date();
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/** Native datetime-local value for the current local time. */
export function nowDatetimeLocal(): string {
  const date = new Date();
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

/** Native date inputs need YYYY-MM-DD; API values may include a time. */
export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "";
  const match = String(iso).match(/^(\d{4}-\d{2}-\d{2})/);
  return match?.[1] ?? "";
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const [year, month, day] = dateOnly(iso).split("-").map(Number);
  if (!year || !month || !day) return null;
  const due = new Date(year, month - 1, day);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / 86_400_000);
}

export type DueTone = "none" | "ok" | "soon" | "overdue";

export function dueTone(iso: string | null | undefined): DueTone {
  const days = daysUntil(iso);
  if (days == null) return "none";
  if (days < 0) return "overdue";
  if (days <= 3) return "soon";
  return "ok";
}

export function dueRemainingLabel(iso: string | null | undefined): string {
  const days = daysUntil(iso);
  if (days == null) return "";
  if (days < 0) {
    const late = Math.abs(days);
    return late === 1 ? "1 gün gecikti" : `${late} gün gecikti`;
  }
  if (days === 0) return "Bugün teslim";
  if (days === 1) return "1 gün kaldı";
  return `${days} gün kaldı`;
}

export function byDueDate(a: { due_date?: string | null }, b: { due_date?: string | null }): number {
  const left = dateOnly(a.due_date);
  const right = dateOnly(b.due_date);
  if (!left && !right) return 0;
  if (!left) return 1;
  if (!right) return -1;
  return left.localeCompare(right);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const dayPart = iso.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(dayPart)) {
    const [year, month, day] = dayPart.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("tr-TR", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }
  return new Date(iso).toLocaleDateString("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}sn`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours) {
    if (mins && secs) return `${hours}s ${mins}dk ${secs}sn`;
    if (mins) return `${hours}s ${mins}dk`;
    return `${hours}s`;
  }
  if (secs) return `${mins}dk ${secs}sn`;
  return `${mins}dk`;
}

export function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
