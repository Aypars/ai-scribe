"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type ConfirmOptions = {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
};

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(async () => false);

export function useConfirm() {
  return useContext(ConfirmContext);
}

type Pending = {
  options: Required<Pick<ConfirmOptions, "title" | "confirmLabel" | "cancelLabel">> & {
    message: string;
  };
  resolve: (value: boolean) => void;
};

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const confirm = useCallback<ConfirmFn>((options) => {
    return new Promise((resolve) => {
      setPending({
        options: {
          title: options.title ?? "Silmek istediğine emin misin?",
          message: options.message,
          confirmLabel: options.confirmLabel ?? "Sil",
          cancelLabel: options.cancelLabel ?? "Vazgeç",
        },
        resolve,
      });
    });
  }, []);

  function finish(value: boolean) {
    pending?.resolve(value);
    setPending(null);
  }

  useEffect(() => {
    if (!pending) return;
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      pending.resolve(false);
      setPending(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending ? (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/55 p-4"
          onClick={() => finish(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-teal-800 dark:bg-[#0f2220]"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="confirm-title" className="text-lg font-semibold text-slate-900 dark:text-teal-50">
              {pending.options.title}
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{pending.options.message}</p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                autoFocus
                onClick={() => finish(false)}
                className="h-11 cursor-pointer rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-teal-800 dark:text-teal-100 dark:hover:bg-teal-950/60"
              >
                {pending.options.cancelLabel}
              </button>
              <button
                type="button"
                onClick={() => finish(true)}
                className="h-11 cursor-pointer rounded-lg bg-rose-600 px-4 text-sm font-semibold text-white hover:bg-rose-700"
              >
                {pending.options.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </ConfirmContext.Provider>
  );
}
