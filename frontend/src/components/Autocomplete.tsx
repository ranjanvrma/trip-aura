import { useEffect, useId, useRef, useState } from "react";

interface Props<T> {
  value: string;
  onChange: (text: string) => void;            // free typing
  onSelect: (item: T) => void;                 // picked from the dropdown
  fetchItems: (q: string, signal: AbortSignal) => Promise<T[]>;
  renderItem: (item: T) => React.ReactNode;
  itemKey: (item: T) => string;
  minChars?: number;
  placeholder?: string;
  required?: boolean;
  footer?: string;
  className?: string;
}

/** Accessible combobox: debounced search, arrow keys / Enter / Escape, mouse selection. */
export default function Autocomplete<T>({ value, onChange, onSelect, fetchItems, renderItem, itemKey, minChars = 2,
                                         placeholder, required, footer, className }: Props<T>) {
  const [items, setItems] = useState<T[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const typed = useRef(false);   // only search after the user types (not after a selection)
  const listId = useId();

  useEffect(() => {
    if (!typed.current || value.trim().length < minChars) {
      setItems([]);
      return;
    }
    const ctrl = new AbortController();
    const t = window.setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetchItems(value.trim(), ctrl.signal);
        setItems(res);
        setError(null);
        setOpen(true);
        setActive(res.length ? 0 : -1);
      } catch (e) {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "Suggestions unavailable");
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    }, 220);
    return () => { ctrl.abort(); window.clearTimeout(t); };
  }, [value, minChars, fetchItems]);

  const choose = (item: T) => {
    typed.current = false;
    onSelect(item);
    setOpen(false);
    setItems([]);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || !items.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => (a + 1) % items.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => (a - 1 + items.length) % items.length); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); choose(items[active]); }
    else if (e.key === "Escape") setOpen(false);
  };

  return (
    <div className={`ac ${className ?? ""}`}>
      <input
        value={value} placeholder={placeholder} required={required} autoComplete="off"
        role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        onChange={(e) => { typed.current = true; onChange(e.target.value); }}
        onKeyDown={onKeyDown}
        onFocus={() => items.length && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {loading && <span className="ac-spin" aria-hidden>...</span>}
      {open && (items.length > 0 || error) && (
        <ul className="ac-list" id={listId} role="listbox">
          {error && <li className="ac-empty">{error}</li>}
          {items.map((it, i) => (
            <li key={itemKey(it)} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                className={i === active ? "ac-active" : ""}
                onMouseDown={(e) => { e.preventDefault(); choose(it); }} onMouseEnter={() => setActive(i)}>
              {renderItem(it)}
            </li>
          ))}
          {footer && items.length > 0 && <li className="ac-footer">{footer}</li>}
        </ul>
      )}
    </div>
  );
}
