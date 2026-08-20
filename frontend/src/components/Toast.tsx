"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type ToastItem = { id: number; message: string };

const ToastContext = createContext<(message: string) => void>(() => undefined);

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, message }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((item) => item.id !== id));
    }, 3200);
  }, []);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="pointer-events-none fixed right-6 bottom-6 z-[60] flex w-80 max-w-[calc(100%-3rem)] flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="rounded-lg bg-teal-700 px-4 py-3 text-sm font-medium text-white shadow-lg"
          >
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
