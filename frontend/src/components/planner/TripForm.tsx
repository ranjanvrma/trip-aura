import { useCallback, useEffect, useState } from "react";
import { api } from "../../services/api";
import type {
  AddressSuggestion, ApiOptions, ApiStatus, CitySuggestion, LatLng, ParsedTrip, TransportMode, TripRequest, TripStyle,
} from "../../types";
import { MODE_LABEL, pretty } from "../../utils";
import Autocomplete from "../ui/Autocomplete";
import NumberInput from "../ui/NumberInput";
import ChipSelect from "./ChipSelect";

const STYLE: Record<TripStyle, { label: string; hint: string }> = {
  budget: { label: "Lowest cost", hint: "Cheaper meals, free or cheap sights, walking and public transport." },
  mid: { label: "Mid-range", hint: "A balance of cost, comfort and time." },
  premium: { label: "Premium", hint: "Better restaurants and faster door-to-door rides, still within your budget." },
};

interface Props {
  options: ApiOptions;
  status: ApiStatus | null;
  submitting: boolean;
  onSubmit: (req: TripRequest) => void;
  prefill?: { parsed: ParsedTrip; version: number } | null;
  onCityLocation?: (loc: LatLng | null) => void;
}

const today = () => new Date().toISOString().slice(0, 10);

