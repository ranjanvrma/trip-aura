import { useCallback } from "react";
import type { SavedTrip } from "./localTrips";
import { deleteSavedTrip, listSavedTrips, saveTrip } from "./localTrips";
import { mutate } from "./swr";
import { useToast } from "./toast";

const UNDO_MS = 5000;

export function useDeleteTrip() {
  const toast = useToast();
  return useCallback((trip: SavedTrip) => {
    deleteSavedTrip(trip.id);
    mutate("localTrips", listSavedTrips());
    mutate(`local-trip:${trip.id}`, null);
    toast.show({
      tone: "info", message: `Deleted "${trip.title}"`, actionLabel: "Undo", ms: UNDO_MS,
      onAction: () => {
        saveTrip(trip.itinerary, trip.id, trip.created_at);
        mutate(`local-trip:${trip.id}`, trip);
        mutate("localTrips", listSavedTrips());
      },
    });
  }, [toast]);
}
