import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { type LucideIcon, ArrowRight, CornerDownLeft, FileText, ListChecks, MapPin, Moon, Plus, Search, Shield, Sun } from "lucide-react";
import { listSavedTrips } from "../../lib/localTrips";
import { useSWR } from "../../lib/swr";
import { trapTab } from "../../lib/focusTrap";
import { modKey } from "../../lib/platform";
import { toggleTheme, useTheme } from "../../lib/theme";
import Kbd from "../ui/Kbd";

export interface Command { id: string; label: string; hint?: string; group: string; icon?: LucideIcon; run: () => void }

interface Ctx { open: () => void; setPageCommands: (c: Command[]) => void }
const CommandContext = createContext<Ctx | null>(null);
export const useCommands = () => useContext(CommandContext)!;

/** Pages add their own commands (for example "Go to day 2") while they are mounted. */
export function usePageCommands(commands: Command[]) {
  const { setPageCommands } = useCommands();
  useEffect(() => { setPageCommands(commands); return () => setPageCommands([]); }, [commands, setPageCommands]);
}

export function CommandProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [pageCommands, setPageCommands] = useState<Command[]>([]);
  const open = useCallback(() => setOpen(true), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo(() => ({ open, setPageCommands }), [open]);
  return (
    <CommandContext.Provider value={value}>
      {children}
      <AnimatePresence>{isOpen && <Palette pageCommands={pageCommands} onClose={() => setOpen(false)} />}</AnimatePresence>
    </CommandContext.Provider>
  );
}

function Palette({ pageCommands, onClose }: { pageCommands: Command[]; onClose: () => void }) {
  const nav = useNavigate();
  const trips = useSWR("localTrips", async () => listSavedTrips());
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const go = useCallback((path: string) => () => nav(path, { viewTransition: true }), [nav]);
  const theme = useTheme();

  const all = useMemo<Command[]>(() => {
    const base: Command[] = [
      { id: "new", label: "Plan a new trip", group: "Navigate", icon: Plus, run: go("/") },
      { id: "trips", label: "My trips", group: "Navigate", icon: ListChecks, run: go("/trips") },
      { id: "terms", label: "Terms of use", group: "Legal", icon: FileText, run: go("/terms") },
      { id: "privacy", label: "Privacy policy", group: "Legal", icon: Shield, run: go("/privacy") },
      { id: "theme", label: `Switch to ${theme === "dark" ? "light" : "dark"} theme`, group: "Appearance",
        icon: theme === "dark" ? Sun : Moon, run: toggleTheme },
    ];
    const saved = (trips.data ?? []).slice(0, 8).map<Command>((t) => ({
      id: `trip-${t.id}`, label: t.title, hint: `${t.num_days} days`, group: "Saved trips", icon: MapPin, run: go(`/trips/${t.id}`),
    }));
    return [...pageCommands, ...saved, ...base];
  }, [pageCommands, trips.data, go, theme]);

  const shown = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return all;
    return all.filter((c) => `${c.label} ${c.group}`.toLowerCase().includes(term));
  }, [all, q]);

  // focus goes to the search box, and back to whatever opened the menu when it closes
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => opener?.focus?.();
  }, []);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const run = (c: Command | undefined) => { if (!c) return; onClose(); c.run(); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, shown.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); run(shown[active]); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else trapTab(e, input.current?.closest(".cmd") ?? null);
  };

  let lastGroup = "";
  return (
    <div className="cmd-root" onKeyDown={onKey}>
      <motion.div className="sheet-scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.div className="cmd" role="dialog" aria-modal="true" aria-label="Command menu"
                  initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.98, transition: { duration: 0.12 } }}
                  transition={{ type: "spring", stiffness: 500, damping: 36 }}>
        <div className="cmd-search">
          <Search size={18} aria-hidden />
          <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setActive(0); }} placeholder="Search pages, trips and actions"
                 role="combobox" aria-expanded="true" aria-controls="cmd-list" aria-autocomplete="list"
                 aria-activedescendant={shown[active] ? `cmd-${shown[active].id}` : undefined} />
          <Kbd>Esc</Kbd>
        </div>
        <ul className="cmd-list" id="cmd-list" role="listbox" ref={listRef}>
          {shown.length === 0 && <li className="cmd-empty">Nothing matches "{q}"</li>}
          {shown.map((c, i) => {
            const header = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            const Icon = c.icon ?? ArrowRight;
            return (
              <li key={c.id} role="presentation">
                {header && <div className="cmd-group">{header}</div>}
                <div id={`cmd-${c.id}`} role="option" aria-selected={i === active} data-index={i}
                     className={`cmd-item ${i === active ? "is-active" : ""}`}
                     onMouseMove={() => setActive(i)} onClick={() => run(c)}>
                  <Icon size={16} />
                  <span className="cmd-label">{c.label}</span>
                  {c.hint && <span className="cmd-hint">{c.hint}</span>}
                  {i === active && <CornerDownLeft size={14} className="cmd-enter" aria-hidden />}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="cmd-foot">
          <span><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
          <span><Kbd>Enter</Kbd> open</span>
          <span><Kbd>{modKey()}</Kbd><Kbd>K</Kbd> toggle</span>
        </div>
      </motion.div>
    </div>
  );
}
