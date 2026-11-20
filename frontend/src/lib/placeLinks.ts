import type { Place } from "../types";

/** Directions to a place in Google Maps: a plain link, no key and no cost. The place id makes Google open the
 *  right listing when the plan was enriched; otherwise the coordinates are enough. */
export function directionsUrl(p: Place): string {
  const q = new URLSearchParams({ api: "1", destination: `${p.location.lat.toFixed(6)},${p.location.lng.toFixed(6)}` });
  const gid = p.external_ids?.google;
  if (gid && /^[\w-]{10,300}$/.test(gid)) q.set("destination_place_id", gid);
  return `https://www.google.com/maps/dir/?${q.toString()}`;
}

/** The place's photo from Wikimedia Commons, at one of Commons' standard thumbnail widths. */
export function photoUrl(file: string, width: 330 | 500): string {
  return `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(file)}?width=${width}`;
}

/** The photo's page on Commons, which names its author and licence. */
export function photoPage(file: string): string {
  return `https://commons.wikimedia.org/wiki/File:${encodeURIComponent(file.replace(/ /g, "_"))}`;
}
