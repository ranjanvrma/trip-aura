import type { BudgetSummary as Budget } from "../types";
import { fmtMoney } from "../utils";

const CATS = [
  { key: "food", label: "Food", color: "var(--c-food)" },
  { key: "transport", label: "Transport", color: "var(--c-transport)" },
  { key: "attractions", label: "Tickets", color: "var(--c-tickets)" },
  { key: "accommodation", label: "Stay", color: "var(--c-stay)" },
] as const;

const R = 42;
const C = 2 * Math.PI * R;

/** Ring chart of the planned spend by category: one circle, each category drawn as a stroke-dash segment. */
function Donut({ b }: { b: Budget }) {
  const parts = CATS.map((c) => ({ ...c, value: b.by_category[c.key] })).filter((c) => c.value > 0);
  const total = parts.reduce((s, c) => s + c.value, 0);
  let offset = 0;
  return (
    <svg viewBox="0 0 100 100" className="donut" role="img"
         aria-label={total ? parts.map((p) => `${p.label} ${Math.round((p.value / total) * 100)} percent`).join(", ") : "Nothing planned yet"}>
      <circle cx="50" cy="50" r={R} className="donut-bg" />
      {parts.map((p) => {
        const len = (p.value / total) * C;
        const seg = (
          <circle key={p.key} cx="50" cy="50" r={R} className="donut-seg" stroke={p.color}
                  strokeDasharray={`${Math.max(len - 1.2, 0.5)} ${C}`} strokeDashoffset={-offset} />
        );
        offset += len;
        return seg;
      })}
    </svg>
  );
}

export default function BudgetSummary({ b }: { b: Budget }) {
  const f = (n: number) => fmtMoney(n, b.currency);
  const pct = Math.min(100, (b.planned_total / b.total_budget) * 100);
  const maxDay = Math.max(...b.per_day.map((d) => d.total), 1);
  const cats = CATS.map((c) => ({ ...c, value: b.by_category[c.key] })).filter((c) => c.value > 0);

  return (
    <section className="tile budget" aria-labelledby="budget-title">
      <h2 id="budget-title" className="tile-title">Budget</h2>

      <div className="budget-hero">
        <div className="donut-wrap">
          <Donut b={b} />
          <div className="donut-center">
            <span className="small muted">Planned</span>
            <strong className="num">{f(b.planned_total)}</strong>
          </div>
        </div>
        <ul className="budget-legend">
          {cats.map((c) => (
            <li key={c.key}>
              <span className="legend-dot" style={{ background: c.color }} aria-hidden />
              <span>{c.label}</span>
              <span className="num">{f(c.value)}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className={`meter ${b.over_budget ? "meter-over" : ""}`} role="img"
           aria-label={`${Math.round(pct)} percent of your budget is planned`}><span style={{ width: `${pct}%` }} /></div>
      <p className="budget-line">
        <span><strong className="num">{f(b.total_budget)}</strong> budget</span>
        <span className={b.over_budget ? "neg" : "pos"}>
          <strong className="num">{f(Math.abs(b.remaining))}</strong> {b.over_budget ? "over" : "left"}
        </span>
      </p>
      {b.over_budget && <p className="notice notice-warn small">The plan is over your budget. See the ways to save below.</p>}
      <p className="small muted">
        {b.verified_total > 0
          ? <>{f(b.verified_total)} of this is confirmed prices; {f(b.estimated_total)} is estimated.</>
          : <>Every amount here is an estimate from local price levels. Check real prices before you go.</>}
      </p>

      <h3 className="h4">By day</h3>
      <ul className="day-bars">
        {b.per_day.map((d) => (
          <li key={d.day_number}>
            <span className="small muted">Day {d.day_number}</span>
            <span className="day-bar" aria-hidden>
              {CATS.map((c) => d.totals[c.key] > 0 && (
                <span key={c.key} style={{ width: `${(d.totals[c.key] / maxDay) * 100}%`, background: c.color }} />
              ))}
            </span>
            <span className="num small">{f(d.total)}</span>
          </li>
        ))}
      </ul>

      {b.applied_optimizations.length > 0 && (
        <>
          <h3 className="h4">Applied to fit your budget</h3>
          <ul className="small">{b.applied_optimizations.map((o) => <li key={o}>{o}</li>)}</ul>
        </>
      )}
      {b.suggestions.length > 0 && (
        <>
          <h3 className="h4">Ways to save</h3>
          <ul className="small">
            {b.suggestions.map((s) => <li key={s.message}>{s.message} <strong>save about {f(s.estimated_saving)}</strong></li>)}
          </ul>
        </>
      )}
      {b.notes.length > 0 && (
        <details className="data-notes">
          <summary>How these numbers were worked out</summary>
          <ul className="small muted">{b.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
