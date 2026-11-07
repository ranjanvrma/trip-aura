import { useState } from "react";
import { pretty } from "../utils";

interface Props {
  label: string;
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  allowCustom?: boolean;
  placeholder?: string;
}

/** Multi-select chips with optional free-text custom entries. */
export default function ChipSelect({ label, options, value, onChange, allowCustom = true, placeholder }: Props) {
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
      </div>
      {allowCustom && (
        <div className="row gap-s mt-s">
          <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder={placeholder ?? "Add your own"}
                 onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCustom(); } }} />
          <button type="button" className="btn btn-light" onClick={addCustom} disabled={!custom.trim()}>Add</button>
        </div>
      )}
    </fieldset>
  );
}
