"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthScreen } from "@/components/AuthScreen";
import { resetPassword, setSession } from "@/lib/api";

const field =
  "h-11 rounded-lg border border-slate-200 bg-white px-3 text-slate-900 outline-none ring-teal-600/20 placeholder:text-slate-400 focus:border-teal-600 focus:ring-4 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = (params.get("token") || "").trim();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Şifreler aynı değil");
      return;
    }
    if (!token) {
      setError("Bağlantı eksik. E-postadaki linki kullan.");
      return;
    }
    setPending(true);
    try {
      const data = await resetPassword({ token, password });
      setSession(data);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sıfırlama başarısız");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthScreen title="Yeni şifre" subtitle="En az 6 karakter. Bağlantı 1 saat geçerli.">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Yeni şifre</span>
          <input
            type="password"
            name="password"
            autoComplete="new-password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={field}
            placeholder="••••••••"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Şifre tekrar</span>
          <input
            type="password"
            name="confirm"
            autoComplete="new-password"
            required
            minLength={6}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={field}
            placeholder="••••••••"
          />
        </label>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button
          type="submit"
          disabled={pending}
          className="h-11 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
        >
          {pending ? "Kaydediliyor…" : "Şifreyi kaydet"}
        </button>
        <Link href="/login" className="text-center text-sm font-medium text-teal-700 hover:underline dark:text-teal-300">
          Girişe dön
        </Link>
      </form>
    </AuthScreen>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<AuthScreen title="Yeni şifre" />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
