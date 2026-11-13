import type { DayPlan } from "../../types";

const toMin = (hm: string) => {
  const [h, m] = hm.split(":").map(Number);
  return h * 60 + m;
};
const LABEL: Record<string, string> = { activity: "Sight", meal: "Meal", rest: "Break", travel: "Travel" };

/**
 * The day at a glance: one horizontal bar from the first start to the last end, with a block for each
 * sight, meal, break and travel leg in proportion to its real length.
 */
export default function DayRibbon({ day }: { day: DayPlan }) {
  const blocks = day.items.filter((i) => i.type in LABEL && i.end !== i.start);
  if (blocks.length === 0) return null;
  const start = Math.min(...blocks.map((b) => toMin(b.start)));
  const end = Math.max(...blocks.map((b) => toMin(b.end)));
  const span = Math.max(end - start, 1);
  const hours: number[] = [];
  for (let h = Math.ceil(start / 60); h * 60 <= end; h += 2) hours.push(h);

  return (
    <div className="ribbon" role="img"
         aria-label={`Day ${day.day_number} runs from ${blocks[0].start} to ${blocks[blocks.length - 1].end}`}>
      <div className="ribbon-track">
        {blocks.map((b) => (
          <span key={b.id} className={`ribbon-block ribbon-${b.type}`} title={`${b.start} ${LABEL[b.type]}: ${b.title}`}
                style={{ left: `${((toMin(b.start) - start) / span) * 100}%`, width: `${Math.max(((toMin(b.end) - toMin(b.start)) / span) * 100, 0.6)}%` }} />
        ))}
      </div>
      <div className="ribbon-scale" aria-hidden>
        {hours.map((h) => (
          <span key={h} style={{ left: `${((h * 60 - start) / span) * 100}%` }}>{String(h).padStart(2, "0")}</span>
        ))}
      </div>
    </div>
  );
}

export function RibbonLegend() {
  return (
    <ul className="ribbon-legend small muted" aria-label="Day ribbon colours">
      <li><span className="ribbon-key ribbon-activity" /> Sights</li>
      <li><span className="ribbon-key ribbon-meal" /> Meals</li>
      <li><span className="ribbon-key ribbon-rest" /> Breaks</li>
      <li><span className="ribbon-key ribbon-travel" /> Travel</li>
    </ul>
  );
}
