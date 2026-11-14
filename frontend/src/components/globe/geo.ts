// Pure sphere maths shared by the globe scene and the sun position. No three.js here, so the
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

/** Signed angle (radians) to add to `from` to reach `to` the short way round. */
export function shortestTurn(from: number, to: number): number {
  const twoPi = Math.PI * 2;
  return ((((to - from + Math.PI) % twoPi) + twoPi) % twoPi) - Math.PI;
}
