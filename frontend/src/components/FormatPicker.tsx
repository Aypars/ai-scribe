"use client";

import { useEffect, useState } from "react";

import { FORMAT_CHOICES, type ExportFormat } from "@/lib/export-office";

export function FormatPicker({
  value,
  onChange,
  name = "export-format",
}: {
  value: ExportFormat;
  onChange: (value: ExportFormat) => void;
  name?: string;
}) {
  return (
    <div className="space-y-2">
      {FORMAT_CHOICES.map((choice) => {
        const active = value === choice.id;
        return (
          <label
            key={choice.id}
            className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5 ${
              active
                ? "border-teal-600 bg-teal-50/80 dark:border-teal-500 dark:bg-teal-950/50"
                : "border-slate-200 hover:bg-slate-50 dark:border-teal-800 dark:hover:bg-teal-950/40"
            }`}
          >
            <input
              type="radio"
              name={name}
              className="mt-1 accent-teal-700"
              checked={active}
              onChange={() => onChange(choice.id)}
            />
            <span>
              <span className="block text-sm font-medium text-slate-800 dark:text-teal-50">{choice.title}</span>
              <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">{choice.hint}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}

export function ExportFormatDialog({
  open,
  exporting,
  onClose,
  onConfirm,
}: {
  open: boolean;
  exporting: boolean;
  onClose: () => void;
  onConfirm: (format: ExportFormat) => void;
}) {
  const [format, setFormat] = useState<ExportFormat>("pdf");

  useEffect(() => {
    if (open) setFormat("pdf");
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/55 p-4"
      onClick={() => {
        if (!exporting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-format-title"
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220]"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="export-format-title" className="text-lg font-semibold text-slate-900 dark:text-teal-50">
          Dışa aktar
        </h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Dosya biçimini seç.</p>
        <div className="mt-4">
          <FormatPicker value={format} onChange={setFormat} />
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            disabled={exporting}
            onClick={onClose}
            className="h-11 cursor-pointer rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 dark:border-teal-800 dark:text-teal-100 dark:hover:bg-teal-950/60"
          >
            Vazgeç
          </button>
          <button
            type="button"
            disabled={exporting}
            onClick={() => onConfirm(format)}
            className="h-11 cursor-pointer rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
          >
            {exporting ? "Hazırlanıyor…" : "Dışa aktar"}
          </button>
        </div>
      </div>
    </div>
  );
}
