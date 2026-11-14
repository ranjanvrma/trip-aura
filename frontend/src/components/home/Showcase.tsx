import { motion } from "motion/react";
import { useMemo, useState } from "react";
import type { LatLng } from "../../types";
import { haversineKm } from "../../utils";

/* ------------------------------------------------------------------ route demo
   Real places in Lisbon. "Reordered" is worked out here, in the browser, the same way the planner does it:
   nearest stop first, then 2-opt swaps until no swap shortens the loop. */
const STOPS: { name: string; at: LatLng }[] = [
  { name: "Rossio (your stay)", at: { lat: 38.7139, lng: -9.1394 } },
  { name: "Belém Tower", at: { lat: 38.6916, lng: -9.216 } },
  { name: "Gulbenkian Museum", at: { lat: 38.7374, lng: -9.1539 } },
  { name: "LX Factory", at: { lat: 38.7035, lng: -9.1789 } },
  { name: "Oceanário de Lisboa", at: { lat: 38.7635, lng: -9.0937 } },
  { name: "Jerónimos Monastery", at: { lat: 38.6979, lng: -9.2068 } },
  { name: "National Tile Museum", at: { lat: 38.7248, lng: -9.1135 } },
];
const W = 340, H = 200, PAD = 24;

function loopKm(order: number[]): number {
  return order.reduce((km, s, i) => km + haversineKm(STOPS[s].at, STOPS[order[(i + 1) % order.length]].at), 0);
}

function reorder(): number[] {
  const left = STOPS.map((_, i) => i).slice(1);
  const order = [0];
  while (left.length) {
    const from = STOPS[order[order.length - 1]].at;
    left.sort((a, b) => haversineKm(from, STOPS[a].at) - haversineKm(from, STOPS[b].at));
    order.push(left.shift()!);
  }
  for (let improved = true; improved;) {
    improved = false;
    for (let i = 1; i < order.length - 1; i++) {
      for (let j = i + 1; j < order.length; j++) {
        const next = [...order.slice(0, i), ...order.slice(i, j + 1).reverse(), ...order.slice(j + 1)];
        if (loopKm(next) < loopKm(order) - 1e-9) { order.splice(0, order.length, ...next); improved = true; }
      }
    }
  }
  return order;
}

function RouteDemo() {
  const [tidy, setTidy] = useState(false);
  const { listed, best, point } = useMemo(() => {
    const lats = STOPS.map((s) => s.at.lat), lngs = STOPS.map((s) => s.at.lng);
    const [minLat, maxLat, minLng, maxLng] = [Math.min(...lats), Math.max(...lats), Math.min(...lngs), Math.max(...lngs)];
    const point = (i: number) => ({
      x: PAD + ((STOPS[i].at.lng - minLng) / (maxLng - minLng)) * (W - 2 * PAD),
      y: PAD + ((maxLat - STOPS[i].at.lat) / (maxLat - minLat)) * (H - 2 * PAD),
    });
    return { listed: STOPS.map((_, i) => i), best: reorder(), point };
  }, []);
  const order = tidy ? best : listed;
  const d = [...order, order[0]].map((s, i) => `${i ? "L" : "M"}${point(s).x.toFixed(1)} ${point(s).y.toFixed(1)}`).join(" ");
  const [before, after] = [loopKm(listed), loopKm(best)];

  return (
    <article className="demo">
      <header className="demo-head">
        <h3>Try it: the shortest way round</h3>
        <div className="seg-group" role="group" aria-label="Order of stops">
          <button type="button" className="seg" aria-pressed={!tidy} onClick={() => setTidy(false)}>As listed</button>
          <button type="button" className="seg" aria-pressed={tidy} onClick={() => setTidy(true)}>Reordered</button>
        </div>
      </header>
      <svg viewBox={`0 0 ${W} ${H}`} className="route-map" role="img"
           aria-label={`Seven places in Lisbon joined in ${tidy ? "the reordered" : "the listed"} order`}>
        <motion.path initial={false} animate={{ d }} transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1] }} className="route-line" />
        {order.map((s, i) => (
          <g key={s} transform={`translate(${point(s).x.toFixed(1)} ${point(s).y.toFixed(1)})`}>
            <circle r={s === 0 ? 7 : 9} className={s === 0 ? "route-home" : "route-stop"} />
            {s !== 0 && <text className="route-n" textAnchor="middle" dy="3.5">{i}</text>}
          </g>
        ))}
      </svg>
      <p className="demo-figure">
        <strong className="num">{(tidy ? after : before).toFixed(1)} km</strong>
        <span className="muted"> {tidy ? `${Math.round((1 - after / before) * 100)}% less than the listed order` : "in the order you listed them"}</span>
      </p>
      <p className="small muted">Seven real places in Lisbon, straight-line distances. A plan orders each day like this, then fits opening hours and meals around it.</p>
    </article>
  );
}

const METHOD = [
  ["Gather", "Places come from Overture Maps, Wikidata, OpenStreetMap and Wikivoyage, and are kept for 30 days."],
  ["Score", "Each place is scored for you: interests, budget, distance, transport, time and pace. Outside ratings never count."],
  ["Order", "Every day starts from its strongest sight, then the stops are reordered to cut the walking and riding."],
  ["Cost", "Fares, meals and tickets are estimated from local prices, and labelled as estimates."],
];

/** The home page's "how it works": the four steps in words, beside the one step you can try. */
export default function Showcase() {
  return (
    <section className="showcase" aria-labelledby="showcase-title">
      <div className="showcase-text" data-reveal>
        <h2 id="showcase-title" className="h1">How a plan is made</h2>
        <ol className="method">
          {METHOD.map(([title, text]) => (
            <li key={title}><h3>{title}</h3><p>{text}</p></li>
          ))}
        </ol>
      </div>
      <div data-reveal><RouteDemo /></div>
    </section>
  );
}
