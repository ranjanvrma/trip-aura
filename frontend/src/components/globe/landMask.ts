// Builds the land mask once per page: Natural Earth land drawn white on black into an equirectangular canvas
// (2:1, longitude -180 at the left, north at the top), the positions of the land dots sampled from it, and the
// country borders and coastlines as line segments on the sphere.
// The data ships as a lazily loaded chunk of this bundle, so there are no runtime network requests to other
// hosts and no image files.

import { feature, mesh } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import { fibonacciPoint, equirectPixel, latLngToVec, vecToLatLng } from "./geo";
import { landPixelRings } from "./landGeometry";

export const MASK_WIDTH = 2048;
export const MASK_HEIGHT = 1024;

/** Dots spread over the whole sphere; only those on land are kept (about 29 percent). */
const DOT_CANDIDATES = 22_000;

export interface LandData {
  /** Land in the red channel (255 land, 0 sea), antialiased at the coast. */
  canvas: HTMLCanvasElement;
  /** Unit-sphere positions (x, y, z per dot) of the dots that fall on land. */
  dots: Float32Array;
  /** Country borders and coastlines: pairs of points (x, y, z each) for THREE.LineSegments, just above the surface. */
  borders: Float32Array;
}

type Connection = { saveData?: boolean; effectiveType?: string };

/** The 1:50m countries are about 230 kB gzipped; on a data saver or a slow link the 1:110m ones (about 35 kB) do. */
function loadTopology(): Promise<Topology> {
  const conn = (navigator as Navigator & { connection?: Connection }).connection;
  const lite = !!conn && (conn.saveData === true || ["slow-2g", "2g", "3g"].includes(conn.effectiveType ?? ""));
  return lite
    ? import("world-atlas/countries-110m.json").then((m) => m.default)
    : import("world-atlas/countries-50m.json").then((m) => m.default);
}

function landPolygons(topology: Topology): number[][][][] {
  const geo = feature(topology, topology.objects.land);
  const features = "features" in geo ? geo.features : [geo];
  const polygons: number[][][][] = [];
  for (const f of features) {
    const g = f.geometry;
    if (g?.type === "Polygon") polygons.push(g.coordinates);
    else if (g?.type === "MultiPolygon") polygons.push(...g.coordinates);
  }
  return polygons;
}

/** Every country edge once (shared borders and coastlines alike), as line segments on a sphere of radius r. */
function borderSegments(topology: Topology, r: number): Float32Array {
  const lines = mesh(topology, topology.objects.countries as GeometryCollection).coordinates;
  const out: number[] = [];
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const [lng0, lat0] = line[i - 1];
      const [lng1, lat1] = line[i];
      if (Math.abs(lng1 - lng0) > 180) continue;   // a seam along the date line, not a real edge
      out.push(...latLngToVec(lat0, lng0, r), ...latLngToVec(lat1, lng1, r));
    }
  }
  return new Float32Array(out);
}

function build(topology: Topology): LandData {
  const canvas = document.createElement("canvas");
  canvas.width = MASK_WIDTH;
  canvas.height = MASK_HEIGHT;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2D canvas unavailable");

  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, MASK_WIDTH, MASK_HEIGHT);
  ctx.beginPath();
  for (const ring of landPixelRings(landPolygons(topology), MASK_WIDTH, MASK_HEIGHT)) {
    ctx.moveTo(ring[0][0], ring[0][1]);
    for (let i = 1; i < ring.length; i++) ctx.lineTo(ring[i][0], ring[i][1]);
    ctx.closePath();
  }
  ctx.fillStyle = "#fff";
  ctx.fill("evenodd"); // even-odd so lake rings cut holes whatever their winding

  const pixels = ctx.getImageData(0, 0, MASK_WIDTH, MASK_HEIGHT).data;
  const kept: number[] = [];
  for (let i = 0; i < DOT_CANDIDATES; i++) {
    const [x, y, z] = fibonacciPoint(i, DOT_CANDIDATES);
    const { lat, lng } = vecToLatLng(x, y, z);
    const [px, py] = equirectPixel(lng, lat, MASK_WIDTH, MASK_HEIGHT);
    const ix = Math.min(MASK_WIDTH - 1, Math.floor(px));
    const iy = Math.min(MASK_HEIGHT - 1, Math.floor(py));
    if (pixels[(iy * MASK_WIDTH + ix) * 4] > 160) kept.push(x, y, z);
  }
  return { canvas, dots: new Float32Array(kept), borders: borderSegments(topology, 1.0016) };
}

let pending: Promise<LandData> | null = null;

/** Shared by every mount (React StrictMode mounts twice); a failed load is not cached, so a remount retries. */
export function loadLand(): Promise<LandData> {
  pending ??= loadTopology().then(build).catch((err: unknown) => {
    pending = null;
    throw err;
  });
  return pending;
}
