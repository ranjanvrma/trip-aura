import { useCallback } from "react";
import { api, ApiError } from "../services/api";
import type { TripSummary } from "../types";
import { mutate } from "./swr";
import { useToast } from "./toast";

const UNDO_MS = 5000;

/**
 * Optimistic delete with undo: the trip disappears at once and a toast offers Undo for 5 seconds.
 * The DELETE request is only sent when that window closes; if it fails, the trip comes back.
 */
export function useDeleteTrip() {
  const toast = useToast();
  return useCallback((trip: TripSummary) => {
    let undone = false;
    mutate<TripSummary[]>("trips", (list = []) => list.filter((t) => t.id !== trip.id));
    const restore = () => mutate<TripSummary[]>("trips", (list = []) =>
      list.some((t) => t.id === trip.id) ? list
        : [...list, trip].sort((a, b) => b.created_at.localeCompare(a.created_at)));
    const timer = window.setTimeout(async () => {
      if (undone) return;
      try {
        await api.deleteTrip(trip.id);
      } catch (e) {
        restore();
        toast.show({ tone: "error", message: `Couldn't delete "${trip.title}": ${(e as ApiError).message}` });
      }
    }, UNDO_MS);
    toast.show({
      tone: "info", message: `Deleted "${trip.title}"`, actionLabel: "Undo", ms: UNDO_MS,
      onAction: () => { undone = true; window.clearTimeout(timer); restore(); },
    });
  }, [toast]);
}
