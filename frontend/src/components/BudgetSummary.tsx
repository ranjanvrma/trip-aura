import type { BudgetSummary as Budget } from "../types";
import { fmtMoney } from "../utils";

export default function BudgetSummary({ b }: { b: Budget }) {
  const f = (n: number) => fmtMoney(n, b.currency);
  const pct = Math.min(100, (b.planned_total / b.total_budget) * 100);
  const cats: [string, number][] = [
    ["Food", b.by_category.food], ["Transport", b.by_category.transport],
    ["Attractions", b.by_category.attractions], ["Accommodation", b.by_category.accommodation],
  ];
  return (
    <section className="tile">
      <h2 className="tile-title">Budget</h2>
      <div className="budget-top">
        <div><div className="small muted">Planned</div><strong>{f(b.planned_total)}</strong></div>
        <div><div className="small muted">Budget</div><strong>{f(b.total_budget)}</strong></div>
        <div><div className="small muted">Remaining</div>
          <strong className={b.over_budget ? "neg" : "pos"}>{f(b.remaining)}</strong></div>
      </div>
      <div className={`meter ${b.over_budget ? "meter-over" : ""}`}><span style={{ width: `${pct}%` }} /></div>
      {b.over_budget && <p className="warn">The plan is over your budget. See the suggestions below.</p>}

      <table className="table small">
        <tbody>
          {cats.map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{f(v)}</td></tr>)}
          <tr className="muted"><td>Verified / user-entered</td><td className="num">{f(b.verified_total)}</td></tr>
          <tr className="muted"><td>Estimated</td><td className="num">{f(b.estimated_total)}</td></tr>
        </tbody>
      </table>

      <h4>Per day</h4>
      <table className="table small">
        <thead><tr><th>Day</th><th className="num">Food</th><th className="num">Transport</th><th className="num">Entry</th><th className="num">Total</th></tr></thead>
        <tbody>
          {b.per_day.map((d) => (
            <tr key={d.day_number}>
              <td>{d.day_number}</td><td className="num">{f(d.totals.food)}</td><td className="num">{f(d.totals.transport)}</td>
              <td className="num">{f(d.totals.attractions)}</td><td className="num">{f(d.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {b.applied_optimizations.length > 0 && (
        <>
          <h4>Applied to fit your budget</h4>
          <ul className="small">{b.applied_optimizations.map((o) => <li key={o}>{o}</li>)}</ul>
        </>
      )}
      {b.suggestions.length > 0 && (
        <>
          <h4>Ways to save</h4>
          <ul className="small">
            {b.suggestions.map((s) => <li key={s.message}>{s.message} <strong>save ~{f(s.estimated_saving)}</strong></li>)}
          </ul>
        </>
      )}
      {b.notes.map((n) => <p key={n} className="small muted">{n}</p>)}
    </section>
  );
}
