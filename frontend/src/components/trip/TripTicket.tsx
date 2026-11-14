import { Link } from "react-router-dom";
import { FileDown, Plus, RotateCcw } from "lucide-react";
import ContourArt from "../art/ContourArt";
import type { Itinerary } from "../../types";
import { cityMark, dataSourceLabel, fmtDay, fmtDuration, fmtMoney } from "../../utils";

/** Totals worked out from the plan itself; nothing here is invented. */
function tripStats(it: Itinerary) {
  const items = it.days.flatMap((d) => d.items);
  const legs = items.filter((i) => i.type === "travel" && i.travel);
  return {
    stops: items.filter((i) => i.type === "activity").length,
    meals: items.filter((i) => i.type === "meal").length,
    km: legs.reduce((s, i) => s + (i.travel?.chosen.distance_km ?? 0), 0),
    travelMin: legs.reduce((s, i) => s + (i.travel?.chosen.duration_min ?? 0), 0),
  };
}

interface Props { it: Itinerary; regenerating: boolean; onRegenerate: () => void; onDownload: () => void }

/** The trip header, laid out like a travel ticket: where and when on the left, the plan's totals on the stub. */
export default function TripTicket({ it, regenerating, onRegenerate, onDownload }: Props) {
  const r = it.request;
  const s = tripStats(it);
  const first = it.days[0]?.date;
  const last = it.days[it.days.length - 1]?.date;
  const city = r.destination_city.split(",")[0];
  const region = r.destination_city.split(",").slice(1).join(",").trim();

  return (
    <header className="ticket">
      <div className="ticket-main">
        <ContourArt seed={r.destination_city} className="ticket-art" />
        <h1 className="ticket-city">
          <span className="ticket-mark" aria-hidden>{cityMark(r.destination_city)}</span>
          <span>{city}</span>
        </h1>
        <p className="ticket-sub">
          {region && <>{region} · </>}
          {first && last && (first === last ? fmtDay(first) : `${fmtDay(first)} to ${fmtDay(last)}`)}
        </p>
        <p className="small muted ticket-meta">
          From {it.accommodation.name} · <span className="num">{r.travelers}</span> traveller{r.travelers > 1 ? "s" : ""} · {r.pace} pace
          {" · "}<span className="badge">{dataSourceLabel(it.data_source)}</span>
        </p>
        <div className="ticket-actions">
          <button className="btn" onClick={onRegenerate} disabled={regenerating}>
            {regenerating ? <><span className="spinner" aria-hidden /> Regenerating</> : <><RotateCcw size={16} aria-hidden /> Regenerate</>}
          </button>
          <button className="btn" onClick={onDownload}><FileDown size={16} aria-hidden /> Download PDF</button>
          <Link className="btn btn-primary" to="/" viewTransition><Plus size={16} aria-hidden /> New trip</Link>
        </div>
      </div>
      <dl className="ticket-stub" aria-label="Plan totals">
        <div><dt>Days</dt><dd className="num">{it.days.length}</dd></div>
        <div><dt>Sights</dt><dd className="num">{s.stops}</dd></div>
        <div><dt>Meals</dt><dd className="num">{s.meals}</dd></div>
        <div><dt>On the move</dt><dd className="num">{s.km.toFixed(1)} km<small>{fmtDuration(s.travelMin)}</small></dd></div>
        <div className="ticket-total">
          <dt>Planned spend</dt>
          <dd className="num">{fmtMoney(it.budget.planned_total, it.budget.currency)}
            <small>of {fmtMoney(it.budget.total_budget, it.budget.currency)}, mostly estimates</small></dd>
        </div>
      </dl>
    </header>
  );
}
