import { Link } from "react-router-dom";
import { Trash } from "lucide-react";
import type { SavedTrip } from "../../lib/localTrips";
import { cityMark, dataSourceLabel } from "../../utils";

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

/** A saved trip as a small pass: city mark, city, length and when it was made, with delete beside it. */
export default function TripPass({ trip, onDelete }: { trip: SavedTrip; onDelete: (t: SavedTrip) => void }) {
  const [city, ...rest] = trip.destination.split(",");
  return (
    <li className="trip-pass">
      <Link to={`/trips/${trip.id}`} viewTransition className="trip-pass-link">
        <span className="trip-pass-code" aria-hidden>{cityMark(trip.destination)}</span>
        <span className="trip-pass-main">
          <strong className="truncate">{city}</strong>
          <span className="small muted truncate">{rest.join(",").trim() || trip.title}</span>
        </span>
        <span className="trip-pass-meta small">
          <span className="num">{trip.num_days} {trip.num_days === 1 ? "day" : "days"}</span>
          <span className="muted">{fmtDate(trip.created_at)} · {dataSourceLabel(trip.data_source)}</span>
        </span>
      </Link>
      <button className="icon-btn hit" onClick={() => onDelete(trip)} aria-label={`Delete ${trip.title}`}>
        <Trash size={16} aria-hidden />
      </button>
    </li>
  );
}
