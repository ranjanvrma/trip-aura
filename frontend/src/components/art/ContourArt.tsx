import { useMemo } from "react";

/** Small deterministic PRNG (mulberry32) so the same seed always draws the same artwork. */
function rng(seed: string): () => number {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  let a = h >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function ring(cx: number, cy: number, r: number, wobble: { k: number; amp: number; phase: number }[], squash: number): string {
  const pts: [number, number][] = [];
  const n = 48;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const rr = r * (1 + wobble.reduce((s, w) => s + w.amp * Math.sin(w.k * a + w.phase), 0));
    pts.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr * squash]);
  }
  // smooth closed curve through the midpoints
  const mid = (p: [number, number], q: [number, number]) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
  const start = mid(pts[n - 1], pts[0]);
  let d = `M${start[0].toFixed(1)} ${start[1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const m = mid(pts[i], pts[(i + 1) % n]);
    d += `Q${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)} ${m[0].toFixed(1)} ${m[1].toFixed(1)}`;
  }
  return d + "Z";
}

/**
 * Decorative contour-map artwork generated from a seed (a city name, a trip id). Used where a photo would
 * normally go: the artwork is honest about being a drawing, costs no network request and is unique per trip.
 * Inherits `color` for the lines.
 */
export default function ContourArt({ seed, className, rings = 9 }: { seed: string; className?: string; rings?: number }) {
  const paths = useMemo(() => {
    const rand = rng(seed);
    const hills = [
      { cx: 90 + rand() * 120, cy: 60 + rand() * 90 },
      { cx: 250 + rand() * 110, cy: 80 + rand() * 110 },
    ];
    const out: { d: string; o: number }[] = [];
    for (const h of hills) {
      const wobble = [
        { k: 2, amp: 0.1 + rand() * 0.1, phase: rand() * 6.28 },
        { k: 3, amp: 0.05 + rand() * 0.08, phase: rand() * 6.28 },
        { k: 5, amp: 0.02 + rand() * 0.04, phase: rand() * 6.28 },
      ];
      const squash = 0.7 + rand() * 0.35;
      const step = 15 + rand() * 6;
      for (let i = 1; i <= rings; i++) out.push({ d: ring(h.cx, h.cy, i * step, wobble, squash), o: 0.9 - i * 0.07 });
    }
    return out;
  }, [seed, rings]);

  return (
    <svg className={className} viewBox="0 0 400 240" preserveAspectRatio="xMidYMid slice" aria-hidden focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.1">
        {paths.map((p, i) => <path key={i} d={p.d} opacity={Math.max(p.o, 0.12)} />)}
      </g>
    </svg>
  );
}
