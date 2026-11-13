import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "../../lib/platform";
import { loadLand } from "./landMask";
import { createGlobeScene, type GlobeScene, type Spot } from "./scene";

/**
 * Thin React shell around the framework-free scene in scene.ts. Lives in the lazily loaded chunk with three.js
 * and the Natural Earth land data; Globe.tsx is the cheap wrapper that loads it.
 */
export default function GlobeCanvas({ target, pins, onReady }: { target: Spot | null; pins: Spot[]; onReady: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<GlobeScene | null>(null);
  // the latest props, read when the scene finishes building (land loads asynchronously)
  const latest = useRef({ target, pins });
  latest.current = { target, pins };

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let cancelled = false;
    // if the land data can't be built the globe still draws, as ocean only
    loadLand().catch(() => null).then((land) => {
      if (cancelled) return;
      scene.current = createGlobeScene(el, land, {
        target: latest.current.target, pins: latest.current.pins, reducedMotion: prefersReducedMotion(), onReady,
      });
    });
    return () => {
      cancelled = true;
      scene.current?.dispose();
      scene.current = null;
    };
  }, [onReady]);

  useEffect(() => { scene.current?.setTarget(target); }, [target]);
  useEffect(() => { scene.current?.setPins(pins); }, [pins]);

  return <div ref={host} className="globe-canvas" />;
}
