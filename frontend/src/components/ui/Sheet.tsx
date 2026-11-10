import { AnimatePresence, motion, useDragControls } from "motion/react";
import { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";
import { useBackToClose } from "../../lib/useBackToClose";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

/** Bottom sheet: swipe or drag down to dismiss, Escape and system back close it. */
export default function Sheet({ open, onClose, title, children }: Props) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const drag = useDragControls();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useBackToClose(open, onClose);

  // keyed on `open` only: callers pass inline onClose functions, and re-running this on every parent render
  // would pull focus back to the panel and forget which element opened the sheet
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    document.documentElement.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.documentElement.classList.remove("no-scroll");
      prev?.focus?.();
    };
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <div className="sheet-root">
          <motion.div className="sheet-scrim" onClick={onClose}
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div
            ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
            className="sheet sheet-bottom"
            initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            drag="y" dragListener={false} dragControls={drag}
            dragConstraints={{ top: 0, bottom: 0 }} dragElastic={{ top: 0.05, bottom: 0.8 }}
            onDragEnd={(_, info) => { if (info.offset.y > 120 || info.velocity.y > 600) onClose(); }}>
            <div className="sheet-handle-zone" onPointerDown={(e) => drag.start(e)}>
              <span className="sheet-handle" aria-hidden />
              <div className="sheet-head">
                <h2 id={titleId} className="sheet-title">{title}</h2>
                <button className="icon-btn hit" onClick={onClose} aria-label="Close">
                  <X size={18} aria-hidden />
                </button>
              </div>
            </div>
            <div className="sheet-body">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
