import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { CircleCheck, CircleX, Info, X } from "lucide-react";

type Tone = "success" | "error" | "info";
interface Toast { id: number; tone: Tone; message: string; actionLabel?: string; onAction?: () => void; ms: number }
interface ToastApi {
  show: (t: Omit<Toast, "id" | "ms"> & { ms?: number }) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
const ICON = { success: CircleCheck, error: CircleX, info: Info };

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef(new Map<number, number>());
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
  }, []);

  const show = useCallback<ToastApi["show"]>((t) => {
    const id = nextId.current++;
    const ms = t.ms ?? (t.tone === "error" ? 7000 : 5000);
    setToasts((all) => [...all.slice(-2), { ...t, id, ms }]);
    timers.current.set(id, window.setTimeout(() => dismiss(id), ms));
    return id;
  }, [dismiss]);

  const value = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications">
        <AnimatePresence initial={false}>
          {toasts.map((t) => {
            const Icon = ICON[t.tone];
            return (
              <motion.div key={t.id} layout className={`toast toast-${t.tone}`}
                          role={t.tone === "error" ? "alert" : "status"}
                          initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: 8, transition: { duration: 0.15 } }}
                          transition={{ type: "spring", stiffness: 420, damping: 34 }}
                          drag="x" dragConstraints={{ left: 0, right: 0 }} dragElastic={0.6}
                          onDragEnd={(_, info) => { if (Math.abs(info.offset.x) > 80) dismiss(t.id); }}>
                <Icon size={18} aria-hidden className="toast-icon" />
                <span className="toast-msg">{t.message}</span>
                {t.actionLabel && (
                  <button className="toast-action" onClick={() => { t.onAction?.(); dismiss(t.id); }}>{t.actionLabel}</button>
                )}
                <button className="icon-btn hit" onClick={() => dismiss(t.id)} aria-label="Dismiss notification">
                  <X size={16} aria-hidden />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
