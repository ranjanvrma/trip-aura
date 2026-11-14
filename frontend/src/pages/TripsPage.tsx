import { Link } from "react-router-dom";
import { MapPinned, Plus } from "lucide-react";
import TripPass from "../components/trip/TripPass";
import { usePageMeta } from "../lib/meta";
import { listSavedTrips } from "../lib/localTrips";
import { useSWR } from "../lib/swr";
import { useDeleteTrip } from "../lib/trips";

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
        <Link to="/" className="btn btn-cta" viewTransition><Plus size={16} aria-hidden /> New trip</Link>
      </header>

      {trips.loading && <p className="muted" role="status">Loading your saved trips…</p>}

      {trips.data?.length === 0 && (
        <section className="tile empty">
          <span className="empty-icon" aria-hidden><MapPinned size={26} /></span>
          <h2 className="h3">No trips yet</h2>
          <p className="muted">Plan a trip and it will be saved in this browser.</p>
          <Link to="/" className="btn btn-cta" viewTransition>Plan a trip</Link>
        </section>
      )}

      {!!trips.data?.length && (
        <ul className="trip-passes" role="list">
          {trips.data.map((trip) => <TripPass key={trip.id} trip={trip} onDelete={deleteTrip} />)}
        </ul>
      )}
    </div>
  );
}
