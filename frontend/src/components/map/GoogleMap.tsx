import { useEffect, useRef, useState } from "react";
import type { MapViewProps } from "./types";

let loader: Promise<void> | null = null;

/** Loads the Maps JavaScript API once. Requires VITE_GOOGLE_MAPS_API_KEY (a browser-restricted key). */
function loadGoogleMaps(key: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve();
  if (loader) return loader;
  loader = new Promise((resolve, reject) => {
    const cb = "__tripauraMapsReady";
    (window as unknown as Record<string, () => void>)[cb] = () => resolve();
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=${cb}&loading=async`;
    s.async = true;
    s.onerror = () => { loader = null; reject(new Error("Failed to load Google Maps JavaScript API")); };
    document.head.appendChild(s);
  });
  return loader;
}

export default function GoogleMap({ markers, polylines, current, selectedId, onSelect, apiKey }:
  MapViewProps & { apiKey: string }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<google.maps.Map | null>(null);
  const overlays = useRef<{ setMap: (m: google.maps.Map | null) => void }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    loadGoogleMaps(apiKey)
      .then(() => {
        if (el.current && !map.current) {
          map.current = new google.maps.Map(el.current, { center: { lat: 20, lng: 0 }, zoom: 13, mapTypeControl: false });
          new google.maps.TrafficLayer().setMap(map.current);
        }
        setReady(true);
      })
      .catch((e: Error) => setError(e.message));
  }, [apiKey]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    overlays.current.forEach((o) => o.setMap(null));
    overlays.current = [];
    const bounds = new google.maps.LatLngBounds();
    for (const p of polylines) {
      const line = new google.maps.Polyline({
        path: p.path, strokeColor: p.color, strokeOpacity: p.dashed ? 0 : 0.8, strokeWeight: 4, map: m,
        icons: p.dashed ? [{ icon: { path: "M 0,-1 0,1", strokeOpacity: 0.9, scale: 3 }, offset: "0", repeat: "14px" }] : undefined,
      });
      overlays.current.push(line);
    }
    for (const mk of markers) {
      const big = mk.kind === "home" || mk.id === selectedId;
      const marker = new google.maps.Marker({
        position: mk.position, map: m, title: mk.title,
        label: { text: mk.label, color: "#fff", fontSize: "11px", fontWeight: "700" },
        icon: { path: google.maps.SymbolPath.CIRCLE, scale: big ? 14 : 11, fillColor: mk.color, fillOpacity: 1,
                strokeColor: "#fff", strokeWeight: 2 },
      });
      marker.addListener("click", () => onSelect?.(mk.id));
      overlays.current.push(marker);
      bounds.extend(mk.position);
    }
    if (current) {
      overlays.current.push(new google.maps.Marker({
        position: current.position, map: m, title: "You are here",
        icon: { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: "#0ea5e9", fillOpacity: 1,
                strokeColor: "#fff", strokeWeight: 3 },
      }));
      if (current.accuracy) {
        overlays.current.push(new google.maps.Circle({ center: current.position, radius: current.accuracy, map: m,
          strokeColor: "#0ea5e9", strokeWeight: 1, fillColor: "#0ea5e9", fillOpacity: 0.1 }));
      }
    }
    const sel = markers.find((x) => x.id === selectedId);
    if (sel) {
      m.panTo(sel.position);
      m.setZoom(Math.max(m.getZoom() ?? 13, 15));
    } else if (!bounds.isEmpty()) {
      m.fitBounds(bounds, 30);
    }
  }, [ready, markers, polylines, current, selectedId, onSelect]);

  if (error) return <div className="map map-error">{error}. Check VITE_GOOGLE_MAPS_API_KEY.</div>;
  return <div ref={el} className="map" />;
}
