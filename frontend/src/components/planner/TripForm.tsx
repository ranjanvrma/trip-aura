import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { api } from "../../services/api";
import type {
  AddressSuggestion, ApiOptions, ApiStatus, CitySuggestion, LatLng, Pace, ParsedTrip, TransportMode, TripRequest, TripStyle,
} from "../../types";
import { MODE_LABEL, pretty } from "../../utils";
import Autocomplete from "../ui/Autocomplete";
import NumberInput from "../ui/NumberInput";
import Select from "../ui/Select";
import Stepper from "../ui/Stepper";
import BoardingPass from "./BoardingPass";
import ChipSelect from "./ChipSelect";

const STYLE: Record<TripStyle, { label: string; hint: string }> = {
  budget: { label: "Lowest cost", hint: "Cheaper meals, free or cheap sights, walking and public transport." },
  mid: { label: "Mid-range", hint: "A balance of cost, comfort and time." },
  premium: { label: "Premium", hint: "Better restaurants and faster door-to-door rides, still within your budget." },
};
const PACE_HINT: Record<Pace, string> = {
  relaxed: "Fewer stops and longer breaks.",
  moderate: "A full day with room to breathe.",
  packed: "As much as the day can hold.",
};
const STEPS = [
  { short: "Where", title: "Where are you going?" },
  { short: "When", title: "When, and who's coming?" },
  { short: "Budget", title: "What's the budget?" },
  { short: "Tastes", title: "What do you enjoy?" },
  { short: "Getting around", title: "How do you like to get around?" },
];
const LAST = STEPS.length - 1;

interface Props {
  options: ApiOptions;
  status: ApiStatus | null;
  submitting: boolean;
  onSubmit: (req: TripRequest) => void;
  prefill?: { parsed: ParsedTrip; version: number } | null;
  onCityLocation?: (loc: LatLng | null) => void;
}

