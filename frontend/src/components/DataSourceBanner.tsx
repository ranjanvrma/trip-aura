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
  // Normal operation: one quiet line. Demo mode and problems (above) stay prominent.
  if (status.data_mode === "open") {
    return (
      <p className="data-line small muted">
        Built on open map data.{" "}
        {status.google.active ? "Google ratings are shown where a place can be matched."
          : "Open data has no ratings, so places show our fit score only."}{" "}
        Travel times and most prices are estimates.
      </p>
    );
  }
  return <p className="data-line small muted">Places, ratings and routes come from Google Maps Platform.</p>;
}
