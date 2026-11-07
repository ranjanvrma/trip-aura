import type {
  AddressSuggestion, ApiErrorBody, ApiOptions, ApiStatus, CitySuggestion, Itinerary, LatLng, LiveProgress, ParsedTrip,
  TransportMode, TripRequest, TripSummary,
} from "../types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the TripAura backend. Is it running on port 8000?");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `Request failed (${res.status})`, err?.details);
  }
  return body as T;
}

export const api = {
  status: () => request<ApiStatus>("/api/meta/status"),
  options: () => request<ApiOptions>("/api/meta/options"),
  listTrips: () => request<TripSummary[]>("/api/trips"),
  getTrip: (id: number) => request<Itinerary>(`/api/trips/${id}`),
  createTrip: (req: TripRequest) => request<Itinerary>("/api/trips", { method: "POST", body: JSON.stringify(req) }),
  regenerate: (id: number) => request<Itinerary>(`/api/trips/${id}/regenerate`, { method: "POST" }),
  deleteTrip: (id: number) => request<void>(`/api/trips/${id}`, { method: "DELETE" }),
  citySuggestions: (q: string, signal?: AbortSignal) =>
    request<{ results: CitySuggestion[] }>(`/api/geo/cities?q=${encodeURIComponent(q)}`, { signal }),
  addressSuggestions: (q: string, near?: LatLng | null, signal?: AbortSignal) =>
    request<{ results: AddressSuggestion[] }>(
      `/api/geo/addresses?q=${encodeURIComponent(q)}${near ? `&lat=${near.lat}&lng=${near.lng}` : ""}`, { signal }),
  parseTrip: (text: string) =>
    request<ParsedTrip>("/api/nlp/parse-trip", { method: "POST", body: JSON.stringify({ text }) }),
  liveProgress: (id: number, body: {
    current: LatLng; accuracy_m?: number; day_number: number; next_item_id?: string | null;
    planned_mode?: TransportMode | null; previous_duration_min?: number | null; client_time?: string;
  }) => request<LiveProgress>(`/api/trips/${id}/live`, { method: "POST", body: JSON.stringify(body) }),
};
