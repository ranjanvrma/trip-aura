import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import Globe from "../components/globe/Globe";
import Showcase from "../components/home/Showcase";
import SplitFlap from "../components/home/SplitFlap";
import DescribeTrip from "../components/planner/DescribeTrip";
import GeneratingPanel from "../components/planner/GeneratingPanel";
import TripForm from "../components/planner/TripForm";
import TripPass from "../components/trip/TripPass";
import Autocomplete from "../components/ui/Autocomplete";
import RetryNotice from "../components/ui/RetryNotice";
import { SkeletonLines } from "../components/ui/Skeleton";
import Stepper from "../components/ui/Stepper";
import { listSavedTrips, saveTrip } from "../lib/localTrips";
import { usePageMeta } from "../lib/meta";
import { mutate, useSWR } from "../lib/swr";
import { useToast } from "../lib/toast";
import { useDeleteTrip } from "../lib/trips";
import { useScrollMotion } from "../lib/useScrollMotion";
import { api, ApiError } from "../services/api";
import type { ApiStatus, CitySuggestion, LatLng, ParsedTrip, TripRequest } from "../types";

// Names for the departure board. Only the names live here: coordinates and the country come from the city index.
const BOARD = ["Lisbon", "Kyoto", "Jaipur", "Istanbul", "Cape Town", "Hanoi", "Prague", "Lima", "Nairobi"];
const BOARD_CELLS = 9;
const SOURCES = ["Overture Maps", "Wikidata", "OpenStreetMap", "Wikivoyage", "GeoNames"];

/** Scroll to the planner, then put the cursor in one of its fields. */
const scrollToPlan = (focusId?: string) => {
  document.getElementById("plan")?.scrollIntoView({ behavior: "smooth", block: "start" });
  if (focusId) window.setTimeout(() => document.getElementById(focusId)?.focus({ preventScroll: true }), 500);
};

