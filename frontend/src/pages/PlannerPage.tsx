import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import TripForm from "../components/TripForm";
import { api, ApiError } from "../services/api";
import type { ApiOptions, ApiStatus, TripRequest, TripSummary } from "../types";

export default function PlannerPage({ status }: { status: ApiStatus | null }) {
  const nav = useNavigate();
  const [options, setOptions] = useState<ApiOptions | null>(null);
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; details?: unknown } | null>(null);

  useEffect(() => {
    api.options().then(setOptions).catch((e: ApiError) => setError({ message: e.message }));
    api.listTrips().then(setTrips).catch(() => undefined);
  }, []);

  const submit = async (req: TripRequest) => {
    setSubmitting(true);
    setError(null);
    try {
      const it = await api.createTrip(req);
      nav(`/trips/${it.trip_id}`, { state: { itinerary: it } });
    } catch (e) {
      const err = e as ApiError;
      setError({ message: err.message, details: err.details });
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (id: number) => {
    await api.deleteTrip(id);
    setTrips((t) => t.filter((x) => x.id !== id));
  };

  return (
    <div className="planner">
      <div>
        {error && (
          <div className="banner banner-error">
            {error.message}
            {Array.isArray(error.details) && (
              <ul className="small">
                {(error.details as { field: string; message: string }[]).map((d) => (
                  <li key={d.field + d.message}>{d.field}: {d.message}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {submitting && status?.data_mode === "open" && (
          <div className="banner banner-live">
            Loading open data for this city... The first trip to a new city can take 1-3 minutes while places are
            downloaded and cached; later trips there are instant.
          </div>
        )}
        {options && status ? <TripForm options={options} status={status} submitting={submitting} onSubmit={submit} />
          : <div className="card">Loading options...</div>}
      </div>
      <aside className="card">
        <h3>Saved trips</h3>
        {trips.length === 0 && <p className="muted small">No trips yet.</p>}
        <ul className="trip-list">
          {trips.map((t) => (
            <li key={t.id} className="row between gap-s">
              <Link to={`/trips/${t.id}`}>{t.title}</Link>
              <span className={`badge ${t.data_source === "mock" ? "badge-mock" : "badge-google"}`}>{t.data_source}</span>
              <button className="btn btn-light small" onClick={() => void remove(t.id)} aria-label={`Delete ${t.title}`}>Delete</button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
