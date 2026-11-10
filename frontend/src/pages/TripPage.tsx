import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CalendarDays, Plus, RotateCcw } from "lucide-react";
import BudgetSummary from "../components/BudgetSummary";
import { type Command, usePageCommands } from "../components/CommandMenu";
import DayCard from "../components/DayCard";
import MapView from "../components/map/MapView";
import type { MapMarker, MapPolyline } from "../components/map/types";
import PlaceDetails from "../components/PlaceDetails";
import RestaurantList from "../components/RestaurantList";
import RetryNotice from "../components/ui/RetryNotice";
import Sheet from "../components/ui/Sheet";
import { Skeleton, SkeletonLines } from "../components/ui/Skeleton";
import { usePageMeta } from "../lib/meta";
import { prefersReducedMotion } from "../lib/platform";
import { mutate, useSWR } from "../lib/swr";
import { useToast } from "../lib/toast";
import { useScrollMotion } from "../lib/useScrollMotion";
import { getSavedTrip, listSavedTrips, saveTrip } from "../lib/localTrips";
import { api, ApiError } from "../services/api";
import type { ItineraryItem } from "../types";
import { dataSourceLabel, dayColor } from "../utils";
import NotFoundPage from "./NotFoundPage";

function useIsNarrow(query = "(max-width: 960px)") {
  const [narrow, setNarrow] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setNarrow(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return narrow;
}

export default function TripPage() {
  const { id } = useParams();
  const toast = useToast();
  const narrow = useIsNarrow();
  const root = useRef<HTMLDivElement>(null);

  const key = id ? `local-trip:${id}` : null;
  const trip = useSWR(key, async () => id ? getSavedTrip(id) : null, { dedupeMs: 30_000 });
  const it = trip.data?.itinerary ?? null;

  const [dayFilter, setDayFilter] = useState<number | "all">("all");
  const [selected, setSelected] = useState<ItineraryItem | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  usePageMeta(it ? `${it.request.num_days} days in ${it.request.destination_city}` : "Your itinerary",
    it ? `Day-by-day plan for ${it.request.destination_city}: sights, meals, transport and budget.` : undefined,
    { noindex: true });
  useScrollMotion(root, [id, dayFilter]);

  const days = useMemo(() => (it ? it.days.filter((d) => dayFilter === "all" || d.day_number === dayFilter) : []), [it, dayFilter]);

  const { markers, polylines } = useMemo(() => {
    const markers: MapMarker[] = [];
    const polylines: MapPolyline[] = [];
    if (!it) return { markers, polylines };
    markers.push({ id: "home", position: it.accommodation.location, label: "H", kind: "home", color: "#2f3a33",
                   title: `${it.accommodation.name} (your accommodation)` });
    for (const d of days) {
      const color = dayColor(d.day_number);
      let n = 0;
      for (const i of d.items) {
        if (i.type === "travel" && i.travel) {
          const path = i.travel.chosen.polyline.length ? i.travel.chosen.polyline : [i.travel.origin, i.travel.destination];
          polylines.push({ id: i.id, path, color, dashed: i.travel.chosen.mode === "walking" });
        } else if (i.place && i.place.id !== "accommodation" && (i.type === "activity" || i.type === "meal" || i.type === "rest")) {
          if (i.type === "activity") n += 1;
          markers.push({
            id: i.id, position: i.place.location, kind: i.type as MapMarker["kind"], color: i.type === "activity" ? color : "#7a746a",
            label: i.type === "activity" ? String(n) : i.type === "meal" ? (i.meal_type?.[0].toUpperCase() ?? "M") : "R",
            title: `Day ${d.day_number} ${i.start} - ${i.title}`,
          });
        }
      }
    }
    return { markers, polylines };
  }, [it, days]);

  // stable map props: the Google renderer rebuilds its overlays and refits the view whenever these change
  const selectById = useCallback((mid: string) => {
    const item = it?.days.flatMap((d) => d.items).find((i) => i.id === mid);
    if (item) setSelected(item);
  }, [it]);
  const regenerate = useCallback(async () => {
    if (!key || !id || !it) return;
    setRegenerating(true);
    try {
      const fresh = await api.previewTrip(it.request);
      const saved = saveTrip(fresh, id, trip.data?.created_at);
      mutate(key, saved);
      mutate("localTrips", listSavedTrips());
      setSelected(null);
      toast.show({ tone: "success", message: "Itinerary regenerated with the latest data" });
    } catch (e) {
      toast.show({ tone: "error", message: `Couldn't regenerate: ${(e as ApiError).message}` });
    } finally {
      setRegenerating(false);
    }
  }, [key, id, it, trip.data?.created_at, toast]);

  const showDay = useCallback((n: number | "all") => {
    const apply = () => setDayFilter(n);
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition && !prefersReducedMotion()) doc.startViewTransition(apply);
    else apply();
  }, []);

  const commands = useMemo<Command[]>(() => !it ? [] : [
    { id: "all-days", label: "Show all days", group: "This trip", icon: CalendarDays, run: () => showDay("all") },
    ...it.days.map<Command>((d) => ({
      id: `day-${d.day_number}`, label: `Show day ${d.day_number}`, hint: `${d.weekday} ${d.date}`, group: "This trip",
      icon: CalendarDays, run: () => showDay(d.day_number),
    })),
    { id: "regen", label: "Regenerate this itinerary", group: "This trip", icon: RotateCcw, run: () => void regenerate() },
  ], [it, showDay, regenerate]);
  usePageCommands(commands);

  if (!key || (trip.data === null && !trip.loading) || (trip.error as ApiError | undefined)?.status === 404) return <NotFoundPage what="trip" />;
  if (trip.error && !it) {
    return (
      <div className="narrow">
        <RetryNotice message={`Couldn't load this trip: ${trip.error.message}`} onRetry={() => void trip.refresh()} />
      </div>
    );
  }
  if (!it) {
    return (
      <div className="trip-layout" aria-busy="true" aria-label="Loading itinerary">
        <div className="tile trip-summary"><Skeleton w="45%" h={28} /><Skeleton w="70%" /></div>
        <div className="trip-grid">
          <div className="stack-m">{[0, 1].map((i) => <div key={i} className="tile"><SkeletonLines lines={6} /></div>)}</div>
          <div className="tile"><Skeleton h={320} r={12} /></div>
        </div>
      </div>
    );
  }

  const r = it.request;
  const details = selected && <PlaceDetails item={selected} onClose={() => setSelected(null)} embedded={narrow} />;

  return (
    <div className="trip-layout" ref={root}>
      <header className="tile trip-summary">
        <div>
          <p className="eyebrow">Itinerary</p>
          <h1 className="h1">{r.num_days} days in {r.destination_city}</h1>
          <p className="muted small">
            From {it.accommodation.name} · <span className="num">{r.travelers}</span> traveller{r.travelers > 1 ? "s" : ""} · {r.pace} pace
            {" · "}<span className="badge">{dataSourceLabel(it.data_source)}</span>
          </p>
        </div>
        <div className="row gap-s wrap">
          <button className="btn btn-ghost" onClick={() => void regenerate()} disabled={regenerating}>
            {regenerating ? <><span className="spinner" aria-hidden /> Regenerating</> : <><RotateCcw size={16} aria-hidden /> Regenerate</>}
          </button>
          <Link className="btn btn-primary" to="/" viewTransition><Plus size={16} aria-hidden /> New trip</Link>
        </div>
      </header>

      {it.disclaimers.filter((d) => d.startsWith("DEMO")).map((d) => <p key={d} className="notice notice-warn small">{d}</p>)}
      {it.disclaimers.some((d) => !d.startsWith("DEMO")) && (
        <details className="about-data">
          <summary>About this data</summary>
          <ul className="small muted">
            {it.disclaimers.filter((d) => !d.startsWith("DEMO")).map((d) => <li key={d}>{d}</li>)}
          </ul>
        </details>
      )}
      {it.warnings.length > 0 && (
        <div className="notice notice-warn small"><ul>{it.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>
      )}
      {it.ai_summary && (
        <section className="tile">
          <h2 className="h3">Trip overview</h2>
          <p className="pre">{it.ai_summary}</p>
          <p className="small muted">Written by a language model from the plan above.</p>
        </section>
      )}

      <div className="day-tabs" role="tablist" aria-label="Days">
        <button role="tab" aria-selected={dayFilter === "all"} className={`seg ${dayFilter === "all" ? "is-on" : ""}`}
                onClick={() => showDay("all")}>All days</button>
        {it.days.map((d) => (
          <button key={d.day_number} role="tab" aria-selected={dayFilter === d.day_number}
                  className={`seg ${dayFilter === d.day_number ? "is-on" : ""}`}
                  style={{ "--day": dayColor(d.day_number) } as React.CSSProperties}
                  onClick={() => showDay(d.day_number)}>
            <span className="day-dot" aria-hidden />Day {d.day_number}
          </button>
        ))}
      </div>

      <div className="trip-grid">
        <div className="stack-m days-col">
          {days.map((d) => (
            <div key={d.day_number} data-reveal>
              <DayCard day={d} color={dayColor(d.day_number)}
                       currency={it.budget.currency} selectedId={selected?.id ?? null} onSelect={setSelected} />
            </div>
          ))}
          {it.unscheduled.length > 0 && (
            <section className="tile" data-reveal>
              <h2 className="h3">Also worth considering</h2>
              <ul className="small">{it.unscheduled.map((u) => <li key={u.place.id}><strong>{u.place.name}</strong>: {u.reason}</li>)}</ul>
            </section>
          )}
          <div data-reveal><RestaurantList recs={it.food_recommendations} popular={it.popular_dishes} /></div>
          {it.attributions.length > 0 && (
            <p className="small muted attributions"><strong>Data sources:</strong> {it.attributions.join(" · ")}</p>
          )}
        </div>
        <div className="side-col">
          <div className="sticky stack-m">
            <div className="tile tile-map">
              <MapView markers={markers} polylines={polylines} selectedId={selected?.id ?? null} onSelect={selectById}
                       current={null} />
            </div>
            {!narrow && details}
            <p className="tile small muted">Live location updates aren’t available for trips saved only in this browser.</p>
            <BudgetSummary b={it.budget} />
          </div>
        </div>
      </div>

      {narrow && (
        <Sheet open={!!selected} onClose={() => setSelected(null)} title={selected?.place?.name ?? "Place"}>
          {details}
        </Sheet>
      )}
    </div>
  );
}
