"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { getToken, loginUser, registerUser, setSession } from "@/lib/api";

type Mode = "login" | "register";

export function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace("/");
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      const data =
        mode === "register"
          ? await registerUser({ name, email, password })
          : await loginUser({ email, password });
      setSession(data);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bir hata oluştu");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex rounded-lg bg-slate-100 p-1 text-sm font-medium dark:bg-teal-950">
        <button
          type="button"
          onClick={() => {
            setMode("login");
            setError("");
          }}
          className={`flex-1 rounded-md py-2 transition ${
            mode === "login"
              ? "bg-white text-slate-900 shadow-sm dark:bg-teal-800 dark:text-teal-50"
              : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-teal-100"
          }`}
        >
          Giriş yap
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("register");
            setError("");
          }}
          className={`flex-1 rounded-md py-2 transition ${
            mode === "register"
              ? "bg-white text-slate-900 shadow-sm dark:bg-teal-800 dark:text-teal-50"
              : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-teal-100"
          }`}
        >
          Kayıt ol
        </button>
      </div>

      {mode === "register" && (
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Ad soyad</span>
          <input
            type="text"
            name="name"
            autoComplete="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-slate-900 outline-none ring-teal-600/20 placeholder:text-slate-400 focus:border-teal-600 focus:ring-4 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
            placeholder="Ayşe Yılmaz"
          />
        </label>
      )}

      <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">E-posta</span>
        <input
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-slate-900 outline-none ring-teal-600/20 placeholder:text-slate-400 focus:border-teal-600 focus:ring-4 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
          placeholder="ornek@sirket.com"
        />
      </label>

      <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Şifre</span>
        <input
          type="password"
          name="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-slate-900 outline-none ring-teal-600/20 placeholder:text-slate-400 focus:border-teal-600 focus:ring-4 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50 dark:focus:border-teal-500"
          placeholder="••••••••"
        />
      </label>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <button
        type="submit"
        disabled={pending}
        className="mt-1 h-11 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending
          ? "Gönderiliyor…"
          : mode === "login"
            ? "Giriş yap"
            : "Hesap oluştur"}
      </button>
      <Link
        href="/login/forgot"
        className="text-center text-sm font-semibold text-teal-700 hover:underline dark:text-teal-300"
      >
        Şifremi unuttum
      </Link>
    </form>
  );
}
