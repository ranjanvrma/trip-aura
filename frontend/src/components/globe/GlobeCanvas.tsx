import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "../../lib/platform";
import { createGlobeScene, type GlobeScene, type Spot } from "./scene";
import { fallbackEarth, loadEarth } from "./textures";

/**
 * Thin React shell around the framework-free scene in scene.ts. Lives in the lazily loaded chunk with three.js;
 * the Earth imagery is fetched alongside it. Globe.tsx is the cheap wrapper that loads it.
 */
export default function GlobeCanvas({ target, pins, onReady }: { target: Spot | null; pins: Spot[]; onReady: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<GlobeScene | null>(null);
  // the latest props, read when the scene finishes building (the imagery loads asynchronously)
  const latest = useRef({ target, pins });
  latest.current = { target, pins };

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let cancelled = false;
    // if the imagery can't be loaded the globe still draws, as a plain blue ball
    loadEarth().catch(fallbackEarth).then((earth) => {
      if (cancelled) { Object.values(earth).forEach((t) => t.dispose()); return; }
      scene.current = createGlobeScene(el, earth, {
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
