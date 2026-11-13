import { Link } from "react-router-dom";
import { CalendarDays, MapPinned, Plus, Trash } from "lucide-react";
import ContourArt from "../components/art/ContourArt";
import { usePageMeta } from "../lib/meta";
import { listSavedTrips } from "../lib/localTrips";
import { useSWR } from "../lib/swr";
import { useDeleteTrip } from "../lib/trips";
import { dataSourceLabel } from "../utils";

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export default function TripsPage() {
  usePageMeta("My trips", "Your saved TripAura itineraries.", { noindex: true });
  const trips = useSWR("localTrips", async () => listSavedTrips());
  const deleteTrip = useDeleteTrip();

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h1">My trips</h1>
          <p className="muted">Saved in this browser on this device. They do not sync to other devices.</p>
        </div>
        <Link to="/" className="btn btn-primary" viewTransition><Plus size={16} aria-hidden /> New trip</Link>
      </header>

      {trips.loading && <p className="muted" role="status">Loading your saved trips…</p>}

      {trips.data?.length === 0 && (
        <section className="tile empty">
          <span className="empty-icon" aria-hidden><MapPinned size={26} /></span>
          <h2 className="h3">No trips yet</h2>
          <p className="muted">Plan a trip and it will be saved in this browser.</p>
          <Link to="/" className="btn btn-primary" viewTransition>Plan a trip</Link>
        </section>
      )}

      {!!trips.data?.length && (
        <ul className="bento cards" role="list">
          {trips.data.map((trip) => (
            <li key={trip.id} className="tile trip-card">
              <Link to={`/trips/${trip.id}`} viewTransition className="trip-card-link">
                <ContourArt seed={trip.destination} className="trip-card-art" />
                <span className="trip-card-city">{trip.destination.split(",")[0]}</span>
                <h2 className="h3">{trip.title}</h2>
                <p className="small muted row gap-s"><CalendarDays size={14} aria-hidden />
                  <span className="num">{trip.num_days} day{trip.num_days > 1 ? "s" : ""}</span> · created {fmtDate(trip.created_at)}
                </p>
                <span className="badge">{dataSourceLabel(trip.data_source)}</span>
              </Link>
              <button className="icon-btn hit trip-card-delete" onClick={() => deleteTrip(trip)} aria-label={`Delete ${trip.title}`}>
                <Trash size={16} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
