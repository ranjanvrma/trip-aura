import { useState } from "react";
import { Check, Plus } from "lucide-react";
import { pretty } from "../utils";

interface Props {
  label: string;
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}

/** Multi-select chips. Custom entries are added through an "Add your own" chip that opens a small inline input. */
export default function ChipSelect({ label, options, value, onChange, placeholder }: Props) {
  const [adding, setAdding] = useState(false);
  const [custom, setCustom] = useState("");
  const all = [...options, ...value.filter((v) => !options.includes(v))];
  const toggle = (o: string) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  const addCustom = () => {
    const v = custom.trim().toLowerCase().replace(/[\s-]+/g, "_");
    if (v && !value.includes(v)) onChange([...value, v]);
    setCustom("");
  };
  return (
    <fieldset className="field">
      <legend>{label}</legend>
      <div className="chips">
        {all.map((o) => (
          <button type="button" key={o} className={`chip ${value.includes(o) ? "chip-on" : ""}`}
                  aria-pressed={value.includes(o)} onClick={() => toggle(o)}>
            {pretty(o)}
          </button>
        ))}
        {adding ? (
          <span className="chip-input">
            <input autoFocus value={custom} maxLength={60} aria-label={`Add to ${label.toLowerCase()}`}
                   placeholder={placeholder ?? "Add your own"} onChange={(e) => setCustom(e.target.value)}
                   onKeyDown={(e) => {
                     if (e.key === "Enter") { e.preventDefault(); addCustom(); }
                     if (e.key === "Escape") { e.stopPropagation(); setCustom(""); setAdding(false); }
                   }}
                   onBlur={() => { if (!custom.trim()) setAdding(false); }} />
            <button type="button" className="icon-btn hit" onMouseDown={(e) => e.preventDefault()} onClick={addCustom}
                    disabled={!custom.trim()} aria-label="Add">
              <Check size={16} aria-hidden />
            </button>
          </span>
        ) : (
          <button type="button" className="chip chip-add" onClick={() => setAdding(true)}>
            <Plus size={13} aria-hidden /> Add your own
          </button>
        )}
      </div>
    </fieldset>
  );
}
