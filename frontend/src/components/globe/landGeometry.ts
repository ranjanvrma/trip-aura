// Turns Natural Earth land polygons (longitude/latitude rings) into pixel rings for an equirectangular canvas.
// Pure: no DOM, so it can be checked outside the browser.
//
// The TopoJSON is stitched across the antimeridian, so a ring such as Eurasia's jumps from -180 to +180 and a
// naive fill would smear a band across the whole map. Each ring is unwrapped into a continuous longitude
// range and drawn at offsets of -360, 0 and +360 so whatever falls inside [-180, 180] lands in place. A ring
// that wraps all the way round (Antarctica) encloses the pole on a sphere, so it is closed along the pole
// line before filling.

import { equirectPixel } from "./geo";

export type PixelRing = Array<[number, number]>;

interface Unwrapped {
  points: Array<[number, number]>;
  minLng: number;
  maxLng: number;
}

function unwrapRing(ring: number[][]): Unwrapped | null {
  if (ring.length < 4) return null;
  const points: Array<[number, number]> = [];
  let offset = 0;
  let prev = ring[0][0];
  let latSum = 0;
  for (const [lng, lat] of ring) {
    const step = lng - prev;
    if (step > 180) offset -= 360;
    else if (step < -180) offset += 360;
    prev = lng;
    points.push([lng + offset, lat]);
    latSum += lat;
  }
  if (offset !== 0) {
    // Wraps the globe: close it along the nearer pole so the even-odd fill covers the polar cap.
    const pole = latSum / ring.length < 0 ? -90 : 90;
    const last = points[points.length - 1][0];
    points.push([last, pole], [points[0][0], pole]);
  }
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % points.length];
    area += x1 * y2 - x2 * y1;
  }
  // world-atlas 50m carries a zero-area ring along the south pole line; it adds nothing and is skipped.
  if (Math.abs(area) < 1e-6) return null;
  let minLng = Infinity;
  let maxLng = -Infinity;
  for (const [lng] of points) {
    minLng = Math.min(minLng, lng);
    maxLng = Math.max(maxLng, lng);
  }
  return { points, minLng, maxLng };
}

/** Every ring of every polygon as pixel rings, ready for one even-odd fill (holes such as lakes cut out). */
export function landPixelRings(polygons: number[][][][], width: number, height: number): PixelRing[] {
  const out: PixelRing[] = [];
  for (const polygon of polygons) {
    for (const ring of polygon) {
      const u = unwrapRing(ring);
      if (!u) continue;
      for (const shift of [-360, 0, 360]) {
        if (u.maxLng + shift < -180 || u.minLng + shift > 180) continue;
        out.push(u.points.map(([lng, lat]) => equirectPixel(lng + shift, lat, width, height)));
      }
    }
  }
  return out;
}
