import type {
  AddressSuggestion, ApiErrorBody, ApiOptions, ApiStatus, AuthSession, CitySuggestion, Itinerary, LatLng, LiveProgress,
  ParsedTrip, TransportMode, TripRequest, TripSummary,
} from "../types";

// Empty in production when Vercel rewrites /api/* to the backend (first-party session cookie), and locally (Vite proxy).
const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown,
              public retryAfter?: number) {
    super(message);
  }
}

// CSRF token for the current session, kept in memory only (the session itself is an HttpOnly cookie).
let csrfToken: string | null = null;
export const setCsrfToken = (t: string | null) => { csrfToken = t; };

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: (() => void) | null) => { onUnauthorized = fn; };

interface RequestOptions extends RequestInit { idempotencyKey?: string }

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { idempotencyKey, ...rest } = init;
  const method = (rest.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(rest.headers as Record<string, string> ?? {}) };
  if (UNSAFE.has(method) && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  if (idempotencyKey) headers["X-Idempotency-Key"] = idempotencyKey;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...rest, method, headers, credentials: "include" });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Can't reach the TripAura server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    if (res.status === 401 && !path.startsWith("/api/auth/")) onUnauthorized?.();
    const retry = Number(res.headers.get("Retry-After")) || undefined;
    const message = res.status === 429
      ? `Too many requests. Try again in ${retry ?? "a few"} seconds.`
      : err?.message ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, err?.code ?? "http_error", message, err?.details, retry);
  }
  return body as T;
}

export const api = {
  status: () => request<ApiStatus>("/api/meta/status"),
  options: () => request<ApiOptions>("/api/meta/options"),

  me: () => request<AuthSession>("/api/auth/me"),
  requestCode: (email: string) =>
    request<{ sent: boolean; expires_in: number }>("/api/auth/request-code", { method: "POST", body: JSON.stringify({ email }) }),
  verifyCode: (email: string, code: string) =>
    request<AuthSession>("/api/auth/verify", { method: "POST", body: JSON.stringify({ email, code }) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  deleteAccount: () => request<void>("/api/auth/account", { method: "DELETE" }),

  listTrips: () => request<TripSummary[]>("/api/trips"),
  getTrip: (id: number) => request<Itinerary>(`/api/trips/${id}`),
  createTrip: (req: TripRequest, idempotencyKey: string) =>
    request<Itinerary>("/api/trips", { method: "POST", body: JSON.stringify(req), idempotencyKey }),
  regenerate: (id: number, idempotencyKey: string) =>
    request<Itinerary>(`/api/trips/${id}/regenerate`, { method: "POST", idempotencyKey }),
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

/** A fresh key per user action; reuse the same key when retrying that action. */
export function newIdempotencyKey(): string {
  const c: Crypto = globalThis.crypto;
  if (typeof c.randomUUID === "function") return c.randomUUID();
  // randomUUID needs a secure context; fall back to 128 random bits as hex
  return Array.from(c.getRandomValues(new Uint8Array(16)), (x) => x.toString(16).padStart(2, "0")).join("");
}
