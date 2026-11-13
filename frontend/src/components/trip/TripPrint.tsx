import { createPortal } from "react-dom";
import type { Itinerary, ItineraryItem, Money } from "../../types";
import { fmtDay, fmtDuration, fmtMoney, MODE_LABEL, pretty } from "../../utils";

const STYLE_LABEL = { budget: "Lowest cost", mid: "Mid-range", premium: "Premium" } as const;
const DISH_LABEL = { popular: "Popular in reviews", mentioned: "Mentioned in reviews", guide: "Named in the travel guide",
  suggestion: "Suggestion" } as const;

/** "€12" or "€12 (estimate)"; nothing for a missing amount. */
function cost(m: Money | null | undefined): string {
  if (!m) return "";
  if (m.amount === 0) return "Free";
  return fmtMoney(m.amount, m.currency) + (m.verified ? "" : " est.");
}

function Row({ item }: { item: ItineraryItem }) {
  if (item.type === "travel" && item.travel) {
    const c = item.travel.chosen;
    return (
      <tr className="pd-row-travel">
        <td className="num">{item.start}</td>
        <td>
          {MODE_LABEL[c.mode]} to {item.travel.to_name}
          <span className="pd-muted"> · {fmtDuration(c.duration_min)}, {c.distance_km.toFixed(1)} km</span>
        </td>
        <td className="num">{cost(c.cost)}</td>
      </tr>
    );
  }
  const place = item.place;
  const detail = [
    item.type === "meal" && item.meal_type ? pretty(item.meal_type) : null,
    item.type === "activity" || item.type === "meal" ? place?.address : null,
    item.type === "activity" ? fmtDuration(item.duration_min) : null,
  ].filter(Boolean).join(" · ");
  return (
    <tr className={`pd-row-${item.type}`}>
      <td className="num">{item.start}{item.end && item.end !== item.start ? `–${item.end}` : ""}</td>
      <td>
        <strong>{item.title}</strong>
        {detail && <span className="pd-muted"> · {detail}</span>}
        {item.notes.length > 0 && <span className="pd-note">{item.notes.join(" ")}</span>}
      </td>
      <td className="num">{cost(item.cost)}</td>
    </tr>
  );
}

/**
 * The trip laid out for paper and PDF: a cover with the summary and budget, one section per day, then food, notes
 * and sources. Rendered into <body> only while printing; everything else on the page is hidden by the print styles.
 */
export default function TripPrint({ it }: { it: Itinerary }) {
  const r = it.request;
  const b = it.budget;
  const city = r.destination_city.split(",")[0];
  const first = it.days[0]?.date;
  const last = it.days[it.days.length - 1]?.date;
  const items = it.days.flatMap((d) => d.items);
  const legs = items.filter((i) => i.type === "travel" && i.travel);
  const km = legs.reduce((s, i) => s + (i.travel?.chosen.distance_km ?? 0), 0);
  const notes = [...it.warnings, ...it.disclaimers];
  const money = (n: number) => fmtMoney(n, b.currency);

  return createPortal(
    <article className="print-doc" aria-hidden>
      <section className="pd-cover">
        <p className="pd-brand">TripAura</p>
        <h1>{it.days.length} {it.days.length === 1 ? "day" : "days"} in {city}</h1>
        <p className="pd-lead">
          {r.destination_city}
          {first && last && <> · {first === last ? fmtDay(first) : `${fmtDay(first)} to ${fmtDay(last)}`}</>}
        </p>
        <p className="pd-muted">
          Staying at {it.accommodation.name} · {r.travelers} traveller{r.travelers > 1 ? "s" : ""} · {r.pace} pace
          · {STYLE_LABEL[r.trip_style ?? "mid"]}
        </p>

        <dl className="pd-stats">
          <div><dt>Sights</dt><dd>{items.filter((i) => i.type === "activity").length}</dd></div>
          <div><dt>Meals</dt><dd>{items.filter((i) => i.type === "meal").length}</dd></div>
          <div><dt>On the move</dt><dd>{km.toFixed(1)} km</dd></div>
          <div><dt>Planned spend</dt><dd>{money(b.planned_total)}<small> of {money(b.total_budget)}</small></dd></div>
        </dl>

        <h2>Budget</h2>
        <table className="pd-table">
          <tbody>
            <tr><td>Food</td><td className="num">{money(b.by_category.food)}</td></tr>
            <tr><td>Transport</td><td className="num">{money(b.by_category.transport)}</td></tr>
            <tr><td>Sights and tickets</td><td className="num">{money(b.by_category.attractions)}</td></tr>
            {b.by_category.accommodation > 0 && <tr><td>Stay</td><td className="num">{money(b.by_category.accommodation)}</td></tr>}
            <tr className="pd-total"><td>Planned total</td><td className="num">{money(b.planned_total)}</td></tr>
            <tr><td>{b.over_budget ? "Over budget by" : "Left in the budget"}</td>
              <td className="num">{money(Math.abs(b.remaining))}</td></tr>
          </tbody>
        </table>
        <p className="pd-muted">
          {money(b.verified_total)} comes from published prices; {money(b.estimated_total)} is estimated. Amounts marked
          "est." are estimates.
        </p>
        {b.notes.length > 0 && <ul className="pd-list pd-muted">{b.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      </section>

      {it.days.map((d) => (
        <section className="pd-day" key={d.day_number}>
          <h2>
            Day {d.day_number}<span className="pd-muted"> · {fmtDay(d.date)}</span>
            <span className="pd-day-total">{money(d.budget.total)}</span>
          </h2>
          <table className="pd-table pd-plan">
            <tbody>{d.items.map((i) => <Row key={i.id} item={i} />)}</tbody>
          </table>
          {d.warnings.length > 0 && <ul className="pd-list pd-muted">{d.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
        </section>
      ))}

      <section className="pd-end">
        {it.popular_dishes.length > 0 && (
          <>
            <h2>Food to try</h2>
            <ul className="pd-list">
              {it.popular_dishes.slice(0, 10).map((d) => (
                <li key={d.name}><strong>{pretty(d.name)}</strong><span className="pd-muted"> · {DISH_LABEL[d.status]}</span></li>
              ))}
            </ul>
          </>
        )}
        {notes.length > 0 && (
          <>
            <h2>About this plan</h2>
            <ul className="pd-list pd-muted">{notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </>
        )}
        <h2>Sources</h2>
        <ul className="pd-list pd-muted">{it.attributions.map((a) => <li key={a}>{a}</li>)}</ul>
        <p className="pd-muted pd-foot">
          Made with TripAura on {new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}.
          Check opening hours and prices before you go.
        </p>
      </section>
    </article>,
    document.body,
  );
}
