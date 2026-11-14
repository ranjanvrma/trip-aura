import { useEffect, useState, type InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
  value: number;
  onValue: (v: number) => void;
  /** For optional fields: what an empty field means. The field may then stay empty. */
  emptyValue?: number;
};

/**
 * A number field that can be emptied while typing. A plain controlled <input type="number"> bound to a number turns
 * an empty field into 0, so clearing it and typing gives "02". This keeps the text as typed, reports only valid
 * numbers, and on blur tidies it (leading zeros gone, an empty field back to the last valid value).
 */
export default function NumberInput({ value, onValue, emptyValue, onBlur, ...rest }: Props) {
  const shown = (v: number) => (v === emptyValue ? "" : String(v));
  const [text, setText] = useState(shown(value));

  // follow outside changes (a typed description filled the form), but not our own echo of what was typed
  useEffect(() => {
    setText((t) => (t !== "" && Number(t) === value ? t : shown(value)));
  }, [value]);

  return (
    <input
      inputMode="decimal"
      step="any"
      {...rest}
      type="number"
      value={text}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);
        if (raw === "" && emptyValue !== undefined) onValue(emptyValue);
        else if (raw !== "" && Number.isFinite(Number(raw))) onValue(Number(raw));
      }}
      onBlur={(e) => {
        setText(text === "" || !Number.isFinite(Number(text)) ? shown(value) : shown(Number(text)));
        onBlur?.(e);
      }}
    />
  );
}
