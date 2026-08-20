"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { useAuth } from "@/hooks/useAuth";

const nav = [
  { href: "/", label: "Dashboard", match: (path: string) => path === "/" },
  { href: "/meetings", label: "Toplantılar", match: (path: string) => path.startsWith("/meetings") },
  { href: "/tasks", label: "Görevler", match: (path: string) => path.startsWith("/tasks") },
  { href: "/people", label: "Kişiler", match: (path: string) => path.startsWith("/people") },
];

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function AppShell({
  title,
  crumb,
  action,
  children,
}: {
  title?: string;
  crumb?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  if (!user) {
    return (
      <div className="flex min-h-full flex-1 items-center justify-center text-sm text-slate-500 dark:text-slate-400">
        Yükleniyor…
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-1 flex-col bg-[#F4F6F8] dark:bg-[#071314]">
      <header className="relative overflow-hidden border-b border-teal-900/40 bg-slate-950">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_0%,rgba(13,148,136,0.32),transparent_42%),radial-gradient(circle_at_90%_120%,rgba(15,118,110,0.18),transparent_40%)]" />
        <div className="relative mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 lg:px-8">
          <div className="flex min-w-0 items-center gap-6">
            <Link href="/" className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-teal-500 text-[10px] font-semibold text-slate-950">
                AS
              </span>
              <span className="text-sm font-semibold tracking-[0.18em] text-teal-300">AI-SCRIBE</span>
            </Link>
            <nav className="hidden items-center gap-1 sm:flex">
              {nav.map((item) => {
                const active = item.match(pathname);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                      active
                        ? "bg-teal-500 text-slate-950"
                        : "text-slate-300 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <button
              type="button"
              onClick={logout}
              className="hidden text-xs text-slate-400 hover:text-teal-200 sm:block"
            >
              Çıkış
            </button>
            <span
              title={user.name}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-800 text-xs font-semibold text-teal-100"
            >
              {initials(user.name)}
            </span>
          </div>
        </div>
        <nav className="relative flex gap-1 overflow-x-auto px-4 pb-2 sm:hidden">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                item.match(pathname) ? "bg-teal-500 text-slate-950" : "text-slate-300"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>

      <div className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 lg:px-8">
        <p className="text-xs text-teal-700/70 dark:text-teal-400/80">AI-SCRIBE / {crumb ?? title}</p>
        {title || action ? (
          <div className="mt-2 mb-6 flex flex-wrap items-center justify-between gap-3">
            {title ? (
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-teal-50">{title}</h1>
            ) : (
              <span />
            )}
            {action}
          </div>
        ) : (
          <div className="mb-5" />
        )}
        {children}
      </div>
    </div>
  );
}
