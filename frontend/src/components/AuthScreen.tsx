"use client";

import { ThemeToggle } from "@/components/ThemeToggle";
import type { ReactNode } from "react";

export function AuthScreen({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-full flex-1">
      <section className="relative hidden w-[46%] flex-col justify-between overflow-hidden bg-slate-950 px-12 py-12 text-slate-100 lg:flex">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(13,148,136,0.28),transparent_42%),radial-gradient(circle_at_80%_80%,rgba(15,118,110,0.18),transparent_40%)]" />
        <p className="relative text-sm font-semibold tracking-[0.2em] text-teal-300">AI-SCRIBE</p>
        <div className="relative max-w-md">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight text-white">
            Toplantı kaydından özet, karar ve görev.
          </h1>
          <p className="mt-4 text-base leading-7 text-slate-300">
            Ses kaydını yükle; transkript, özet ve aksiyon maddeleri otomatik çıksın. Görevleri tek panodan takip
            et.
          </p>
        </div>
        <p className="relative text-xs text-slate-500">Ses analizli toplantı asistanı</p>
      </section>

      <section className="relative flex flex-1 items-center justify-center bg-slate-50 px-6 py-12 dark:bg-[#071314]">
        <div className="absolute top-4 right-4">
          <ThemeToggle className="text-teal-700 hover:bg-teal-50 dark:text-teal-200 dark:hover:bg-white/10" />
        </div>
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <p className="text-sm font-semibold tracking-[0.2em] text-teal-700 dark:text-teal-300">AI-SCRIBE</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-teal-50">{title}</h1>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-teal-800/40 dark:bg-[#0f2220]">
            <div className="mb-6 hidden lg:block">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-teal-50">{title}</h2>
              {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
            </div>
            {children}
          </div>
        </div>
      </section>
    </div>
  );
}