export default function TripForm({ options, status, submitting, onSubmit, prefill, onCityLocation }: Props) {
  const mock = status?.data_mode === "mock";
  const [req, setReq] = useState<TripRequest>(() => ({
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
    trip_style: "mid",
  }));
  const [useCoords, setUseCoords] = useState(false);
  const [coords, setCoords] = useState({ lat: "", lng: "" });
  const [cityLoc, setCityLoc] = useState<LatLng | null>(null);       // from the city dropdown
  const [pinned, setPinned] = useState<LatLng | null>(null);         // exact accommodation point from suggestions
  // the destination country's own currency, offered as a one-click choice
  const [local, setLocal] = useState<{ currency: string; country: string } | null>(null);
  const suggestCurrency = useCallback((c: CitySuggestion) => {
    setLocal(c.currency && options.currencies.includes(c.currency) ? { currency: c.currency, country: c.country } : null);
  }, [options.currencies]);

  useEffect(() => { onCityLocation?.(cityLoc); }, [cityLoc, onCityLocation]);

  // apply fields read from a free-text description (DescribeTrip)
  useEffect(() => {
    if (!prefill) return;
    const f = prefill.parsed.fields;
    setReq((r) => ({
      ...r,
      ...Object.fromEntries(Object.entries(f).filter(([k, v]) => k !== "accommodation" && v !== undefined)),
      currency: f.currency && options.currencies.includes(f.currency) ? f.currency : r.currency,
      accommodation: { ...r.accommodation, ...(f.accommodation ?? {}) },
    }) as TripRequest);
    const city = prefill.parsed.city;
    if (city) { setCityLoc({ lat: city.lat, lng: city.lng }); suggestCurrency(city); }
    if (f.accommodation?.name_or_address) setPinned(null);
  }, [prefill, options.currencies, suggestCurrency]);

  const fetchCities = useCallback(
    (q: string, signal: AbortSignal) => api.citySuggestions(q, signal).then((r) => r.results), []);
  const city = cityLoc ? req.destination_city : "";   // only once a real city is chosen
  const fetchAddresses = useCallback(
    (q: string, signal: AbortSignal) => api.addressSuggestions(q, cityLoc, city, signal).then((r) => r.results),
    [cityLoc, city]);

  const set = <K extends keyof TripRequest>(k: K, v: TripRequest[K]) => setReq((r) => ({ ...r, [k]: v }));
  const toggleMode = (m: TransportMode) =>
    set("transport_modes", req.transport_modes.includes(m) ? req.transport_modes.filter((x) => x !== m) : [...req.transport_modes, m]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const location = useCoords && coords.lat && coords.lng ? { lat: Number(coords.lat), lng: Number(coords.lng) } : pinned;
    onSubmit({ ...req, accommodation: { ...req.accommodation, location } });
  };

  return (
    <form className="form" onSubmit={submit} aria-labelledby="plan-title">
      <h2 id="plan-title" className="tile-title">The trip</h2>

      <div className="grid-2">
        <label className="field">
          <span>Destination city</span>
          <Autocomplete<CitySuggestion>
            inputId="city-input" value={req.destination_city} required minChars={2}
            placeholder={mock ? "Jaipur" : "Lisbon, Kyoto, Jaipur..."}
            onChange={(v) => { set("destination_city", v); setCityLoc(null); setLocal(null); }}
            onSelect={(c) => { set("destination_city", c.query); setCityLoc({ lat: c.lat, lng: c.lng }); suggestCurrency(c); }}
            fetchItems={fetchCities} itemKey={(c) => String(c.id)}
            renderItem={(c) => (
              <span className="ac-item"><strong>{c.name}</strong>
                <span className="muted small"> {[c.region, c.country].filter((x) => x && x !== c.name).join(", ")}</span>
              </span>
            )}
            footer="City data © GeoNames"
          />
          {mock && <small className="muted">Demo mode supports {status?.mock_city} only.</small>}
        </label>
        <label className="field">
          <span>Start date</span>
          <input type="date" min={today()} value={req.start_date ?? ""} onChange={(e) => set("start_date", e.target.value || null)} />
        </label>
      </div>

      <fieldset className="field">
        <legend>Where are you staying?</legend>
        <div className="grid-3">
          <select value={req.accommodation.type}
                  onChange={(e) => set("accommodation", { ...req.accommodation, type: e.target.value })}>
            {options.accommodation_types.map((t) => <option key={t} value={t}>{pretty(t)}</option>)}
          </select>
          <Autocomplete<AddressSuggestion>
            className="span-2" value={req.accommodation.name_or_address} required minChars={3}
            placeholder="Hotel name, Airbnb address or any address"
            onChange={(v) => { set("accommodation", { ...req.accommodation, name_or_address: v }); setPinned(null); }}
            onSelect={(a) => { set("accommodation", { ...req.accommodation, name_or_address: a.label }); setPinned({ lat: a.lat, lng: a.lng }); }}
            fetchItems={fetchAddresses} itemKey={(a) => `${a.lat},${a.lng},${a.label}`}
            renderItem={(a) => <span className="ac-item">{a.label}{a.kind && <span className="muted small"> · {a.kind.replace(/_/g, " ")}</span>}</span>}
            footer={cityLoc ? "Results near your destination · Photon / OpenStreetMap" : "Photon / OpenStreetMap"}
          />
        </div>
        {pinned && !useCoords && (
          <p className="small muted mt-xs">Exact location pinned: {pinned.lat.toFixed(5)}, {pinned.lng.toFixed(5)}</p>
        )}
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
          <NumberInput min={1} max={14} inputMode="numeric" required value={req.num_days} onValue={(v) => set("num_days", v)} />
        </label>
        <label className="field"><span>Travellers</span>
          <NumberInput min={1} max={20} inputMode="numeric" required value={req.travelers} onValue={(v) => set("travelers", v)} />
        </label>
        <label className="field"><span>Total budget</span>
          <NumberInput min={1} required value={req.budget} onValue={(v) => set("budget", v)} />
        </label>
        <label className="field"><span>Currency</span>
          <select value={req.currency} onChange={(e) => set("currency", e.target.value)}>
            {options.currencies.map((c) => (
              <option key={c} value={c}>{c === local?.currency ? `${c} (local)` : c}</option>
            ))}
          </select>
          {local && local.currency !== req.currency && (
            <button type="button" className="currency-hint" onClick={() => set("currency", local.currency)}>
              Use {local.currency}, the currency in {local.country}
            </button>
          )}
        </label>
      </div>
      <label className="field">
        <span>Accommodation cost already in this budget (optional)</span>
        <NumberInput min={0} placeholder="0" emptyValue={0} value={req.accommodation_cost_total}
                     onValue={(v) => set("accommodation_cost_total", v)} />
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
        <legend>How to spend the budget</legend>
        <div className="chips">
          {(options.trip_styles ?? []).map((t) => (
            <button type="button" key={t} className={`chip ${req.trip_style === t ? "chip-on" : ""}`}
                    aria-pressed={req.trip_style === t} onClick={() => set("trip_style", t)}>{STYLE[t].label}</button>
          ))}
        </div>
        {req.trip_style && <small className="muted">{STYLE[req.trip_style].hint}</small>}
      </fieldset>

      <fieldset className="field">
        <legend>Pace</legend>
        <div className="chips">
          {options.paces.map((p) => (
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

      <div className="form-submit">
        <button className="btn btn-primary btn-block" disabled={submitting} aria-keyshortcuts="Control+Enter Meta+Enter">
          {submitting ? <><span className="spinner" aria-hidden /> Building your itinerary</> : "Build my itinerary"}
        </button>
        <p className="small muted">
          {mock ? "Demo data: ratings, prices and times are illustrative."
            : status?.google.active ? "Open map data, with Google ratings where a place matches. Times and most prices are estimates."
            : "Built from open map data. Times and most prices are estimates."}{" "}
          Saved only in this browser.
        </p>
      </div>
    </form>
  );
}
