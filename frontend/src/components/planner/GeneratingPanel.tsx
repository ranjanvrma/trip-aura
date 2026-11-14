import { useEffect, useState } from "react";

const STEPS = [
  "Reading places for the city from open map data",
  "Scoring each place for your interests, budget and pace",
  "Ordering every day to cut travel, with meals and breaks",
  "Costing transport, food and tickets",
];

/**
 * Shown while a plan is being generated (20 to 60 seconds for a city nobody has planned before).
 * The bar is indeterminate and the steps are a description, not a progress report: the server
 * answers once, at the end, so there is no real percentage to show.
 */
export default function GeneratingPanel({ city, firstVisitHint }: { city: string; firstVisitHint: boolean }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const t = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className="generating" role="status" aria-live="polite">
      <h2 className="h1">Building your plan{city ? ` for ${city.split(",")[0]}` : ""}</h2>
      <div className="progress" aria-hidden><span /></div>
      <ol className="generating-steps">
        {STEPS.map((s) => <li key={s}>{s}</li>)}
      </ol>
      <p className="small muted">
        <span className="num" aria-hidden>{seconds} s elapsed. </span>
        {firstVisitHint
          ? "The first plan for a city can take up to a minute while its map data is loaded. After that it takes a few seconds."
          : "This usually takes a few seconds."}
      </p>
    </div>
  );
}
