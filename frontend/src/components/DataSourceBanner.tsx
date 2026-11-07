import type { ApiStatus } from "../types";

export default function DataSourceBanner({ status, error }: { status: ApiStatus | null; error: string | null }) {
  if (error) return <div className="banner banner-error">{error}</div>;
  if (!status) return null;
  if (status.data_mode === "mock") {
    return (
      <div className="banner banner-mock">
        <strong>Demo mode.</strong> Using bundled mock data for {status.mock_city}. Ratings, reviews, prices and
        travel times are illustrative and are <em>not</em> Google data.
      </div>
    );
  }
  if (status.problems.length) return <div className="banner banner-error">{status.problems.join(" ")}</div>;
  return <div className="banner banner-live">Live mode: places, ratings and routes from Google Maps Platform.</div>;
}
