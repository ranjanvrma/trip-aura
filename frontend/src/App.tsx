import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import DataSourceBanner from "./components/DataSourceBanner";
import PlannerPage from "./pages/PlannerPage";
import TripPage from "./pages/TripPage";
import { api, ApiError } from "./services/api";
import type { ApiStatus } from "./types";

export default function App() {
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch((e: ApiError) => setError(e.message));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">TripAura</Link>
        <span className="muted small">Personalised day-wise itineraries</span>
      </header>
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
