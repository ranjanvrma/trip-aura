import { motion } from "motion/react";
import { useMemo, useState } from "react";
import type { LatLng, Pace, TripStyle } from "../../types";
import { fmtDuration, fmtMoney, haversineKm } from "../../utils";

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
        <h3>The shortest way round</h3>
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

/* ------------------------------------------------------------------ budget demo
   The planner's own output for the bundled Jaipur demo data: 2 days, one traveller, budget ₹40,000. */
const STYLES: { key: TripStyle; label: string; food: number; transport: number; tickets: number }[] = [
  { key: "budget", label: "Lowest cost", food: 1662, transport: 820, tickets: 350 },
  { key: "mid", label: "Mid-range", food: 2012, transport: 773, tickets: 450 },
  { key: "premium", label: "Premium", food: 2058, transport: 902, tickets: 450 },
];
const R = 50, C = 2 * Math.PI * R;

function BudgetDemo() {
  const [style, setStyle] = useState<TripStyle>("mid");
  const s = STYLES.find((x) => x.key === style)!;
  const parts = [
    { label: "Food", value: s.food, color: "var(--c-food)" },
    { label: "Transport", value: s.transport, color: "var(--c-transport)" },
    { label: "Tickets", value: s.tickets, color: "var(--c-tickets)" },
  ];
  const total = s.food + s.transport + s.tickets;
  let offset = 0;

  return (
    <article className="demo">
      <header className="demo-head">
        <h3>Your budget, your way</h3>
        <div className="seg-group" role="group" aria-label="Trip style">
          {STYLES.map((x) => (
            <button type="button" key={x.key} className="seg" aria-pressed={style === x.key} onClick={() => setStyle(x.key)}>{x.label}</button>
          ))}
        </div>
      </header>
      <div className="budget-hero">
        <div className="donut-wrap">
          <svg viewBox="0 0 120 120" className="donut" aria-hidden>
            <circle cx="60" cy="60" r={R} className="donut-bg" />
            {parts.map((p) => {
              const len = (p.value / total) * C;
              const seg = <circle key={p.label} cx="60" cy="60" r={R} className="donut-seg" stroke={p.color}
                                  strokeDasharray={`${Math.max(0, len - 2)} ${C}`} strokeDashoffset={-offset} />;
              offset += len;
              return seg;
            })}
          </svg>
          <div className="donut-center"><strong className="num">{fmtMoney(total, "INR")}</strong><span className="small muted">planned</span></div>
        </div>
        <ul className="budget-legend">
          {parts.map((p) => (
            <li key={p.label}><span className="legend-dot" style={{ background: p.color }} /><span>{p.label}</span>
              <span className="num">{fmtMoney(p.value, "INR")}</span></li>
          ))}
        </ul>
      </div>
      <p className="small muted">The planner's own numbers for the two-day Jaipur demo. All three are estimates, and all stay under the budget.</p>
    </article>
  );
}

/* ------------------------------------------------------------------ pace demo (an illustration, not a plan) */
type Block = ["activity" | "meal" | "rest" | "travel", number, number];   // kind, start and end in minutes after midnight
const t = (h: number, m = 0) => h * 60 + m;
const DAYS: Record<Pace, Block[]> = {
  relaxed: [["meal", t(9, 30), t(10, 15)], ["travel", t(10, 15), t(10, 35)], ["activity", t(10, 35), t(12, 5)],
    ["travel", t(12, 5), t(12, 30)], ["meal", t(12, 30), t(13, 45)], ["rest", t(13, 45), t(14, 45)],
    ["travel", t(14, 45), t(15, 5)], ["activity", t(15, 5), t(16, 20)], ["rest", t(16, 20), t(17, 20)],
    ["travel", t(17, 20), t(17, 40)], ["activity", t(17, 40), t(18, 40)], ["travel", t(18, 40), t(19)], ["meal", t(19), t(20, 15)]],
  moderate: [["meal", t(9), t(9, 40)], ["travel", t(9, 40), t(9, 55)], ["activity", t(9, 55), t(11, 10)],
    ["travel", t(11, 10), t(11, 25)], ["activity", t(11, 25), t(12, 25)], ["travel", t(12, 25), t(12, 45)],
    ["meal", t(12, 45), t(13, 45)], ["rest", t(13, 45), t(14, 15)], ["travel", t(14, 15), t(14, 30)],
    ["activity", t(14, 30), t(15, 45)], ["travel", t(15, 45), t(16)], ["activity", t(16), t(17)], ["rest", t(17), t(18, 15)],
    ["travel", t(18, 15), t(18, 45)], ["meal", t(18, 45), t(20)]],
  packed: [["meal", t(8, 15), t(8, 45)], ["travel", t(8, 45), t(9)], ["activity", t(9), t(10)], ["travel", t(10), t(10, 10)],
    ["activity", t(10, 10), t(11)], ["travel", t(11), t(11, 10)], ["activity", t(11, 10), t(12, 10)],
    ["travel", t(12, 10), t(12, 25)], ["meal", t(12, 25), t(13, 10)], ["travel", t(13, 10), t(13, 25)],
    ["activity", t(13, 25), t(14, 25)], ["travel", t(14, 25), t(14, 35)], ["activity", t(14, 35), t(15, 35)],
    ["travel", t(15, 35), t(15, 45)], ["activity", t(15, 45), t(16, 45)], ["rest", t(16, 45), t(17, 15)],
    ["travel", t(17, 15), t(17, 30)], ["activity", t(17, 30), t(18, 30)], ["travel", t(18, 30), t(18, 50)], ["meal", t(18, 50), t(19, 50)]],
};
const DAY_START = t(8), DAY_END = t(21);
const PACES: Pace[] = ["relaxed", "moderate", "packed"];

