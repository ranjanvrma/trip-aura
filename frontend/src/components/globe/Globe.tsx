import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import type { LatLng } from "../../types";

const GlobeCanvas = lazy(() => import("./GlobeCanvas"));

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * The 3D globe is a separate chunk (three.js), fetched after the page is idle. Until it is ready a blurred
 * low-detail placeholder holds the space, so the layout never jumps.
 */
export default function Globe({ target, label }: { target: LatLng | null; label: string }) {
  const [load, setLoad] = useState(false);
  const [ready, setReady] = useState(false);
  const onReady = useCallback(() => setReady(true), []);

  useEffect(() => {
    if (!webglAvailable()) return;
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback;
    const id = idle ? idle(() => setLoad(true)) : window.setTimeout(() => setLoad(true), 600);
    return () => { if (!idle) window.clearTimeout(id); };
  }, []);

  return (
    <figure className="globe" aria-label={label}>
      <div className={`globe-placeholder ${ready ? "is-hidden" : ""}`} aria-hidden />
      {load && <Suspense fallback={null}><GlobeCanvas target={target} onReady={onReady} /></Suspense>}
      <figcaption className="globe-caption small">{label}</figcaption>
    </figure>
  );
}
