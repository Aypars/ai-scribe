"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { AuthScreen } from "@/components/AuthScreen";
import { requestPasswordReset } from "@/lib/api";

const field =
  "h-11 rounded-lg border border-slate-200 bg-white px-3 text-slate-900 outline-none ring-teal-600/20 placeholder:text-slate-400 focus:border-teal-600 focus:ring-4 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [resetUrl, setResetUrl] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      const data = await requestPasswordReset(email);
      setDone(true);
      setResetUrl(data.reset_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "İstek başarısız");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthScreen title="Şifremi unuttum" subtitle="Kayıtlı adrese 1 saatlik bir bağlantı gider.">
      {done ? (
        <div className="space-y-4">
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            Kayıtlıysa mail yolda. Gelen kutusu ve spam’e bak. Gönderen: AI-SCRIBE.
          </p>
          {resetUrl ? (
            <div className="space-y-3">
              <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
                Mail sunucusu yoksa bağlantı burada:
              </p>
              <Link
                href={resetUrl}
                className="flex h-11 items-center justify-center rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
              >
                Yeni şifre belirle
              </Link>
            </div>
          ) : null}
          <Link href="/login" className="block text-center text-sm font-medium text-teal-700 hover:underline dark:text-teal-300">
            Girişe dön
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-300">E-posta</span>
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={field}
              placeholder="ornek@sirket.com"
            />
          </label>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button
            type="submit"
            disabled={pending}
            className="h-11 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
          >
            {pending ? "Gönderiliyor…" : "Bağlantı gönder"}
          </button>
          <Link href="/login" className="text-center text-sm font-medium text-teal-700 hover:underline dark:text-teal-300">
            Girişe dön
          </Link>
        </form>
      )}
    </AuthScreen>
  );
}
