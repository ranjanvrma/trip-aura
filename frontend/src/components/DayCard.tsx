import type { DayPlan, ItineraryItem } from "../types";
import { MODE_LABEL, fmtDay, fmtDuration, fmtMoney, moneyLabel } from "../utils";
import { type LucideIcon, ArrowRight, Coffee, House, Sun } from "lucide-react";
import { ExternalRatingBadge, SuitabilityBadge } from "./RatingBadges";
import DayRibbon from "./trip/DayRibbon";

interface Props {
  day: DayPlan;
  color: string;
  currency: string;
  selectedId: string | null;
  onSelect: (item: ItineraryItem) => void;
}

const ICON: Record<string, LucideIcon> = { start: House, meal: Coffee, rest: Sun, travel: ArrowRight, end: House };

function CostTag({ item }: { item: ItineraryItem }) {
  const m = item.type === "travel" ? item.travel?.chosen.cost : item.cost;
  if (!m) return null;
  return (
    <span className={`cost ${m.verified ? "cost-verified" : "cost-est"}`} title={m.note ?? undefined}>
      {moneyLabel(m)}{m.amount > 0 && <small> {m.verified ? "verified" : m.source === "mock" ? "demo" : "est."}</small>}
    </span>
  );
}

function TravelRow({ item }: { item: ItineraryItem }) {
  const leg = item.travel!;
  const c = leg.chosen;
  return (
    <div className="travel-row">
      <span className="travel-mode">{MODE_LABEL[c.mode]}</span>
      <span>{c.distance_km.toFixed(1)} km · {Math.round(c.duration_min)} min{c.traffic_aware ? " (traffic)" : ""}</span>
      <CostTag item={item} />
      {leg.alternatives.length > 0 && (
        <details className="alts">
          <summary>Alternatives</summary>
          <p className="small muted">{leg.recommendation_reason}</p>
          <ul>
            {leg.alternatives.map((a) => (
              <li key={a.mode} className={a.practical ? "" : "muted"}>
                {a.duration_min === 0 && !a.practical
                  ? <>{MODE_LABEL[a.mode]}: not available{a.note ? ` (${a.note})` : ""}</>
                  : <>{MODE_LABEL[a.mode]}: {Math.round(a.duration_min)} min, {moneyLabel(a.cost)}
                      {!a.practical && " - not practical"}{a.note ? ` (${a.note})` : ""}</>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/**
 * Notes not already said by the line above them. The backend repeats the diet check in both the fit reasons
 * and the notes ("Diet info: unverified" next to "No verified vegetarian information"); each fact shows once.
 */
function extraNotes(it: ItineraryItem): string[] {
  const said = new Set(it.suitability?.reasons.slice(0, 2) ?? []);   // only what the line above actually shows
  const unverifiedSaid = [...said, ...it.notes].some((t) => /^No verified /.test(t));
  return it.notes.filter((n, i) =>
    !said.has(n) && it.notes.indexOf(n) === i && !(unverifiedSaid && n === "Diet info: unverified"));
}

export default function DayCard({ day, color, currency, selectedId, onSelect }: Props) {
  let stop = 0;
  return (
    <section className="tile day" id={`day-${day.day_number}`} style={{ "--day": color } as React.CSSProperties}>
      <header className="day-head">
        <h2 className="h3"><span className="day-dot" aria-hidden />Day {day.day_number} <span className="muted day-date">{fmtDay(day.date)}</span></h2>
        <span className="day-total" title={`Verified ${fmtMoney(day.budget.verified_amount, currency)} · estimated ${fmtMoney(day.budget.estimated_amount, currency)}`}>
          {fmtMoney(day.budget.total, currency)}
        </span>
      </header>
      <DayRibbon day={day} />
      {day.warnings.map((w) => <p key={w} className="warn small">{w}</p>)}
      <ol className="timeline">
        {day.items.map((it) => {
          const Icon = ICON[it.type];
          const isStop = it.type === "activity" || it.type === "meal";
          if (it.type === "activity") stop += 1;
          return (
            <li key={it.id} className={`tl tl-${it.type} ${selectedId === it.id ? "tl-selected" : ""}`}>
              <span className="tl-time">{it.type === "travel" ? "" : it.start}</span>
              <span className="tl-icon" style={it.type === "activity" ? { background: color } : undefined}>
                {it.type === "activity" ? stop : Icon ? <Icon size={12} /> : null}
              </span>
              <div className="tl-body">
                {it.type === "travel" ? <TravelRow item={it} /> : (
                  <>
                    <div className="row wrap gap-s">
                      {isStop || it.place ? (
                        <button className="link" onClick={() => onSelect(it)}>{it.title}</button>
                      ) : <span>{it.title}</span>}
                      {it.type !== "start" && it.type !== "end" && (
                        <span className="muted small num" title={`${it.start} to ${it.end}`}>{fmtDuration(it.duration_min)}</span>
                      )}
                    </div>
                    {isStop && it.place && (
                      <div className="row wrap gap-s mt-xs">
                        <ExternalRatingBadge rating={it.place.external_rating} hideEmpty />
                        <SuitabilityBadge score={it.suitability} />
                        <CostTag item={it} />
                        {it.suitability?.discovery && <span className="badge badge-discovery">Beyond your interests</span>}
                      </div>
                    )}
                    {it.type === "rest" && it.cost && it.cost.amount > 0 && <CostTag item={it} />}
                    {it.suitability && <p className="small muted mt-xs">{it.suitability.reasons.slice(0, 2).join(" · ")}</p>}
                    {extraNotes(it).map((n) => <p key={n} className="small note">{n}</p>)}
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
