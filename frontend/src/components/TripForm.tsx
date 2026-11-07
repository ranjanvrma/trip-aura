import { useState } from "react";
import type { ApiOptions, ApiStatus, Pace, TransportMode, TripRequest } from "../types";
import { MODE_LABEL, pretty } from "../utils";
import ChipSelect from "./ChipSelect";

interface Props {
  options: ApiOptions;
  status: ApiStatus | null;
  submitting: boolean;
  onSubmit: (req: TripRequest) => void;
}

const today = () => new Date().toISOString().slice(0, 10);

export default function TripForm({ options, status, submitting, onSubmit }: Props) {
  const mock = status?.data_mode === "mock";
  const [req, setReq] = useState<TripRequest>({
    accommodation: { type: "hotel", name_or_address: mock ? "Hotel on MI Road, Jaipur" : "" },
    destination_city: mock ? (status?.mock_city ?? "Jaipur") : "",
    start_date: today(),
    num_days: 3,
    travelers: 1,
    budget: 15000,
    currency: "INR",
    accommodation_cost_total: 0,
    interests: ["museums", "monuments", "photography"],
    food_preferences: ["vegetarian"],
    food_categories: ["local_cuisine", "street_food"],
    transport_modes: ["walking", "auto", "metro"],
    pace: "moderate",
    return_to_accommodation: true,
    fit_to_budget: false,
  });
  const [useCoords, setUseCoords] = useState(false);
  const [coords, setCoords] = useState({ lat: "", lng: "" });

  const set = <K extends keyof TripRequest>(k: K, v: TripRequest[K]) => setReq((r) => ({ ...r, [k]: v }));
  const toggleMode = (m: TransportMode) =>
    set("transport_modes", req.transport_modes.includes(m) ? req.transport_modes.filter((x) => x !== m) : [...req.transport_modes, m]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const location = useCoords && coords.lat && coords.lng ? { lat: Number(coords.lat), lng: Number(coords.lng) } : null;
    onSubmit({ ...req, accommodation: { ...req.accommodation, location } });
  };

  return (
    <form className="card form" onSubmit={submit}>
      <h2>Plan your trip</h2>

      <div className="grid-2">
        <label className="field">
          <span>Destination city</span>
          <input required value={req.destination_city} onChange={(e) => set("destination_city", e.target.value)}
                 placeholder="e.g. Jaipur" />
          {mock && <small className="muted">Demo mode supports {status?.mock_city} only.</small>}
        </label>
        <label className="field">
          <span>Start date</span>
          <input type="date" value={req.start_date ?? ""} onChange={(e) => set("start_date", e.target.value || null)} />
        </label>
      </div>

      <fieldset className="field">
        <legend>Where are you staying?</legend>
        <div className="grid-3">
          <select value={req.accommodation.type}
                  onChange={(e) => set("accommodation", { ...req.accommodation, type: e.target.value })}>
            {options.accommodation_types.map((t) => <option key={t} value={t}>{pretty(t)}</option>)}
          </select>
          <input className="span-2" required value={req.accommodation.name_or_address}
                 placeholder="Hotel name, Airbnb address or any address"
                 onChange={(e) => set("accommodation", { ...req.accommodation, name_or_address: e.target.value })} />
        </div>
        <label className="check mt-s">
          <input type="checkbox" checked={useCoords} onChange={(e) => setUseCoords(e.target.checked)} />
          I know the exact coordinates
        </label>
        {useCoords && (
          <div className="grid-2 mt-s">
            <input type="number" step="any" placeholder="Latitude" value={coords.lat}
                   onChange={(e) => setCoords({ ...coords, lat: e.target.value })} />
            <input type="number" step="any" placeholder="Longitude" value={coords.lng}
                   onChange={(e) => setCoords({ ...coords, lng: e.target.value })} />
          </div>
        )}
      </fieldset>

      <div className="grid-4">
        <label className="field"><span>Days</span>
          <input type="number" min={1} max={14} value={req.num_days} onChange={(e) => set("num_days", Number(e.target.value))} />
        </label>
        <label className="field"><span>Travellers</span>
          <input type="number" min={1} max={20} value={req.travelers} onChange={(e) => set("travelers", Number(e.target.value))} />
        </label>
        <label className="field"><span>Total budget</span>
          <input type="number" min={1} value={req.budget} onChange={(e) => set("budget", Number(e.target.value))} />
        </label>
        <label className="field"><span>Currency</span>
          <select value={req.currency} onChange={(e) => set("currency", e.target.value)}>
            {options.currencies.map((c) => <option key={c} disabled={mock && c !== "INR"}>{c}</option>)}
          </select>
        </label>
      </div>
      <label className="field">
        <span>Accommodation cost already in this budget (optional)</span>
        <input type="number" min={0} value={req.accommodation_cost_total}
               onChange={(e) => set("accommodation_cost_total", Number(e.target.value))} />
      </label>

      <ChipSelect label="Interests" options={options.interests} value={req.interests}
                  onChange={(v) => set("interests", v)} placeholder="Custom interest, e.g. street art" />
      <ChipSelect label="Food preferences" options={options.food_preferences} value={req.food_preferences}
                  onChange={(v) => set("food_preferences", v)} placeholder="e.g. no garlic" />
      <ChipSelect label="Preferred food categories" options={options.food_categories} value={req.food_categories}
                  onChange={(v) => set("food_categories", v)} placeholder="e.g. rooftop cafes" />

      <fieldset className="field">
        <legend>Transport</legend>
        <div className="chips">
          {options.transport_modes.map((m) => (
            <button type="button" key={m} className={`chip ${req.transport_modes.includes(m) ? "chip-on" : ""}`}
                    aria-pressed={req.transport_modes.includes(m)} onClick={() => toggleMode(m)}>
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="field">
        <legend>Pace</legend>
        <div className="chips">
          {options.paces.map((p: Pace) => (
            <button type="button" key={p} className={`chip ${req.pace === p ? "chip-on" : ""}`}
                    aria-pressed={req.pace === p} onClick={() => set("pace", p)}>{pretty(p)}</button>
          ))}
        </div>
      </fieldset>

      <div className="row gap-m wrap">
        <label className="check">
          <input type="checkbox" checked={req.return_to_accommodation}
                 onChange={(e) => set("return_to_accommodation", e.target.checked)} />
          End each day at my accommodation
        </label>
        <label className="check">
          <input type="checkbox" checked={req.fit_to_budget} onChange={(e) => set("fit_to_budget", e.target.checked)} />
          Automatically fit the plan to my budget
        </label>
      </div>

      <button className="btn btn-primary" disabled={submitting}>
        {submitting ? "Generating itinerary..." : "Generate itinerary"}
      </button>
    </form>
  );
}
