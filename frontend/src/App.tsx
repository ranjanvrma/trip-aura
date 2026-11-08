import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import DataSourceBanner from "./components/DataSourceBanner";
import PlannerPage from "./pages/PlannerPage";
import TripPage from "./pages/TripPage";
import { api, ApiError } from "./services/api";
import type { ApiStatus } from "./types";

const WAKE_ATTEMPTS = 24;      // ~2 minutes: covers restarts/redeploys and hosts that sleep when idle
const WAKE_DELAY_MS = 5000;

export default function App() {
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waking, setWaking] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = async (attempt: number) => {
      try {
        const s = await api.status();
        if (!cancelled) { setStatus(s); setError(null); setWaking(0); }
      } catch (e) {
        if (cancelled) return;
        if (attempt < WAKE_ATTEMPTS) {
          setWaking(attempt + 1);
          window.setTimeout(() => void load(attempt + 1), WAKE_DELAY_MS);
        } else {
          setWaking(0);
          setError((e as ApiError).message + " The server may be down; please try again later.");
        }
      }
    };
    void load(0);
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">TripAura</Link>
        <span className="muted small">Personalised day-wise itineraries</span>
      </header>
      {waking > 0 && !status && (
        <div className="banner banner-mock">
          Connecting to the TripAura server - it may be starting up or updating.
          This can take up to a minute (attempt {waking} of {WAKE_ATTEMPTS})...
        </div>
      )}
      <DataSourceBanner status={status} error={error} />
      <main>
        <Routes>
          <Route path="/" element={<PlannerPage status={status} />} />
          <Route path="/trips/:id" element={<TripPage />} />
        </Routes>
      </main>
    </div>
  );
}
