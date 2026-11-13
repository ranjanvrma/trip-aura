import type { LatLng, Money, TransportMode } from "./types";

const SYMBOL: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };

export function fmtMoney(amount: number, currency: string): string {
  return `${SYMBOL[currency] ?? currency + " "}${Math.round(amount).toLocaleString()}`;
}

export function moneyLabel(m: Money | null | undefined): string {
  if (!m) return "";
  return m.amount === 0 ? "Free" : fmtMoney(m.amount, m.currency);
}

export function pretty(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const MODE_LABEL: Record<TransportMode, string> = {
  walking: "Walk", metro: "Metro", bus: "Bus", train: "Train", cab: "Cab", auto: "Auto-rickshaw",
  personal_vehicle: "Own vehicle",
};

export function haversineKm(a: LatLng, b: LatLng): number {
  const R = 6371.0088;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** "2026-12-12" -> "Sat, 12 Dec" (the date is a calendar day, so it is read as UTC to avoid time-zone shifts). */
export function fmtDay(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

/** 45 -> "45 min", 90 -> "1 h 30 min", 120 -> "2 h". */
export function fmtDuration(minutes: number): string {
  const m = Math.round(minutes);
  if (m < 60) return `${m} min`;
  return m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`;
}

// muted, distinguishable day colours (readable on the warm map tiles and as white-text pins)
const DAY_COLORS = ["#4f7a5c", "#b0693f", "#4d6f91", "#9a5a6e", "#7d7038", "#5e6294", "#3f7f7a"];
export const dayColor = (dayNumber: number) => DAY_COLORS[(dayNumber - 1) % DAY_COLORS.length];

/** Honesty label for where a trip's places came from. */
export const dataSourceLabel = (source: string) => (source === "mock" ? "Demo data" : "Open data");
