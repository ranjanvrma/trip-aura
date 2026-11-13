// Pure sphere maths shared by the globe scene, the land mask and the sun position. No three.js here, so the
// orientation rules can be checked outside the browser.

export const DEG = Math.PI / 180;

export type Vec3 = [number, number, number];

/**
 * Point on a sphere of radius r for a latitude/longitude. The convention: y is up, longitude 0 faces +z, so
 * `rotation.y = -lng` turns a longitude to face a camera on +z and `rotation.x = lat` then centres its latitude.
 */
export function latLngToVec(lat: number, lng: number, r = 1): Vec3 {
  const phi = (90 - lat) * DEG;
  const theta = (lng + 90) * DEG;
  return [-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)];
}

/** Inverse of latLngToVec. The globe fragment shader does the same sums, so keep the two in step. */
export function vecToLatLng(x: number, y: number, z: number): { lat: number; lng: number } {
  const len = Math.hypot(x, y, z) || 1;
  const lat = Math.asin(Math.max(-1, Math.min(1, y / len))) / DEG;
  const theta = Math.atan2(z, -x) / DEG;
  return { lat, lng: wrapDegrees(theta - 90) };
}

/** Longitude folded into [-180, 180). */
export function wrapDegrees(lng: number): number {
  return ((((lng + 180) % 360) + 360) % 360) - 180;
}

/** Signed angle (radians) to add to `from` to reach `to` the short way round. */
export function shortestTurn(from: number, to: number): number {
  const twoPi = Math.PI * 2;
  return ((((to - from + Math.PI) % twoPi) + twoPi) % twoPi) - Math.PI;
}

/** Equirectangular pixel for a longitude/latitude: x grows east from -180, y grows south from +90. */
export function equirectPixel(lng: number, lat: number, width: number, height: number): [number, number] {
  return [((lng + 180) / 360) * width, ((90 - lat) / 180) * height];
}

/** The i-th of n points spread evenly over the unit sphere (Fibonacci lattice): an even dot grid with no rows. */
export function fibonacciPoint(i: number, n: number): Vec3 {
  const y = 1 - ((i + 0.5) / n) * 2;
  const r = Math.sqrt(1 - y * y);
  const a = i * Math.PI * (3 - Math.sqrt(5));
  return [Math.cos(a) * r, y, Math.sin(a) * r];
}
