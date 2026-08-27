"use client";

import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { useToast } from "@/components/Toast";
import { changePassword, updateProfile } from "@/lib/api";
import { notifyAuthUserChanged, useAuth } from "@/hooks/useAuth";

const field =
  "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none ring-teal-600/20 placeholder:text-slate-400 focus:border-teal-600 focus:ring-4 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500";

export default function SettingsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [name, setName] = useState("");
  const [namePending, setNamePending] = useState(false);
  const [nameError, setNameError] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordPending, setPasswordPending] = useState(false);
  const [passwordError, setPasswordError] = useState("");

  useEffect(() => {
    if (user) setName(user.name);
  }, [user]);

  async function handleName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNameError("");
    setNamePending(true);
    try {
      await updateProfile(name.trim());
      notifyAuthUserChanged();
      toast("Ad güncellendi");
    } catch (err) {
      setNameError(err instanceof Error ? err.message : "Kayıt başarısız");
    } finally {
      setNamePending(false);
    }
  }

  async function handlePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError("");
    if (newPassword !== confirmPassword) {
      setPasswordError("Şifreler aynı değil");
      return;
    }
    setPasswordPending(true);
    try {
      await changePassword({ current_password: currentPassword, new_password: newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast("Şifre güncellendi");
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Şifre değiştirilemedi");
    } finally {
      setPasswordPending(false);
    }
  }

  return (
    <AppShell title="Hesap" crumb="Hesap">
      <div className="mx-auto max-w-xl space-y-5">
        <form
          onSubmit={handleName}
          className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]"
        >
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-teal-50">Profil</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Görünen adın başlıkta ve dışa aktarmada kullanılır.</p>
          </div>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-300">Ad soyad</span>
            <input
              required
              maxLength={255}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-300">E-posta</span>
            <input value={user?.email ?? ""} disabled className={`${field} cursor-not-allowed opacity-70`} />
          </label>
          {nameError ? <p className="text-sm text-rose-600">{nameError}</p> : null}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={namePending || !name.trim() || name.trim() === user?.name}
              className="h-11 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {namePending ? "Kaydediliyor…" : "Adı kaydet"}
            </button>
          </div>
        </form>

        <form
          onSubmit={handlePassword}
          className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-teal-800/40 dark:bg-[#0f2220]"
        >
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-teal-50">Şifre</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">En az 6 karakter. Unuttuysan girişteki sıfırlamayı kullan.</p>
          </div>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-300">Mevcut şifre</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className={field}
              placeholder="••••••••"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-300">Yeni şifre</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={6}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className={field}
              placeholder="••••••••"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-300">Yeni şifre tekrar</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={6}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={field}
              placeholder="••••••••"
            />
          </label>
          {passwordError ? <p className="text-sm text-rose-600">{passwordError}</p> : null}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={passwordPending}
              className="h-11 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {passwordPending ? "Kaydediliyor…" : "Şifreyi kaydet"}
            </button>
          </div>
        </form>
      </div>
    </AppShell>
  );
}
