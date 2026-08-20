import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { ConfirmProvider } from "@/components/ConfirmDialog";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/Toast";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin", "latin-ext"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI-SCRIBE",
  description: "Ses analizli toplantı asistanı ve iş takip sistemi",
};

const themeScript = `(function(){try{var t=localStorage.getItem("ai-scribe-theme");if(t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch(e){}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="tr"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="flex min-h-full flex-col bg-[#F4F6F8] font-sans text-slate-900 dark:bg-[#071314] dark:text-teal-50">
        <ThemeProvider>
          <ConfirmProvider>
            <ToastProvider>{children}</ToastProvider>
          </ConfirmProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
