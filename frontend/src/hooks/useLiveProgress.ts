import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../services/api";
import type { LatLng, LiveProgress, TransportAlert } from "../types";
import { haversineKm } from "../utils";

const MOVE_THRESHOLD_KM = 0.05;      // re-check after moving 50 m
const REFRESH_MS = 2 * 60 * 1000;    // and at least every 2 minutes (traffic changes)

function nowHM(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/**
 * Sends the live position to the backend for fresh estimates while enabled.
 * Keeps the previous duration so the backend can detect traffic changes and
 * raises browser notifications (if allowed) for new alerts.
 */
export function useLiveProgress(tripId: number | null, dayNumber: number, position: LatLng | null,
                                accuracy: number | null, enabled: boolean, targetItemId: string | null) {
  const [progress, setProgress] = useState<LiveProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [alerts, setAlerts] = useState<(TransportAlert & { at: string })[]>([]);
  const lastPos = useRef<LatLng | null>(null);
  const lastDuration = useRef<number | null>(null);
  const seen = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    if (!tripId || !position) return;
    setLoading(true);
    try {
      const res = await api.liveProgress(tripId, {
        current: position, accuracy_m: accuracy ?? undefined, day_number: dayNumber,
        next_item_id: targetItemId, previous_duration_min: lastDuration.current, client_time: nowHM(),
      });
      setProgress(res);
      setError(null);
      lastPos.current = position;
      lastDuration.current = res.recommended?.duration_min ?? null;
      const fresh = res.alerts.filter((a) => !seen.current.has(a.kind + a.message));
      fresh.forEach((a) => seen.current.add(a.kind + a.message));
      if (fresh.length) {
        setAlerts((prev) => [...fresh.map((a) => ({ ...a, at: res.checked_at })), ...prev].slice(0, 10));
        if ("Notification" in window && Notification.permission === "granted") {
          fresh.filter((a) => a.kind !== "low_accuracy")
            .forEach((a) => new Notification("TripAura", { body: a.message }));
        }
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not refresh travel estimates.");
    } finally {
      setLoading(false);
    }
  }, [tripId, position, accuracy, dayNumber, targetItemId]);

  // refresh when moved enough
  useEffect(() => {
    if (!enabled || !position) return;
    if (!lastPos.current || haversineKm(lastPos.current, position) >= MOVE_THRESHOLD_KM) void refresh();
  }, [enabled, position, refresh]);

  // periodic refresh to pick up traffic changes
  useEffect(() => {
    if (!enabled) return;
    const t = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(t);
  }, [enabled, refresh]);

  // reset when disabled or target changes
  useEffect(() => {
    if (!enabled) {
      setProgress(null);
      lastPos.current = null;
      lastDuration.current = null;
    }
  }, [enabled]);
  useEffect(() => { lastDuration.current = null; lastPos.current = null; }, [targetItemId, dayNumber]);

  return { progress, error, loading, alerts, refresh };
}
