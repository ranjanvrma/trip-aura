import GoogleMap from "./GoogleMap";
import LeafletMap from "./LeafletMap";
import type { MapViewProps } from "./types";

const GOOGLE_KEY = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined)?.trim() ?? "";

/** Picks the Google Maps renderer when a browser key is configured, otherwise Leaflet/OSM. */
export default function MapView(props: MapViewProps) {
  return (
    <div className="map-wrap">
      {GOOGLE_KEY ? <GoogleMap {...props} apiKey={GOOGLE_KEY} /> : <LeafletMap {...props} />}
      <div className="map-caption">
        {GOOGLE_KEY ? "Google Maps (traffic layer on)" : "OpenStreetMap preview - set VITE_GOOGLE_MAPS_API_KEY for Google Maps"}
        {" · "}Solid lines: vehicle / transit, dashed: walking. Mock routes are straight-line approximations.
      </div>
    </div>
  );
}
