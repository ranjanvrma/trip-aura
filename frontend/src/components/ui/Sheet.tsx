import { AnimatePresence, motion, useDragControls } from "motion/react";
import { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";
import { useBackToClose } from "../../lib/useBackToClose";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  side?: "bottom" | "right";
}

/** Bottom sheet (mobile) or side panel: swipe or drag down to dismiss, Escape and system back close it. */
export default function Sheet({ open, onClose, title, children, side = "bottom" }: Props) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const drag = useDragControls();
  useBackToClose(open, onClose);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.documentElement.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.documentElement.classList.remove("no-scroll");
      prev?.focus?.();
    };
  }, [open, onClose]);

  const bottom = side === "bottom";
  return (
    <AnimatePresence>
      {open && (
        <div className="sheet-root">
          <motion.div className="sheet-scrim" onClick={onClose}
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div
            ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
            className={`sheet sheet-${side}`}
            initial={bottom ? { y: "100%" } : { x: "100%" }}
            animate={bottom ? { y: 0 } : { x: 0 }}
            exit={bottom ? { y: "100%" } : { x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            drag={bottom ? "y" : "x"} dragListener={false} dragControls={drag}
            dragConstraints={bottom ? { top: 0, bottom: 0 } : { left: 0, right: 0 }}
            dragElastic={bottom ? { top: 0.05, bottom: 0.8 } : { left: 0.05, right: 0.8 }}
            onDragEnd={(_, info) => {
              const dist = bottom ? info.offset.y : info.offset.x;
              const vel = bottom ? info.velocity.y : info.velocity.x;
              if (dist > 120 || vel > 600) onClose();
            }}>
            <div className="sheet-handle-zone" onPointerDown={(e) => drag.start(e)}>
              {bottom && <span className="sheet-handle" aria-hidden />}
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
