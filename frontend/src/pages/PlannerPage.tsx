import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Trash } from "lucide-react";
import Globe from "../components/globe/Globe";
import DescribeTrip from "../components/planner/DescribeTrip";
import GeneratingPanel from "../components/planner/GeneratingPanel";
import TripForm from "../components/planner/TripForm";
import RetryNotice from "../components/ui/RetryNotice";
import { SkeletonLines } from "../components/ui/Skeleton";
import { listSavedTrips, saveTrip } from "../lib/localTrips";
import { usePageMeta } from "../lib/meta";
import { mutate, useSWR } from "../lib/swr";
import { useToast } from "../lib/toast";
import { useDeleteTrip } from "../lib/trips";
import { useScrollMotion } from "../lib/useScrollMotion";
import { api, ApiError } from "../services/api";
import type { ApiStatus, LatLng, ParsedTrip, TripRequest } from "../types";

// One-click starting points. Only the names live here: coordinates and the country come from the city index.
const QUICK_CITIES = ["Lisbon", "Kyoto", "Jaipur", "Mexico City", "Istanbul", "Cape Town"];

const scrollToPlan = (focusCity: boolean) => {
  document.getElementById("plan")?.scrollIntoView({ behavior: "smooth", block: "start" });
  if (focusCity) window.setTimeout(() => document.getElementById("city-input")?.focus({ preventScroll: true }), 450);
};

export default function PlannerPage({ status }: { status: ApiStatus | null }) {
  usePageMeta(null);
  const nav = useNavigate();
  const toast = useToast();
  const root = useRef<HTMLDivElement>(null);
  const ready = status !== null;
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

  useScrollMotion(root, [options.data !== undefined]);

  // keyboard: "/" focuses the city field, Ctrl/Cmd+Enter submits from anywhere in the form
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest("input, textarea, select, [contenteditable]");
      if (e.key === "/" && !typing) { e.preventDefault(); document.getElementById("city-input")?.focus(); }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && (e.target as HTMLElement)?.closest("form.form")) {
        e.preventDefault();
        document.querySelector<HTMLFormElement>("form.form")?.requestSubmit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const applyParsed = (p: ParsedTrip) => setPrefill((old) => ({ parsed: p, version: (old?.version ?? 0) + 1 }));

  const pickCity = async (name: string) => {
    try {
      const [city] = (await api.citySuggestions(name)).results;
      if (!city) return;
      applyParsed({ fields: { destination_city: city.query }, understood: [], notes: [], city });
      scrollToPlan(false);
    } catch (e) {
      toast.show({ tone: "error", message: (e as ApiError).message });
    }
  };

  const submit = async (req: TripRequest) => {
    setSubmitting(true);
    setPendingCity(req.destination_city);
    setError(null);
    // the progress panel replaces the long form, so jump to the top of the tile once it has rendered
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

  return (
    <div className="bento planner" ref={root}>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <h1 id="hero-title" className="display">
            Every day of your trip, <em>planned stop by stop.</em>
          </h1>
          <p className="lead">
            Tell it the city and where you're staying. You get each day in an order that saves walking, meals that
            suit how you eat, and what the day will roughly cost.
          </p>
          <div className="hero-actions">
            <a href="#plan" className="btn btn-primary btn-lg" onClick={(e) => { e.preventDefault(); scrollToPlan(true); }}>
              Plan a trip <ArrowRight size={18} aria-hidden />
            </a>
          </div>
          {formReady && status?.data_mode !== "mock" && (
            <div className="quick-cities">
              <span className="small muted">Or start from</span>
              <ul>
                {QUICK_CITIES.map((c) => (
                  <li key={c}><button type="button" className="quick-city" onClick={() => void pickCity(c)}>{c}</button></li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="hero-globe" data-parallax="0.08">
          <Globe target={cityLoc} pins={pins}
                 label={cityLoc ? "Your destination on the globe" : "The globe, with your saved trips marked"} />
        </div>
      </section>

      <div className="plan-col">
        <section className="tile tile-describe" data-reveal>
          {formReady ? <DescribeTrip onParsed={applyParsed} /> : <SkeletonLines lines={4} />}
        </section>

        <section className="tile tile-form" id="plan" data-reveal aria-busy={submitting}>
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
            // kept mounted (hidden) while generating, so the details are still there if the request fails
            <div hidden={submitting}>
              <TripForm options={options.data!} status={status!} submitting={submitting} onSubmit={(r) => void submit(r)}
                        prefill={prefill} onCityLocation={setCityLoc} />
            </div>
          ) : options.error ? (
            <RetryNotice message={`Couldn't load the form options: ${options.error.message}`} onRetry={() => void options.refresh()} />
          ) : (
            <div className="stack-m"><SkeletonLines lines={2} /><SkeletonLines lines={3} /><SkeletonLines lines={3} /></div>
          )}
        </section>
      </div>

      <aside className="side-stack" aria-label="Your trips and how plans are made">
        <section className="tile tile-saved" data-reveal aria-labelledby="saved-title">
          <div className="tile-head">
            <h2 id="saved-title" className="tile-title">Your trips</h2>
            {!!trips.data?.length && <Link to="/trips" className="small" viewTransition>See all</Link>}
          </div>
          {trips.loading ? <SkeletonLines lines={3} />
            : trips.data?.length === 0 ? <p className="small muted">Plans you make are kept here, in this browser.</p>
            : (
              <ul className="trip-list">
                {trips.data?.slice(0, 6).map((t) => (
                  <li key={t.id} className="trip-row">
                    <Link to={`/trips/${t.id}`} viewTransition className="trip-link">
                      <span className="truncate">{t.destination.split(",")[0]}</span>
                      <span className="small muted num">{t.num_days} {t.num_days === 1 ? "day" : "days"}</span>
                    </Link>
                    <button className="icon-btn hit" onClick={() => deleteTrip(t)} aria-label={`Delete ${t.title}`}>
                      <Trash size={16} aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
        </section>

        <section className="method" data-reveal aria-labelledby="method-title">
          <h2 id="method-title" className="tile-title">How the plan is made</h2>
          <ol>
            <li>Places come from Overture Maps, Wikidata, OpenStreetMap and Wikivoyage, and are kept for 30 days.</li>
            <li>Each one is scored for you: interests, budget, distance, transport, time and pace. Outside ratings never count.</li>
            <li>Every day starts from its strongest sight, then the stops are reordered to cut the walking and riding.</li>
            <li>Fares, meals and tickets are estimated from local prices, and labelled as estimates.</li>
          </ol>
        </section>
      </aside>
    </div>
  );
}
