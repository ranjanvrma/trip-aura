import type { ApiStatus } from "../types";

export default function DataSourceBanner({ status, error }: { status: ApiStatus | null; error: string | null }) {
  if (error) return <div className="notice notice-error">{error}</div>;
  if (!status) return null;
  if (status.data_mode === "mock") {
    return (
      <div className="notice notice-warn">
        <strong>Demo mode.</strong> Using bundled mock data for {status.mock_city}. Ratings, reviews, prices and
        travel times are illustrative and are <em>not</em> Google data.
      </div>
    );
  }
  if (status.problems.length) return <div className="notice notice-error">{status.problems.join(" ")}</div>;
  if (status.data_mode === "open") {
    return (
      <div className="notice notice-ok small">
        <strong>Worldwide open data.</strong> Places come from {status.open_data?.sources.join(", ")}.
        {status.google.active ? " Google ratings are added where a place can be matched." :
          " Open data has no ratings; add a Google key for ratings."} Travel times are estimates.
      </div>
    );
  }
  return <div className="notice notice-ok small">Live mode: places, ratings and routes from Google Maps Platform.</div>;
}
