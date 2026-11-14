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

// bright, distinguishable day colours for the dark interface (pins and markers carry dark text)
const DAY_COLORS = ["#6fe3cf", "#ff8f66", "#8ab4ff", "#f2c26b", "#ef9bbd", "#a9dc8f", "#c9b3ff"];
export const dayColor = (dayNumber: number) => DAY_COLORS[(dayNumber - 1) % DAY_COLORS.length];

/** "LIS" from "Lisbon, Portugal": a ticket-style city mark made from the city's own letters. */
export function cityMark(city: string): string {
  const letters = city.split(",")[0].normalize("NFD").replace(/[^A-Za-z]/g, "").toUpperCase();
  return (letters.slice(0, 3) || "TRP").padEnd(3, letters.slice(-1) || "X");
}

/** Honesty label for where a trip's places came from. */
export const dataSourceLabel = (source: string) => (source === "mock" ? "Demo data" : "Open data");
