import { useEffect, useRef, useState } from "react";
import type { LatLng } from "../types";

export interface GeoState {
  position: LatLng | null;
  accuracy: number | null;
  error: string | null;
  permission: PermissionState | "unsupported" | "unknown";
}

/**
 * Browser Geolocation wrapper. Tracking starts only when `enabled` is true
 * (the user switched it on) and the watch is cleared as soon as it is false.
 */
export function useGeolocation(enabled: boolean): GeoState {
  const [state, setState] = useState<GeoState>({
    position: null, accuracy: null, error: null, permission: "unknown",
  });
  const watchId = useRef<number | null>(null);

  useEffect(() => {
    if (!("geolocation" in navigator)) {
      setState((s) => ({ ...s, permission: "unsupported", error: "This browser does not support geolocation." }));
      return;
    }
    navigator.permissions?.query({ name: "geolocation" as PermissionName })
      .then((p) => {
        setState((s) => ({ ...s, permission: p.state }));
        p.onchange = () => setState((s) => ({ ...s, permission: p.state }));
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!enabled || !("geolocation" in navigator)) {
      if (watchId.current !== null) {
        navigator.geolocation.clearWatch(watchId.current);
        watchId.current = null;
      }
      setState((s) => ({ ...s, position: null, accuracy: null, error: null }));
      return;
    }
    watchId.current = navigator.geolocation.watchPosition(
      (pos) => setState((s) => ({
        ...s, error: null, permission: "granted",
        position: { lat: pos.coords.latitude, lng: pos.coords.longitude },
        accuracy: pos.coords.accuracy,
      })),
      (err) => setState((s) => ({
        ...s,
        error: err.code === err.PERMISSION_DENIED
          ? "Location permission was denied. Enable it in your browser settings to use live updates."
          : err.code === err.TIMEOUT ? "Timed out getting your location." : "Your location is unavailable.",
        permission: err.code === err.PERMISSION_DENIED ? "denied" : s.permission,
      })),
      { enableHighAccuracy: true, maximumAge: 15000, timeout: 20000 },
    );
    return () => {
      if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
      watchId.current = null;
    };
  }, [enabled]);

  return state;
}
