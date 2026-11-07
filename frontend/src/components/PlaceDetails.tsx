import type { ItineraryItem } from "../types";
import { moneyLabel, pretty } from "../utils";
import { ExternalRatingBadge, ScoreBreakdown, SuitabilityBadge } from "./RatingBadges";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function PlaceDetails({ item, onClose }: { item: ItineraryItem; onClose: () => void }) {
  const p = item.place;
  if (!p) return null;
  const fee = item.type === "meal" ? p.avg_cost_per_person : p.entry_fee;
  return (
    <aside className="card details">
      <div className="row between">
        <h3>{p.name}</h3>
        <button className="btn btn-light" onClick={onClose} aria-label="Close details">{"✕"}</button>
      </div>
      {p.description && <p>{p.description}</p>}
      {p.address && <p className="small muted">{p.address}</p>}

      <div className="two-ratings">
        <div>
          <div className="small muted">External rating</div>
          <ExternalRatingBadge rating={p.external_rating} />
          <div className="small muted">{p.external_rating?.label}</div>
        </div>
        <div>
          <div className="small muted">Your suitability</div>
          <SuitabilityBadge score={item.suitability} />
          <div className="small muted">TripAura's own score - not a review rating</div>
        </div>
      </div>

      {item.suitability && (
        <>
          <h4>Why it matches you</h4>
          <ul className="reasons">{item.suitability.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <ScoreBreakdown score={item.suitability} />
        </>
      )}

      <h4>Practical info</h4>
      <ul className="small">
        <li>Scheduled: {item.start}-{item.end} ({item.duration_min} min)</li>
        {fee && <li>{item.type === "meal" ? "Avg. cost per person" : "Entry fee per person"}: {moneyLabel(fee)}
          {" "}<span className="muted">({fee.verified ? "verified" : fee.note ?? "estimate"})</span></li>}
        {!fee && item.type === "activity" && <li>Entry fee: not published - {moneyLabel(item.cost)} assumed</li>}
        {p.categories.filter((c) => !c.startsWith("search:")).length > 0 &&
          <li>Tags: {p.categories.filter((c) => !c.startsWith("search:") && c !== "food").map(pretty).join(", ")}</li>}
        {p.cuisines.length > 0 && <li>Cuisine: {p.cuisines.map(pretty).join(", ")}</li>}
      </ul>

      {p.opening_hours && (
        p.opening_hours.known ? (
          <table className="hours small">
            <tbody>
              {DAYS.map((d, i) => {
                const r = p.opening_hours!.weekly[String(i)] ?? [];
                return <tr key={d}><td>{d}</td><td>{r.length ? r.map((x) => `${x.open}-${x.close}`).join(", ") : "Closed"}</td></tr>;
              })}
            </tbody>
          </table>
        ) : <p className="small warn">Opening hours not published by the provider.</p>
      )}
      {p.reviews.length > 0 && (
        <>
          <h4>Reviews <span className="muted small">({p.source === "google" ? "from Google" : "demo reviews"})</span></h4>
          <ul className="small reviews">{p.reviews.slice(0, 3).map((r) => <li key={r.text}>"{r.text}"</li>)}</ul>
        </>
      )}
      {p.google_maps_uri && <a href={p.google_maps_uri} target="_blank" rel="noreferrer">Open in Google Maps</a>}
    </aside>
  );
}
