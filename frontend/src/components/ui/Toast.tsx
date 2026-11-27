import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

type ToastTone = "success" | "error" | "info";

interface ToastItem {
  id: string;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  toast: (message: string, tone?: ToastTone) => void;
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const ICONS = {
  success: <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />,
  error: <AlertTriangle className="h-4 w-4 text-danger" aria-hidden />,
  info: <Info className="h-4 w-4 text-accent" aria-hidden />,
};

const TONE_BORDER = {
  success: "border-success/30",
  error: "border-danger/30",
  info: "border-accent/30",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (message: string, tone: ToastTone = "info") => {
      const id = crypto.randomUUID();
      setItems((current) => [...current.slice(-3), { id, tone, message }]);
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), tone === "error" ? 6500 : 4200),
      );
    },
    [dismiss],
  );

  useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((timer) => clearTimeout(timer));
      map.clear();
    };
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      toast: push,
      success: (message: string) => push(message, "success"),
      error: (message: string) => push(message, "error"),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {createPortal(
        <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              role="status"
              className={clsx(
                "pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-surface px-4 py-3 text-sm text-fg shadow-pop",
                TONE_BORDER[item.tone],
              )}
            >
              <span className="mt-0.5">{ICONS[item.tone]}</span>
              <p className="flex-1 leading-snug">{item.message}</p>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => dismiss(item.id)}
                className="rounded p-0.5 text-subdued hover:bg-surface-2 hover:text-fg"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
