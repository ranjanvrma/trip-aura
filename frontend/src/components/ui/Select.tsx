import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

export interface SelectOption { value: string; label: string; hint?: string }

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  label: string;                 // accessible name
  searchable?: boolean;          // a filter box for long lists
  id?: string;
}

/**
 * A designed dropdown (button + listbox) in place of the browser's select. Arrow keys move, Enter picks, Escape
 * closes, and long lists get a filter box. Focus returns to the button when it closes.
 */
export default function Select({ value, onChange, options, label, searchable = false, id }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const listId = useId();

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((o) => `${o.label} ${o.hint ?? ""}`.toLowerCase().includes(q)) : options;
  }, [options, query]);
  const current = options.find((o) => o.value === value);

  const close = (refocus = true) => {
    setOpen(false);
    setQuery("");
    if (refocus) button.current?.focus();
  };
  const pick = (v: string) => { onChange(v); close(); };

  // open on the current value, with the filter box (or the list) focused
  useEffect(() => {
    if (!open) return;
    setActive(Math.max(0, options.findIndex((o) => o.value === value)));
    (searchable ? search.current : list.current)?.focus();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open, shown]);

  // click outside closes without stealing focus from what was clicked
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) close(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(shown.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(shown.length - 1); }
    else if (e.key === "Enter") { e.preventDefault(); if (shown[active]) pick(shown[active].value); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === "Tab") close(false);
  };

  return (
    <div className={`select ${open ? "is-open" : ""}`} ref={root}>
      <button type="button" id={id} ref={button} className="select-button" aria-haspopup="listbox" aria-expanded={open}
              aria-label={`${label}: ${current?.label ?? value}`}
              onClick={() => (open ? close() : setOpen(true))}
              onKeyDown={(e) => { if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); setOpen(true); } }}>
        <span className="select-value">{current?.label ?? value}</span>
        {current?.hint && <span className="select-hint">{current.hint}</span>}
        <ChevronDown size={16} aria-hidden className="select-chevron" />
      </button>
      {open && (
        <div className="select-pop" onKeyDown={onKeyDown}>
          {searchable && (
            <input ref={search} className="select-search" value={query} placeholder="Type to filter" aria-label={`Filter ${label}`}
                   role="combobox" aria-expanded="true" aria-controls={listId} aria-autocomplete="list"
                   aria-activedescendant={shown[active] ? `${listId}-${active}` : undefined} onChange={(e) => { setQuery(e.target.value); setActive(0); }} />
          )}
          <ul className="select-list" id={listId} ref={list} role="listbox" aria-label={label} tabIndex={-1}
              aria-activedescendant={shown[active] ? `${listId}-${active}` : undefined}>
            {shown.map((o, i) => (
              <li key={o.value} id={`${listId}-${i}`} data-i={i} role="option" aria-selected={o.value === value}
                  className={`select-option ${i === active ? "is-active" : ""}`}
                  onPointerEnter={() => setActive(i)} onClick={() => pick(o.value)}>
                <span>{o.label}</span>
                {o.hint && <span className="select-hint">{o.hint}</span>}
                {o.value === value && <Check size={15} aria-hidden />}
              </li>
            ))}
            {shown.length === 0 && <li className="select-empty">Nothing matches</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
