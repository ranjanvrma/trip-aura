import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { CalendarDays, Plus, RotateCcw } from "lucide-react";
import BudgetSummary from "../components/BudgetSummary";
import { type Command, usePageCommands } from "../components/CommandMenu";
import DayCard from "../components/DayCard";
import LiveLocationPanel from "../components/LiveLocationPanel";
import MapView from "../components/map/MapView";
import type { MapMarker, MapPolyline } from "../components/map/types";
import PlaceDetails from "../components/PlaceDetails";
import RestaurantList from "../components/RestaurantList";
import Sheet from "../components/ui/Sheet";
import { Skeleton, SkeletonLines } from "../components/ui/Skeleton";
import { useGeolocation } from "../hooks/useGeolocation";
import { useLiveProgress } from "../hooks/useLiveProgress";
import { usePageMeta } from "../lib/meta";
import { mutate, seed, useSWR } from "../lib/swr";
import { useToast } from "../lib/toast";
import { useScrollMotion } from "../lib/useScrollMotion";
import { api, ApiError, newIdempotencyKey } from "../services/api";
import type { Itinerary, ItineraryItem } from "../types";
import { DAY_COLORS } from "../utils";
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
  const tripId = Number(id);
  const loc = useLocation();
  const toast = useToast();
  const narrow = useIsNarrow();
  const root = useRef<HTMLDivElement>(null);

  // the itinerary handed over by the planner is shown at once (cache seeded), then revalidated
  const handed = (loc.state as { itinerary?: Itinerary } | null)?.itinerary;
  const key = Number.isFinite(tripId) ? `trip:${tripId}` : null;
  if (key && handed?.trip_id === tripId) seed(key, handed);
  const trip = useSWR(key, () => api.getTrip(tripId), { dedupeMs: 30_000 });
  const it = trip.data ?? null;

  const [dayFilter, setDayFilter] = useState<number | "all">("all");
  const [selected, setSelected] = useState<ItineraryItem | null>(null);
  const [liveOn, setLiveOn] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const regenKey = useRef<string | null>(null);

  usePageMeta(it ? `${it.request.num_days} days in ${it.request.destination_city}` : "Your itinerary",
    it ? `Day-by-day plan for ${it.request.destination_city}: sights, meals, transport and budget.` : undefined,
    { noindex: true });
  useScrollMotion(root, [it?.trip_id, dayFilter]);

  const liveDay = dayFilter === "all" ? 1 : dayFilter;
  const geo = useGeolocation(liveOn);
  const live = useLiveProgress(it ? tripId : null, liveDay, geo.position, geo.accuracy, liveOn, target);

  const days = useMemo(() => (it ? it.days.filter((d) => dayFilter === "all" || d.day_number === dayFilter) : []), [it, dayFilter]);

  const { markers, polylines } = useMemo(() => {
    const markers: MapMarker[] = [];
    const polylines: MapPolyline[] = [];
    if (!it) return { markers, polylines };
    markers.push({ id: "home", position: it.accommodation.location, label: "H", kind: "home", color: "#2f3a33",
                   title: `${it.accommodation.name} (your accommodation)` });
    for (const d of days) {
      const color = DAY_COLORS[(d.day_number - 1) % DAY_COLORS.length];
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

  const targets = useMemo(() => it?.days.find((d) => d.day_number === liveDay)?.items
    .filter((i) => (i.type === "activity" || i.type === "meal") && i.place)
    .map((i) => ({ id: i.id, label: `${i.start} ${i.title}` })) ?? [], [it, liveDay]);

  const selectById = (mid: string) => {
    const item = it?.days.flatMap((d) => d.items).find((i) => i.id === mid);
    if (item) setSelected(item);
  };

  const regenerate = useCallback(async () => {
    if (!key) return;
    regenKey.current ??= newIdempotencyKey();   // the same key is reused if this attempt is retried
    setRegenerating(true);
    try {
      const fresh = await api.regenerate(tripId, regenKey.current);
      regenKey.current = null;
      mutate(key, fresh);
      setSelected(null);
      toast.show({ tone: "success", message: "Itinerary regenerated with the latest data" });
    } catch (e) {
      toast.show({ tone: "error", message: `Couldn't regenerate: ${(e as ApiError).message}` });
    } finally {
      setRegenerating(false);
    }
  }, [key, tripId, toast]);

  const showDay = useCallback((n: number | "all") => {
    const apply = () => setDayFilter(n);
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) doc.startViewTransition(apply);
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

  if (!key || (trip.error as ApiError | undefined)?.status === 404) return <NotFoundPage what="trip" />;
  if (trip.error && !it) {
    return (
      <div className="narrow">
        <div className="notice notice-error" role="alert">
          Couldn't load this trip: {trip.error.message}{" "}
          <button className="link" onClick={() => void trip.refresh()}>Try again</button>
        </div>
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
          <h1 className="h1 balance">{r.num_days} days in {r.destination_city}</h1>
          <p className="muted small">
            From {it.accommodation.name} · <span className="num">{r.travelers}</span> traveller{r.travelers > 1 ? "s" : ""} · {r.pace} pace
            {" · "}<span className="badge">{it.data_source === "mock" ? "Demo data" : "Open data"}</span>
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
                  style={{ "--day": DAY_COLORS[(d.day_number - 1) % DAY_COLORS.length] } as React.CSSProperties}
                  onClick={() => showDay(d.day_number)}>
            <span className="day-dot" aria-hidden />Day {d.day_number}
          </button>
        ))}
      </div>

      <div className="trip-grid">
        <div className="stack-m days-col">
          {days.map((d) => (
            <div key={d.day_number} data-reveal>
              <DayCard day={d} color={DAY_COLORS[(d.day_number - 1) % DAY_COLORS.length]}
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
                       current={geo.position ? { position: geo.position, accuracy: geo.accuracy } : null} />
            </div>
            {!narrow && details}
            <LiveLocationPanel enabled={liveOn} onToggle={setLiveOn} geo={geo} progress={live.progress}
                               alerts={live.alerts} loading={live.loading} error={live.error}
                               onRefresh={() => void live.refresh()} targets={targets} targetId={target}
                               onTarget={setTarget} />
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