export default function PlannerPage({ status }: { status: ApiStatus | null }) {
  usePageMeta(null);
  const nav = useNavigate();
  const toast = useToast();
  const root = useRef<HTMLDivElement>(null);
  const ready = status !== null;
  const mock = status?.data_mode === "mock";
  const options = useSWR(ready ? "options" : null, api.options, { dedupeMs: 60_000 });
  const trips = useSWR("localTrips", async () => listSavedTrips());
  const deleteTrip = useDeleteTrip();
  // saved trips appear as pins on the globe (newest first, so the arc runs from the latest trip)
  const pins = useMemo(() => (trips.data ?? []).slice(0, 12).map((t) => ({
    lat: t.itinerary.accommodation.location.lat, lng: t.itinerary.accommodation.location.lng, label: t.title,
  })), [trips.data]);

  const [submitting, setSubmitting] = useState(false);
  const [pendingCity, setPendingCity] = useState("");
  const [prefill, setPrefill] = useState<{ parsed: ParsedTrip; version: number } | null>(null);
  const [error, setError] = useState<{ message: string; details?: unknown } | null>(null);
  const [cityLoc, setCityLoc] = useState<LatLng | null>(null);
  // the hero's quick start: a city and a length, handed to the planner below
  const [heroCity, setHeroCity] = useState("");
  const [heroPick, setHeroPick] = useState<CitySuggestion | null>(null);
  const [heroDays, setHeroDays] = useState(3);
  const board = useMemo(() => (mock ? [status?.mock_city ?? "Jaipur"] : BOARD), [mock, status?.mock_city]);

  useScrollMotion(root, [options.data !== undefined, trips.data?.length]);

  // keyboard: "/" focuses the city field, Ctrl/Cmd+Enter submits from anywhere in the form
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest("input, textarea, select, [contenteditable]");
      if (e.key === "/" && !typing) { e.preventDefault(); scrollToPlan("city-input"); }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && (e.target as HTMLElement)?.closest("form.form")) {
        e.preventDefault();
        document.querySelector<HTMLFormElement>("form.form")?.requestSubmit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const applyParsed = useCallback(
    (p: ParsedTrip) => setPrefill((old) => ({ parsed: p, version: (old?.version ?? 0) + 1 })), []);
  const fetchCities = useCallback(
    (q: string, signal: AbortSignal) => api.citySuggestions(q, signal).then((r) => r.results), []);

  /** Hand a city (and optionally a length) to the planner, which turns the globe and fills the pass. */
  const startWith = (city: CitySuggestion, days?: number) => {
    applyParsed({ fields: { destination_city: city.query, ...(days ? { num_days: days } : {}) }, understood: [], notes: [], city });
    setHeroCity(city.query);
    setHeroPick(city);
  };

  const pickByName = async (name: string) => {
    try {
      const [city] = (await api.citySuggestions(name)).results;
      if (!city) return;
      startWith(city);
      scrollToPlan("stay-input");
    } catch (e) {
      toast.show({ tone: "error", message: (e as ApiError).message });
    }
  };

  const startFromHero = async (e: React.FormEvent) => {
    e.preventDefault();
    // leave the field: the planner takes over, and late suggestions must not open under a field nobody is in
    (document.activeElement as HTMLElement | null)?.blur();
    try {
      const city = heroPick ?? (heroCity.trim().length >= 2 ? (await api.citySuggestions(heroCity.trim())).results[0] : undefined);
      if (!city) { scrollToPlan("city-input"); return; }
      startWith(city, heroDays);
      scrollToPlan("stay-input");
    } catch (err) {
      toast.show({ tone: "error", message: (err as ApiError).message });
    }
  };

  const submit = async (req: TripRequest) => {
    setSubmitting(true);
    setPendingCity(req.destination_city);
    setError(null);
    // the progress panel replaces the planner, so jump to the top of the section once it has rendered
    window.setTimeout(() => document.getElementById("plan")?.scrollIntoView({ behavior: "auto", block: "start" }), 0);
    try {
      const it = await api.previewTrip(req);
      const saved = saveTrip(it);
      mutate("localTrips", listSavedTrips());
      toast.show({ tone: "success", message: `Your ${it.days.length}-day plan for ${req.destination_city} is ready` });
      nav(`/trips/${saved.id}`, { viewTransition: true });
    } catch (e) {
      const err = e as ApiError;
      setError({ message: err.message, details: err.details });
      toast.show({ tone: "error", message: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  const formReady = options.data && status;

  // "Plan a trip" links from the bar and the footer arrive as /#plan
  const { hash, key: navKey } = useLocation();
  useEffect(() => { if (hash === "#plan") scrollToPlan(); }, [hash, navKey]);

  return (
    <div className="home" ref={root}>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <h1 id="hero-title" className="display" aria-label="Your days in any city, planned stop by stop">
            <span aria-hidden>Your days in</span>
            <SplitFlap words={board} cells={BOARD_CELLS} onPick={(w) => void pickByName(w)} />
            <span aria-hidden>planned <em>stop by stop.</em></span>
          </h1>
          <p className="lead">
            Tell it the city and where you're staying. You get each day in an order that saves walking, meals that
            suit how you eat, and what the day will roughly cost.
          </p>

          {mock ? (
            <div className="hero-actions">
              <button type="button" className="btn btn-cta btn-lg" onClick={() => scrollToPlan("stay-input")}>
                Plan a trip <ArrowRight size={18} aria-hidden />
              </button>
            </div>
          ) : (
            <form className="starter" onSubmit={(e) => void startFromHero(e)} aria-label="Start a plan">
              <label className="starter-field starter-city">
                <span>Where to</span>
                <Autocomplete<CitySuggestion>
                  inputId="hero-city" value={heroCity} minChars={2} placeholder="Any city in the world"
                  onChange={(v) => { setHeroCity(v); setHeroPick(null); }}
                  onSelect={(c) => startWith(c)}
                  fetchItems={fetchCities} itemKey={(c) => String(c.id)}
                  renderItem={(c) => (
                    <span className="ac-item"><strong>{c.name}</strong>
                      <span className="muted small"> {[c.region, c.country].filter((x) => x && x !== c.name).join(", ")}</span>
                    </span>
                  )}
                  footer="City data © GeoNames"
                />
              </label>
              <div className="starter-field">
                <label htmlFor="hero-days">Days</label>
                <Stepper id="hero-days" label="days" min={1} max={14} value={heroDays} onValue={setHeroDays} />
              </div>
              <button className="btn btn-cta btn-lg">Start planning <ArrowRight size={18} aria-hidden /></button>
            </form>
          )}
          <p className="hero-alt small muted">
            Or <a href="#describe" onClick={(e) => { e.preventDefault(); document.getElementById("describe-text")?.focus(); }}>describe
            the whole trip in one sentence</a>. No account needed.
          </p>
        </div>

        <div className="hero-globe" data-parallax="0.06">
          <Globe target={cityLoc} pins={pins}
                 label={cityLoc ? "Your destination on the globe" : "The globe, with your saved trips marked"} />
        </div>

        <ul className="sources" aria-label="Open data the plans are built from">
          <li className="muted">Built on open data from</li>
          {SOURCES.map((s) => <li key={s}>{s}</li>)}
        </ul>
      </section>

      <Showcase />

      <section className="describe-band" id="describe" data-reveal>
        {formReady ? <DescribeTrip onParsed={(p) => { applyParsed(p); scrollToPlan("stay-input"); }} /> : <SkeletonLines lines={4} />}
      </section>

      <section className="plan" id="plan" aria-busy={submitting}>
        <header className="section-head">
          <h2 id="plan-title" className="h1">Plan your trip</h2>
          <p className="lead">Five short questions. Your pass fills in as you go.</p>
        </header>
        {error && (
          <div className="notice notice-error" role="alert">
            <strong>{error.message}</strong>
            {Array.isArray(error.details) && (
              <ul className="small">
                {(error.details as { field: string; message: string }[]).map((d) => (
                  <li key={d.field + d.message}>{d.field || "request"}: {d.message}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {submitting && <GeneratingPanel city={pendingCity} firstVisitHint={status?.data_mode === "open"} />}
        {formReady ? (
          // kept mounted (hidden) while generating, so the answers are still there if the request fails
          <div hidden={submitting}>
            <TripForm options={options.data!} status={status!} submitting={submitting} onSubmit={(r) => void submit(r)}
                      prefill={prefill} onCityLocation={setCityLoc} />
          </div>
        ) : options.error ? (
          <RetryNotice message={`Couldn't load the planner: ${options.error.message}`} onRetry={() => void options.refresh()} />
        ) : (
          <div className="tile stack-m"><SkeletonLines lines={2} /><SkeletonLines lines={3} /><SkeletonLines lines={3} /></div>
        )}
      </section>

      {!!trips.data?.length && (
        <section className="recent" aria-labelledby="saved-title" data-reveal>
          <header className="section-head section-head-row">
            <h2 id="saved-title" className="h1">Your trips</h2>
            <Link to="/trips" viewTransition>See all</Link>
          </header>
          <ul className="trip-passes">
            {trips.data.slice(0, 6).map((t) => <TripPass key={t.id} trip={t} onDelete={deleteTrip} />)}
          </ul>
        </section>
      )}
    </div>
  );
}
