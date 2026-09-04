"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { AppShell } from "@/components/AppShell";
import { AttendeeListEditor, joinAttendeeList } from "@/components/AttendeeListEditor";
import { useToast } from "@/components/Toast";
import { createMeeting } from "@/lib/api";
import { nowDatetimeLocal } from "@/lib/dates";

const field =
  "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

const MEDIA_NAME = /\.(mp3|wav|m4a|mp4|webm|mov)$/i;

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function NewMeetingPage() {
  const router = useRouter();
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(nowDatetimeLocal);
  const [attendeeNames, setAttendeeNames] = useState<string[]>([]);
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState<"tr" | "en">("tr");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function clearFile() {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function pickFile(next: File | null) {
    if (!next) {
      clearFile();
      return;
    }
    if (!MEDIA_NAME.test(next.name)) {
      setError("Sadece MP3, WAV, M4A, MP4, WEBM veya MOV");
      return;
    }
    if (next.size > 500 * 1024 * 1024) {
      setError("Dosya 500 MB sınırını aşıyor");
      return;
    }
    setError(null);
    setFile(next);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Ses veya video seçin");
      return;
    }
    if (date > nowDatetimeLocal()) {
      setError("Toplantı tarihi şu andan ileri olamaz");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const meeting = await createMeeting({
        title,
        date,
        attendees: joinAttendeeList(attendeeNames),
        description,
        language,
        audio: file,
      });
      toast("Toplantı başarıyla oluşturuldu");
      router.push(`/meetings/${meeting.meeting_id}?transcribing=1`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Yükleme başarısız");
      setSaving(false);
    }
  }

  return (
    <AppShell title="Yeni toplantı yükle" crumb="Yeni toplantı">
      <form
        onSubmit={handleSubmit}
        className="mx-auto max-w-2xl space-y-5 rounded-2xl border border-slate-200/80 bg-white p-8 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]"
      >
        <p className="text-sm text-slate-500">
          Ses veya video yükleyin; yazıya çevirme bittikten sonra katılımcılar konuşmacılara eşlenir.
          Videodan ses otomatik çıkarılır. Özet ve görev atama için transkript hazır olunca Analiz yap’a basarsınız.
        </p>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Toplantı başlığı</span>
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={field}
            placeholder="örn. Q3 Ürün Yol Haritası Görüşmesi"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Tarih</span>
          <input
            type="datetime-local"
            required
            max={nowDatetimeLocal()}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Katılımcılar</span>
          <AttendeeListEditor
            names={attendeeNames}
            onChange={setAttendeeNames}
            hint="İsmi yazıp Onayla’ya basın. Transkriptte adı geçmeyen kişi konuşmacıya bağlanmaz."
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Açıklama</span>
          <textarea
            rows={3}
            maxLength={4000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Toplantının konusu veya notlar (isteğe bağlı)"
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
          />
        </label>
        <div className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Kayıt dili</span>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Whisper ve özet bu dile göre çalışır. Konuşulan dili seç; yanlış dil transkripti bozar.
          </p>
          <div className="flex rounded-lg bg-slate-100 p-1 text-sm font-medium dark:bg-teal-950">
            <button
              type="button"
              onClick={() => setLanguage("tr")}
              className={`flex-1 rounded-md py-2 transition ${
                language === "tr"
                  ? "bg-white text-slate-900 shadow-sm dark:bg-teal-800 dark:text-teal-50"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-teal-100"
              }`}
            >
              Türkçe
            </button>
            <button
              type="button"
              onClick={() => setLanguage("en")}
              className={`flex-1 rounded-md py-2 transition ${
                language === "en"
                  ? "bg-white text-slate-900 shadow-sm dark:bg-teal-800 dark:text-teal-50"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-teal-100"
              }`}
            >
              English
            </button>
          </div>
        </div>
        <div className="flex flex-col gap-2 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Kayıt</span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp3,.wav,.m4a,.mp4,.webm,.mov,audio/*,video/mp4,video/webm,video/quicktime"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
          />
          <div
            className="rounded-xl border border-dashed border-slate-300 bg-slate-50 dark:border-teal-800 dark:bg-teal-950/40"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              pickFile(event.dataTransfer.files[0] ?? null);
            }}
          >
            {!file ? (
              <div className="flex min-h-40 flex-col items-center justify-center px-4 py-10">
                <span className="mb-2 text-2xl text-indigo-400">♪</span>
                <p className="font-medium text-slate-800 dark:text-teal-50">Dosyayı buraya sürükle ve bırak</p>
                <p className="mt-1 text-xs text-slate-400">MP3, WAV, M4A, MP4, WEBM, MOV · Maks. 500 MB</p>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="mt-4 h-10 cursor-pointer rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:hover:bg-teal-900/40"
                >
                  Dosya seç
                </button>
              </div>
            ) : (
              <div className="flex min-h-40 flex-col p-5">
                <p className="font-medium text-slate-800 dark:text-teal-50">{file.name}</p>
                <p className="mt-1 text-xs text-slate-400">{formatFileSize(file.size)}</p>
                <div className="mt-auto flex justify-end gap-2 pt-6">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="h-9 cursor-pointer rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-slate-200 dark:hover:bg-teal-900/40"
                  >
                    Değiştir
                  </button>
                  <button
                    type="button"
                    onClick={clearFile}
                    className="h-9 cursor-pointer rounded-lg px-3 text-sm font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                  >
                    Sil
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        <div className="flex justify-end gap-3 pt-2">
          <Link
            href="/meetings"
            className="inline-flex h-11 items-center rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-teal-900/40"
          >
            İptal
          </Link>
          <button
            type="submit"
            disabled={saving}
            className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? "Yükleniyor…" : "Yükle ve yazıya çevir"}
          </button>
        </div>
      </form>
    </AppShell>
  );
}
