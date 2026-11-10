import type { AddressSuggestion, ApiErrorBody, ApiOptions, ApiStatus, CitySuggestion, Itinerary, LatLng, ParsedTrip, TripRequest } from "../types";

// Empty in production when Vercel rewrites /api/* to the backend, and locally (Vite proxy).
const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init.headers as Record<string, string> ?? {}) };
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, method, headers });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Can't reach the TripAura server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    const retry = Number(res.headers.get("Retry-After")) || undefined;
    const message = res.status === 429
      ? `Too many requests. Try again in ${retry ?? "a few"} seconds.`
      : err?.message ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, err?.code ?? "http_error", message, err?.details);
  }
  return body as T;
}

export const api = {
  status: () => request<ApiStatus>("/api/meta/status"),
  options: () => request<ApiOptions>("/api/meta/options"),
  previewTrip: (req: TripRequest) =>
    request<Itinerary>("/api/trips/preview", { method: "POST", body: JSON.stringify(req) }),
  citySuggestions: (q: string, signal?: AbortSignal) =>
    request<{ results: CitySuggestion[] }>(`/api/geo/cities?q=${encodeURIComponent(q)}`, { signal }),
  addressSuggestions: (q: string, near?: LatLng | null, signal?: AbortSignal) =>
    request<{ results: AddressSuggestion[] }>(
      `/api/geo/addresses?q=${encodeURIComponent(q)}${near ? `&lat=${near.lat}&lng=${near.lng}` : ""}`, { signal }),
  parseTrip: (text: string) =>
    request<ParsedTrip>("/api/nlp/parse-trip", { method: "POST", body: JSON.stringify({ text }) }),
};
