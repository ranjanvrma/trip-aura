import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import BudgetSummary from "../components/BudgetSummary";
import DayCard from "../components/DayCard";
import LiveLocationPanel from "../components/LiveLocationPanel";
import MapView from "../components/map/MapView";
import type { MapMarker, MapPolyline } from "../components/map/types";
import PlaceDetails from "../components/PlaceDetails";
import RestaurantList from "../components/RestaurantList";
import { useGeolocation } from "../hooks/useGeolocation";
import { useLiveProgress } from "../hooks/useLiveProgress";
import { api, ApiError } from "../services/api";
import type { Itinerary, ItineraryItem } from "../types";
import { DAY_COLORS } from "../utils";

export default function TripPage() {
  const { id } = useParams();
  const tripId = Number(id);
  const loc = useLocation();
  const [it, setIt] = useState<Itinerary | null>((loc.state as { itinerary?: Itinerary } | null)?.itinerary ?? null);
  const [error, setError] = useState<string | null>(null);
  const [dayFilter, setDayFilter] = useState<number | "all">("all");
  const [selected, setSelected] = useState<ItineraryItem | null>(null);
  const [liveOn, setLiveOn] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    if (!it || it.trip_id !== tripId) {
      api.getTrip(tripId).then(setIt).catch((e: ApiError) => setError(e.message));
    }
  }, [tripId]); // eslint-disable-line react-hooks/exhaustive-deps

  const liveDay = dayFilter === "all" ? 1 : dayFilter;
  const geo = useGeolocation(liveOn);
  const live = useLiveProgress(tripId, liveDay, geo.position, geo.accuracy, liveOn, target);

  const days = useMemo(() => (it ? it.days.filter((d) => dayFilter === "all" || d.day_number === dayFilter) : []), [it, dayFilter]);

  const { markers, polylines } = useMemo(() => {
    const markers: MapMarker[] = [];
    const polylines: MapPolyline[] = [];
    if (!it) return { markers, polylines };
    markers.push({ id: "home", position: it.accommodation.location, label: "H", kind: "home", color: "#111827",
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
            id: i.id, position: i.place.location, kind: i.type as MapMarker["kind"], color: i.type === "activity" ? color : "#6b7280",
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

  const regenerate = async () => {
    setRegenerating(true);
    try { setIt(await api.regenerate(tripId)); } catch (e) { setError((e as ApiError).message); }
    finally { setRegenerating(false); }
  };

  if (error) return <div className="banner banner-error">{error} <Link to="/">Back</Link></div>;
  if (!it) return <div className="card">Loading itinerary...</div>;
  const r = it.request;

  return (
    <div className="trip">
      <div className="trip-head card">
        <div>
          <h2>{r.num_days} days in {r.destination_city}</h2>
          <p className="muted small">
            From {it.accommodation.name} · {r.travelers} traveller{r.travelers > 1 ? "s" : ""} · {r.pace} pace ·
            data: <span className={`badge ${it.data_source === "mock" ? "badge-mock" : "badge-google"}`}>{it.data_source}</span>
          </p>
        </div>
        <div className="row gap-s">
          <button className="btn btn-light" onClick={() => void regenerate()} disabled={regenerating}>
            {regenerating ? "Regenerating..." : "Regenerate"}
          </button>
          <Link className="btn btn-light" to="/">New trip</Link>
        </div>
      </div>

      {it.disclaimers.map((d) => <p key={d} className={`small ${d.startsWith("DEMO") ? "banner banner-mock" : "muted"}`}>{d}</p>)}
      {it.warnings.length > 0 && <ul className="warn small">{it.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      {it.ai_summary && <div className="card ai"><h3>Trip overview <span className="small muted">(AI-written from the plan data)</span></h3><p className="pre">{it.ai_summary}</p></div>}
      {it.ai_status.startsWith("error") && <p className="small warn">AI summary unavailable: {it.ai_status}</p>}

      <div className="tabs">
        <button className={`chip ${dayFilter === "all" ? "chip-on" : ""}`} onClick={() => setDayFilter("all")}>All days</button>
        {it.days.map((d) => (
          <button key={d.day_number} className={`chip ${dayFilter === d.day_number ? "chip-on" : ""}`}
                  style={{ borderColor: DAY_COLORS[(d.day_number - 1) % DAY_COLORS.length] }}
                  onClick={() => setDayFilter(d.day_number)}>Day {d.day_number}</button>
        ))}
      </div>

      <div className="trip-grid">
        <div className="col-main">
          {days.map((d) => (
            <DayCard key={d.day_number} day={d} color={DAY_COLORS[(d.day_number - 1) % DAY_COLORS.length]}
                     currency={it.budget.currency} selectedId={selected?.id ?? null} onSelect={setSelected} />
          ))}
          {it.unscheduled.length > 0 && (
            <section className="card">
              <h3>Also worth considering</h3>
              <ul className="small">{it.unscheduled.map((u) => <li key={u.place.id}><strong>{u.place.name}</strong> - {u.reason}</li>)}</ul>
            </section>
          )}
          <RestaurantList recs={it.food_recommendations} popular={it.popular_dishes} />
          {it.attributions.length > 0 && (
            <footer className="small muted attributions">
              <strong>Data sources:</strong> {it.attributions.join(" · ")}
            </footer>
          )}
        </div>
        <div className="col-side">
          <div className="sticky">
            <MapView markers={markers} polylines={polylines} selectedId={selected?.id ?? null} onSelect={selectById}
                     current={geo.position ? { position: geo.position, accuracy: geo.accuracy } : null} />
            {selected && <PlaceDetails item={selected} onClose={() => setSelected(null)} />}
            <LiveLocationPanel enabled={liveOn} onToggle={setLiveOn} geo={geo} progress={live.progress}
                               alerts={live.alerts} loading={live.loading} error={live.error}
                               onRefresh={() => void live.refresh()} targets={targets} targetId={target}
                               onTarget={setTarget} />
            <BudgetSummary b={it.budget} />
          </div>
        </div>
      </div>
    </div>
  );
}
