import { Minus, Plus } from "lucide-react";
import NumberInput from "./NumberInput";

interface Props {
  value: number;
  onValue: (v: number) => void;
  min: number;
  max: number;
  label: string;        // what is being counted, for the button labels ("days")
  id?: string;
}

/** A whole number with minus and plus buttons; the number itself can still be typed. */
export default function Stepper({ value, onValue, min, max, label, id }: Props) {
  const clamp = (v: number) => Math.max(min, Math.min(max, Math.round(v)));
  return (
    <div className="stepper">
      <button type="button" className="stepper-btn" aria-label={`Fewer ${label}`} disabled={value <= min}
              onClick={() => onValue(clamp(value - 1))}><Minus size={16} aria-hidden /></button>
      <NumberInput id={id} min={min} max={max} inputMode="numeric" required value={value} onValue={onValue}
                   aria-label={label} />
      <button type="button" className="stepper-btn" aria-label={`More ${label}`} disabled={value >= max}
              onClick={() => onValue(clamp(value + 1))}><Plus size={16} aria-hidden /></button>
    </div>
  );
}
