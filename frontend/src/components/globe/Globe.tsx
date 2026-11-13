import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import type { LatLng } from "../../types";
import "./globe.css";

const GlobeCanvas = lazy(() => import("./GlobeCanvas"));

export interface GlobePin { lat: number; lng: number; label: string }

const NO_PINS: GlobePin[] = [];

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * The 3D globe. three.js and the land data are a separate chunk, fetched once the page is idle; until the first
 * frame is drawn a soft CSS globe holds the space, so the layout never jumps. Without WebGL the CSS globe stays.
 */
export default function Globe({ target, label, pins = NO_PINS }: { target: LatLng | null; label: string; pins?: GlobePin[] }) {
  const [load, setLoad] = useState(false);
  const [ready, setReady] = useState(false);
  const onReady = useCallback(() => setReady(true), []);

  useEffect(() => {
    if (!webglAvailable()) return;
    const w = window as Window & { requestIdleCallback?: (cb: () => void) => number; cancelIdleCallback?: (id: number) => void };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => setLoad(true));
      return () => w.cancelIdleCallback?.(id);
    }
    const id = window.setTimeout(() => setLoad(true), 600);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <figure className={`globe ${ready ? "is-ready" : ""}`} aria-label={label}>
      <div className="globe-shadow" aria-hidden />
      <div className="globe-placeholder" aria-hidden />
      {load && <Suspense fallback={null}><GlobeCanvas target={target} pins={pins} onReady={onReady} /></Suspense>}
      <figcaption className="globe-caption">
        <span className="globe-caption-main">{label}</span>
        <span className="globe-caption-note">Lit side: where it is daytime now · Land: Natural Earth</span>
      </figcaption>
    </figure>
  );
}
