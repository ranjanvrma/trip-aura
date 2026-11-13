import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Trash } from "lucide-react";
import DescribeTrip from "../components/DescribeTrip";
import GeneratingPanel from "../components/GeneratingPanel";
import Globe from "../components/globe/Globe";
import TripForm from "../components/TripForm";
import RetryNotice from "../components/ui/RetryNotice";
import { Kbd, SkeletonLines } from "../components/ui/Skeleton";
import { usePageMeta } from "../lib/meta";
import { modKey } from "../lib/platform";
import { mutate, useSWR } from "../lib/swr";
import { useToast } from "../lib/toast";
import { useDeleteTrip } from "../lib/trips";
import { useScrollMotion } from "../lib/useScrollMotion";
import { listSavedTrips, saveTrip } from "../lib/localTrips";
import { api, ApiError } from "../services/api";
import type { ApiStatus, LatLng, ParsedTrip, TripRequest } from "../types";

export default function PlannerPage({ status }: { status: ApiStatus | null }) {
  usePageMeta(null);
  const nav = useNavigate();
  const toast = useToast();
  const root = useRef<HTMLDivElement>(null);
  const ready = status !== null;
  const options = useSWR(ready ? "options" : null, api.options, { dedupeMs: 60_000 });
  const trips = useSWR("localTrips", async () => listSavedTrips());
  const deleteTrip = useDeleteTrip();

  const [submitting, setSubmitting] = useState(false);
  const [pendingCity, setPendingCity] = useState("");
  const [prefill, setPrefill] = useState<{ parsed: ParsedTrip; version: number } | null>(null);
  const [error, setError] = useState<{ message: string; details?: unknown } | null>(null);
  const [cityLoc, setCityLoc] = useState<LatLng | null>(null);

  useScrollMotion(root, [options.data !== undefined]);

  // keyboard: "/" focuses the city field, Ctrl/Cmd+Enter submits the form
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

  const submit = async (req: TripRequest) => {
    setSubmitting(true);
    setPendingCity(req.destination_city);
    setError(null);
    // The form is long and the progress panel that replaces it is short, so jump to the top of the tile
    // once the panel has rendered (an instant jump: the content under the pointer is changing anyway).
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

  return (
    <div className="bento planner" ref={root}>
      <section className="tile tile-hero" data-reveal>
        <p className="eyebrow">Day-by-day trip planner</p>
        <h1 className="display">Plan each day of your trip, stop by stop.</h1>
        <p className="lead">
          Pick a city and where you're staying. TripAura orders the sights to cut travel time, checks opening hours,
          adds meals that fit your diet and shows the cost of each day.
        </p>
        <div className="hero-actions">
          <a href="#plan" className="btn btn-primary" onClick={(e) => {
            e.preventDefault();
            document.getElementById("plan")?.scrollIntoView({ behavior: "smooth", block: "start" });
            window.setTimeout(() => document.getElementById("city-input")?.focus({ preventScroll: true }), 450);
          }}>Start planning <ArrowRight size={16} aria-hidden /></a>
          <span className="small muted shortcut-hint">or press <Kbd>/</Kbd> to jump to the city field</span>
        </div>
      </section>

      <section className="tile tile-globe" data-reveal>
        <div data-parallax="0.12" className="globe-wrap">
          <Globe target={cityLoc} label={cityLoc ? "Your destination" : "Any city with open map data"} />
        </div>
      </section>

      <section className="tile tile-describe" data-reveal>
        {options.data && status
          ? <DescribeTrip onParsed={(p) => setPrefill((old) => ({ parsed: p, version: (old?.version ?? 0) + 1 }))} />
          : <SkeletonLines lines={4} />}
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
        {options.data && status ? (
          // kept mounted (hidden) while generating, so the details are still there if the request fails
          <div hidden={submitting}>
            <TripForm options={options.data} status={status} submitting={submitting} onSubmit={(r) => void submit(r)}
                      prefill={prefill} onCityLocation={setCityLoc} />
          </div>
        ) : options.error ? (
          <RetryNotice message={`Couldn't load the form options: ${options.error.message}`} onRetry={() => void options.refresh()} />
        ) : (
          <div className="stack-m"><SkeletonLines lines={2} /><SkeletonLines lines={3} /><SkeletonLines lines={3} /></div>
        )}
      </section>

      <aside className="tile tile-saved" data-reveal aria-labelledby="saved-title">
        <div className="tile-head">
          <h2 id="saved-title" className="tile-title">Saved trips</h2>
          <Link to="/trips" className="small" viewTransition>View all</Link>
        </div>
        {trips.loading ? <SkeletonLines lines={3} />
          : trips.data?.length === 0 ? <p className="small muted">No saved trips yet. Your first plan will appear here.</p>
          : (
            <ul className="trip-list">
              {trips.data?.slice(0, 6).map((t) => (
                <li key={t.id} className="trip-row">
                  <Link to={`/trips/${t.id}`} viewTransition className="trip-link">
                    <span className="truncate">{t.title}</span>
                    <span className="small muted num">{t.num_days} days</span>
                  </Link>
                  <button className="icon-btn hit" onClick={() => deleteTrip(t)} aria-label={`Delete ${t.title}`}>
                    <Trash size={16} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}
      </aside>

      <section className="tile tile-steps" data-reveal aria-labelledby="how-title">
        <h2 id="how-title" className="tile-title">How a plan is built</h2>
        <ol className="steps">
          <li><span><strong>Places.</strong> Overture Maps, Wikidata, OpenStreetMap and Wikivoyage are read for your city and cached for 30 days.</span></li>
          <li><span><strong>Fit.</strong> Each place gets a 0 to 5 score for your interests, budget, distance, transport, time and pace.</span></li>
          <li><span><strong>Order.</strong> Each day starts from its strongest sight and is reordered to shorten the walking and riding.</span></li>
          <li><span><strong>Cost.</strong> Fares, meals and tickets are estimated from local price levels and marked as estimates.</span></li>
        </ol>
      </section>

      <section className="tile tile-shortcuts" data-reveal aria-labelledby="keys-title">
        <h2 id="keys-title" className="tile-title">Keyboard</h2>
        <dl className="keys">
          <div><dt><Kbd>{modKey()}</Kbd><Kbd>K</Kbd></dt><dd>Search pages, trips and actions</dd></div>
          <div><dt><Kbd>/</Kbd></dt><dd>Jump to the city field</dd></div>
          <div><dt><Kbd>{modKey()}</Kbd><Kbd>Enter</Kbd></dt><dd>Generate from anywhere in the form</dd></div>
          <div><dt><Kbd>Esc</Kbd></dt><dd>Close a menu or panel</dd></div>
        </dl>
      </section>
    </div>
  );
}
