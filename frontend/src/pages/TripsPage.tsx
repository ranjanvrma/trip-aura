import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { CalendarDays, MapPinned, Plus, Trash } from "lucide-react";
import RetryNotice from "../components/ui/RetryNotice";
import { Skeleton } from "../components/ui/Skeleton";
import { useAuth } from "../lib/auth";
import { usePageMeta } from "../lib/meta";
import { clearCache, useSWR } from "../lib/swr";
import { useToast } from "../lib/toast";
import { useDeleteTrip } from "../lib/trips";
import { api, ApiError } from "../services/api";
import { dataSourceLabel } from "../utils";

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export default function TripsPage() {
  usePageMeta("My trips", "Your saved TripAura itineraries.", { noindex: true });
  const { user, checking, deleteAccount } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const removeAccount = async () => {
    setDeleting(true);
    try {
      await deleteAccount();
      clearCache();
      toast.show({ tone: "success", message: "Your account and trips were deleted" });
      nav("/", { replace: true });
    } catch (e) {
      toast.show({ tone: "error", message: `Couldn't delete the account: ${(e as ApiError).message}` });
      setDeleting(false);
    }
  };
  const trips = useSWR(user ? "trips" : null, api.listTrips);
  const deleteTrip = useDeleteTrip();

  if (!checking && !user) return <Navigate to="/signin?next=/trips" replace />;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="h1">My trips</h1>
          <p className="muted">Plans you've generated. Deleting a trip can be undone for a few seconds.</p>
        </div>
        <Link to="/" className="btn btn-primary" viewTransition><Plus size={16} aria-hidden /> New trip</Link>
      </header>

      {trips.error && (
        <RetryNotice message={`Couldn't load your trips: ${trips.error.message}`} onRetry={() => void trips.refresh()} />
      )}

      {(checking || trips.loading) && (
        <div className="bento cards" aria-busy="true" aria-label="Loading trips">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="tile trip-card"><Skeleton w="70%" h={18} /><Skeleton w="40%" /><Skeleton w="55%" /></div>
          ))}
        </div>
      )}

      {trips.data?.length === 0 && (
        <section className="tile empty">
          <span className="empty-icon" aria-hidden><MapPinned size={26} /></span>
          <h2 className="h3">No trips yet</h2>
          <p className="muted">Pick a city and where you're staying, and your first day-by-day plan will be saved here.</p>
          <Link to="/" className="btn btn-primary" viewTransition>Plan a trip</Link>
        </section>
      )}

      {!!trips.data?.length && (
        <ul className="bento cards" role="list">
          {trips.data.map((t) => (
            <li key={t.id} className="tile trip-card">
              <Link to={`/trips/${t.id}`} viewTransition className="trip-card-link">
                <h2 className="h3">{t.title}</h2>
                <p className="small muted row gap-s"><CalendarDays size={14} aria-hidden />
                  <span className="num">{t.num_days} day{t.num_days > 1 ? "s" : ""}</span> · created {fmtDate(t.created_at)}
                </p>
                <span className="badge">{dataSourceLabel(t.data_source)}</span>
              </Link>
              <button className="icon-btn hit trip-card-delete" onClick={() => deleteTrip(t)} aria-label={`Delete ${t.title}`}>
                <Trash size={16} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      {user && (
        <section className="tile danger" aria-labelledby="account-title">
          <h2 id="account-title" className="h3">Account</h2>
          <p className="small muted">Signed in as <strong>{user.email}</strong>. Deleting your account removes it, every trip and all sign-in sessions. This can't be undone.</p>
          {!confirming ? (
            <button className="btn btn-danger-ghost" onClick={() => setConfirming(true)}>Delete account</button>
          ) : (
            <div className="row gap-s wrap" role="group" aria-label="Confirm account deletion">
              <button className="btn btn-danger" onClick={() => void removeAccount()} disabled={deleting}>
                {deleting ? <><span className="spinner" aria-hidden /> Deleting</> : "Yes, delete everything"}
              </button>
              <button className="btn btn-ghost" onClick={() => setConfirming(false)} disabled={deleting}>Keep my account</button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
