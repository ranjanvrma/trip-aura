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

export const DAY_COLORS = ["#2563eb", "#db2777", "#16a34a", "#ea580c", "#7c3aed", "#0891b2", "#ca8a04"];