/** Today's date where the traveller is (not in UTC, which is yesterday or tomorrow for part of every day). */
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** The planner, one question at a time, with the trip so far shown as a boarding pass beside it. */
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
    // auto-rickshaws only by default for the Jaipur demo; elsewhere the planner swaps them for cabs anyway
    transport_modes: mock ? ["walking", "auto", "metro"] : ["walking", "metro", "bus"],
    pace: "moderate",
    return_to_accommodation: true,
    fit_to_budget: false,
    trip_style: "mid",
  }));
  const [step, setStep] = useState(0);
  const [useCoords, setUseCoords] = useState(false);
  const [coords, setCoords] = useState({ lat: "", lng: "" });
  const [cityLoc, setCityLoc] = useState<LatLng | null>(null);       // from the city dropdown
  const [pinned, setPinned] = useState<LatLng | null>(null);         // exact accommodation point from suggestions
  // the destination country's own currency, offered as a one-click choice
  const [local, setLocal] = useState<{ currency: string; country: string } | null>(null);
  const panels = useRef<(HTMLElement | null)[]>([]);
  const moved = useRef(false);   // the step was changed by the traveller (not the first render)
  const appliedPrefill = useRef(0);

  const suggestCurrency = useCallback((c: CitySuggestion) => {
    setLocal(c.currency && options.currencies.includes(c.currency) ? { currency: c.currency, country: c.country } : null);
  }, [options.currencies]);

  useEffect(() => { onCityLocation?.(cityLoc); }, [cityLoc, onCityLocation]);

  // apply fields read from a free-text description or the hero's quick start, and begin at the first question
  useEffect(() => {
    // once per prefill: this must not run again when the options are refetched, or it would wipe later answers
    if (!prefill || prefill.version === appliedPrefill.current) return;
    appliedPrefill.current = prefill.version;
    const f = prefill.parsed.fields;
    setReq((r) => ({
      ...r,
      ...Object.fromEntries(Object.entries(f).filter(([k, v]) => k !== "accommodation" && v !== undefined)),
      currency: f.currency && options.currencies.includes(f.currency) ? f.currency : r.currency,
      accommodation: { ...r.accommodation, ...(f.accommodation ?? {}) },
    }) as TripRequest);
    const city = prefill.parsed.city;
    if (city) { setCityLoc({ lat: city.lat, lng: city.lng }); suggestCurrency(city); }
    if (city || f.accommodation?.name_or_address) setPinned(null);   // a pin belongs to the previous city or stay
    setStep(0);
  }, [prefill, options.currencies, suggestCurrency]);

  // moving between questions puts focus on the new question's heading (never on first load, which would scroll the page)
  useEffect(() => {
    if (!moved.current) return;
    panels.current[step]?.querySelector<HTMLElement>("h3")?.focus({ preventScroll: true });
  }, [step]);

  const fetchCities = useCallback(
    (q: string, signal: AbortSignal) => api.citySuggestions(q, signal).then((r) => r.results), []);
  const city = cityLoc ? req.destination_city : "";   // only once a real city is chosen
  const fetchAddresses = useCallback(
    (q: string, signal: AbortSignal) => api.addressSuggestions(q, cityLoc, city, signal).then((r) => r.results),
    [cityLoc, city]);
  const currencyOptions = useMemo(() => options.currencies.map((c) => ({
    value: c, label: c, hint: c === local?.currency ? `used in ${local.country}` : undefined,
  })), [options.currencies, local]);

  const set = <K extends keyof TripRequest>(k: K, v: TripRequest[K]) => setReq((r) => ({ ...r, [k]: v }));
  const toggleMode = (m: TransportMode) =>
    set("transport_modes", req.transport_modes.includes(m) ? req.transport_modes.filter((x) => x !== m) : [...req.transport_modes, m]);

  /** The first field of a step that the browser considers invalid, if any. */
  const invalidIn = (s: number) =>
    Array.from(panels.current[s]?.querySelectorAll<HTMLInputElement>("input, textarea") ?? []).find((el) => !el.checkValidity());

  const go = (to: number) => {
    // going forward passes through every question on the way, and stops at the first one that still needs an answer
    for (let s = step; s < to; s++) {
      const bad = invalidIn(s);
      if (!bad) continue;
      moved.current = true;
      setStep(s);
      window.setTimeout(() => bad.reportValidity(), 60);
      return false;
    }
    moved.current = true;
    setStep(to);
    return true;
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (step < LAST) { go(step + 1); return; }
    for (let s = 0; s <= LAST; s++) {
      const bad = invalidIn(s);
      if (bad) { moved.current = true; setStep(s); window.setTimeout(() => bad.reportValidity(), 60); return; }
    }
    const location = useCoords && coords.lat && coords.lng ? { lat: Number(coords.lat), lng: Number(coords.lng) } : pinned;
    onSubmit({ ...req, accommodation: { ...req.accommodation, location } });
  };

  const panel = (i: number) => ({
    ref: (el: HTMLElement | null) => { panels.current[i] = el; },
    className: "wiz-panel", hidden: step !== i, "aria-labelledby": `wiz-q${i}`,
  });
  const question = (i: number) => <h3 id={`wiz-q${i}`} className="wiz-q" tabIndex={-1}>{STEPS[i].title}</h3>;

  return (
    <div className="planner-grid">
      <form className="form wiz" onSubmit={submit} aria-labelledby="plan-title" noValidate>
        <ol className="wiz-steps" aria-label="Questions">
          {STEPS.map((s, i) => (
            <li key={s.short}>
              <button type="button" className={`wiz-step ${i === step ? "is-current" : i < step ? "is-done" : ""}`}
                      aria-current={i === step ? "step" : undefined} onClick={() => go(i)}>
                <span className="wiz-n num" aria-hidden>{i < step ? <Check size={13} /> : i + 1}</span>
                <span className="wiz-name">{s.short}</span>
              </button>
            </li>
          ))}
        </ol>

        <section {...panel(0)}>
          {question(0)}
          <label className="field">
            <span>Destination city</span>
            <Autocomplete<CitySuggestion>
              inputId="city-input" value={req.destination_city} required minChars={2}
              placeholder={mock ? "Jaipur" : "Lisbon, Kyoto, Jaipur..."}
              onChange={(v) => { set("destination_city", v); setCityLoc(null); setLocal(null); setPinned(null); }}
              onSelect={(c) => { set("destination_city", c.query); setCityLoc({ lat: c.lat, lng: c.lng }); suggestCurrency(c); setPinned(null); }}
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
          <fieldset className="field">
            <legend>Where are you staying?</legend>
            <div className="chips">
              {options.accommodation_types.map((t) => (
                <button type="button" key={t} className="chip" aria-pressed={req.accommodation.type === t}
                        onClick={() => set("accommodation", { ...req.accommodation, type: t })}>{pretty(t)}</button>
              ))}
            </div>
            <Autocomplete<AddressSuggestion>
              className="mt-s" inputId="stay-input" ariaLabel="Hotel name or address" value={req.accommodation.name_or_address} required minChars={3}
              placeholder="Hotel name, Airbnb address or any address"
              onChange={(v) => { set("accommodation", { ...req.accommodation, name_or_address: v }); setPinned(null); }}
              onSelect={(a) => { set("accommodation", { ...req.accommodation, name_or_address: a.label }); setPinned({ lat: a.lat, lng: a.lng }); }}
              fetchItems={fetchAddresses} itemKey={(a) => `${a.lat},${a.lng},${a.label}`}
              renderItem={(a) => <span className="ac-item">{a.label}{a.kind && <span className="muted small"> · {a.kind.replace(/_/g, " ")}</span>}</span>}
              footer={cityLoc ? "Results near your destination · Photon / OpenStreetMap" : "Photon / OpenStreetMap"}
            />
            {pinned && !useCoords && (
              <p className="small muted mt-xs">Exact location pinned: {pinned.lat.toFixed(5)}, {pinned.lng.toFixed(5)}</p>
            )}
            <label className="check mt-s">
              <input type="checkbox" checked={useCoords} onChange={(e) => setUseCoords(e.target.checked)} />
              I know the exact coordinates
            </label>
            {useCoords && (
              <div className="grid-2 mt-s">
                <input type="number" step="any" min={-90} max={90} placeholder="Latitude" aria-label="Latitude" value={coords.lat}
                       onChange={(e) => setCoords({ ...coords, lat: e.target.value })} />
                <input type="number" step="any" min={-180} max={180} placeholder="Longitude" aria-label="Longitude" value={coords.lng}
                       onChange={(e) => setCoords({ ...coords, lng: e.target.value })} />
              </div>
            )}
          </fieldset>
        </section>

        <section {...panel(1)}>
          {question(1)}
          <label className="field">
            <span>First day</span>
            <input type="date" min={today()} value={req.start_date ?? ""} onChange={(e) => set("start_date", e.target.value || null)} />
          </label>
          <div className="grid-2">
            <div className="field"><label htmlFor="wiz-days">Days</label>
              <Stepper id="wiz-days" label="days" min={1} max={14} value={req.num_days} onValue={(v) => set("num_days", v)} />
            </div>
            <div className="field"><label htmlFor="wiz-people">Travellers</label>
              <Stepper id="wiz-people" label="travellers" min={1} max={20} value={req.travelers} onValue={(v) => set("travelers", v)} />
            </div>
          </div>
        </section>

        <section {...panel(2)}>
          {question(2)}
          <div className="grid-2">
            <label className="field"><span>Total for the trip</span>
              <NumberInput min={1} required value={req.budget} onValue={(v) => set("budget", v)} />
            </label>
            <div className="field"><span>Currency</span>
              <Select label="Currency" value={req.currency} onChange={(v) => set("currency", v)} options={currencyOptions}
                      searchable={options.currencies.length > 8} />
              {local && local.currency !== req.currency && (
                <button type="button" className="currency-hint" onClick={() => set("currency", local.currency)}>
                  Use {local.currency}, the currency in {local.country}
                </button>
              )}
            </div>
          </div>
          <fieldset className="field">
            <legend>How to spend it</legend>
            <div className="cards-3">
              {(options.trip_styles ?? []).map((t) => (
                <button type="button" key={t} className="pick" aria-pressed={req.trip_style === t} onClick={() => set("trip_style", t)}>
                  <strong>{STYLE[t].label}</strong><span>{STYLE[t].hint}</span>
                </button>
              ))}
            </div>
          </fieldset>
          <label className="field">
            <span>Stay cost already inside this budget (optional)</span>
            <NumberInput min={0} placeholder="0" emptyValue={0} value={req.accommodation_cost_total}
                         onValue={(v) => set("accommodation_cost_total", v)} />
          </label>
          <label className="check">
            <input type="checkbox" checked={req.fit_to_budget} onChange={(e) => set("fit_to_budget", e.target.checked)} />
            If the plan goes over, swap in cheaper options automatically
          </label>
        </section>

        <section {...panel(3)}>
          {question(3)}
          <ChipSelect label="Interests" options={options.interests} value={req.interests}
                      onChange={(v) => set("interests", v)} placeholder="Custom interest, e.g. street art" />
          <ChipSelect label="How you eat" options={options.food_preferences} value={req.food_preferences}
                      onChange={(v) => set("food_preferences", v)} placeholder="e.g. no garlic" />
          <ChipSelect label="Kinds of food" options={options.food_categories} value={req.food_categories}
                      onChange={(v) => set("food_categories", v)} placeholder="e.g. rooftop cafes" />
        </section>

        <section {...panel(4)}>
          {question(4)}
          <fieldset className="field">
            <legend>Transport you're happy to use</legend>
            <div className="chips">
              {options.transport_modes.map((m) => (
                <button type="button" key={m} className="chip" aria-pressed={req.transport_modes.includes(m)} onClick={() => toggleMode(m)}>
                  {MODE_LABEL[m]}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="field">
            <legend>Pace</legend>
            <div className="cards-3">
              {options.paces.map((p) => (
                <button type="button" key={p} className="pick" aria-pressed={req.pace === p} onClick={() => set("pace", p)}>
                  <strong>{pretty(p)}</strong><span>{PACE_HINT[p]}</span>
                </button>
              ))}
            </div>
          </fieldset>
          <label className="check">
            <input type="checkbox" checked={req.return_to_accommodation}
                   onChange={(e) => set("return_to_accommodation", e.target.checked)} />
            End each day back at my stay
          </label>
        </section>

        <div className="wiz-nav">
          <button type="button" className="btn btn-ghost" onClick={() => go(step - 1)} disabled={step === 0}>
            <ArrowLeft size={16} aria-hidden /> Back
          </button>
          <div className="wiz-progress" aria-hidden><span style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} /></div>
          {step < LAST ? (
            <button className="btn btn-cta">Next <ArrowRight size={16} aria-hidden /></button>
          ) : (
            <button className="btn btn-cta" disabled={submitting} aria-keyshortcuts="Control+Enter Meta+Enter">
              {submitting ? <><span className="spinner" aria-hidden /> Building your itinerary</> : <>Build my itinerary <ArrowRight size={16} aria-hidden /></>}
            </button>
          )}
        </div>
        <p className="small muted wiz-note">
          {mock ? "Demo data: ratings, prices and times are illustrative."
            : status?.google.active ? "Open map data, with Google ratings where a place matches. Times and most prices are estimates."
            : "Built from open map data. Times and most prices are estimates."}{" "}
          Saved only in this browser.
        </p>
      </form>

      <BoardingPass req={req} step={step} steps={STEPS.length} />
    </div>
  );
}
