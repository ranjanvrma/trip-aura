import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { CommandProvider } from "./components/layout/CommandMenu";
import DataSourceBanner from "./components/layout/DataSourceBanner";
import Layout from "./components/layout/Layout";
import { SkeletonLines } from "./components/ui/Skeleton";
import { ToastProvider } from "./lib/toast";
import PlannerPage from "./pages/PlannerPage";
import { api, ApiError } from "./services/api";
import type { ApiStatus } from "./types";

// route-level code splitting; Layout also warms these chunks on link hover
const TripPage = lazy(() => import("./pages/TripPage"));
const TripsPage = lazy(() => import("./pages/TripsPage"));
const TermsPage = lazy(() => import("./pages/LegalPages").then((m) => ({ default: m.TermsPage })));
const PrivacyPage = lazy(() => import("./pages/LegalPages").then((m) => ({ default: m.PrivacyPage })));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

const WAKE_ATTEMPTS = 24;      // about 2 minutes: covers restarts and hosts that sleep when idle
const WAKE_DELAY_MS = 5000;

function useServerStatus() {
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waking, setWaking] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    const load = async (attempt: number) => {
      try {
        const s = await api.status();
        if (!cancelled) { setStatus(s); setError(null); setWaking(0); }
      } catch (e) {
        if (cancelled) return;
        if (attempt < WAKE_ATTEMPTS) {
          setWaking(attempt + 1);
          timer = window.setTimeout(() => void load(attempt + 1), WAKE_DELAY_MS);
        } else {
          setWaking(0);
          setError(`${(e as ApiError).message} The server may be down; please try again later.`);
        }
      }
    };
    void load(0);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);
  return { status, error, waking };
}

export default function App() {
  const { status, error, waking } = useServerStatus();
  const onPlanner = useLocation().pathname === "/";

  const banner = (
    <div className="banners">
      {waking > 0 && !status && (
        <div className="notice notice-info" role="status">
          <span className="spinner" aria-hidden /> Connecting to the TripAura server. It may be starting up, which can take up to a minute
          (attempt <span className="num">{waking}</span> of {WAKE_ATTEMPTS}).
        </div>
      )}
      {(onPlanner || error) && <DataSourceBanner status={status} error={error} />}
    </div>
  );

  const page = (el: React.ReactNode) => <Suspense fallback={<div className="tile"><SkeletonLines lines={5} /></div>}>{el}</Suspense>;

  return (
    <ToastProvider>
      <CommandProvider>
        <Routes>
          <Route element={<Layout banner={banner} />}>
            <Route index element={<PlannerPage status={status} />} />
            <Route path="trips" element={page(<TripsPage />)} />
            <Route path="trips/:id" element={page(<TripPage />)} />
            <Route path="signin" element={<Navigate to="/" replace />} />
            <Route path="terms" element={page(<TermsPage />)} />
            <Route path="privacy" element={page(<PrivacyPage />)} />
            <Route path="*" element={page(<NotFoundPage />)} />
          </Route>
        </Routes>
      </CommandProvider>
    </ToastProvider>
  );
}
