import type { Itinerary, TripSummary } from "../types";

const STORAGE_KEY = "tripaura.saved-trips.v1";
const MAX_TRIPS = 25;

export interface SavedTrip extends TripSummary {
  itinerary: Itinerary;
}

export function listSavedTrips(): SavedTrip[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((trip): trip is SavedTrip =>
      !!trip && typeof trip.id === "string" && typeof trip.title === "string" &&
      typeof trip.created_at === "string" && !!trip.itinerary?.request);
  } catch {
    return [];
  }
}

function writeSavedTrips(trips: SavedTrip[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trips.slice(0, MAX_TRIPS)));
  } catch {
    throw new Error("This browser couldn't save the trip. Check available storage and try again.");
  }
}

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function saveTrip(itinerary: Itinerary, id = newId(), createdAt = new Date().toISOString()): SavedTrip {
  const localItinerary = { ...itinerary, trip_id: null };
  const trip: SavedTrip = {
    id,
    title: `${itinerary.request.num_days} day${itinerary.request.num_days === 1 ? "" : "s"} in ${itinerary.request.destination_city}`,
    destination: itinerary.request.destination_city,
    num_days: itinerary.request.num_days,
    data_source: itinerary.data_source,
    created_at: createdAt,
    itinerary: localItinerary,
  };
  const remaining = listSavedTrips().filter((item) => item.id !== id);
  writeSavedTrips([trip, ...remaining]);
  return trip;
}

export function getSavedTrip(id: string): SavedTrip | null {
  return listSavedTrips().find((trip) => trip.id === id) ?? null;
}

export function deleteSavedTrip(id: string): SavedTrip | null {
  const trips = listSavedTrips();
  const removed = trips.find((trip) => trip.id === id) ?? null;
  if (removed) writeSavedTrips(trips.filter((trip) => trip.id !== id));
  return removed;
}
