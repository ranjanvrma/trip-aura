import type { Place } from "../types";

/** How well known a place is, from the free data stored with its city: English Wikipedia readers in the 30 days
 *  before the city was loaded, and whether Wikivoyage's city guide lists it under "See". Never a review rating and
 *  never part of the fit score. */
export interface Popularity {
  level: 0 | 1 | 2 | 3;
  label: "Landmark" | "Popular" | "Known" | null;
  readers: number | null;
  guidePick: boolean;
}

// thresholds from real counts (Nov 2026): Hawa Mahal 11,800 and Belem Tower 9,400 readers a month are landmarks
const TIERS: [number, 1 | 2 | 3, Popularity["label"]][] = [[5000, 3, "Landmark"], [1000, 2, "Popular"], [200, 1, "Known"]];

export function popularity(p: Place): Popularity {
  const readers = p.readers ?? null;
  const guidePick = !!p.guide_pick;
  const tier = TIERS.find(([min]) => (readers ?? 0) >= min);
  if (tier) return { level: tier[1], label: tier[2], readers, guidePick };
  return guidePick ? { level: 1, label: "Known", readers, guidePick } : { level: 0, label: null, readers, guidePick };
}

/** "9.4k" */
export function compactCount(n: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n).toLowerCase();
}

/** One sentence that says where the tier comes from, for tooltips and screen readers. */
export function popularityNote(pop: Popularity): string {
  const parts: string[] = [];
  if (pop.readers != null) {
    parts.push(`${pop.readers.toLocaleString("en")} people read its English Wikipedia article in the 30 days before this city's data was loaded`);
  }
  if (pop.guidePick) parts.push("Wikivoyage's city guide lists it under See");
  return parts.length ? parts.join(". ") + "." : "No Wikipedia article or guide listing for this place.";
}