function PaceDemo() {
  const [pace, setPace] = useState<Pace>("moderate");
  const blocks = DAYS[pace];
  const minutes = (kind: Block[0]) => blocks.filter((b) => b[0] === kind).reduce((s, b) => s + b[2] - b[1], 0);
  const sights = blocks.filter((b) => b[0] === "activity").length;

  return (
    <article className="demo">
      <header className="demo-head">
        <h3>A day at your pace</h3>
        <div className="seg-group" role="group" aria-label="Pace">
          {PACES.map((p) => (
            <button type="button" key={p} className="seg" aria-pressed={pace === p} onClick={() => setPace(p)}>{p[0].toUpperCase() + p.slice(1)}</button>
          ))}
        </div>
      </header>
      <div className="ribbon" aria-hidden>
        <div className="ribbon-track ribbon-tall">
          {blocks.map(([kind, a, b]) => (
            <motion.span key={`${kind}${a}`} className={`ribbon-block ribbon-${kind}`} initial={{ opacity: 0, scaleX: 0.4 }}
                         animate={{ opacity: 1, scaleX: 1 }} transition={{ duration: 0.35, delay: ((a - DAY_START) / (DAY_END - DAY_START)) * 0.35 }}
                         style={{ left: `${((a - DAY_START) / (DAY_END - DAY_START)) * 100}%`, width: `${((b - a) / (DAY_END - DAY_START)) * 100}%` }} />
          ))}
        </div>
        <div className="ribbon-scale">
          {[9, 12, 15, 18].map((h) => <span key={h} style={{ left: `${((t(h) - DAY_START) / (DAY_END - DAY_START)) * 100}%` }}>{h}:00</span>)}
        </div>
      </div>
      <dl className="pace-stats">
        <div><dt><span className="ribbon-key ribbon-activity" /> Sights</dt><dd className="num">{sights} stops, {fmtDuration(minutes("activity"))}</dd></div>
        <div><dt><span className="ribbon-key ribbon-meal" /> Meals</dt><dd className="num">{fmtDuration(minutes("meal"))}</dd></div>
        <div><dt><span className="ribbon-key ribbon-rest" /> Breaks</dt><dd className="num">{fmtDuration(minutes("rest"))}</dd></div>
        <div><dt><span className="ribbon-key ribbon-travel" /> On the move</dt><dd className="num">{fmtDuration(minutes("travel"))}</dd></div>
      </dl>
      <p className="small muted">An illustration of how pace reshapes a day. Your plan shows this ribbon for every day.</p>
    </article>
  );
}

const METHOD = [
  ["Gather", "Places come from Overture Maps, Wikidata, OpenStreetMap and Wikivoyage, and are kept for 30 days."],
  ["Score", "Each place is scored for you: interests, budget, distance, transport, time and pace. Outside ratings never count."],
  ["Order", "Every day starts from its strongest sight, then the stops are reordered to cut the walking and riding."],
  ["Cost", "Fares, meals and tickets are estimated from local prices, and labelled as estimates."],
];

/** The home page's "see how it works" section: three small things to play with, then the four steps in words. */
export default function Showcase() {
  return (
    <section className="showcase" aria-labelledby="showcase-title">
      <header className="section-head" data-reveal>
        <h2 id="showcase-title" className="h1">See how a plan comes together</h2>
        <p className="lead">Three parts of the planner you can try right here.</p>
      </header>
      <div className="demo-grid">
        <div data-reveal><RouteDemo /></div>
        <div data-reveal><BudgetDemo /></div>
        <div data-reveal><PaceDemo /></div>
      </div>
      <ol className="method" data-reveal>
        {METHOD.map(([title, text]) => (
          <li key={title}><h3>{title}</h3><p>{text}</p></li>
        ))}
      </ol>
    </section>
  );
}
